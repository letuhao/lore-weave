package api_test

// PG-gated contract test for the public MCP credential subsystem (P1).
// Gated on AUTH_TEST_PG_URL (skips in the normal job); point it at a throwaway PG.
// Covers the DoD: create→resolve end-to-end, revoke kills it, deleted account
// invalidates the key (H-L), wrong secret is rejected, and the Q-GATE flag off
// blocks creation.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/auth-service/internal/api"
	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/migrate"
)

const mcpTestSecret = "test-secret-at-least-32-characters-long!"
const mcpInternalTok = "itok-mcp"

func mcpKeysServer(t *testing.T, flagOn bool) (*api.Server, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("AUTH_TEST_PG_URL")
	if dsn == "" {
		t.Skip("AUTH_TEST_PG_URL not set; skipping PG mcp-keys test")
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
	cfg := &config.Config{
		JWTSecret:            mcpTestSecret,
		InternalServiceToken: mcpInternalTok,
		PublicMcpEnabled:     flagOn,
		AccessTokenTTL:       time.Hour,
	}
	return api.NewServer(pool, cfg), pool
}

func mkUser(t *testing.T, pool *pgxpool.Pool) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	email := "mcpkey-" + uuid.NewString() + "@test.local"
	if err := pool.QueryRow(context.Background(),
		`INSERT INTO users (email, password_hash) VALUES ($1, 'x') RETURNING id`, email,
	).Scan(&id); err != nil {
		t.Fatalf("insert user: %v", err)
	}
	return id
}

func bearer(t *testing.T, uid uuid.UUID) string {
	t.Helper()
	tok, err := authjwt.SignAccess([]byte(mcpTestSecret), uid, uuid.New(), time.Hour)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	return tok
}

