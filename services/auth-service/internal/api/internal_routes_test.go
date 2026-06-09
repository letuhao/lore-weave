package api

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/loreweave/auth-service/internal/config"
)

func TestInternalRoutesRequireToken(t *testing.T) {
	cfg := &config.Config{
		JWTSecret:            "test-jwt-secret-at-least-32-characters-long",
		InternalServiceToken: "test-internal-token-for-routes",
	}
	s := NewServer(nil, cfg)
	handler := s.Router()

	t.Run("missing token", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/internal/users/00000000-0000-0000-0000-000000000001/profile", nil)
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized {
			t.Fatalf("expected 401, got %d", rec.Code)
		}
	})

	t.Run("wrong token", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/internal/users/00000000-0000-0000-0000-000000000001/profile", nil)
		req.Header.Set("X-Internal-Token", "wrong-token")
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized {
			t.Fatalf("expected 401, got %d", rec.Code)
		}
	})

	t.Run("valid token passes middleware", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/internal/users/00000000-0000-0000-0000-000000000001/profile", nil)
		req.Header.Set("X-Internal-Token", "test-internal-token-for-routes")
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		// Without DB pool handler returns 500/404 — not 401.
		if rec.Code == http.StatusUnauthorized {
			t.Fatalf("valid token should not return 401, got %d", rec.Code)
		}
	})
}
