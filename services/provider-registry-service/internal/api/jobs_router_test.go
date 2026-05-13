package api

// Phase 2b — router-layer tests for the async LLM job endpoints.
// Mirrors the proxy_router_test.go pattern: validates auth + query
// param + json-body shape errors WITHOUT a real DB pool. The deeper
// path (insert + worker + cancel) is exercised by the live smoke
// test executed manually after rebuild.

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestSubmitLlmJob_RequiresJWT(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/llm/jobs",
		strings.NewReader(`{}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestInternalSubmitLlmJob_RequiresInternalToken(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no internal token: expected 401, got %d", w.Code)
	}
}

func TestInternalSubmitLlmJob_MissingUserID(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs",
		strings.NewReader(`{}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "user_id") {
		t.Errorf("expected user_id mention in body, got %s", w.Body.String())
	}
}

func TestInternalSubmitLlmJob_InvalidUserID(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id=not-a-uuid",
		strings.NewReader(`{}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestInternalSubmitLlmJob_NoJobsSubsystem(t *testing.T) {
	// router-only server has no DB pool → jobsRepo is nil → 503.
	// Phase 5a: caller-input validation runs BEFORE the 503 check, so a
	// fully-valid chat request is needed to exercise the 503 path
	// (anything else would return 400 first). This is intentional —
	// callers learn malformed-input issues immediately, even when the
	// subsystem happens to be down.
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{"operation":"chat","model_source":"user_model","model_ref":"`+uuid.NewString()+`","input":{"messages":[]}}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (no subsystem), got %d body=%s", w.Code, w.Body.String())
	}
}

// ── Phase 5a: tts rejection at submit ─────────────────────────────────

// TestInternalSubmitLlmJob_TtsRejectedAtSubmit pins the Phase 5a contract
// rule: tts is supported ONLY via /v1/llm/stream. Submitting tts via the
// jobs endpoint MUST return 400 with code LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS
// and a hint pointing at the streaming endpoint, BEFORE the subsystem
// availability check (handler-level caller-input validation order).
func TestInternalSubmitLlmJob_TtsRejectedAtSubmit(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "tts",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"text": "hello", "voice": "alloy"}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS, got %d body=%s", w.Code, w.Body.String())
	}
	body := w.Body.String()
	if !strings.Contains(body, "LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS") {
		t.Errorf("expected LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS in body, got %s", body)
	}
	if !strings.Contains(body, "/v1/llm/stream") {
		t.Errorf("expected hint pointing at /v1/llm/stream, got %s", body)
	}
}

// TestInternalSubmitLlmJob_SttAcceptedAtSubmit confirms stt is NOT
// rejected at the handler — it routes to the worker (which then calls
// adapter.Transcribe). With a router-only server (no jobsRepo), a valid
// stt submission progresses past the validation gauntlet to the 503
// service-unavailable check. That's the signal the handler accepted it.
func TestInternalSubmitLlmJob_SttAcceptedAtSubmit(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "stt",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"audio_url": "https://example.com/audio.wav", "language": "en"}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	// stt is valid → progresses past validation → hits 503 (no DB pool in router-only mode).
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (validation-passed, subsystem-not-ready), got %d body=%s", w.Code, w.Body.String())
	}
	if strings.Contains(w.Body.String(), "LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS") {
		t.Errorf("stt MUST NOT be rejected at submit; body=%s", w.Body.String())
	}
}

func TestGetLlmJob_RequiresJWT(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/llm/jobs/"+uuid.NewString(),
		nil,
	)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestCancelLlmJob_RequiresJWT(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodDelete,
		"/v1/llm/jobs/"+uuid.NewString(),
		nil,
	)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestInternalGetLlmJob_InvalidJobID(t *testing.T) {
	// Even with valid auth + user_id, a malformed job_id path param
	// returns 400 LLM_INVALID_REQUEST. We expect 503 here because the
	// router-only server has no jobs subsystem; the validation 400
	// happens AFTER the subsystem check in our handler. This test
	// pins that ordering — change-detector for any future refactor
	// that flips the check order (which would silently mask invalid
	// IDs as 503).
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodGet,
		"/internal/llm/jobs/not-a-uuid?user_id="+uuid.NewString(),
		nil,
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (subsystem-check first), got %d", w.Code)
	}
}
