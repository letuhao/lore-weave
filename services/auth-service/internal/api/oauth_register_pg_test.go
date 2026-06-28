package api_test

// PG-gated open Dynamic Client Registration (RFC 7591, P5 slice 3). Gated on
// AUTH_TEST_PG_URL. Covers the DoD: register a public PKCE client (no secret) →
// usable in the slice-2 flow; flag-off → 403; bad redirect_uri → 400; per-IP
// rate-limit → 429; an audit row is written.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/auth-service/internal/api"
	"github.com/loreweave/auth-service/internal/authjwt/signertest"
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/migrate"
)

func oauthRegisterServer(t *testing.T, dcrEnabled bool, ratePerHour int) (*api.Server, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("AUTH_TEST_PG_URL")
	if dsn == "" {
		t.Skip("AUTH_TEST_PG_URL not set; skipping PG oauth-register test")
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
		DCREnabled: dcrEnabled, DCRRatePerHour: ratePerHour,
	})
	return srv, pool
}

func registerPublic(t *testing.T, base string, payload map[string]any) (*http.Response, map[string]any) {
	t.Helper()
	body, _ := json.Marshal(payload)
	res, err := http.Post(base+"/oauth/register", "application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatalf("register: %v", err)
	}
	var out map[string]any
	json.NewDecoder(res.Body).Decode(&out)
	res.Body.Close()
	return res, out
}

func TestOAuthDCR_PG(t *testing.T) {
	srv, pool := oauthRegisterServer(t, true, 100)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()
	ctx := context.Background()

	redirectURI := "https://client.test/cb"

	// Happy path → 201, a client_id, NO secret, public PKCE method.
	res, out := registerPublic(t, ts.URL, map[string]any{
		"client_name":      "Self-served Bot",
		"redirect_uris":    []string{redirectURI},
		"scopes_requested": []string{"read", "domain:book"},
	})
	if res.StatusCode != http.StatusCreated {
		t.Fatalf("register status = %d, want 201", res.StatusCode)
	}
	clientID, _ := out["client_id"].(string)
	if clientID == "" {
		t.Fatalf("no client_id in %v", out)
	}
	if _, hasSecret := out["client_secret"]; hasSecret {
		t.Error("a PUBLIC PKCE client must not be issued a secret")
	}
	if out["token_endpoint_auth_method"] != "none" {
		t.Errorf("auth method = %v, want none", out["token_endpoint_auth_method"])
	}

	// The client is persisted active and usable by the slice-2 flow.
	var status string
	if err := pool.QueryRow(ctx, `SELECT status FROM mcp_oauth_clients WHERE client_id=$1`, clientID).Scan(&status); err != nil {
		t.Fatalf("client not persisted: %v", err)
	}
	if status != "active" {
		t.Errorf("client status = %q, want active", status)
	}

	// An audit row was written for the issued client.
	var auditOutcome string
	if err := pool.QueryRow(ctx,
		`SELECT outcome FROM mcp_oauth_client_registrations WHERE client_id=$1`, clientID,
	).Scan(&auditOutcome); err != nil {
		t.Fatalf("no audit row for %s: %v", clientID, err)
	}
	if auditOutcome != "registered" {
		t.Errorf("audit outcome = %q, want registered", auditOutcome)
	}

	// Bad redirect_uri → 400 invalid_redirect_uri (+ a 'rejected' audit row).
	bad, badOut := registerPublic(t, ts.URL, map[string]any{
		"client_name":   "Bad",
		"redirect_uris": []string{"https://app/cb#frag"},
	})
	if bad.StatusCode != http.StatusBadRequest || badOut["error"] != "invalid_redirect_uri" {
		t.Errorf("bad redirect: status=%d err=%v, want 400 invalid_redirect_uri", bad.StatusCode, badOut["error"])
	}
	var rejected int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM mcp_oauth_client_registrations WHERE outcome='rejected' AND reason='invalid_redirect_uri'`,
	).Scan(&rejected); err != nil || rejected == 0 {
		t.Errorf("expected a rejected audit row, got count=%d err=%v", rejected, err)
	}

	// Empty redirect_uris → 400.
	empty, _ := registerPublic(t, ts.URL, map[string]any{"client_name": "NoRedirect"})
	if empty.StatusCode != http.StatusBadRequest {
		t.Errorf("empty redirect_uris status = %d, want 400", empty.StatusCode)
	}

	// Too many redirect_uris → 400 invalid_redirect_uri (input-cap, DoS guard).
	many := make([]string, 11)
	for i := range many {
		many[i] = "https://client.test/cb"
	}
	tooMany, tmOut := registerPublic(t, ts.URL, map[string]any{"client_name": "Many", "redirect_uris": many})
	if tooMany.StatusCode != http.StatusBadRequest || tmOut["error"] != "invalid_redirect_uri" {
		t.Errorf("too many redirect_uris: status=%d err=%v, want 400 invalid_redirect_uri", tooMany.StatusCode, tmOut["error"])
	}

	// Over-long client_name → 400 invalid_client_metadata (input-cap).
	longName := make([]byte, 300)
	for i := range longName {
		longName[i] = 'a'
	}
	tooLong, tlOut := registerPublic(t, ts.URL, map[string]any{"client_name": string(longName), "redirect_uris": []string{redirectURI}})
	if tooLong.StatusCode != http.StatusBadRequest || tlOut["error"] != "invalid_client_metadata" {
		t.Errorf("long client_name: status=%d err=%v, want 400 invalid_client_metadata", tooLong.StatusCode, tlOut["error"])
	}
}

func TestOAuthDCR_FlagOff_PG(t *testing.T) {
	srv, _ := oauthRegisterServer(t, false, 100) // DCR disabled
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()
	res, out := registerPublic(t, ts.URL, map[string]any{
		"client_name": "X", "redirect_uris": []string{"https://client.test/cb"},
	})
	if res.StatusCode != http.StatusForbidden || out["error"] != "registration_disabled" {
		t.Errorf("flag-off: status=%d err=%v, want 403 registration_disabled", res.StatusCode, out["error"])
	}
}

func TestOAuthDCR_RateLimit_PG(t *testing.T) {
	srv, _ := oauthRegisterServer(t, true, 2) // 2 per hour per IP
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()
	payload := map[string]any{"client_name": "RL", "redirect_uris": []string{"https://client.test/cb"}}
	// First two succeed (201), the third is rate-limited (429).
	for i := 0; i < 2; i++ {
		res, _ := registerPublic(t, ts.URL, payload)
		if res.StatusCode != http.StatusCreated {
			t.Fatalf("call %d status = %d, want 201", i+1, res.StatusCode)
		}
	}
	res, out := registerPublic(t, ts.URL, payload)
	if res.StatusCode != http.StatusTooManyRequests || out["error"] != "rate_limited" {
		t.Errorf("3rd call: status=%d err=%v, want 429 rate_limited", res.StatusCode, out["error"])
	}
}
