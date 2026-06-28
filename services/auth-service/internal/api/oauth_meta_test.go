package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/loreweave/auth-service/internal/authjwt/signertest"
	"github.com/loreweave/auth-service/internal/config"
)

func newOAuthTestServer(t *testing.T, enable bool) (*Server, *signertest.LocalRSASigner) {
	t.Helper()
	signer, err := signertest.Generate(2048)
	if err != nil {
		t.Fatal(err)
	}
	srv := &Server{cfg: &config.Config{PublicAppURL: "https://app.loreweave.dev"}}
	if enable {
		srv.EnableOAuth(signer, "loreweave-mcp-oauth", "https://app.loreweave.dev/mcp", 10*time.Minute, 60)
	}
	return srv, signer
}

func TestOAuthJWKS(t *testing.T) {
	srv, signer := newOAuthTestServer(t, true)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	res, err := http.Get(ts.URL + "/oauth/jwks")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status = %d", res.StatusCode)
	}
	var body struct {
		Keys []map[string]any `json:"keys"`
	}
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if len(body.Keys) != 1 {
		t.Fatalf("want 1 key, got %d", len(body.Keys))
	}
	k := body.Keys[0]
	if k["kty"] != "RSA" || k["alg"] != "RS256" || k["use"] != "sig" {
		t.Errorf("bad jwk header fields: %+v", k)
	}
	if k["kid"] != signer.KID() {
		t.Errorf("kid = %v, want %v", k["kid"], signer.KID())
	}
	if k["n"] == "" || k["e"] == "" {
		t.Errorf("n/e missing: %+v", k)
	}
}

func TestOAuthASMetadata(t *testing.T) {
	srv, _ := newOAuthTestServer(t, true)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	res, err := http.Get(ts.URL + "/.well-known/oauth-authorization-server")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status = %d", res.StatusCode)
	}
	var m map[string]any
	if err := json.NewDecoder(res.Body).Decode(&m); err != nil {
		t.Fatal(err)
	}
	if m["issuer"] != "loreweave-mcp-oauth" {
		t.Errorf("issuer = %v", m["issuer"])
	}
	if m["authorization_endpoint"] != "https://app.loreweave.dev/oauth/authorize" {
		t.Errorf("authorization_endpoint = %v", m["authorization_endpoint"])
	}
	if m["token_endpoint"] != "https://app.loreweave.dev/oauth/token" {
		t.Errorf("token_endpoint = %v", m["token_endpoint"])
	}
	if m["jwks_uri"] != "https://app.loreweave.dev/oauth/jwks" {
		t.Errorf("jwks_uri = %v", m["jwks_uri"])
	}
	// PKCE S256 only.
	pkce, _ := m["code_challenge_methods_supported"].([]any)
	if len(pkce) != 1 || pkce[0] != "S256" {
		t.Errorf("code_challenge_methods_supported = %v (want [S256])", m["code_challenge_methods_supported"])
	}
}

func TestOAuthEndpoints_404WhenDisabled(t *testing.T) {
	srv, _ := newOAuthTestServer(t, false)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	for _, p := range []string{"/oauth/jwks", "/.well-known/oauth-authorization-server"} {
		res, err := http.Get(ts.URL + p)
		if err != nil {
			t.Fatal(err)
		}
		res.Body.Close()
		if res.StatusCode != http.StatusNotFound {
			t.Errorf("%s: status = %d, want 404 when oauth disabled", p, res.StatusCode)
		}
	}
}
