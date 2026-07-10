package api

import (
	"bytes"
	"context"
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/loreweave/provider-registry-service/internal/config"
	"github.com/loreweave/provider-registry-service/internal/migrate"
)

// ── always-run unit tests (no DB) ──────────────────────────────────────────────

const mcpTestInternalToken = "settings-mcp-internal-token-aaaaaaaa"
const mcpTestJWTSecret = "settings-mcp-jwt-secret-32-chars-001"

// mcpTestConfirmSecret is the DEDICATED confirm-token signing secret (key-split
// from JWTSecret) — distinct so a test relying on the wrong key would fail.
const mcpTestConfirmSecret = "settings-mcp-confirm-secret-32-chr-1"

func mcpUnitServer() *Server {
	return &Server{cfg: &config.Config{InternalServiceToken: mcpTestInternalToken, JWTSecret: mcpTestJWTSecret}}
}

// callMCP fires a JSON-RPC request at the settings /mcp handler with the given
// envelope headers and returns the decoded response envelope.
func callMCP(t *testing.T, ts *httptest.Server, internalToken, userID, method string, params any) (map[string]any, int) {
	t.Helper()
	reqBody := map[string]any{"jsonrpc": "2.0", "id": 1, "method": method}
	if params != nil {
		reqBody["params"] = params
	}
	b, _ := json.Marshal(reqBody)
	req, _ := http.NewRequest(http.MethodPost, ts.URL, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	if internalToken != "" {
		req.Header.Set(lwmcp.HeaderInternalToken, internalToken)
	}
	if userID != "" {
		req.Header.Set(lwmcp.HeaderUserID, userID)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer resp.Body.Close()
	var out map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&out)
	return out, resp.StatusCode
}

func TestSettingsMCP_RejectsMissingOrWrongToken(t *testing.T) {
	ts := httptest.NewServer(mcpUnitServer().mcpHandler())
	defer ts.Close()
	if _, code := callMCP(t, ts, "", uuid.NewString(), "tools/list", nil); code != http.StatusUnauthorized {
		t.Fatalf("missing token must be 401, got %d", code)
	}
	if _, code := callMCP(t, ts, "wrong", uuid.NewString(), "tools/list", nil); code != http.StatusUnauthorized {
		t.Fatalf("wrong token must be 401, got %d", code)
	}
}

// listTools returns the tools[] array from a tools/list call.
func listTools(t *testing.T, ts *httptest.Server) []map[string]any {
	t.Helper()
	out, code := callMCP(t, ts, mcpTestInternalToken, uuid.NewString(), "tools/list", nil)
	if code != http.StatusOK {
		t.Fatalf("tools/list status %d: %v", code, out)
	}
	result, _ := out["result"].(map[string]any)
	raw, _ := result["tools"].([]any)
	tools := make([]map[string]any, 0, len(raw))
	for _, r := range raw {
		if m, ok := r.(map[string]any); ok {
			tools = append(tools, m)
		}
	}
	if len(tools) == 0 {
		t.Fatalf("expected tools, got none: %v", out)
	}
	return tools
}

// allowedSettingsPrefixes MIRRORS ai-gateway's `EXTRA_PREFIX_MAP.settings` (+ the base
// `settings_` from PROVIDER_PREFIX). The C-GW gate drops-and-WARNS any federated tool whose
// name matches none of its provider's prefixes — it does not error — so a drift here is
// silent: the tool simply vanishes from the catalog (exactly how `story_search` was once
// lost). A Go test cannot import the TS map, so this is a hand-synced mirror. Adding a tool
// under a NEW namespace on this server means updating BOTH this slice and
// services/ai-gateway/src/config/config.ts.
var allowedSettingsPrefixes = []string{
	"settings_", // the provider's base namespace
	"web_",      // Track D CD5 — the universal `web_search` lives on provider-registry
}

// Every tool on the settings server MUST carry C-TOOL _meta.tier + _meta.scope, and its
// name MUST start with one of the prefixes the gateway allows for this provider (C-GW).
func TestSettingsMCP_EveryToolHasTierScopeAndPrefix(t *testing.T) {
	ts := httptest.NewServer(mcpUnitServer().mcpHandler())
	defer ts.Close()
	tools := listTools(t, ts)
	// 5 Tier-R reads + 6 Tier-A + 1 Tier-W + 1 Tier-R paid (web_search) = 13.
	// provider_create/update_secret are deliberately NOT tools (OD-S1).
	if len(tools) != 13 {
		t.Errorf("expected 13 settings tools, got %d", len(tools))
	}
	for _, tool := range tools {
		name, _ := tool["name"].(string)
		matched := false
		for _, p := range allowedSettingsPrefixes {
			if strings.HasPrefix(name, p) {
				matched = true
				break
			}
		}
		if !matched {
			t.Errorf("tool %q matches none of the gateway's allowed prefixes %v — the C-GW gate "+
				"would silently DROP it from the federated catalog", name, allowedSettingsPrefixes)
		}
		meta, _ := tool["_meta"].(map[string]any)
		if meta == nil {
			t.Errorf("tool %q has no _meta", name)
			continue
		}
		tier, _ := meta[lwmcp.MetaKeyTier].(string)
		switch lwmcp.Tier(tier) {
		case lwmcp.TierR, lwmcp.TierA, lwmcp.TierW, lwmcp.TierS:
		default:
			t.Errorf("tool %q _meta.tier invalid: %q", name, tier)
		}
		scope, _ := meta[lwmcp.MetaKeyScope].(string)
		if lwmcp.Scope(scope) != lwmcp.ScopeUser {
			t.Errorf("tool %q _meta.scope must be user (settings is user-scoped), got %q", name, scope)
		}
	}
}

// web_search is the platform's only PAID tool on this server. The two properties below are
// the ones consumers actually branch on, and they are ORTHOGONAL: `paid` governs money
// (chat's spend gate), `tier` governs mutation (ask-mode + the approval card). A paid READ
// stays Tier R — promoting it to A/W would wrongly block it in ask mode, and dropping
// `paid` would let a model spend the user's money with no consent prompt.
func TestSettingsMCP_WebSearchIsPaidTierR(t *testing.T) {
	ts := httptest.NewServer(mcpUnitServer().mcpHandler())
	defer ts.Close()

	var found map[string]any
	for _, tool := range listTools(t, ts) {
		if name, _ := tool["name"].(string); name == "web_search" {
			found = tool
			break
		}
	}
	if found == nil {
		t.Fatal("web_search is not registered on the settings MCP server")
	}
	meta, _ := found["_meta"].(map[string]any)
	if meta == nil {
		t.Fatal("web_search has no _meta")
	}
	if tier, _ := meta[lwmcp.MetaKeyTier].(string); lwmcp.Tier(tier) != lwmcp.TierR {
		t.Errorf("web_search _meta.tier = %q, want R (it writes nothing; paid ⊥ tier)", tier)
	}
	if paid, _ := meta[lwmcp.MetaKeyPaid].(bool); !paid {
		t.Error("web_search _meta.paid is not true — chat's spend gate would never prompt, " +
			"letting a model spend the user's money without consent")
	}
}

// OD-S1 / SEC-1: NO settings tool may accept a raw secret as an argument — a secret
// must never be an LLM-visible tool arg. Scan every tool's input schema for a
// property whose name looks like a secret (secret, api_key, password, token,
// ciphertext). model_register deliberately has no secret arg; provider_create /
// provider_update_secret are not registered at all.
func TestSettingsMCP_NoToolAcceptsRawSecret(t *testing.T) {
	ts := httptest.NewServer(mcpUnitServer().mcpHandler())
	defer ts.Close()
	banned := []string{"secret", "api_key", "apikey", "password", "passwd", "token", "ciphertext", "credential_secret", "private_key"}
	// confirm_token is the Tier-W flow's bearer token, NOT a provider secret — but
	// note no settings TOOL even takes confirm_token (that's a frontend tool); so the
	// banned list can stay strict.
	for _, tool := range listTools(t, ts) {
		name, _ := tool["name"].(string)
		schema, _ := tool["inputSchema"].(map[string]any)
		props, _ := schema["properties"].(map[string]any)
		for prop := range props {
			lower := strings.ToLower(prop)
			for _, b := range banned {
				if strings.Contains(lower, b) {
					t.Errorf("tool %q exposes a secret-like arg %q (OD-S1: a secret must never be an LLM-visible tool argument)", name, prop)
				}
			}
		}
	}
	// Also assert the two secret-ingesting operations are NOT tools.
	for _, tool := range listTools(t, ts) {
		name, _ := tool["name"].(string)
		if name == "settings_provider_create" || name == "settings_provider_update_secret" ||
			name == "provider_create" || name == "provider_update_secret" {
			t.Errorf("%q must NOT be a tool (OD-S1 — route to UI via ui_navigate instead)", name)
		}
	}
}

// The Tier-W model_delete confirm token: mint→verify happy path, plus expired and
// forged are refused. Uses the kit directly (deterministic, no DB) — the same spine
// the confirm route runs.
func TestSettingsMCP_ConfirmTokenRoundTrip(t *testing.T) {
	secret := mcpTestJWTSecret
	uid := uuid.New()
	resID := uuid.New()

	tok, err := lwmcp.MintConfirmToken(secret, uid, resID, settingsConfirmDescriptor, map[string]any{"user_model_id": resID.String()}, settingsConfirmTTL)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	claims, err := lwmcp.VerifyConfirmToken(secret, tok)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if claims.UserID != uid || claims.ResourceID != resID || claims.Descriptor != settingsConfirmDescriptor {
		t.Fatalf("claims mismatch: %+v", claims)
	}

	// Forged: wrong secret must NOT verify.
	if _, err := lwmcp.VerifyConfirmToken("a-different-secret-also-32-chars-xx", tok); err == nil {
		t.Fatal("a token signed with a different secret must be rejected")
	}

	// Expired: a negative TTL is already past expiry.
	expiredTok, _ := lwmcp.MintConfirmToken(secret, uid, resID, settingsConfirmDescriptor, nil, -1*time.Minute)
	if _, err := lwmcp.VerifyConfirmToken(secret, expiredTok); err == nil {
		t.Fatal("an expired token must be rejected")
	}
}

// undoHintForProfile must restore exactly the fields a patch touched (C-ACTIVITY
// Tier-A undo). A patch of display_name yields an undo restoring the prior
// display_name only.
func TestSettingsMCP_UndoHintForProfile(t *testing.T) {
	before := json.RawMessage(`{"display_name":"Old Name","locale":"en","bio":"old bio"}`)
	patch := map[string]any{"display_name": "New Name"}
	hint := undoHintForProfile(before, patch)
	if hint["tool"] != "settings_update_profile" {
		t.Fatalf("undo tool: %v", hint["tool"])
	}
	args, _ := hint["args"].(map[string]any)
	if args["display_name"] != "Old Name" {
		t.Fatalf("undo must restore prior display_name, got %v", args["display_name"])
	}
	if _, leaked := args["locale"]; leaked {
		t.Fatal("undo must only restore the field the patch changed")
	}
}

// ── DB-gated behavioral tests (skipped without TEST_PROVIDER_REGISTRY_DB_URL) ───

// mcpDBServer builds a real-pool server + a live /mcp httptest server.
func mcpDBServer(t *testing.T) (*Server, *pgxpool.Pool, *httptest.Server) {
	t.Helper()
	dsn := os.Getenv("TEST_PROVIDER_REGISTRY_DB_URL")
	if dsn == "" {
		t.Skip("TEST_PROVIDER_REGISTRY_DB_URL unset — skipping settings MCP DB test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New: %v", err)
	}
	if err := migrate.Up(ctx, pool); err != nil {
		pool.Close()
		t.Fatalf("migrate.Up: %v", err)
	}
	srv := NewServer(pool, &config.Config{
		JWTSecret:                 mcpTestJWTSecret,
		ConfirmTokenSigningSecret: mcpTestConfirmSecret,
		InternalServiceToken:      mcpTestInternalToken,
		// UsageBillingServiceURL not required for these paths; NewServer needs a
		// non-nil cfg only.
		UsageBillingServiceURL: "http://localhost:8086",
	}, nil, nil)
	ts := httptest.NewServer(srv.mcpHandler())
	t.Cleanup(func() { ts.Close(); pool.Close() })
	return srv, pool, ts
}

// seedCredAndModel inserts a provider_credentials row (with an ENCRYPTED secret)
// and a user_models row for userID. Returns (credID, modelID). Cleaned up after.
func seedCredAndModel(t *testing.T, srv *Server, pool *pgxpool.Pool, userID uuid.UUID, plaintextSecret string) (uuid.UUID, uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	cipher, _, err := srv.encryptSecret(plaintextSecret)
	if err != nil {
		t.Fatalf("encryptSecret: %v", err)
	}
	var credID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO provider_credentials (owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, status)
VALUES ($1,'openai','test-cred','http://up',$2,'active') RETURNING provider_credential_id`,
		userID, cipher).Scan(&credID); err != nil {
		t.Fatalf("seed cred: %v", err)
	}
	var modelID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO user_models (owner_user_id, provider_credential_id, provider_kind, provider_model_name, is_active)
VALUES ($1,$2,'openai','gpt-4o',true) RETURNING user_model_id`,
		userID, credID).Scan(&modelID); err != nil {
		t.Fatalf("seed model: %v", err)
	}
	t.Cleanup(func() {
		bg := context.Background()
		_, _ = pool.Exec(bg, `DELETE FROM user_models WHERE provider_credential_id=$1`, credID)
		_, _ = pool.Exec(bg, `DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credID)
	})
	return credID, modelID
}

// callTool fires a tools/call for the named tool as userID; returns the raw JSON
// of the response (result + any error).
func callTool(t *testing.T, ts *httptest.Server, userID, tool string, args map[string]any) (map[string]any, int) {
	t.Helper()
	params := map[string]any{"name": tool}
	if args != nil {
		params["arguments"] = args
	}
	return callMCP(t, ts, mcpTestInternalToken, userID, "tools/call", params)
}

// HEADLINE TEST (H13): a known credential's secret must NEVER appear in any read
// tool's output. We seed a credential whose plaintext secret is a unique sentinel,
// then assert the sentinel is absent from settings_list_providers and
// settings_list_models output (the whole serialized response).
func TestSettingsMCP_SecretRedaction(t *testing.T) {
	srv, pool, ts := mcpDBServer(t)
	const sentinel = "sk-SUPER-SECRET-sentinel-DO-NOT-LEAK-9f3a"
	userID := uuid.New()
	credID, _ := seedCredAndModel(t, srv, pool, userID, sentinel)

	for _, tc := range []struct {
		tool string
		args map[string]any
	}{
		{"settings_list_providers", nil},
		{"settings_list_models", nil},
		{"settings_provider_inventory", map[string]any{"provider_credential_id": credID.String()}},
	} {
		out, code := callTool(t, ts, userID.String(), tc.tool, tc.args)
		if code != http.StatusOK {
			t.Fatalf("%s status %d: %v", tc.tool, code, out)
		}
		blob, _ := json.Marshal(out)
		if strings.Contains(string(blob), sentinel) {
			t.Fatalf("%s LEAKED the credential secret in its output", tc.tool)
		}
		// also assert has_secret boolean is exposed (truthful) for providers
		if tc.tool == "settings_list_providers" && !strings.Contains(string(blob), "has_secret") {
			t.Errorf("settings_list_providers should expose has_secret boolean")
		}
	}
}

// User-scope isolation (SEC-2/H13): user A cannot read or mutate user B's model.
func TestSettingsMCP_UserScopeIsolation(t *testing.T) {
	srv, pool, ts := mcpDBServer(t)
	userA := uuid.New()
	userB := uuid.New()
	_, modelB := seedCredAndModel(t, srv, pool, userB, "secret-b")

	// A lists models → must NOT see B's model.
	out, code := callTool(t, ts, userA.String(), "settings_list_models", nil)
	if code != http.StatusOK {
		t.Fatalf("list status %d", code)
	}
	if strings.Contains(mustJSON(out), modelB.String()) {
		t.Fatal("user A saw user B's model in settings_list_models")
	}

	// A tries to favorite B's model → must be refused (not accessible / isError).
	out, _ = callTool(t, ts, userA.String(), "settings_model_set_favorite", map[string]any{"user_model_id": modelB.String(), "value": true})
	if !toolIsError(out) {
		t.Fatalf("user A mutating user B's model must error, got %v", out)
	}
	// And B's model is unchanged (still not favorite).
	var fav bool
	_ = pool.QueryRow(context.Background(), `SELECT is_favorite FROM user_models WHERE user_model_id=$1`, modelB).Scan(&fav)
	if fav {
		t.Fatal("user A's cross-tenant mutation actually changed user B's model")
	}
}

// Tier-W confirm round-trip: settings_model_delete mints a token; the confirm route
// deletes; a replay and a forged token are both refused.
func TestSettingsMCP_ModelDeleteConfirmRoundTrip(t *testing.T) {
	srv, pool, ts := mcpDBServer(t)
	userID := uuid.New()
	_, modelID := seedCredAndModel(t, srv, pool, userID, "secret-d")

	// 1. Tier-W tool mints a confirm token (does NOT delete).
	out, code := callTool(t, ts, userID.String(), "settings_model_delete", map[string]any{"user_model_id": modelID.String()})
	if code != http.StatusOK || toolIsError(out) {
		t.Fatalf("model_delete mint failed: %v", out)
	}
	token := extractStructured(t, out, "confirm_token")
	if token == "" {
		t.Fatalf("no confirm_token in result: %v", out)
	}
	// Model still present (mint did not delete).
	var n int
	_ = pool.QueryRow(context.Background(), `SELECT count(*) FROM user_models WHERE user_model_id=$1`, modelID).Scan(&n)
	if n != 1 {
		t.Fatal("mint must NOT delete the model")
	}

	// 2. Confirm via the JWT-gated route → deletes.
	confirmStatus := postConfirm(t, srv, userID, token)
	if confirmStatus != http.StatusNoContent {
		t.Fatalf("confirm expected 204, got %d", confirmStatus)
	}
	_ = pool.QueryRow(context.Background(), `SELECT count(*) FROM user_models WHERE user_model_id=$1`, modelID).Scan(&n)
	if n != 0 {
		t.Fatal("confirm must delete the model")
	}

	// 3. Replay the same token → refused (single-use).
	if code := postConfirm(t, srv, userID, token); code == http.StatusNoContent {
		t.Fatal("a replayed confirm token must be refused")
	}

	// 4. Forged token → refused.
	forged, _ := lwmcp.MintConfirmToken("not-the-real-secret-but-32-chars-xx", userID, modelID, settingsConfirmDescriptor, nil, settingsConfirmTTL)
	if code := postConfirm(t, srv, userID, forged); code == http.StatusNoContent {
		t.Fatal("a forged confirm token must be refused")
	}
}

// Cross-user confirm rejection: user A mints a model_delete confirm token, then
// user B (a different signed-in user) POSTs it to the confirm route. The
// claims.UserID != userID check (settings_actions.go) fires BEFORE the single-use
// ledger consume, so B gets a 403 AND cannot burn A's token — A can still confirm.
func TestSettingsMCP_ModelDeleteConfirmCrossUserRejected(t *testing.T) {
	srv, pool, ts := mcpDBServer(t)
	userA := uuid.New()
	userB := uuid.New()
	_, modelID := seedCredAndModel(t, srv, pool, userA, "secret-x")

	// A mints a confirm token (does NOT delete).
	out, code := callTool(t, ts, userA.String(), "settings_model_delete", map[string]any{"user_model_id": modelID.String()})
	if code != http.StatusOK || toolIsError(out) {
		t.Fatalf("model_delete mint failed: %v", out)
	}
	token := extractStructured(t, out, "confirm_token")
	if token == "" {
		t.Fatalf("no confirm_token in result: %v", out)
	}

	// B posts A's token → 403 (bound to the proposer), checked before consume.
	if code := postConfirmAs(t, srv, userB, token); code != http.StatusForbidden {
		t.Fatalf("cross-user confirm expected 403, got %d", code)
	}
	// B's attempt did NOT burn the token AND did NOT delete A's model.
	var n int
	_ = pool.QueryRow(context.Background(), `SELECT count(*) FROM user_models WHERE user_model_id=$1`, modelID).Scan(&n)
	if n != 1 {
		t.Fatal("cross-user confirm must not delete the proposer's model")
	}
	// A can still confirm its own token (not consumed by B's rejected attempt).
	if code := postConfirmAs(t, srv, userA, token); code != http.StatusNoContent {
		t.Fatalf("proposer confirm after rejected cross-user attempt expected 204, got %d", code)
	}
}

// postConfirm drives the JWT-gated /v1/settings/actions/confirm handler directly.
func postConfirm(t *testing.T, srv *Server, userID uuid.UUID, token string) int {
	return postConfirmAs(t, srv, userID, token)
}

// postConfirmAs is postConfirm with an explicit JWT-bearer user (used to drive the
// cross-user path: the bearer user differs from the token's proposer).
func postConfirmAs(t *testing.T, srv *Server, bearerUser uuid.UUID, token string) int {
	t.Helper()
	body, _ := json.Marshal(map[string]string{"confirm_token": token})
	req := httptest.NewRequest(http.MethodPost, "/v1/settings/actions/confirm", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+signedToken(t, mcpTestJWTSecret, bearerUser, "user"))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.confirmSettingsAction(rec, req)
	return rec.Code
}

// postConfirmViaInternalEnvelope drives confirmSettingsAction exactly the way
// auth-service's public-MCP confirm-replay does (mcp_approvals.go::replayConfirm):
// query-param token, nil body, X-Internal-Token+X-User-Id, NO Authorization
// header. Found live 2026-07-08: this route 401'd that shape unconditionally
// before resolveConfirmCaller (D-PMCP-WORKER-CARRIER retrofit).
func postConfirmViaInternalEnvelope(srv *Server, internalTok, userID, token string) int {
	req := httptest.NewRequest(http.MethodPost, "/v1/settings/actions/confirm?token="+token, nil)
	if internalTok != "" {
		req.Header.Set("X-Internal-Token", internalTok)
	}
	if userID != "" {
		req.Header.Set("X-User-Id", userID)
	}
	rec := httptest.NewRecorder()
	srv.confirmSettingsAction(rec, req)
	return rec.Code
}

// TestSettingsMCP_ModelDeleteConfirmInternalReplayEnvelope proves the retrofit:
// auth-service's confirm-replay shape (no Bearer JWT at all) now succeeds, and
// still fails closed on a wrong/missing/malformed internal envelope.
func TestSettingsMCP_ModelDeleteConfirmInternalReplayEnvelope(t *testing.T) {
	srv, pool, ts := mcpDBServer(t)
	userID := uuid.New()
	_, modelID := seedCredAndModel(t, srv, pool, userID, "secret-e")

	out, code := callTool(t, ts, userID.String(), "settings_model_delete", map[string]any{"user_model_id": modelID.String()})
	if code != http.StatusOK || toolIsError(out) {
		t.Fatalf("model_delete mint failed: %v", out)
	}
	token := extractStructured(t, out, "confirm_token")
	if token == "" {
		t.Fatalf("no confirm_token in result: %v", out)
	}

	if code := postConfirmViaInternalEnvelope(srv, mcpTestInternalToken, userID.String(), token); code != http.StatusNoContent {
		t.Fatalf("internal-envelope confirm-replay expected 204, got %d", code)
	}
	var n int
	_ = pool.QueryRow(context.Background(), `SELECT count(*) FROM user_models WHERE user_model_id=$1`, modelID).Scan(&n)
	if n != 0 {
		t.Fatal("internal-envelope confirm must delete the model")
	}

	// resolveConfirmCaller rejects before the token is ever decoded/consumed, so
	// the negative cases below can reuse the already-consumed token — only the
	// envelope itself is under test here.
	if code := postConfirmViaInternalEnvelope(srv, "wrong-token", userID.String(), token); code == http.StatusNoContent {
		t.Fatal("wrong internal token must not be accepted")
	}
	if code := postConfirmViaInternalEnvelope(srv, mcpTestInternalToken, "", token); code == http.StatusNoContent {
		t.Fatal("internal token with no X-User-Id must not be accepted")
	}
	if code := postConfirmViaInternalEnvelope(srv, mcpTestInternalToken, "not-a-uuid", token); code == http.StatusNoContent {
		t.Fatal("internal token with malformed X-User-Id must not be accepted")
	}
	// Correct internal token, SYNTACTICALLY-valid X-User-Id naming a DIFFERENT user
	// than the token's bound proposer → still 403: resolveConfirmCaller resolves the
	// (wrong) caller successfully via the envelope path, but decodeSettingsConfirm's
	// claims.UserID != userID check fires identically regardless of which auth path
	// produced userID. That check runs BEFORE consumeSettingsToken, so the
	// already-consumed token above is still usable here (its signature/claims are
	// unaffected by consumption) — mirrors glossary's
	// TestConfirmAction_InternalReplayEnvelope_WrongOrMissingCredsRejected.
	if code := postConfirmViaInternalEnvelope(srv, mcpTestInternalToken, uuid.New().String(), token); code != http.StatusForbidden {
		t.Errorf("internal envelope naming a different user than the proposer = %d, want 403", code)
	}
}

// ── small helpers ──────────────────────────────────────────────────────────────

func mustJSON(v any) string {
	b, _ := json.Marshal(v)
	return string(b)
}

// toolIsError reports whether a tools/call response is an error (JSON-RPC error OR
// an isError tool result).
func toolIsError(out map[string]any) bool {
	if _, ok := out["error"]; ok {
		return true
	}
	result, _ := out["result"].(map[string]any)
	if result == nil {
		return false
	}
	if isErr, _ := result["isError"].(bool); isErr {
		return true
	}
	return false
}

// extractStructured pulls a string field out of a tools/call structuredContent
// result (the typed output object).
func extractStructured(t *testing.T, out map[string]any, field string) string {
	t.Helper()
	result, _ := out["result"].(map[string]any)
	if result == nil {
		return ""
	}
	if sc, ok := result["structuredContent"].(map[string]any); ok {
		if v, ok := sc[field].(string); ok {
			return v
		}
	}
	return ""
}

// TestSettingsMCP_NoOutStructUsesRawMessage — the bug class that made
// settings_get_profile and settings_update_profile fail 100% of calls, for every user,
// from the day they were written.
//
// `json.RawMessage` is `[]byte`. The MCP Go SDK infers its output schema as
// `["null","array"]`, but `encoding/json` marshals it as the raw JSON it HOLDS — an
// object. The SDK then validates the tool's own output against its own declared schema
// and rejects the call:
//
//	validating /properties/profile: type: map[...] has type "object", want one of "null, array"
//
// Nothing caught it: every wire gate asserts over `tools/list` METADATA and never issues a
// `tools/call`, and no NL probe covered these tools. A deterministic capability sweep
// (scripts/eval/tool_liveness/sweep.py) found it by simply calling every Tier-R tool.
//
// NOTE this asserts on the TYPE, not the schema. A genuine Go slice (`[]webSearchSource`)
// also declares `["null","array"]` — and correctly marshals as an array. The schema shape
// cannot tell the two apart; the field's Go type can.
func TestSettingsMCP_NoOutStructUsesRawMessage(t *testing.T) {
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, "mcp_server.go", nil, 0)
	if err != nil {
		t.Fatalf("parse mcp_server.go: %v", err)
	}
	checked := 0
	ast.Inspect(f, func(n ast.Node) bool {
		ts, ok := n.(*ast.TypeSpec)
		if !ok || !strings.HasSuffix(ts.Name.Name, "Out") {
			return true
		}
		st, ok := ts.Type.(*ast.StructType)
		if !ok {
			return true
		}
		checked++
		for _, field := range st.Fields.List {
			sel, ok := field.Type.(*ast.SelectorExpr)
			if !ok {
				continue
			}
			pkg, _ := sel.X.(*ast.Ident)
			if pkg != nil && pkg.Name == "json" && sel.Sel.Name == "RawMessage" {
				name := "<embedded>"
				if len(field.Names) > 0 {
					name = field.Names[0].Name
				}
				t.Errorf("%s.%s is json.RawMessage — the SDK declares it ['null','array'] but "+
					"marshals the object it holds, so the tool's OWN output fails validation and "+
					"every call errors. Use map[string]any (see profileObject).", ts.Name.Name, name)
			}
		}
		return true
	})
	if checked == 0 {
		t.Fatal("found no *Out structs to check — this gate is inert")
	}
	t.Logf("checked %d MCP Out structs", checked)
}
