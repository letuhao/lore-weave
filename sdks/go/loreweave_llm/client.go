package loreweave_llm

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

// AuthMode selects how the client authenticates to the gateway.
type AuthMode string

const (
	// AuthInternal — service-to-service: X-Internal-Token header + ?user_id=.
	// The gateway resolves the user's BYOK model from user_id (multi-tenant).
	AuthInternal AuthMode = "internal"
	// AuthJWT — end-user: Authorization: Bearer. user_id comes from the token.
	AuthJWT AuthMode = "jwt"
)

// Options configures a Client.
type Options struct {
	BaseURL       string // gateway base URL (no trailing /v1/... — that's appended)
	AuthMode      AuthMode
	InternalToken string       // required for AuthInternal
	BearerToken   string       // required for AuthJWT
	UserID        string       // AuthInternal default user; per-call override available
	HTTPClient    *http.Client // optional; the caller may inject a traced transport
}

// Client calls the LLM gateway. Construct one per process; it is safe for
// concurrent use (the underlying http.Client is).
type Client struct {
	baseURL       string
	authMode      AuthMode
	internalToken string
	bearer        string
	userID        string
	http          *http.Client
}

// NewClient validates the options and returns a Client. There is no client-level
// timeout by default — completions can be long; bound them with the call context.
func NewClient(opts Options) (*Client, error) {
	if strings.TrimSpace(opts.BaseURL) == "" {
		return nil, errors.New("loreweave_llm: BaseURL is required")
	}
	mode := opts.AuthMode
	if mode == "" {
		mode = AuthInternal
	}
	switch mode {
	case AuthInternal:
		if opts.InternalToken == "" {
			return nil, errors.New("loreweave_llm: internal auth requires InternalToken")
		}
	case AuthJWT:
		if opts.BearerToken == "" {
			return nil, errors.New("loreweave_llm: jwt auth requires BearerToken")
		}
	default:
		return nil, fmt.Errorf("loreweave_llm: unknown auth mode %q", mode)
	}
	hc := opts.HTTPClient
	if hc == nil {
		hc = &http.Client{}
	}
	return &Client{
		baseURL:       strings.TrimRight(opts.BaseURL, "/"),
		authMode:      mode,
		internalToken: opts.InternalToken,
		bearer:        opts.BearerToken,
		userID:        opts.UserID,
		http:          hc,
	}, nil
}

// Complete runs a non-streaming completion: it opens the stream, accumulates
// `token` deltas into Result.Text (and `reasoning` deltas into Result.Reasoning),
// captures usage + finish reason, and returns when the gateway emits `done`. An
// SSE `error` frame or an HTTP >= 400 becomes an *Error. The optional userID
// overrides the client's default for this call (required for AuthInternal when the
// client was built without a default UserID — the multi-tenant pattern).
func (c *Client) Complete(ctx context.Context, req StreamRequest, userID ...string) (Result, error) {
	var res Result
	var text, reasoning strings.Builder
	err := c.stream(ctx, req, firstOr(userID), func(ev sseEvent) error {
		switch ev.Type {
		case "token":
			var d tokenData
			if err := json.Unmarshal(ev.Data, &d); err != nil {
				return err
			}
			text.WriteString(d.Delta)
		case "reasoning":
			var d tokenData
			if json.Unmarshal(ev.Data, &d) == nil {
				reasoning.WriteString(d.Delta)
			}
		case "usage":
			var d usageData
			if json.Unmarshal(ev.Data, &d) == nil {
				res.Usage = Usage(d)
			}
		case "done":
			var d doneData
			_ = json.Unmarshal(ev.Data, &d)
			res.FinishReason = d.FinishReason
		case "error":
			var d errorData
			_ = json.Unmarshal(ev.Data, &d)
			return fromCode(d.Code, d.Message)
		}
		return nil
	})
	if err != nil {
		return Result{}, err
	}
	res.Text = text.String()
	res.Reasoning = reasoning.String()
	return res, nil
}

// stream POSTs the request and dispatches each SSE event to onEvent. Returns the
// first error from onEvent (incl. a translated `error` frame) or a transport/HTTP error.
func (c *Client) stream(ctx context.Context, req StreamRequest, userID string, onEvent func(sseEvent) error) error {
	if req.StreamFormat == "" {
		req.StreamFormat = "openai"
	}
	endpoint, params, headers, err := c.endpoint(userID)
	if err != nil {
		return err
	}
	body, err := json.Marshal(req)
	if err != nil {
		return err
	}
	u := endpoint
	if enc := params.Encode(); enc != "" {
		u += "?" + enc
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")
	for k, v := range headers {
		httpReq.Header.Set(k, v)
	}
	resp, err := c.http.Do(httpReq)
	if err != nil {
		return &Error{Code: "LLM_TRANSPORT", Message: err.Error()}
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return c.httpError(resp)
	}
	return scanSSE(resp.Body, onEvent)
}

func (c *Client) endpoint(userID string) (string, url.Values, map[string]string, error) {
	params := url.Values{}
	headers := map[string]string{}
	switch c.authMode {
	case AuthJWT:
		headers["Authorization"] = "Bearer " + c.bearer
		return c.baseURL + "/v1/llm/stream", params, headers, nil
	default: // AuthInternal
		uid := userID
		if uid == "" {
			uid = c.userID
		}
		if uid == "" {
			return "", nil, nil, &Error{Code: "LLM_INVALID_REQUEST", Message: "internal auth requires user_id (per-call or at construction)"}
		}
		headers["X-Internal-Token"] = c.internalToken
		params.Set("user_id", uid)
		return c.baseURL + "/internal/llm/stream", params, headers, nil
	}
}

// httpError classifies an HTTP >= 400 response: prefer the gateway's JSON
// {code,message}, fall back to a status-derived code.
func (c *Client) httpError(resp *http.Response) error {
	b, _ := io.ReadAll(io.LimitReader(resp.Body, 8*1024))
	var d errorData
	if json.Unmarshal(b, &d) == nil && d.Code != "" {
		return &Error{Code: d.Code, Message: d.Message, StatusCode: resp.StatusCode}
	}
	return &Error{Code: statusToCode(resp.StatusCode), Message: strings.TrimSpace(string(b)), StatusCode: resp.StatusCode}
}

func statusToCode(status int) string {
	switch status {
	case http.StatusBadRequest:
		return "LLM_INVALID_REQUEST"
	case http.StatusTooManyRequests:
		return "LLM_RATE_LIMITED"
	case http.StatusNotFound:
		return "LLM_MODEL_NOT_FOUND"
	case http.StatusRequestTimeout, http.StatusGatewayTimeout:
		return "LLM_TIMEOUT"
	default:
		return "LLM_PROVIDER_ERROR"
	}
}

func firstOr(s []string) string {
	if len(s) > 0 {
		return s[0]
	}
	return ""
}
