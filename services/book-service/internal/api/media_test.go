package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/llmgw"
)

// ── writeImageGenError typed-error → HTTP routing tests ───────────────
//
// These tests exercise the extracted helper directly (no DB / no MinIO
// / no JWT fixtures needed). They verify the contract that each typed
// SDK error maps to the expected HTTP status + LoreWeave error code.

// fakeLLMError builds a *llmgw.Error that satisfies errors.Is for the
// requested sentinel. Uses the SDK's exported codes to ensure the
// codeSentinels map round-trips.
func fakeLLMError(t *testing.T, code, message string, statusCode int, retryAfterS float64) error {
	t.Helper()
	// Use fmt.Errorf wrap to ensure the helper's errors.As/Is contract
	// survives wrapping (per /review-impl(DESIGN) MED#3 regression-lock).
	base := &llmgw.Error{}
	// We can't call newErrorFromCode (unexported), so we trigger one
	// via a real SDK call path with a known-bad config. Easier: marshal
	// an inline submit-job response with the desired code and let the
	// SDK construct the typed error. Actually simplest: use the SDK's
	// public sentinels via fmt.Errorf wrap — errors.Is on a sentinel
	// works without needing the *Error struct.
	_ = base
	// Wrap the sentinel inside fmt.Errorf so errors.Is matches.
	// Status code + retry-after are tested via direct *llmgw.Error
	// construction in dedicated tests.
	return wrappedSentinelError{code: code, message: message, statusCode: statusCode, retryAfterS: retryAfterS}
}

// wrappedSentinelError is a test-only error type that satisfies the
// errors.Is contract for any *llmgw.* sentinel by code. Used because
// llmgw's newErrorFromCode is unexported.
type wrappedSentinelError struct {
	code        string
	message     string
	statusCode  int
	retryAfterS float64
}

func (e wrappedSentinelError) Error() string {
	return fmt.Sprintf("%s: %s", e.code, e.message)
}

func (e wrappedSentinelError) Is(target error) bool {
	// Match against llmgw sentinels by their error message which is the code.
	if target == nil {
		return false
	}
	return target.Error() == e.code
}

// As lets errors.As(err, &*llmgw.Error{}) capture our fields.
func (e wrappedSentinelError) As(target any) bool {
	if llmErrPtr, ok := target.(**llmgw.Error); ok {
		*llmErrPtr = &llmgw.Error{
			Code:        e.code,
			Message:     e.message,
			StatusCode:  e.statusCode,
			RetryAfterS: e.retryAfterS,
		}
		return true
	}
	return false
}

func TestWriteImageGenError_ContentPolicy_Returns400(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_IMAGE_CONTENT_POLICY_VIOLATION", "violence detected", 400, 0)
	writeImageGenError(w, err)
	if w.Code != 400 {
		t.Errorf("status = %d, want 400", w.Code)
	}
	body := w.Body.String()
	if !strings.Contains(body, "CONTENT_POLICY") {
		t.Errorf("body missing CONTENT_POLICY code: %s", body)
	}
	if !strings.Contains(body, "violence detected") {
		t.Errorf("body missing original message: %s", body)
	}
}

func TestWriteImageGenError_QuotaExceeded_Returns402(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_QUOTA_EXCEEDED", "out of credits", 402, 0)
	writeImageGenError(w, err)
	if w.Code != 402 {
		t.Errorf("status = %d, want 402", w.Code)
	}
	if !strings.Contains(w.Body.String(), "NO_PROVIDER") {
		t.Errorf("body missing NO_PROVIDER code: %s", w.Body.String())
	}
}

func TestWriteImageGenError_ModelNotFound_Returns402(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_MODEL_NOT_FOUND", "model gone", 404, 0)
	writeImageGenError(w, err)
	if w.Code != 402 {
		t.Errorf("status = %d, want 402 (mapped from ErrModelNotFound)", w.Code)
	}
}

func TestWriteImageGenError_InvalidRequest_Returns400(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_INVALID_REQUEST", "bad uuid", 400, 0)
	writeImageGenError(w, err)
	if w.Code != 400 {
		t.Errorf("status = %d, want 400", w.Code)
	}
	if !strings.Contains(w.Body.String(), "BOOK_VALIDATION_ERROR") {
		t.Errorf("body missing BOOK_VALIDATION_ERROR: %s", w.Body.String())
	}
}

