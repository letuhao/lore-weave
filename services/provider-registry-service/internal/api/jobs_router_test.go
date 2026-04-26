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
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{"operation":"chat","model_source":"user_model","model_ref":"`+uuid.NewString()+`","input":{}}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (no subsystem), got %d body=%s", w.Code, w.Body.String())
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
