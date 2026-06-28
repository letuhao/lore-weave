package api_test

// PG-gated end-to-end OAuth 2.1 auth-code + PKCE flow (P5 slice 2). Gated on
// AUTH_TEST_PG_URL (skips in the normal job). Covers the DoD: register a client →
// consent (downscoped) → code → token (PKCE) → access+refresh → refresh rotation →
// single-use code + one-time refresh enforced.

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/auth-service/internal/api"
	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/authjwt/signertest"
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/migrate"
)

const oauthResource = "https://app.test/mcp"

func oauthFlowServer(t *testing.T) (*api.Server, *pgxpool.Pool, string) {
	t.Helper()
	dsn := os.Getenv("AUTH_TEST_PG_URL")
	if dsn == "" {
		t.Skip("AUTH_TEST_PG_URL not set; skipping PG oauth-flow test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := migrate.Up(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	cfg := &config.Config{JWTSecret: mcpTestSecret, InternalServiceToken: mcpInternalTok, PublicMcpEnabled: true, AccessTokenTTL: time.Hour}
	srv := api.NewServer(pool, cfg)
	signer, err := signertest.Generate(2048)
	if err != nil {
		t.Fatal(err)
	}
	srv.EnableOAuth(signer, api.OAuthOptions{
		Issuer: "loreweave-mcp-oauth", Resource: oauthResource, AccessTTL: time.Hour,
		DefaultRPM: 60, CodeTTL: time.Minute, RefreshTTL: 24 * time.Hour,
		ConsentURL: "https://app.test/oauth/consent",
	})
	return srv, pool, mcpInternalTok
}

func TestOAuthAuthCodeFlow_PG(t *testing.T) {
	srv, pool, itok := oauthFlowServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()
	ctx := context.Background()

	uid := mkUser(t, pool)
	userJWT, err := authjwt.SignAccess([]byte(mcpTestSecret), uid, uuid.New(), time.Hour)
	if err != nil {
		t.Fatal(err)
	}

	// 1) Register a public PKCE client (internal seed; slice 3 makes this public DCR).
	redirectURI := "https://client.test/cb"
	clientID := registerClient(t, ts.URL, itok, redirectURI)

	// 2) PKCE pair.
	verifier := "verifier-0123456789-0123456789-0123456789"
	sum := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(sum[:])

	// 3) Consent (owner JWT) — grant a DOWNSCOPED set (requested read+write_auto, grant read only).
	code := consentForCode(t, ts.URL, userJWT, map[string]any{
		"client_id":             clientID,
		"redirect_uri":          redirectURI,
		"granted_scopes":        []string{"read", "domain:book"},
		"requested_scopes":      []string{"read", "domain:book", "write_auto"},
		"code_challenge":        challenge,
		"code_challenge_method": "S256",
		"resource":              oauthResource,
		"state":                 "xyz",
	})

	// 4) Token exchange (auth-code + PKCE).
	tok := tokenExchange(t, ts.URL, map[string]any{
		"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
		"client_id": clientID, "redirect_uri": redirectURI,
	})
	if tok.AccessToken == "" || tok.RefreshToken == "" {
		t.Fatalf("missing tokens: %+v", tok)
	}
	if tok.Scope != "read domain:book" {
		t.Errorf("scope = %q, want the downscoped set", tok.Scope)
	}
	// access token: sub=uid, aud=resource.
	claims := parseOAuth(t, srv, tok.AccessToken)
	if claims.Subject != uid.String() {
		t.Errorf("sub = %q want %q", claims.Subject, uid.String())
	}

	// 5) Reusing the code fails (single-use).
	reuse := tokenExchangeRaw(t, ts.URL, map[string]any{
		"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "client_id": clientID, "redirect_uri": redirectURI,
	})
	if reuse != http.StatusBadRequest {
		t.Errorf("code reuse status = %d, want 400", reuse)
	}

	// 6) Refresh rotation: the refresh token issues a new pair; the OLD refresh then fails.
	rot := tokenExchange(t, ts.URL, map[string]any{"grant_type": "refresh_token", "refresh_token": tok.RefreshToken, "client_id": clientID})
	if rot.AccessToken == "" || rot.RefreshToken == "" || rot.RefreshToken == tok.RefreshToken {
		t.Fatalf("refresh did not rotate: %+v", rot)
	}
	old := tokenExchangeRaw(t, ts.URL, map[string]any{"grant_type": "refresh_token", "refresh_token": tok.RefreshToken, "client_id": clientID})
	if old != http.StatusBadRequest {
		t.Errorf("old refresh status = %d, want 400 (rotated out)", old)
	}

	// 7) PKCE failure: a fresh code with a WRONG verifier is rejected.
	code2 := consentForCode(t, ts.URL, userJWT, map[string]any{
		"client_id": clientID, "redirect_uri": redirectURI, "granted_scopes": []string{"read"},
		"code_challenge": challenge, "code_challenge_method": "S256", "resource": oauthResource,
	})
	badPkce := tokenExchangeRaw(t, ts.URL, map[string]any{
		"grant_type": "authorization_code", "code": code2, "code_verifier": "WRONG", "client_id": clientID, "redirect_uri": redirectURI,
	})
	if badPkce != http.StatusBadRequest {
		t.Errorf("bad PKCE status = %d, want 400", badPkce)
	}
	_ = ctx
}

// --- helpers ----------------------------------------------------------------

func registerClient(t *testing.T, base, itok, redirectURI string) string {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"client_name": "Test", "redirect_uris": []string{redirectURI}, "scopes_requested": []string{"read", "domain:book"}})
	req, _ := http.NewRequest("POST", base+"/internal/oauth/clients", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", itok)
	res, err := http.DefaultClient.Do(req)
	if err != nil || res.StatusCode != http.StatusCreated {
		t.Fatalf("register client: err=%v status=%v", err, res.StatusCode)
	}
	defer res.Body.Close()
	var out struct {
		ClientID string `json:"client_id"`
	}
	json.NewDecoder(res.Body).Decode(&out)
	if out.ClientID == "" {
		t.Fatal("no client_id")
	}
	return out.ClientID
}

func consentForCode(t *testing.T, base, jwt string, payload map[string]any) string {
	t.Helper()
	body, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", base+"/v1/account/oauth/consent", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+jwt)
	res, err := http.DefaultClient.Do(req)
	if err != nil || res.StatusCode != http.StatusOK {
		t.Fatalf("consent: err=%v status=%v", err, res.StatusCode)
	}
	defer res.Body.Close()
	var out struct {
		RedirectURI string `json:"redirect_uri"`
	}
	json.NewDecoder(res.Body).Decode(&out)
	u, err := url.Parse(out.RedirectURI)
	if err != nil {
		t.Fatalf("parse redirect: %v", err)
	}
	code := u.Query().Get("code")
	if code == "" {
		t.Fatalf("no code in redirect %q", out.RedirectURI)
	}
	return code
}

type oauthTokenResp struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	Scope        string `json:"scope"`
}

