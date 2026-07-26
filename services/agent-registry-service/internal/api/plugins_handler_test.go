package api

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"

	"github.com/loreweave/foundation/contracts/adminjwt"
)

// mintJWT builds a plain platform-USER HS256 token (exp + UUID sub — the shape the
// shared platformjwt verifier requires). The `role` arg is vestigial: the user token
// carries no role (D-JWT-ROLE-GATE) — admin authority is the RS256 admin token's job
// (see newMockAdminServer). Kept in the signature so existing callers compile unchanged.
func mintJWT(t *testing.T, sub, _ string) string {
	t.Helper()
	claims := jwt.RegisteredClaims{
		Subject:   sub,
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	}
	tok, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(testCfg().JWTSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return tok
}

func newMockServer(t *testing.T) (*Server, pgxmock.PgxPoolIface) {
	t.Helper()
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock: %v", err)
	}
	return NewServer(mock, testCfg()), mock
}

// newMockAdminServer builds a mock-DB Server with RS256 admin verification enabled
// against a freshly generated key, plus a mint() that signs admin tokens with the
// matching private key (the same RS256/iss/aud/kid contract auth-service emits).
// Mirrors provider-registry's newAdminTestServer + glossary's g7 admin-test shape.
func newMockAdminServer(t *testing.T) (*Server, pgxmock.PgxPoolIface, func(scopes []string) string) {
	t.Helper()
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock: %v", err)
	}
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("genkey: %v", err)
	}
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatalf("marshal pub: %v", err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	cfg := testCfg()
	cfg.AdminJWTPublicKeyPEM = string(pubPEM)
	srv := NewServer(mock, cfg)
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
				Subject:   adminSub,
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
	return srv, mock, mint
}

func doJSON(s *Server, method, path, token, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	s.Router().ServeHTTP(rec, req)
	return rec
}

func TestCreatePlugin_Unauthenticated(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/plugins", "", `{"name":"io.x/y"}`)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", rec.Code)
	}
}

func TestCreatePlugin_InvalidName(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	tok := mintJWT(t, uuid.NewString(), "")
	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/plugins", tok, `{"name":"NOT VALID"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d (%s)", rec.Code, rec.Body.String())
	}
	var e errorBody
	_ = json.Unmarshal(rec.Body.Bytes(), &e)
	if e.Code != "VALIDATION_ERROR" {
		t.Fatalf("want VALIDATION_ERROR, got %q", e.Code)
	}
}

// TestCreatePlugin_SystemTierRequiresAdmin proves the D-JWT-ROLE-GATE fix: a System-tier
// create is gated by the RS256 admin token (contracts/adminjwt), not the dead HS256 `role`
// claim. The createPlugin handler runs requireUser (HS256) FIRST, so a regular user token
// reaches the tier=system branch and is rejected by requireAdminScope — 503 when the admin
// key is unconfigured (fail closed), 401 when it is configured (an HS256 user token never
// satisfies the RS256 admin verifier). Either way a normal user can never create a System row.
func TestCreatePlugin_SystemTierRequiresAdmin(t *testing.T) {
	// Admin NOT configured → fail closed (503), never reachable by any token. No DB op.
	s, mock := newMockServer(t)
	defer mock.Close()
	tok := mintJWT(t, uuid.NewString(), "") // regular user
	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/plugins", tok, `{"name":"io.x/y","tier":"system"}`)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("admin-unconfigured system create → want 503, got %d (%s)", rec.Code, rec.Body.String())
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unexpected DB calls (unconfigured): %v", err)
	}

	// Admin configured → a regular HS256 user token is rejected by the RS256 admin gate (401),
	// still before any DB op. (A pure RS256 admin token can't even pass requireUser here — the
	// admin-authored System write path is the ingest route, covered in ingest_test.go.)
	sa, amock, _ := newMockAdminServer(t)
	defer amock.Close()
	rec = doJSON(sa, http.MethodPost, "/v1/agent-registry/plugins", mintJWT(t, uuid.NewString(), ""), `{"name":"io.x/y","tier":"system"}`)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("user token at admin gate → want 401, got %d (%s)", rec.Code, rec.Body.String())
	}
	if err := amock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unexpected DB calls (configured): %v", err)
	}
}

// With no BOOK_SERVICE_INTERNAL_URL (grants==nil), a book-tier write is refused
// 501 — book-tier requires the grant client (D-REG-BOOK-GRANT, fail-closed). The
// grant-wired path (404/503) is covered by the live governance smoke.
func TestCreatePlugin_BookTierRequiresGrantClient(t *testing.T) {
	s, mock := newMockServer(t) // testCfg has no BookServiceInternalURL → grants nil
	defer mock.Close()
	tok := mintJWT(t, uuid.NewString(), "")
	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/plugins", tok, `{"name":"io.x/y","tier":"book","book_id":"`+uuid.NewString()+`"}`)
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("want 501 (no grant client), got %d", rec.Code)
	}
}

func TestEffectiveCatalog_RequiresInternalToken(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	req := httptest.NewRequest(http.MethodGet, "/internal/effective-catalog?user_id="+uuid.NewString(), nil)
	rec := httptest.NewRecorder()
	s.Router().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("want 401 without internal token, got %d", rec.Code)
	}
}
