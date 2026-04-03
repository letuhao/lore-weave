package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/config"
)

func testServer(secret string) *Server {
	return NewServer(nil, &config.Config{
		JWTSecret:              secret,
		UsageBillingServiceURL: "http://localhost:8086",
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
		t.Fatal("expected auth failure for invalid token")
	}
}

func TestEncryptDecryptSecret(t *testing.T) {
	t.Parallel()

	srv := testServer("12345678901234567890123456789012")
	cipherText, _, err := srv.encryptSecret("my-secret")
	if err != nil {
		t.Fatalf("encrypt secret: %v", err)
	}
	plain, err := srv.decryptSecret(cipherText)
	if err != nil {
		t.Fatalf("decrypt secret: %v", err)
	}
	if plain != "my-secret" {
		t.Fatalf("secret mismatch: got %q", plain)
	}
}

func TestParseUUIDParam(t *testing.T) {
	t.Parallel()

	id := uuid.New()
	req := withRouteParam(httptest.NewRequest(http.MethodGet, "/", nil), "user_model_id", id.String())
	rr := httptest.NewRecorder()
	got, ok := parseUUIDParam(rr, req, "user_model_id")
	if !ok || got != id {
		t.Fatalf("expected uuid parse success, got=%v ok=%v", got, ok)
	}

	badReq := withRouteParam(httptest.NewRequest(http.MethodGet, "/", nil), "user_model_id", "bad")
	badRR := httptest.NewRecorder()
	if _, ok := parseUUIDParam(badRR, badReq, "user_model_id"); ok {
		t.Fatal("expected parse failure for invalid uuid")
	}
	if badRR.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", badRR.Code)
	}
}

func TestCreateProviderCredentialValidation(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)
	userID := uuid.New()

	cases := []struct {
		name       string
		body       map[string]any
		wantStatus int
	}{
		{
			name: "missing provider_kind",
			body: map[string]any{
				"provider_kind": "",
				"display_name":  "x",
			},
			wantStatus: http.StatusBadRequest,
		},
		{
			name: "missing display_name",
			body: map[string]any{
				"provider_kind": "openai",
				"display_name":  "",
			},
			wantStatus: http.StatusBadRequest,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			raw, _ := json.Marshal(tc.body)
			req := httptest.NewRequest(http.MethodPost, "/v1/model-registry/providers", bytes.NewReader(raw))
			req.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))
			rr := httptest.NewRecorder()
			srv.createProviderCredential(rr, req)
			if rr.Code != tc.wantStatus {
				t.Fatalf("expected status %d, got %d", tc.wantStatus, rr.Code)
			}
		})
	}
}

func TestCreateProviderCredentialUnauthorized(t *testing.T) {
	t.Parallel()

	srv := testServer("12345678901234567890123456789012")
	req := httptest.NewRequest(http.MethodPost, "/v1/model-registry/providers", bytes.NewBufferString(`{}`))
	rr := httptest.NewRecorder()
	srv.createProviderCredential(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rr.Code)
	}
}

func TestCreateUserModelValidationWithoutDB(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)
	userID := uuid.New()

	cases := []struct {
		name string
		body string
	}{
		{name: "invalid provider_credential_id", body: `{"provider_credential_id":"bad","provider_model_name":"m1"}`},
		{name: "missing provider_model_name", body: `{"provider_credential_id":"` + uuid.NewString() + `"}`},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			req := httptest.NewRequest(http.MethodPost, "/v1/model-registry/user-models", bytes.NewBufferString(tc.body))
			req.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))
			rr := httptest.NewRecorder()
			srv.createUserModel(rr, req)
			if rr.Code != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d", rr.Code)
			}
		})
	}
}

func TestPatchUserModelBoolFieldMissingFlag(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)
	userID := uuid.New()
	modelID := uuid.New()

	req := httptest.NewRequest(http.MethodPatch, "/v1/model-registry/user-models/"+modelID.String()+"/activation", bytes.NewBufferString(`{}`))
	req = withRouteParam(req, "user_model_id", modelID.String())
	req.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))

	rr := httptest.NewRecorder()
	srv.patchUserModelActivation(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}
}

func TestPlatformModelAdminGuard(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)
	userID := uuid.New()
	req := httptest.NewRequest(http.MethodPost, "/v1/model-registry/platform-models", bytes.NewBufferString(`{}`))
	req.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, "user"))
	rr := httptest.NewRecorder()
	srv.createPlatformModel(rr, req)
	if rr.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", rr.Code)
	}
}

func TestInvokeModelValidationAndUnauthorized(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)
	userID := uuid.New()

	unauthReq := httptest.NewRequest(http.MethodPost, "/v1/model-registry/invoke", bytes.NewBufferString(`{}`))
	unauthRR := httptest.NewRecorder()
	srv.invokeModel(unauthRR, unauthReq)
	if unauthRR.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", unauthRR.Code)
	}

	invalidRefReq := httptest.NewRequest(http.MethodPost, "/v1/model-registry/invoke", bytes.NewBufferString(`{"model_source":"user_model","model_ref":"bad","input":{}}`))
	invalidRefReq.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))
	invalidRefRR := httptest.NewRecorder()
	srv.invokeModel(invalidRefRR, invalidRefReq)
	if invalidRefRR.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid model_ref, got %d", invalidRefRR.Code)
	}

	invalidSourceReq := httptest.NewRequest(http.MethodPost, "/v1/model-registry/invoke", bytes.NewBufferString(`{"model_source":"bad_source","model_ref":"`+uuid.NewString()+`","input":{}}`))
	invalidSourceReq.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))
	invalidSourceRR := httptest.NewRecorder()
	srv.invokeModel(invalidSourceRR, invalidSourceReq)
	if invalidSourceRR.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid model_source, got %d", invalidSourceRR.Code)
	}
}
