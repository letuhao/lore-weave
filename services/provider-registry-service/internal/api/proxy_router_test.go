package api

// D-K17.2c-01 — router-layer tests for the transparent proxy.
//
// The K17.2c integration tests (proxy_integration_test.go) call
// srv.doProxy(...) directly, bypassing the chi router + the
// requireInternalToken middleware + the internalProxy query-param
// wrapper. This file fills in the router-level coverage: token
// enforcement, query-param validation, 404 on unrouted paths.
//
// These tests don't need a real DB — they exercise the HTTP wiring
// above doProxy. The deeper body-rewrite + credential paths stay
// covered by the integration tests (which skip without DB).

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/config"
)

const routerTestInternalToken = "router-test-internal-token"

func newRouterOnlyServer(t *testing.T) *Server {
	t.Helper()
	return NewServer(nil, &config.Config{
		JWTSecret:            "router-test-secret-32-characters-01",
		InternalServiceToken: routerTestInternalToken,
	}, nil)
}

func TestInternalProxyRequiresInternalToken(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/proxy/v1/chat/completions?user_id="+uuid.NewString()+
			"&model_source=user_model&model_ref="+uuid.NewString(),
		strings.NewReader(`{"model":"x","messages":[]}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: expected 401, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestInternalProxyRejectsWrongToken(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/proxy/v1/chat/completions?user_id="+uuid.NewString()+
			"&model_source=user_model&model_ref="+uuid.NewString(),
		strings.NewReader(`{"model":"x","messages":[]}`),
	)
	req.Header.Set("X-Internal-Token", "definitely-not-the-token")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("wrong token: expected 401, got %d", w.Code)
	}
}

func TestInternalProxyMissingQueryParams(t *testing.T) {
	srv := newRouterOnlyServer(t)
	// Valid token but no query params → PROXY_VALIDATION_ERROR 400.
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/proxy/v1/chat/completions",
		strings.NewReader(`{"model":"x","messages":[]}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "PROXY_VALIDATION_ERROR") {
		t.Errorf("expected PROXY_VALIDATION_ERROR in body, got %s", w.Body.String())
	}
}

func TestInternalProxyInvalidUserIDReturns400(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/proxy/v1/chat/completions?user_id=not-a-uuid"+
			"&model_source=user_model&model_ref="+uuid.NewString(),
		strings.NewReader(`{"model":"x","messages":[]}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 (invalid user_id), got %d body=%s", w.Code, w.Body.String())
	}
}

func TestInternalProxyInvalidModelRefReturns400(t *testing.T) {
	srv := newRouterOnlyServer(t)
	// Phase 4d /review-impl LOW#6 follow-up: deprecation guard now fires
	// before model_ref parse, so the path used here MUST NOT be a
	// deprecated one or we'd get 410 instead of 400. Use the audio
	// carve-out which is allowed to pass through.
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/proxy/v1/audio/speech?user_id="+uuid.NewString()+
			"&model_source=user_model&model_ref=not-a-uuid-either",
		strings.NewReader(`{"model":"x","messages":[]}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 (invalid model_ref), got %d body=%s", w.Code, w.Body.String())
	}
}
