package llmgw

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

// jobsEndpoint resolves the URL + query params + headers for a given
// operation kind, honoring auth_mode (jwt vs internal). The userID
// override (per-call) takes precedence over the Client's ctor UserID.
//
// Returns InvalidRequest error when auth_mode='internal' and no UserID
// is resolvable.
func (c *Client) jobsEndpoint(kind string, jobID, userIDOverride string) (string, url.Values, http.Header, error) {
	headers := http.Header{}
	params := url.Values{}

	var base string
	if c.authMode == AuthJWT {
		base = c.baseURL + "/v1/llm/jobs"
		headers.Set("Authorization", "Bearer "+c.bearerToken)
	} else {
		effectiveUser := userIDOverride
		if effectiveUser == "" {
			effectiveUser = c.userID
		}
		if effectiveUser == "" {
			return "", nil, nil, newErrorFromCode(
				"LLM_INVALID_REQUEST",
				"internal auth_mode requires user_id (per-call override or ctor default)",
				0,
			)
		}
		base = c.baseURL + "/internal/llm/jobs"
		headers.Set("X-Internal-Token", c.internalToken)
		params.Set("user_id", effectiveUser)
	}

	switch kind {
	case "submit":
		return base, params, headers, nil
	case "get", "cancel":
		if jobID == "" {
			return "", nil, nil, newErrorFromCode(
				"LLM_INVALID_REQUEST",
				"jobID is required for get/cancel",
				0,
			)
		}
		return base + "/" + jobID, params, headers, nil
	default:
		return "", nil, nil, newErrorFromCode(
			"LLM_INVALID_REQUEST",
			fmt.Sprintf("unknown endpoint kind %q", kind),
			0,
		)
	}
}

// submitJob POSTs a submit-job envelope and returns the 202 response.
func (c *Client) submitJob(ctx context.Context, body map[string]any, userIDOverride string) (*submitJobResponse, error) {
	endpoint, params, headers, err := c.jobsEndpoint("submit", "", userIDOverride)
	if err != nil {
		return nil, err
	}

	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return nil, newErrorFromCode("LLM_DECODE_ERROR", "submit body marshal failed: "+err.Error(), 0)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint+"?"+params.Encode(), bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, newErrorFromCode("LLM_HTTP_ERROR", "submit_job request build: "+err.Error(), 0)
	}
	for k, v := range headers {
		req.Header[k] = v
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, newErrorFromCode("LLM_HTTP_ERROR", "submit_job transport failure: "+err.Error(), 0)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, c.raiseHTTPError(resp)
	}

	var out submitJobResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, newErrorFromCode("LLM_DECODE_ERROR", "submit_job response decode: "+err.Error(), resp.StatusCode)
	}
	return &out, nil
}

// getJob GETs the current Job state. 404 surfaces as ErrJobNotFound.
func (c *Client) getJob(ctx context.Context, jobID, userIDOverride string) (*job, error) {
	endpoint, params, headers, err := c.jobsEndpoint("get", jobID, userIDOverride)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint+"?"+params.Encode(), nil)
	if err != nil {
		return nil, newErrorFromCode("LLM_HTTP_ERROR", "get_job request build: "+err.Error(), 0)
	}
	for k, v := range headers {
		req.Header[k] = v
	}
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, newErrorFromCode("LLM_HTTP_ERROR", "get_job transport failure: "+err.Error(), 0)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, newErrorFromCode("LLM_JOB_NOT_FOUND", fmt.Sprintf("job %s not found", jobID), 404)
	}
	if resp.StatusCode >= 400 {
		return nil, c.raiseHTTPError(resp)
	}

	var out job
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, newErrorFromCode("LLM_DECODE_ERROR", "get_job response decode: "+err.Error(), resp.StatusCode)
	}
	return &out, nil
}

// cancelJob DELETEs the job. 204 and 409 (already terminal) both return
// nil — idempotent semantic since the desired state (job not running)
// is already true in both cases. 404 surfaces as ErrJobNotFound.
func (c *Client) cancelJob(ctx context.Context, jobID, userIDOverride string) error {
	endpoint, params, headers, err := c.jobsEndpoint("cancel", jobID, userIDOverride)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, endpoint+"?"+params.Encode(), nil)
	if err != nil {
		return newErrorFromCode("LLM_HTTP_ERROR", "cancel_job request build: "+err.Error(), 0)
	}
	for k, v := range headers {
		req.Header[k] = v
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return newErrorFromCode("LLM_HTTP_ERROR", "cancel_job transport failure: "+err.Error(), 0)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNoContent || resp.StatusCode == http.StatusConflict {
		return nil
	}
	if resp.StatusCode == http.StatusNotFound {
		return newErrorFromCode("LLM_JOB_NOT_FOUND", fmt.Sprintf("job %s not found", jobID), 404)
	}
	return c.raiseHTTPError(resp)
}

