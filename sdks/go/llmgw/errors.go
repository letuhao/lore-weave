package llmgw

import (
	"errors"
	"fmt"
)

// Error is the error type returned by all SDK methods. The Code field
// matches the gateway's openapi ErrorBody.code namespace.
//
// Match by sentinel using errors.Is:
//
//	if errors.Is(err, llmgw.ErrImageContentPolicy) { ... }
//
// Retrieve fields (StatusCode, RetryAfterS, Message) using errors.As:
//
//	var llmErr *llmgw.Error
//	if errors.As(err, &llmErr) {
//	    log.Printf("status=%d retry_after=%fs", llmErr.StatusCode, llmErr.RetryAfterS)
//	}
type Error struct {
	Code        string  // e.g. "LLM_IMAGE_CONTENT_POLICY_VIOLATION"
	Message     string  // human-readable message from gateway
	StatusCode  int     // HTTP status if known (0 for SDK-side validation errors)
	RetryAfterS float64 // populated for ErrRateLimited; 0 otherwise
	inner       error   // sentinel for errors.Is matching
}

func (e *Error) Error() string {
	if e.StatusCode > 0 {
		return fmt.Sprintf("%s (http=%d): %s", e.Code, e.StatusCode, e.Message)
	}
	return fmt.Sprintf("%s: %s", e.Code, e.Message)
}

// Unwrap returns the sentinel error for errors.Is chain-walking.
func (e *Error) Unwrap() error { return e.inner }

// Sentinel errors. Match via errors.Is(err, ErrXxx) — never compare
// `err == ErrXxx` directly because actual returned errors wrap a sentinel
// inside *Error.
var (
	ErrAuthFailed            = errors.New("LLM_AUTH_FAILED")
	ErrInvalidRequest        = errors.New("LLM_INVALID_REQUEST")
	ErrQuotaExceeded         = errors.New("LLM_QUOTA_EXCEEDED")
	ErrModelNotFound         = errors.New("LLM_MODEL_NOT_FOUND")
	ErrRateLimited           = errors.New("LLM_RATE_LIMITED")
	ErrUpstream              = errors.New("LLM_UPSTREAM_ERROR")
	ErrImageContentPolicy    = errors.New("LLM_IMAGE_CONTENT_POLICY_VIOLATION")
	ErrImageGenerationFailed = errors.New("LLM_IMAGE_GENERATION_FAILED")
	ErrJobNotFound           = errors.New("LLM_JOB_NOT_FOUND")
	ErrJobTerminal           = errors.New("LLM_JOB_TERMINAL")
	ErrHTTPTransport         = errors.New("LLM_HTTP_ERROR")
	ErrDecode                = errors.New("LLM_DECODE_ERROR")
)

// codeSentinels maps gateway error codes to their sentinel error.
// Unknown codes fall through to a nil inner — *Error is still
// constructable, but errors.Is(err, anySentinel) returns false.
var codeSentinels = map[string]error{
	"LLM_AUTH_FAILED":                    ErrAuthFailed,
	"LLM_INVALID_REQUEST":                ErrInvalidRequest,
	"LLM_QUOTA_EXCEEDED":                 ErrQuotaExceeded,
	"LLM_MODEL_NOT_FOUND":                ErrModelNotFound,
	"LLM_RATE_LIMITED":                   ErrRateLimited,
	"LLM_UPSTREAM_ERROR":                 ErrUpstream,
	"LLM_IMAGE_CONTENT_POLICY_VIOLATION": ErrImageContentPolicy,
	"LLM_IMAGE_GENERATION_FAILED":        ErrImageGenerationFailed,
	"LLM_JOB_NOT_FOUND":                  ErrJobNotFound,
	"LLM_JOB_TERMINAL":                   ErrJobTerminal,
	"LLM_HTTP_ERROR":                     ErrHTTPTransport,
	"LLM_DECODE_ERROR":                   ErrDecode,
}

// newErrorFromCode constructs a *Error with the sentinel populated for
// errors.Is matching.
//
// ALL Error construction in the SDK MUST go through this helper (or
// newErrorFromCodeWithRetry). Manual struct construction risks
// forgetting to populate `inner`, silently breaking errors.Is for
// callers. Per /review-impl(DESIGN) HIGH#1.
func newErrorFromCode(code, message string, statusCode int) *Error {
	return &Error{
		Code:       code,
		Message:    message,
		StatusCode: statusCode,
		inner:      codeSentinels[code], // nil if unknown — OK
	}
}

// newErrorFromCodeWithRetry — same as newErrorFromCode but with retry-after.
// Used for 429 / LLM_RATE_LIMITED responses where the gateway provides
// a retry_after_s hint in the response body.
func newErrorFromCodeWithRetry(code, message string, statusCode int, retryAfterS float64) *Error {
	return &Error{
		Code:        code,
		Message:     message,
		StatusCode:  statusCode,
		RetryAfterS: retryAfterS,
		inner:       codeSentinels[code],
	}
}