func doJSON(s *api.Server, method, path, token string, body any) *httptest.ResponseRecorder {
	var buf bytes.Buffer
	if body != nil {
		_ = json.NewEncoder(&buf).Encode(body)
	}
	req := httptest.NewRequest(method, path, &buf)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func resolve(s *api.Server, key string) *httptest.ResponseRecorder {
	var buf bytes.Buffer
	_ = json.NewEncoder(&buf).Encode(map[string]string{"key": key})
	req := httptest.NewRequest(http.MethodPost, "/internal/mcp-keys/resolve", &buf)
	req.Header.Set("X-Internal-Token", mcpInternalTok)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func TestMcpKeys_CreateResolveRevoke_PG(t *testing.T) {
	s, pool := mcpKeysServer(t, true)
	uid := mkUser(t, pool)
	tok := bearer(t, uid)

	// Create → 201 + full secret once.
	rr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys", tok, map[string]any{"name": "my-agent"})
	if rr.Code != http.StatusCreated {
		t.Fatalf("create: got %d body=%s", rr.Code, rr.Body.String())
	}
	var created struct {
		KeyID string `json:"key_id"`
		Key   string `json:"key"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &created); err != nil || created.Key == "" {
		t.Fatalf("create body: %v %s", err, rr.Body.String())
	}

	// Resolve → 200, owner matches.
	rr = resolve(s, created.Key)
	if rr.Code != http.StatusOK {
		t.Fatalf("resolve: got %d body=%s", rr.Code, rr.Body.String())
	}
	var res struct {
		UserID string `json:"user_id"`
		KeyID  string `json:"key_id"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &res)
	if res.UserID != uid.String() {
		t.Fatalf("resolved user %s, want %s", res.UserID, uid)
	}

	// Wrong secret (same-ish prefix, bad body) → 401.
	if rr := resolve(s, created.Key+"tampered"); rr.Code != http.StatusUnauthorized {
		t.Fatalf("tampered resolve: got %d, want 401", rr.Code)
	}

	// List shows it (no secret).
	rr = doJSON(s, http.MethodGet, "/v1/account/mcp-keys", tok, nil)
	if rr.Code != http.StatusOK || !bytes.Contains(rr.Body.Bytes(), []byte(created.KeyID)) {
		t.Fatalf("list: %d %s", rr.Code, rr.Body.String())
	}
	if bytes.Contains(rr.Body.Bytes(), []byte("key_hash")) || bytes.Contains(rr.Body.Bytes(), []byte(created.Key)) {
		t.Fatal("list leaked secret/hash material")
	}

	// Revoke → 204, then resolve fails.
	if rr := doJSON(s, http.MethodDelete, "/v1/account/mcp-keys/"+created.KeyID, tok, nil); rr.Code != http.StatusNoContent {
		t.Fatalf("revoke: got %d", rr.Code)
	}
	if rr := resolve(s, created.Key); rr.Code != http.StatusUnauthorized {
		t.Fatalf("resolve after revoke: got %d, want 401", rr.Code)
	}
}

func TestMcpKeys_PatchUpdatesMetadata_PG(t *testing.T) {
	// Owner edits a key's safe metadata (name / rate limit / spend cap / expiry)
	// without revoking + re-creating. Scope/secret are untouched; the resolve path
	// must reflect the new limits, and expiry can be both SET and CLEARED (tri-state).
	s, pool := mcpKeysServer(t, true)
	uid := mkUser(t, pool)
	tok := bearer(t, uid)

	rr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys", tok,
		map[string]any{"name": "before", "rate_limit_rpm": 60})
	var created struct {
		KeyID string `json:"key_id"`
		Key   string `json:"key"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &created)

	// PATCH name + rate limit + spend cap + a future expiry.
	future := time.Now().Add(24 * time.Hour).UTC().Format(time.RFC3339)
	rr = doJSON(s, http.MethodPatch, "/v1/account/mcp-keys/"+created.KeyID, tok, map[string]any{
		"name": "after", "rate_limit_rpm": 120, "spend_cap_usd": 5.5, "expires_at": future,
	})
	if rr.Code != http.StatusOK {
		t.Fatalf("patch: got %d body=%s", rr.Code, rr.Body.String())
	}
	var view struct {
		Name         string   `json:"name"`
		RateLimitRPM int      `json:"rate_limit_rpm"`
		SpendCapUSD  *float64 `json:"spend_cap_usd"`
		ExpiresAt    *string  `json:"expires_at"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &view); err != nil {
		t.Fatalf("patch body: %v %s", err, rr.Body.String())
	}
	if view.Name != "after" || view.RateLimitRPM != 120 || view.SpendCapUSD == nil || *view.SpendCapUSD != 5.5 || view.ExpiresAt == nil {
		t.Fatalf("patch did not apply: %+v", view)
	}
	// The resolve hot path reflects the new rate limit (proves it persisted, not just echoed).
	rr = resolve(s, created.Key)
	if rr.Code != http.StatusOK {
		t.Fatalf("resolve after patch: %d", rr.Code)
	}
	var res struct {
		RateLimitRPM int `json:"rate_limit_rpm"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &res)
	if res.RateLimitRPM != 120 {
		t.Fatalf("resolved rate_limit_rpm = %d, want 120", res.RateLimitRPM)
	}

	// Clear the expiry ("" ⇒ NULL) AND the spend cap (null ⇒ no cap); the key must
	// still resolve and report neither. spend_cap is sent as an explicit JSON null.
	rr = doJSON(s, http.MethodPatch, "/v1/account/mcp-keys/"+created.KeyID, tok,
		map[string]any{"expires_at": "", "spend_cap_usd": nil})
	_ = json.Unmarshal(rr.Body.Bytes(), &view)
	if rr.Code != http.StatusOK || view.ExpiresAt != nil || view.SpendCapUSD != nil {
		t.Fatalf("clear expiry/cap: got %d expires=%v cap=%v", rr.Code, view.ExpiresAt, view.SpendCapUSD)
	}
	// A bare PATCH (name only) must NOT disturb the now-cleared cap (absent ≠ null).
	rr = doJSON(s, http.MethodPatch, "/v1/account/mcp-keys/"+created.KeyID, tok,
		map[string]any{"name": "renamed"})
	_ = json.Unmarshal(rr.Body.Bytes(), &view)
	if rr.Code != http.StatusOK || view.SpendCapUSD != nil {
		t.Fatalf("name-only patch disturbed cap: got %d cap=%v", rr.Code, view.SpendCapUSD)
	}

	// A bad expires_at is rejected; another user's key 404s (owner-scoped).
	if rr := doJSON(s, http.MethodPatch, "/v1/account/mcp-keys/"+created.KeyID, tok,
		map[string]any{"expires_at": "not-a-date"}); rr.Code != http.StatusBadRequest {
		t.Fatalf("bad expires_at: got %d, want 400", rr.Code)
	}
	other := bearer(t, mkUser(t, pool))
	if rr := doJSON(s, http.MethodPatch, "/v1/account/mcp-keys/"+created.KeyID, other,
		map[string]any{"name": "hijack"}); rr.Code != http.StatusNotFound {
		t.Fatalf("cross-owner patch: got %d, want 404", rr.Code)
	}
}

func TestMcpKeys_DeletedAccountInvalidatesKey_PG(t *testing.T) {
	s, pool := mcpKeysServer(t, true)
	uid := mkUser(t, pool)
	tok := bearer(t, uid)

	rr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys", tok, map[string]any{"name": "k"})
	var created struct {
		Key string `json:"key"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &created)
	if rr := resolve(s, created.Key); rr.Code != http.StatusOK {
		t.Fatalf("pre-deactivate resolve: %d", rr.Code)
	}
	// H-L: a suspended/deleted owner's key resolves to nothing.
	if _, err := pool.Exec(context.Background(),
		`UPDATE users SET account_status='deleted' WHERE id=$1`, uid); err != nil {
		t.Fatalf("deactivate: %v", err)
	}
	if rr := resolve(s, created.Key); rr.Code != http.StatusUnauthorized {
		t.Fatalf("resolve after account delete: got %d, want 401 (H-L)", rr.Code)
	}
}

func TestMcpKeys_NegativeSpendCapRejected_PG(t *testing.T) {
	s, pool := mcpKeysServer(t, true)
	uid := mkUser(t, pool)
	tok := bearer(t, uid)
	rr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys", tok,
		map[string]any{"name": "k", "spend_cap_usd": -1})
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("negative spend_cap: got %d, want 400", rr.Code)
	}
}