// waitTerminal polls getJob with exponential backoff until status is
// {completed, failed, cancelled}, or ctx is cancelled.
//
// transientRetryBudget=0 (fixed for generate_image per Python SDK
// precedent — silent retry could double-charge BYOK on expensive image
// generation).
func (c *Client) waitTerminal(ctx context.Context, jobID, userIDOverride string, opts pollOptions) (*job, error) {
	interval := opts.pollInterval
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	maxInterval := opts.maxPollInterval
	if maxInterval <= 0 {
		maxInterval = 10 * time.Second
	}

	httpFailures := 0
	for {
		// Honor cancellation early.
		if err := ctx.Err(); err != nil {
			return nil, err
		}

		j, err := c.getJob(ctx, jobID, userIDOverride)
		if err != nil {
			// HTTP-transport errors consume retry budget. Other gateway
			// errors (job-not-found, auth, etc.) propagate immediately.
			if errors.Is(err, ErrHTTPTransport) {
				httpFailures++
				if httpFailures > opts.transientRetryBudget {
					return nil, err
				}
				if err := sleepWithCtx(ctx, interval); err != nil {
					return nil, err
				}
				interval = nextInterval(interval, maxInterval)
				continue
			}
			return nil, err
		}

		if j.isTerminal() {
			return j, nil
		}

		if err := sleepWithCtx(ctx, interval); err != nil {
			return nil, err
		}
		interval = nextInterval(interval, maxInterval)
	}
}

// nextInterval applies 1.5× backoff with max-cap.
func nextInterval(current, max time.Duration) time.Duration {
	next := time.Duration(float64(current) * 1.5)
	if next > max {
		return max
	}
	return next
}

// sleepWithCtx sleeps for d but returns ctx.Err() if cancelled.
func sleepWithCtx(ctx context.Context, d time.Duration) error {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-t.C:
		return nil
	}
}

// raiseHTTPError reads the response body, decodes as ErrorBody, and
// constructs the appropriate typed *Error via newErrorFromCode. The
// caller-side code (body's `code` field) takes precedence over the
// status-bucket fallback so operation-specific codes
// (LLM_IMAGE_CONTENT_POLICY_VIOLATION on 400) surface as their
// dedicated sentinels.
func (c *Client) raiseHTTPError(resp *http.Response) error {
	bodyBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 16*1024))
	var body struct {
		Code        string  `json:"code"`
		Message     string  `json:"message"`
		RetryAfterS float64 `json:"retry_after_s,omitempty"`
	}
	_ = json.Unmarshal(bodyBytes, &body)

	code := body.Code
	message := body.Message
	if code == "" {
		// Body wasn't valid JSON OR didn't have a code. Use status bucket.
		code = statusToCode(resp.StatusCode)
		if message == "" {
			message = string(bodyBytes)
			if len(message) > 500 {
				message = message[:500]
			}
		}
	}

	if resp.StatusCode == http.StatusTooManyRequests || body.RetryAfterS > 0 {
		return newErrorFromCodeWithRetry(code, message, resp.StatusCode, body.RetryAfterS)
	}
	return newErrorFromCode(code, message, resp.StatusCode)
}

// statusToCode is the status-bucket fallback when the body doesn't
// carry a `code` field. Mirrors Python SDK's _raise_http_error logic.
func statusToCode(status int) string {
	switch status {
	case http.StatusUnauthorized:
		return "LLM_AUTH_FAILED"
	case http.StatusPaymentRequired:
		return "LLM_QUOTA_EXCEEDED"
	case http.StatusNotFound:
		return "LLM_MODEL_NOT_FOUND"
	case http.StatusTooManyRequests:
		return "LLM_RATE_LIMITED"
	case http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return "LLM_UPSTREAM_ERROR"
	default:
		if status >= 400 && status < 500 {
			return "LLM_INVALID_REQUEST"
		}
		return "LLM_ERROR"
	}
}
