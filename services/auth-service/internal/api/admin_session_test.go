package api

// Browser-facing admin-session exchange (admin CMS): a logged-in admin principal
// self-mints an RS256 admin JWT from their HS256 user token. Proves: an admin gets
// a verifiable admin token carrying their role/scopes; a non-admin user → 403; no
// token → 401; disabled → 404. No live PG (fake store + in-process signer).

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/adminjwt"

	"github.com/loreweave/auth-service/internal/adminprincipal"
	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/authjwt/signertest"
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/ratelimit"
)

const sessionTestSecret = "admin_session_test_secret_32_chars_min!!"

func postBearer(t *testing.T, ts *httptest.Server, path, bearer string) *http.Response {
	t.Helper()
	req, _ := http.NewRequest(http.MethodPost, ts.URL+path, nil)
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	return resp
}

func newSessionTestServer(t *testing.T) (*Server, *fakeStore, *signertest.LocalRSASigner) {
	t.Helper()
	signer, err := signertest.Generate(2048)
	if err != nil {
		t.Fatalf("generate signer: %v", err)
	}
	store := &fakeStore{principals: map[uuid.UUID]adminprincipal.Principal{}}
	srv := &Server{cfg: &config.Config{JWTSecret: sessionTestSecret}, secret: []byte(sessionTestSecret), rl: ratelimit.New(time.Minute, 1000)}
	srv.EnableAdminIssuance(signer, store, testIssuerSecret, testHMACKey, 15*time.Minute)
	return srv, store, signer
}

func TestAdminSession_Exchange(t *testing.T) {
	srv, store, signer := newSessionTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	// An active admin principal exchanges their user token for an admin token.
	uid := uuid.New()
	addPrincipal(store, uid, "admin", []string{"admin:read", "admin:write"}, true)
	userTok, err := authjwt.SignAccess([]byte(sessionTestSecret), uid, uuid.New(), time.Hour)
	if err != nil {
		t.Fatalf("sign user token: %v", err)
	}
	resp := postBearer(t, ts, "/v1/admin/session", userTok)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("admin exchange: status = %d, want 200", resp.StatusCode)
	}
	var out adminSessionResp
	_ = json.NewDecoder(resp.Body).Decode(&out)
	resp.Body.Close()
	claims, err := adminjwt.Verify(out.Token, signer.PublicKey(), signer.KID())
	if err != nil {
		t.Fatalf("issued admin token failed verify: %v", err)
	}
	if claims.Subject != uid.String() || claims.Role != "admin" {
		t.Fatalf("unexpected claims: %+v", claims)
	}
	hasWrite := false
	for _, sc := range claims.Scopes {
		if sc == "admin:write" {
			hasWrite = true
		}
	}
	if !hasWrite {
		t.Fatalf("token missing admin:write scope: %v", claims.Scopes)
	}

	// A logged-in NON-admin user → 403 (authority comes only from admin_principals).
	other := uuid.New()
	otherTok, _ := authjwt.SignAccess([]byte(sessionTestSecret), other, uuid.New(), time.Hour)
	r403 := postBearer(t, ts, "/v1/admin/session", otherTok)
	if r403.StatusCode != http.StatusForbidden {
		t.Fatalf("non-admin: status = %d, want 403", r403.StatusCode)
	}
	r403.Body.Close()

	// No token → 401.
	r401 := postBearer(t, ts, "/v1/admin/session", "")
	if r401.StatusCode != http.StatusUnauthorized {
		t.Fatalf("no token: status = %d, want 401", r401.StatusCode)
	}
	r401.Body.Close()

	// An inactive admin principal → 403.
	inactive := uuid.New()
	addPrincipal(store, inactive, "admin", []string{"admin:write"}, false)
	inactiveTok, _ := authjwt.SignAccess([]byte(sessionTestSecret), inactive, uuid.New(), time.Hour)
	rInactive := postBearer(t, ts, "/v1/admin/session", inactiveTok)
	if rInactive.StatusCode != http.StatusForbidden {
		t.Fatalf("inactive admin: status = %d, want 403", rInactive.StatusCode)
	}
	rInactive.Body.Close()
}

func TestAdminSession_DisabledIs404(t *testing.T) {
	srv := &Server{cfg: &config.Config{JWTSecret: sessionTestSecret}, secret: []byte(sessionTestSecret), rl: ratelimit.New(time.Minute, 1000)}
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()
	tok, _ := authjwt.SignAccess([]byte(sessionTestSecret), uuid.New(), uuid.New(), time.Hour)
	resp := postBearer(t, ts, "/v1/admin/session", tok)
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("disabled: status = %d, want 404", resp.StatusCode)
	}
	resp.Body.Close()
}
