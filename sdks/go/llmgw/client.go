package llmgw

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
)

// Options configures NewClient.
//
// NOTE: This intentionally accepts http.RoundTripper rather than a full
// *http.Client. A user-injected Client.Timeout would silently cap each
// per-poll request (the SDK polls until terminal — minutes for image
// generation; per /review-impl(DESIGN) HIGH#5). The SDK builds its
// internal *http.Client with no Timeout; all cancellation goes through
// the caller's context.Context.
type Options struct {
	// Required.
	BaseURL  string   // e.g. "http://provider-registry-service:8085"
	AuthMode AuthMode // AuthJWT or AuthInternal

	// AuthJWT.
	BearerToken string

	// AuthInternal.
	InternalToken string

	// Optional. When AuthMode=AuthInternal and UserID is empty here,
	// every per-call request must supply a UserID override.
	UserID string

	// Optional. Default: http.DefaultTransport.
	Transport http.RoundTripper
}

// Client is the goroutine-safe entry point to the unified LLM gateway.
//
// Construct ONE Client per process at startup; share it across all
// handler goroutines.
type Client struct {
	baseURL       string
	authMode      AuthMode
	bearerToken   string
	internalToken string
	userID        string
	http          *http.Client
}

// NewClient validates options and returns a usable Client.
func NewClient(opts Options) (*Client, error) {
	if opts.BaseURL == "" {
		return nil, newErrorFromCode("LLM_INVALID_REQUEST", "BaseURL is required", 0)
	}
	switch opts.AuthMode {
	case AuthJWT:
		if opts.BearerToken == "" {
			return nil, newErrorFromCode("LLM_INVALID_REQUEST", "AuthJWT requires BearerToken", 0)
		}
	case AuthInternal:
		if opts.InternalToken == "" {
			return nil, newErrorFromCode("LLM_INVALID_REQUEST", "AuthInternal requires InternalToken", 0)
		}
	default:
		return nil, newErrorFromCode("LLM_INVALID_REQUEST",
			fmt.Sprintf("unknown AuthMode %q", opts.AuthMode), 0)
	}

	transport := opts.Transport
	if transport == nil {
		transport = http.DefaultTransport
	}

	return &Client{
		baseURL:       strings.TrimRight(opts.BaseURL, "/"),
		authMode:      opts.AuthMode,
		bearerToken:   opts.BearerToken,
		internalToken: opts.InternalToken,
		userID:        opts.UserID,
		// HIGH#5 — NO Timeout on the http.Client. Cancellation is via ctx.
		http: &http.Client{Transport: transport},
	}, nil
}

// GenerateImage submits an image_gen job, polls until terminal, and
// returns the decoded ImageGenResult.
//
// Polling defaults: 0.5s initial, 10s max, 1.5× backoff.
// transientRetryBudget is fixed at 0 (silent retry could double-charge
// BYOK on expensive image generation).
//
// Cancellation via ctx. All wall-clock cancellation is the caller's
// responsibility — the SDK's internal *http.Client has no Timeout.
func (c *Client) GenerateImage(ctx context.Context, req GenerateImageRequest) (*ImageGenResult, error) {
	// ── Pre-flight validation (SDK boundary) ──────────────────────────

	if _, err := uuid.Parse(req.ModelRef); err != nil {
		return nil, newErrorFromCode(
			"LLM_INVALID_REQUEST",
			fmt.Sprintf("model_ref must be UUID-shaped, got %q", req.ModelRef),
			0,
		)
	}
	if strings.TrimSpace(req.Prompt) == "" {
		return nil, newErrorFromCode(
			"LLM_INVALID_REQUEST",
			"prompt must be non-empty",
			0,
		)
	}
	if req.ModelSource != ModelSourceUser && req.ModelSource != ModelSourcePlatform {
		return nil, newErrorFromCode(
			"LLM_INVALID_REQUEST",
			fmt.Sprintf("model_source must be user_model or platform_model, got %q", req.ModelSource),
			0,
		)
	}

	// ── Build wire payload (MED#1 — explicit map; preserves caller intent) ──

	input := map[string]any{"prompt": req.Prompt}
	if req.Size != nil {
		input["size"] = *req.Size
	}
	if req.N != nil {
		input["n"] = *req.N
	}
	if req.ResponseFormat != nil {
		input["response_format"] = *req.ResponseFormat
	}
	if req.Quality != nil {
		input["quality"] = *req.Quality
	}
	if req.Style != nil {
		input["style"] = *req.Style
	}
	if req.Background != nil {
		input["background"] = *req.Background
	}

	body := map[string]any{
		"operation":    "image_gen",
		"model_source": string(req.ModelSource),
		"model_ref":    req.ModelRef,
		"input":        input,
	}

	// ── Submit + wait for terminal ────────────────────────────────────

	submitted, err := c.submitJob(ctx, body, req.UserID)
	if err != nil {
		return nil, err
	}

	terminal, err := c.waitTerminal(ctx, submitted.JobID, req.UserID, pollOptions{
		pollInterval:         req.PollInterval,
		maxPollInterval:      req.MaxPollInterval,
		transientRetryBudget: 0, // fixed for image_gen — double-charge guard
	})
	if err != nil {
		return nil, err
	}

	// ── Decode terminal result ────────────────────────────────────────

	switch terminal.Status {
	case JobCompleted:
		if terminal.Result == nil {
			return nil, newErrorFromCode("LLM_UPSTREAM_ERROR",
				fmt.Sprintf("image_gen job %s completed but result is empty", submitted.JobID),
				0)
		}
		return decodeImageGenResult(terminal.Result)
	case JobCancelled:
		return nil, newErrorFromCode("LLM_JOB_TERMINAL",
			fmt.Sprintf("image_gen job %s cancelled", submitted.JobID), 0)
	case JobFailed:
		if terminal.Error == nil {
			return nil, newErrorFromCode("LLM_UPSTREAM_ERROR",
				fmt.Sprintf("image_gen job %s failed without error body", submitted.JobID), 0)
		}
		return nil, newErrorFromCodeWithRetry(
			terminal.Error.Code,
			terminal.Error.Message,
			0, // job-level errors don't carry HTTP status
			terminal.Error.RetryAfterS,
		)
	default:
		return nil, newErrorFromCode("LLM_DECODE_ERROR",
			fmt.Sprintf("unexpected terminal status %q", terminal.Status), 0)
	}
}

// decodeImageGenResult re-encodes the generic Result map to JSON and
// decodes into the typed ImageGenResult — preserving JSON tag semantics
// (omitempty, etc.) and giving Go-style error messages on malformed
// shapes.
func decodeImageGenResult(result map[string]any) (*ImageGenResult, error) {
	raw, err := json.Marshal(result)
	if err != nil {
		return nil, newErrorFromCode("LLM_DECODE_ERROR",
			"image_gen result re-marshal failed: "+err.Error(), 0)
	}
	var out ImageGenResult
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, newErrorFromCode("LLM_DECODE_ERROR",
			"image_gen result decode failed: "+err.Error(), 0)
	}
	if len(out.Data) == 0 {
		return nil, newErrorFromCode("LLM_UPSTREAM_ERROR",
			"image_gen result data array is empty", 0)
	}
	return &out, nil
}
