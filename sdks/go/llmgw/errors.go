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
//
// Stays a SINGLE-error Unwrap on purpose. A transport failure joins its cause
// into `inner` (see newTransportError) rather than returning []error, because
// the stdlib errors.Unwrap() function returns nil for a multi-error Unwrap —
// which would silently break every caller that walks the chain that way.
func (e *Error) Unwrap() error { return e.inner }

// Sentinel errors. Match via errors.Is(err, ErrXxx) — never compare
// `err == ErrXxx` directly because actual returned errors wrap a sentinel
// inside *Error.
var (
	ErrAuthFailed     = errors.New("LLM_AUTH_FAILED")
	ErrInvalidRequest = errors.New("LLM_INVALID_REQUEST")
	ErrQuotaExceeded  = errors.New("LLM_QUOTA_EXCEEDED")
	// ErrModelUnpriced -- 402 like ErrQuotaExceeded, and it used to SHARE that code.
	// Opposite problems: a spend cap is raised or waited out; an unpriced model needs
	// its rates set. A caller that cannot tell them apart cannot advise the user.
	ErrModelUnpriced         = errors.New("LLM_MODEL_UNPRICED")
	ErrModelNotFound         = errors.New("LLM_MODEL_NOT_FOUND")
	ErrRateLimited           = errors.New("LLM_RATE_LIMITED")
	ErrUpstream              = errors.New("LLM_UPSTREAM_ERROR")
	ErrImageContentPolicy    = errors.New("LLM_IMAGE_CONTENT_POLICY_VIOLATION")
	ErrImageGenerationFailed = errors.New("LLM_IMAGE_GENERATION_FAILED")
	// Phase 5e-β.2 — audio_gen-specific sentinel.
	ErrAudioGenerationFailed = errors.New("LLM_AUDIO_GENERATION_FAILED")
	// Phase 5e-β.2 — gateway-side storage failure (upstream TTS succeeded
	// but MinIO staging failed). Distinct so callers don't auto-retry
	// (which would double-charge BYOK).
	ErrGatewayStorage = errors.New("LLM_GATEWAY_STORAGE_ERROR")
	ErrJobNotFound    = errors.New("LLM_JOB_NOT_FOUND")
	ErrJobTerminal    = errors.New("LLM_JOB_TERMINAL")
	ErrHTTPTransport  = errors.New("LLM_HTTP_ERROR")
	ErrDecode         = errors.New("LLM_DECODE_ERROR")
)

// codeSentinels maps gateway error codes to their sentinel error.
// Unknown codes fall through to a nil inner — *Error is still
// constructable, but errors.Is(err, anySentinel) returns false.
var codeSentinels = map[string]error{
	"LLM_AUTH_FAILED":                    ErrAuthFailed,
	"LLM_INVALID_REQUEST":                ErrInvalidRequest,
	"LLM_QUOTA_EXCEEDED":                 ErrQuotaExceeded,
	"LLM_MODEL_UNPRICED":                 ErrModelUnpriced,
	"LLM_MODEL_NOT_FOUND":                ErrModelNotFound,
	"LLM_RATE_LIMITED":                   ErrRateLimited,
	"LLM_UPSTREAM_ERROR":                 ErrUpstream,
	"LLM_IMAGE_CONTENT_POLICY_VIOLATION": ErrImageContentPolicy,
	"LLM_IMAGE_GENERATION_FAILED":        ErrImageGenerationFailed,
	"LLM_AUDIO_GENERATION_FAILED":        ErrAudioGenerationFailed,
	"LLM_GATEWAY_STORAGE_ERROR":          ErrGatewayStorage,
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

// newTransportError wraps a real transport/context failure, KEEPING the cause so
// errors.Is can still see it. Use this — never newErrorFromCode — whenever the
// message is built from another error's text.
//
// 🔴 THE CAUSE USED TO BE THROWN AWAY. The transport formatted the real error into
// Message with `+err.Error()` and kept only the code sentinel, so
// errors.Is(err, context.Canceled) was FALSE for a cancelled request — a caller
// could not tell "the user cancelled" from "the network broke", which is the exact
// distinction cancellation handling is built on. It surfaced as a FLAKY test:
// TestWaitTerminal_ContextCancellation passed when the cancel landed between polls
// and failed when it landed mid-request, so it went red only under load.
func newTransportError(code, message string, statusCode int, cause error) *Error {
	inner := codeSentinels[code]
	switch {
	case inner != nil && cause != nil:
		// Both reachable from one error: errors.Is(err, ErrHTTPTransport) says WHAT
		// kind of failure, errors.Is(err, context.Canceled) says WHY.
		inner = fmt.Errorf("%w: %w", inner, cause)
	case inner == nil:
		inner = cause
	}
	return &Error{
		Code:       code,
		Message:    message,
		StatusCode: statusCode,
		inner:      inner,
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
