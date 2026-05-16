package llmgw

import (
	"errors"
	"fmt"
	"testing"
)

// HIGH#1 regression-lock — every codeSentinels entry must round-trip
// through newErrorFromCode and remain reachable via errors.Is.
//
// If a future contributor adds a new code to codeSentinels but forgets
// to populate `inner` via the helper, callers' errors.Is(err, ErrXxx)
// silently returns false and content-policy violations etc. fall to
// the default 502 path. This test catches that drift at SDK build time.
func TestNewErrorFromCode_AllKnownCodesMatchSentinels(t *testing.T) {
	for code, sentinel := range codeSentinels {
		err := newErrorFromCode(code, "test message", 500)
		if !errors.Is(err, sentinel) {
			t.Errorf("errors.Is(newErrorFromCode(%q), sentinel) returned false — inner not populated", code)
		}
	}
}

func TestNewErrorFromCode_UnknownCode_DoesNotPanic(t *testing.T) {
	err := newErrorFromCode("LLM_FUTURE_UNKNOWN_CODE", "msg", 500)
	if err.Code != "LLM_FUTURE_UNKNOWN_CODE" {
		t.Errorf("Code lost: got %q", err.Code)
	}
	if errors.Is(err, ErrAuthFailed) {
		t.Errorf("unexpected sentinel match on unknown code")
	}
	if errors.Is(err, ErrInvalidRequest) {
		t.Errorf("unexpected sentinel match on unknown code")
	}
}

func TestNewErrorFromCodeWithRetry_PopulatesRetryAfter(t *testing.T) {
	err := newErrorFromCodeWithRetry("LLM_RATE_LIMITED", "slow down", 429, 12.5)
	if err.RetryAfterS != 12.5 {
		t.Errorf("RetryAfterS not set: got %v, want 12.5", err.RetryAfterS)
	}
	if !errors.Is(err, ErrRateLimited) {
		t.Errorf("errors.Is(err, ErrRateLimited) returned false")
	}
}

func TestError_ErrorString_IncludesCodeAndStatus(t *testing.T) {
	err := newErrorFromCode("LLM_INVALID_REQUEST", "missing prompt", 400)
	got := err.Error()
	if !contains(got, "LLM_INVALID_REQUEST") {
		t.Errorf("Error() missing code: %q", got)
	}
	if !contains(got, "http=400") {
		t.Errorf("Error() missing status: %q", got)
	}
	if !contains(got, "missing prompt") {
		t.Errorf("Error() missing message: %q", got)
	}
}

func TestError_ErrorString_NoStatusWhenZero(t *testing.T) {
	err := newErrorFromCode("LLM_INVALID_REQUEST", "bad UUID", 0)
	got := err.Error()
	if contains(got, "http=") {
		t.Errorf("Error() included http=N for SDK-side validation error: %q", got)
	}
}

func TestError_Unwrap_ReturnsInner(t *testing.T) {
	err := newErrorFromCode("LLM_QUOTA_EXCEEDED", "out of credits", 402)
	unwrapped := errors.Unwrap(err)
	if unwrapped != ErrQuotaExceeded {
		t.Errorf("Unwrap returned %v, want ErrQuotaExceeded", unwrapped)
	}
}

func TestError_WrappedInFmtErrorf_StillMatches(t *testing.T) {
	// MED#3 — callers must use errors.As / errors.Is to handle wrapped
	// errors. Verify the wrap+match contract works.
	original := newErrorFromCode("LLM_IMAGE_CONTENT_POLICY_VIOLATION", "rephrase", 400)
	wrapped := fmt.Errorf("submit failed: %w", original)
	if !errors.Is(wrapped, ErrImageContentPolicy) {
		t.Errorf("errors.Is across fmt.Errorf wrap returned false")
	}
	var llmErr *Error
	if !errors.As(wrapped, &llmErr) {
		t.Errorf("errors.As across fmt.Errorf wrap returned false")
	}
	if llmErr.Code != "LLM_IMAGE_CONTENT_POLICY_VIOLATION" {
		t.Errorf("errors.As yielded wrong Code: %q", llmErr.Code)
	}
}

func TestStatusToCode_KnownStatuses(t *testing.T) {
	cases := []struct {
		status int
		want   string
	}{
		{401, "LLM_AUTH_FAILED"},
		{402, "LLM_QUOTA_EXCEEDED"},
		{404, "LLM_MODEL_NOT_FOUND"},
		{429, "LLM_RATE_LIMITED"},
		{502, "LLM_UPSTREAM_ERROR"},
		{503, "LLM_UPSTREAM_ERROR"},
		{504, "LLM_UPSTREAM_ERROR"},
		{400, "LLM_INVALID_REQUEST"},
		{418, "LLM_INVALID_REQUEST"}, // any 4xx fallback
		{500, "LLM_ERROR"},
		{501, "LLM_ERROR"},
	}
	for _, c := range cases {
		got := statusToCode(c.status)
		if got != c.want {
			t.Errorf("statusToCode(%d) = %q, want %q", c.status, got, c.want)
		}
	}
}

func contains(haystack, needle string) bool {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
