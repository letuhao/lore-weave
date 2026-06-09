package api

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/loreweave/auth-service/internal/config"
)

func TestRegisterDisabledWhenPublicRegistrationOff(t *testing.T) {
	cfg := &config.Config{
		JWTSecret:                 "test-jwt-secret-at-least-32-characters-long",
		InternalServiceToken:      "test-internal-token-for-routes",
		AllowPublicRegistration:   false,
		PasswordMinLength:         8,
	}
	s := NewServer(nil, cfg)
	handler := s.Router()

	req := httptest.NewRequest(http.MethodPost, "/v1/auth/register", bytes.NewBufferString(`{"email":"a@b.co","password":"Test1234!"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", rec.Code)
	}
}
