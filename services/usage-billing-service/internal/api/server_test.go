package api

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/usage-billing-service/internal/config"
)

func testServer(secret string) *Server {
	return NewServer(nil, &config.Config{
		JWTSecret: secret,
	})
}

func signedToken(t *testing.T, secret string, userID uuid.UUID, role string) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, accessClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID.String(),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
		},
		Role: role,
	})
	signed, err := token.SignedString([]byte(secret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return signed
}

func withRouteParam(req *http.Request, key, value string) *http.Request {
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add(key, value)
	return req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
}

func TestAuthSuccessAndFailure(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	userID := uuid.New()
	srv := testServer(secret)

	okReq := httptest.NewRequest(http.MethodGet, "/", nil)
	okReq.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, "admin"))
	gotID, gotRole, ok := srv.auth(okReq)
	if !ok || gotID != userID || gotRole != "admin" {
		t.Fatalf("expected auth success, got id=%v role=%s ok=%v", gotID, gotRole, ok)
	}

	badReq := httptest.NewRequest(http.MethodGet, "/", nil)
	badReq.Header.Set("Authorization", "Bearer invalid")
	if _, _, ok := srv.auth(badReq); ok {
		t.Fatal("expected auth failure")
	}
}

func TestParseIntDefault(t *testing.T) {
	t.Parallel()

	if got := parseIntDefault("", 20, 1, 100); got != 20 {
		t.Fatalf("expected default 20, got %d", got)
	}
	if got := parseIntDefault("5", 20, 1, 100); got != 5 {
		t.Fatalf("expected parsed 5, got %d", got)
	}
	if got := parseIntDefault("-1", 20, 1, 100); got != 1 {
		t.Fatalf("expected min clamp 1, got %d", got)
	}
	if got := parseIntDefault("200", 20, 1, 100); got != 100 {
		t.Fatalf("expected max clamp 100, got %d", got)
	}
}

type fakeScanner struct {
	values []any
	err    error
}

func (f fakeScanner) Scan(dest ...any) error {
	if f.err != nil {
		return f.err
	}
	for i := range dest {
		switch d := dest[i].(type) {
		case *uuid.UUID:
			*d = f.values[i].(uuid.UUID)
		case *string:
			*d = f.values[i].(string)
		case *int:
			*d = f.values[i].(int)
		case *float64:
			*d = f.values[i].(float64)
		case *time.Time:
			*d = f.values[i].(time.Time)
		default:
			return errors.New("unsupported dest type")
		}
	}
	return nil
}

func TestScanUsageLogRow(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	vals := []any{
		uuid.New(), uuid.New(), uuid.New(), "openai", "user_model", uuid.New(),
		1, 2, 3, 0.1, "quota", "success", "m03-v1", "in", "out", "kref", "AES-256-GCM", 1, now,
	}
	row, err := scanUsageLogRow(fakeScanner{values: vals})
	if err != nil {
		t.Fatalf("scanUsageLogRow failed: %v", err)
	}
	if row["billing_decision"] != "quota" {
		t.Fatalf("unexpected billing_decision: %v", row["billing_decision"])
	}
	if row["total_tokens"] != 3 {
		t.Fatalf("unexpected total_tokens: %v", row["total_tokens"])
	}
}

func TestRecordInvocationValidation(t *testing.T) {
	t.Parallel()

	srv := testServer("12345678901234567890123456789012")
	req := httptest.NewRequest(http.MethodPost, "/internal/model-billing/record", bytes.NewBufferString(`{"request_id":"bad"}`))
	rr := httptest.NewRecorder()
	srv.recordInvocation(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}

	req2 := httptest.NewRequest(http.MethodPost, "/internal/model-billing/record", bytes.NewBufferString(`{"request_id":"`+uuid.NewString()+`","owner_user_id":"`+uuid.NewString()+`","model_ref":"00000000-0000-0000-0000-000000000000"}`))
	rr2 := httptest.NewRecorder()
	srv.recordInvocation(rr2, req2)
	if rr2.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for nil model_ref, got %d", rr2.Code)
	}
}

func TestUsageHandlersUnauthorizedAndForbidden(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)
	userID := uuid.New()

	listReq := httptest.NewRequest(http.MethodGet, "/v1/model-billing/usage-logs", nil)
	listRR := httptest.NewRecorder()
	srv.listUsageLogs(listRR, listReq)
	if listRR.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", listRR.Code)
	}

	adminReq := httptest.NewRequest(http.MethodGet, "/v1/model-billing/admin/usage", nil)
	adminReq.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, "user"))
	adminRR := httptest.NewRecorder()
	srv.adminListUsage(adminRR, adminReq)
	if adminRR.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", adminRR.Code)
	}

	reconReq := httptest.NewRequest(http.MethodPost, "/v1/model-billing/admin/reconciliation", bytes.NewBufferString(`{}`))
	reconReq.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, "user"))
	reconRR := httptest.NewRecorder()
	srv.createReconciliation(reconRR, reconReq)
	if reconRR.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", reconRR.Code)
	}
}

func TestGetUsageLogDetailValidation(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)
	userID := uuid.New()

	req := httptest.NewRequest(http.MethodGet, "/v1/model-billing/usage-logs/bad", nil)
	req = withRouteParam(req, "usage_log_id", "bad")
	req.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))
	rr := httptest.NewRecorder()
	srv.getUsageLogDetail(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}
}
