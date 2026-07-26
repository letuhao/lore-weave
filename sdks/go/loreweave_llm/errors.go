package loreweave_llm

import (
	"errors"
	"fmt"
)

// Error is a gateway-reported failure carrying the gateway error code, so callers
// can branch on it (errors.As to *Error, or errors.Is the sentinels below). Raised
// from an SSE `error` frame or an HTTP >= 400 response.
type Error struct {
	Code       string
	Message    string
	StatusCode int // HTTP status when the failure was HTTP-level (0 for an SSE-frame error)
}

func (e *Error) Error() string {
	if e.StatusCode != 0 {
		return fmt.Sprintf("loreweave_llm: %s (code=%s, status=%d)", e.Message, e.Code, e.StatusCode)
	}
	return fmt.Sprintf("loreweave_llm: %s (code=%s)", e.Message, e.Code)
}

// Sentinels for the codes a caller is likely to branch on. Match a concrete
// *Error via errors.Is — Is reports true when the codes match.
var (
	ErrInvalidRequest = &Error{Code: "LLM_INVALID_REQUEST", Message: "invalid request"}
	ErrProvider       = &Error{Code: "LLM_PROVIDER_ERROR", Message: "provider error"}
	ErrRateLimited    = &Error{Code: "LLM_RATE_LIMITED", Message: "rate limited"}
	ErrModelNotFound  = &Error{Code: "LLM_MODEL_NOT_FOUND", Message: "model not found"}
	ErrTimeout        = &Error{Code: "LLM_TIMEOUT", Message: "timeout"}
)

// Is matches by code so `errors.Is(err, ErrRateLimited)` works against any *Error
// carrying that code (regardless of message/status).
func (e *Error) Is(target error) bool {
	var t *Error
	if !errors.As(target, &t) {
		return false
	}
	return e.Code == t.Code
}

// fromCode builds an *Error from an SSE error frame.
func fromCode(code, message string) *Error {
	if message == "" {
		message = code
	}
	return &Error{Code: code, Message: message}
}
