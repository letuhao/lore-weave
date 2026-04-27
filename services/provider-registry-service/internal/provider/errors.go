package provider

import (
	"errors"
	"fmt"
)

// Phase 4a-α Step 0b — typed upstream errors so the worker can decide
// whether to retry vs. fail. Today every upstream HTTP/network error
// surfaces as a generic fmt.Errorf which makes retry-classification
// impossible. Knowledge-service's K17.3 today absorbs ≤1 retry on
// rate-limit / 5xx / timeout via its own caller-side wrapper; with
// Phase 4a migration that wrapper goes away, so the gateway-side
// worker MUST take over the retry semantic to avoid a quality
// regression on local LLMs (LM Studio routinely emits transient 502s).

// ErrUpstreamRateLimited — provider returned 429. RetryAfterS is the
// upstream's `Retry-After` header value in seconds (delta-seconds form
// only; HTTP-date form is ignored). Nil when header absent/unparseable.
type ErrUpstreamRateLimited struct {
	StatusCode   int
	Body         string // truncated provider response body for logging
	RetryAfterS  *float64
}

func (e *ErrUpstreamRateLimited) Error() string {
	return fmt.Sprintf("provider rate limited: HTTP %d: %s", e.StatusCode, e.Body)
}

// ErrUpstreamTransient — provider returned 5xx (502/503/504 typically).
// Worker treats this as retry-eligible.
type ErrUpstreamTransient struct {
	StatusCode int
	Body       string
}

func (e *ErrUpstreamTransient) Error() string {
	return fmt.Sprintf("provider transient error: HTTP %d: %s", e.StatusCode, e.Body)
}

// ErrUpstreamTimeout — network/transport timeout reaching the upstream
// provider. Distinct from ErrUpstreamTransient because the provider
// never produced an HTTP response. Worker treats as retry-eligible.
type ErrUpstreamTimeout struct {
	Underlying error
}

func (e *ErrUpstreamTimeout) Error() string {
	return fmt.Sprintf("provider timeout: %v", e.Underlying)
}

func (e *ErrUpstreamTimeout) Unwrap() error { return e.Underlying }

// ErrUpstreamPermanent — provider returned 4xx other than 429 (400, 401,
// 403, 404, 413, 422, etc.). Caller bug or upstream config issue —
// retrying with the same args will always fail. Worker does NOT retry.
type ErrUpstreamPermanent struct {
	StatusCode int
	Body       string
}

func (e *ErrUpstreamPermanent) Error() string {
	return fmt.Sprintf("provider permanent error: HTTP %d: %s", e.StatusCode, e.Body)
}

// IsTransientUpstreamError reports whether the worker should retry the
// upstream call. True for rate-limit / 5xx / timeout; false for
// permanent (4xx-except-429) and for any non-typed error (default-deny).
func IsTransientUpstreamError(err error) bool {
	if err == nil {
		return false
	}
	var rl *ErrUpstreamRateLimited
	var trans *ErrUpstreamTransient
	var to *ErrUpstreamTimeout
	return errors.As(err, &rl) || errors.As(err, &trans) || errors.As(err, &to)
}

// RetryAfter returns the suggested retry delay in seconds for a transient
// error, or 0 when the error doesn't carry one. Used by the worker to
// honor Retry-After on rate-limit responses; falls back to a fixed
// backoff at the call site when this returns 0.
func RetryAfter(err error) float64 {
	var rl *ErrUpstreamRateLimited
	if errors.As(err, &rl) && rl.RetryAfterS != nil && *rl.RetryAfterS > 0 {
		return *rl.RetryAfterS
	}
	return 0
}

// ClassifyUpstreamHTTP turns an HTTP status code + a small body sample
// into the right typed error. Used by streamer.go and anthropic_streamer.go
// at the open-stream boundary. Returns nil for status < 400 (caller
// should not call this for non-error responses).
//
// retryAfterS is the parsed "Retry-After: N" header value (delta-seconds
// only). Pass nil when the response carries no parseable header.
func ClassifyUpstreamHTTP(statusCode int, body string, retryAfterS *float64) error {
	if statusCode < 400 {
		return nil
	}
	if statusCode == 429 {
		return &ErrUpstreamRateLimited{
			StatusCode:  statusCode,
			Body:        body,
			RetryAfterS: retryAfterS,
		}
	}
	if statusCode >= 500 {
		return &ErrUpstreamTransient{
			StatusCode: statusCode,
			Body:       body,
		}
	}
	return &ErrUpstreamPermanent{
		StatusCode: statusCode,
		Body:       body,
	}
}