func TestWriteImageGenError_RateLimitedWithRetry_SetsRetryAfter(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_RATE_LIMITED", "slow down", 429, 30)
	writeImageGenError(w, err)
	if w.Code != 429 {
		t.Errorf("status = %d, want 429", w.Code)
	}
	if got := w.Header().Get("Retry-After"); got != "30" {
		t.Errorf("Retry-After = %q, want \"30\"", got)
	}
	if !strings.Contains(w.Body.String(), "RATE_LIMITED") {
		t.Errorf("body missing RATE_LIMITED code: %s", w.Body.String())
	}
}

func TestWriteImageGenError_RateLimitedNoRetry_NoHeader(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_RATE_LIMITED", "slow down", 429, 0)
	writeImageGenError(w, err)
	if got := w.Header().Get("Retry-After"); got != "" {
		t.Errorf("Retry-After should be empty when RetryAfterS=0; got %q", got)
	}
}

// /review-impl(DESIGN) MED#2 regression-lock: ErrImageGenerationFailed
// is a SEPARATE case from ErrUpstream — verify body messages differ.
func TestWriteImageGenError_ImageGenerationFailed_HasDistinctMessage(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_IMAGE_GENERATION_FAILED", "ComfyUI failed", 0, 0)
	writeImageGenError(w, err)
	if w.Code != 502 {
		t.Errorf("status = %d, want 502", w.Code)
	}
	body := w.Body.String()
	if !strings.Contains(body, "retryable") {
		t.Errorf("ErrImageGenerationFailed body should mention retryable; got %s", body)
	}
}

func TestWriteImageGenError_Upstream_HasDistinctMessage(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_UPSTREAM_ERROR", "gateway 5xx", 502, 0)
	writeImageGenError(w, err)
	if w.Code != 502 {
		t.Errorf("status = %d, want 502", w.Code)
	}
	body := w.Body.String()
	if !strings.Contains(body, "upstream error") {
		t.Errorf("ErrUpstream body should mention upstream; got %s", body)
	}
	if strings.Contains(body, "retryable") {
		t.Errorf("ErrUpstream body should NOT collapse with ErrImageGenerationFailed message; got %s", body)
	}
}

func TestWriteImageGenError_JobTerminal_Returns504(t *testing.T) {
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_JOB_TERMINAL", "cancelled", 0, 0)
	writeImageGenError(w, err)
	if w.Code != 504 {
		t.Errorf("status = %d, want 504", w.Code)
	}
}

func TestWriteImageGenError_AuthFailed_Returns402_NoProvider(t *testing.T) {
	// /review-impl(BUILD) MED#2 — ErrAuthFailed from the gateway can mean
	// either book-service internal-token rejection (rare, our config bug)
	// OR upstream BYOK key revoked (common, user's config). The latter
	// is the dominant path, so map to 402 NO_PROVIDER (FE prompts user
	// to fix their key) rather than 502 PROVIDER_ERROR.
	w := httptest.NewRecorder()
	err := fakeLLMError(t, "LLM_AUTH_FAILED", "bad token", 401, 0)
	writeImageGenError(w, err)
	if w.Code != 402 {
		t.Errorf("status = %d, want 402", w.Code)
	}
	if !strings.Contains(w.Body.String(), "NO_PROVIDER") {
		t.Errorf("body missing NO_PROVIDER: %s", w.Body.String())
	}
}

func TestWriteImageGenError_Unknown_Returns502(t *testing.T) {
	w := httptest.NewRecorder()
	err := errors.New("totally unknown error")
	writeImageGenError(w, err)
	if w.Code != 502 {
		t.Errorf("status = %d, want 502 (catch-all)", w.Code)
	}
}

// MED#3 regression-lock: writeImageGenError works on errors wrapped via
// fmt.Errorf. If a future caller wraps the SDK error with extra context,
// the handler must still surface the typed mapping.
func TestWriteImageGenError_WrappedError_StillMatches(t *testing.T) {
	w := httptest.NewRecorder()
	original := fakeLLMError(t, "LLM_IMAGE_CONTENT_POLICY_VIOLATION", "bad prompt", 400, 0)
	wrapped := fmt.Errorf("outer context: %w", original)
	writeImageGenError(w, wrapped)
	if w.Code != 400 {
		t.Errorf("wrapped error: status = %d, want 400", w.Code)
	}
}

