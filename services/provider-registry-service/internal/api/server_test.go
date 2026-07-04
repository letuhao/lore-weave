package api

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/loreweave/provider-registry-service/internal/config"
)

func testServer(secret string) *Server {
	return NewServer(nil, &config.Config{
		JWTSecret:              secret,
		UsageBillingServiceURL: "http://localhost:8086",
	}, nil, nil)
}

// signedToken mints a platform-USER HS256 token (exp + UUID sub — the shape the
// shared platformjwt verifier requires). The `role` arg is vestigial: the user
// token carries no role (D-JWT-ROLE-GATE) — admin authority is the RS256 admin
// token's job (see newAdminTestServer). Kept in the signature so existing callers
// compile unchanged.
func signedToken(t *testing.T, secret string, userID uuid.UUID, _ string) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   userID.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
	})
	signed, err := token.SignedString([]byte(secret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return signed
}

// newAdminTestServer builds a Server with RS256 admin verification enabled against
// a freshly generated key, plus a mint() that signs admin tokens with the matching
// private key (the same RS256/iss/aud/kid contract auth-service emits). Mirrors
// glossary-service's newAdminTestServer.
func newAdminTestServer(t *testing.T, secret string) (*Server, func(scopes []string) string) {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("genkey: %v", err)
	}
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatalf("marshal pub: %v", err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	srv := NewServer(nil, &config.Config{
		JWTSecret:              secret,
		UsageBillingServiceURL: "http://localhost:8086",
		AdminJWTPublicKeyPEM:   string(pubPEM),
	}, nil, nil)
	if srv.adminPub == nil {
		t.Fatal("admin verification not enabled on the test server")
	}
	kid, err := adminjwt.KeyFingerprint(&priv.PublicKey)
	if err != nil {
		t.Fatalf("fingerprint: %v", err)
	}
	mint := func(scopes []string) string {
		claims := adminjwt.AdminClaims{
			Role:   "admin",
			Scopes: scopes,
			RegisteredClaims: jwt.RegisteredClaims{
				Issuer:    adminjwt.Issuer,
				Audience:  jwt.ClaimStrings{adminjwt.Audience},
				Subject:   uuid.NewString(),
				ID:        uuid.NewString(),
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
			},
		}
		tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
		tok.Header["kid"] = kid
		signed, err := tok.SignedString(priv)
		if err != nil {
			t.Fatalf("sign admin token: %v", err)
		}
		return signed
	}
	return srv, mint
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
	okReq.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))
	gotID, ok := srv.auth(okReq)
	if !ok || gotID != userID {
		t.Fatalf("expected auth success, got id=%v ok=%v", gotID, ok)
	}

	badReq := httptest.NewRequest(http.MethodGet, "/", nil)
	badReq.Header.Set("Authorization", "Bearer invalid")
	if _, ok := srv.auth(badReq); ok {
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

// TestPlatformModelAdminGuard proves the D-JWT-ROLE-GATE fix: the platform-model
// write endpoints are gated by the RS256 admin token (contracts/adminjwt), not the
// dead HS256 `role` claim.
func TestPlatformModelAdminGuard(t *testing.T) {
	t.Parallel()
	secret := "12345678901234567890123456789012"
	userID := uuid.New()
	post := func(srv *Server, authz, body string) int {
		req := httptest.NewRequest(http.MethodPost, "/v1/model-registry/platform-models", bytes.NewBufferString(body))
		if authz != "" {
			req.Header.Set("Authorization", authz)
		}
		rr := httptest.NewRecorder()
		srv.createPlatformModel(rr, req)
		return rr.Code
	}

	// Admin NOT configured → fail closed (503), never reachable by any token.
	if code := post(testServer(secret), "Bearer "+signedToken(t, secret, userID, ""), `{}`); code != http.StatusServiceUnavailable {
		t.Fatalf("admin-unconfigured: expected 503, got %d", code)
	}

	// Admin configured:
	srv, mintAdmin := newAdminTestServer(t, secret)
	// A regular HS256 user token is rejected by the RS256 admin gate → 401.
	if code := post(srv, "Bearer "+signedToken(t, secret, userID, ""), `{}`); code != http.StatusUnauthorized {
		t.Fatalf("user token at admin gate: expected 401, got %d", code)
	}
	// A valid admin token WITHOUT the required scope → 403.
	if code := post(srv, "Bearer "+mintAdmin([]string{"admin:read"}), `{}`); code != http.StatusForbidden {
		t.Fatalf("wrong-scope admin: expected 403, got %d", code)
	}
	// No token → 401.
	if code := post(srv, "", `{}`); code != http.StatusUnauthorized {
		t.Fatalf("no token: expected 401, got %d", code)
	}
	// A valid admin token WITH admin:write PASSES the gate: send an INVALID body so
	// the handler stops at the 400 body-decode AFTER the gate (a nil-pool test server
	// would panic on the INSERT). A 400 proves the gate was passed (not 401/403/503).
	if code := post(srv, "Bearer "+mintAdmin([]string{scopeAdminWrite}), `not-json`); code != http.StatusBadRequest {
		t.Fatalf("valid admin:write must pass the gate → 400 on bad body, got %d", code)
	}
}