func TestMcpKeys_ResolveRateLimited_PG(t *testing.T) {
	// H-H end-to-end: hammering one prefix with a wrong secret hits 429 BEFORE the
	// per-attempt Argon2 verify can run unbounded — proving the cap is wired at the
	// endpoint (not just the limiter primitive).
	s, pool := mcpKeysServer(t, true)
	uid := mkUser(t, pool)
	tok := bearer(t, uid)
	rr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys", tok, map[string]any{"name": "k"})
	var created struct {
		Key string `json:"key"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &created)
	// Same 12-char prefix, wrong body → forces a verify attempt each time.
	bad := created.Key[:len(created.Key)-4] + "ZZZZ"
	saw429 := false
	for range 40 {
		if resolve(s, bad).Code == http.StatusTooManyRequests {
			saw429 = true
			break
		}
	}
	if !saw429 {
		t.Fatal("expected a 429 after repeated wrong-secret attempts on one prefix (H-H)")
	}
}

func TestMcpKeys_FlagOffBlocksCreate_PG(t *testing.T) {
	s, pool := mcpKeysServer(t, false)
	uid := mkUser(t, pool)
	tok := bearer(t, uid)
	rr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys", tok, map[string]any{"name": "k"})
	if rr.Code != http.StatusForbidden {
		t.Fatalf("create with flag off: got %d, want 403", rr.Code)
	}
}

// The FE reads public_mcp_enabled off the profile to decide whether to show the
// MCP-access tab. Guard that contract both ways so a refactor can't silently drop
// the field (which would hide the tab forever with nothing red).
func TestProfile_ReflectsPublicMcpFlag_PG(t *testing.T) {
	for _, flagOn := range []bool{true, false} {
		s, pool := mcpKeysServer(t, flagOn)
		uid := mkUser(t, pool)
		tok := bearer(t, uid)
		rr := doJSON(s, http.MethodGet, "/v1/account/profile", tok, nil)
		if rr.Code != http.StatusOK {
			t.Fatalf("profile (flag=%v): got %d body=%s", flagOn, rr.Code, rr.Body.String())
		}
		var body struct {
			PublicMcpEnabled bool `json:"public_mcp_enabled"`
		}
		if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
			t.Fatalf("profile body (flag=%v): %v %s", flagOn, err, rr.Body.String())
		}
		if body.PublicMcpEnabled != flagOn {
			t.Fatalf("profile public_mcp_enabled = %v, want %v", body.PublicMcpEnabled, flagOn)
		}
	}
}