// /review-impl(BUILD) MED#1 — End-to-end test that constructs a REAL
// *llmgw.Error through a real SDK call (instead of the wrappedSentinelError
// stub) and routes it through writeImageGenError. This exercises the actual
// errors.Is Unwrap chain — the stub-only tests pass even when the SDK's
// sentinels are reshaped, because they bypass the chain. This test fails
// if a future SDK refactor breaks the errors.Is contract.
func TestWriteImageGenError_RealSDKContentPolicy_RoutesTo400(t *testing.T) {
	// Spin up a gateway that returns a 4-step async-job flow ending in
	// JobFailed with LLM_IMAGE_CONTENT_POLICY_VIOLATION.
	var pollCount int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			// submit
			w.WriteHeader(http.StatusAccepted)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"job_id":       "00000000-0000-0000-0000-000000000abc",
				"status":       "pending",
				"submitted_at": "2026-05-14T00:00:00Z",
			})
			return
		}
		// poll → fail terminal
		pollCount++
		_ = json.NewEncoder(w).Encode(map[string]any{
			"job_id":    "00000000-0000-0000-0000-000000000abc",
			"operation": "image_gen",
			"status":    "failed",
			"error": map[string]any{
				"code":    "LLM_IMAGE_CONTENT_POLICY_VIOLATION",
				"message": "real SDK content-policy violation",
			},
		})
	}))
	defer server.Close()

	client, err := llmgw.NewClient(llmgw.Options{
		BaseURL:       server.URL,
		AuthMode:      llmgw.AuthInternal,
		InternalToken: "tok",
		UserID:        "user-1",
	})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}

	_, sdkErr := client.GenerateImage(context.Background(), llmgw.GenerateImageRequest{
		Prompt:          "p",
		ModelSource:     llmgw.ModelSourceUser,
		ModelRef:        "00000000-0000-0000-0000-000000000001",
		PollInterval:    1 * time.Millisecond,
		MaxPollInterval: 10 * time.Millisecond,
	})
	if sdkErr == nil {
		t.Fatal("expected SDK error")
	}

	// Feed the REAL *llmgw.Error into writeImageGenError; this exercises
	// the actual errors.Is(real_err, llmgw.ErrImageContentPolicy) path.
	w := httptest.NewRecorder()
	writeImageGenError(w, sdkErr)
	if w.Code != 400 {
		t.Errorf("status = %d, want 400 (real SDK error not matched by writeImageGenError)", w.Code)
	}
	if !strings.Contains(w.Body.String(), "CONTENT_POLICY") {
		t.Errorf("body missing CONTENT_POLICY code; real SDK error didn't match: %s", w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "real SDK content-policy violation") {
		t.Errorf("body missing real SDK error message: %s", w.Body.String())
	}
}

// ── Grep-locks — prevent regressions of the legacy direct-httpx path ──
//
// (CO#3 fix — these live in the SAME file as the migration tests so
// deletion of the lock is co-resistant with deletion of the tests.)

func TestNoLegacyLLMResolutionInMediaGo(t *testing.T) {
	body, err := os.ReadFile("media.go")
	if err != nil {
		t.Fatalf("read media.go: %v", err)
	}
	src := string(body)

	forbidden := []string{
		"/internal/credentials/",
		"/v1/images/generations",
		"creds.ProviderKind",
		"creds.ProviderModelName",
		"creds.BaseURL",
		"creds.APIKey",
	}
	for _, f := range forbidden {
		if strings.Contains(src, f) {
			t.Errorf("media.go must NOT contain %q after 5e-β.1 migration", f)
		}
	}

	required := []string{
		`"github.com/loreweave/llmgw"`,
		"s.llmgw.GenerateImage(",
		"llmgw.ErrImageContentPolicy",
		"writeImageGenError(",
	}
	for _, r := range required {
		if !strings.Contains(src, r) {
			t.Errorf("media.go must contain %q after 5e-β.1 migration", r)
		}
	}
}

// Phase 5e-β.2 — audio.go is now migrated. The Phase 5e-β.1 anti-bait
// (TestAudioGoStillUsesLegacyPath) is deleted; the positive lock lives
// in audio_test.go::TestNoLegacyLLMResolutionInAudioGo.