func tokenExchange(t *testing.T, base string, payload map[string]any) oauthTokenResp {
	t.Helper()
	body, _ := json.Marshal(payload)
	res, err := http.Post(base+"/oauth/token", "application/json", bytes.NewReader(body))
	if err != nil || res.StatusCode != http.StatusOK {
		t.Fatalf("token: err=%v status=%v", err, res.StatusCode)
	}
	defer res.Body.Close()
	var out oauthTokenResp
	json.NewDecoder(res.Body).Decode(&out)
	return out
}

func tokenExchangeRaw(t *testing.T, base string, payload map[string]any) int {
	t.Helper()
	body, _ := json.Marshal(payload)
	res, err := http.Post(base+"/oauth/token", "application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	res.Body.Close()
	return res.StatusCode
}

func parseOAuth(t *testing.T, srv *api.Server, token string) authjwt.OAuthAccessClaims {
	t.Helper()
	// Parse without re-verifying the signature here (the verifier path is unit-tested
	// on the edge) — decode the payload to assert the claims the AS minted.
	parts := bytes.Split([]byte(token), []byte("."))
	if len(parts) != 3 {
		t.Fatalf("token not a JWT")
	}
	raw, err := base64.RawURLEncoding.DecodeString(string(parts[1]))
	if err != nil {
		t.Fatalf("decode claims: %v", err)
	}
	var c authjwt.OAuthAccessClaims
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatalf("unmarshal claims: %v", err)
	}
	_ = srv
	return c
}
