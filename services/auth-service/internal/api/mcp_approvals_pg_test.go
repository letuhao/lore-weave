package api_test

// PG-gated contract test for the public MCP human-approval queue (P4 / OD-2).
// Reuses the mcp_keys_pg_test.go harness (mkUser/bearer/doJSON) + a local server
// builder that wires a STUB domain confirm endpoint so the approve-execute replay
// (including the X-Mcp-Key-Id attribution header) is verifiable end-to-end.
// Gated on AUTH_TEST_PG_URL.

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
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/migrate"
)

// approvalsServer builds an auth Server whose composition confirm route points at the
// supplied stub URL (so approve-execute is exercisable without a real domain service).
func approvalsServer(t *testing.T, compositionURL string) (*api.Server, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("AUTH_TEST_PG_URL")
	if dsn == "" {
		t.Skip("AUTH_TEST_PG_URL not set; skipping PG approvals test")
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
		JWTSecret:                mcpTestSecret,
		InternalServiceToken:     mcpInternalTok,
		PublicMcpEnabled:         true,
		AccessTokenTTL:           time.Hour,
		DomainConfirmServiceURLs: map[string]string{"composition": compositionURL},
	}
	return api.NewServer(pool, cfg), pool
}

func createApproval(s *api.Server, body any) *httptest.ResponseRecorder {
	var buf bytes.Buffer
	_ = json.NewEncoder(&buf).Encode(body)
	req := httptest.NewRequest(http.MethodPost, "/internal/mcp-keys/approvals", &buf)
	req.Header.Set("X-Internal-Token", mcpInternalTok)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func TestMcpApprovals_CreateListApproveDeny_PG(t *testing.T) {
	// Stub composition confirm endpoint — records the attribution headers, returns OK.
	var gotKeyID, gotUserID, gotCap, gotInternal string
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotKeyID = r.Header.Get("X-Mcp-Key-Id")
		gotUserID = r.Header.Get("X-User-Id")
		gotCap = r.Header.Get("X-Mcp-Spend-Cap-Usd")
		gotInternal = r.Header.Get("X-Internal-Token")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"outcome":"action_done"}`))
	}))
	defer stub.Close()

	s, pool := approvalsServer(t, stub.URL)
	uid := mkUser(t, pool)
	tok := bearer(t, uid)

	// A capped key to attribute the executed spend to.
	kr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys", tok, map[string]any{"name": "agent", "spend_cap_usd": 9})
	if kr.Code != http.StatusCreated {
		t.Fatalf("create key: %d %s", kr.Code, kr.Body.String())
	}
	var key struct {
		KeyID string `json:"key_id"`
	}
	_ = json.Unmarshal(kr.Body.Bytes(), &key)

	// Divert a propose into the queue (internal-token).
	cr := createApproval(s, map[string]any{
		"key_id": key.KeyID, "owner_user_id": uid.String(),
		"tool_name": "composition_generate", "domain": "composition",
		"confirm_token": "tok-secret", "preview": map[string]any{"title": "Generate scene"},
		"cost_estimate_usd": 0.5,
	})
	if cr.Code != http.StatusCreated {
		t.Fatalf("create approval: %d %s", cr.Code, cr.Body.String())
	}
	var created struct {
		ApprovalID string `json:"approval_id"`
	}
	_ = json.Unmarshal(cr.Body.Bytes(), &created)
	if created.ApprovalID == "" {
		t.Fatalf("no approval_id: %s", cr.Body.String())
	}

	// Internal-token required for create.
	noTok := httptest.NewRequest(http.MethodPost, "/internal/mcp-keys/approvals", bytes.NewBufferString("{}"))
	nr := httptest.NewRecorder()
	s.Router().ServeHTTP(nr, noTok)
	if nr.Code != http.StatusUnauthorized {
		t.Fatalf("create without internal token: expected 401, got %d", nr.Code)
	}

	// Owner lists pending — 1 row, and it must NOT echo the confirm token.
	lr := doJSON(s, http.MethodGet, "/v1/account/mcp-keys/approvals?status=pending", tok, nil)
	if lr.Code != http.StatusOK {
		t.Fatalf("list: %d %s", lr.Code, lr.Body.String())
	}
	if bytes.Contains(lr.Body.Bytes(), []byte("tok-secret")) {
		t.Fatalf("list must NOT echo the confirm token: %s", lr.Body.String())
	}
	var listed struct {
		Items []struct {
			ApprovalID string `json:"approval_id"`
			ToolName   string `json:"tool_name"`
			Status     string `json:"status"`
		} `json:"items"`
	}
	_ = json.Unmarshal(lr.Body.Bytes(), &listed)
	if len(listed.Items) != 1 || listed.Items[0].Status != "pending" {
		t.Fatalf("expected 1 pending, got %+v", listed.Items)
	}

	// Cross-owner cannot see it.
	uid2 := mkUser(t, pool)
	tok2 := bearer(t, uid2)
	cl := doJSON(s, http.MethodGet, "/v1/account/mcp-keys/approvals?status=pending", tok2, nil)
	var crossList struct {
		Items []json.RawMessage `json:"items"`
	}
	_ = json.Unmarshal(cl.Body.Bytes(), &crossList)
	if len(crossList.Items) != 0 {
		t.Fatalf("cross-owner must see 0, got %d", len(crossList.Items))
	}

	// Cross-owner cannot deny it (anti-oracle 404).
	cd := doJSON(s, http.MethodPost, "/v1/account/mcp-keys/approvals/"+created.ApprovalID+"/deny", tok2, nil)
	if cd.Code != http.StatusNotFound {
		t.Fatalf("cross-owner deny: expected 404, got %d", cd.Code)
	}

	// Owner approves → the stub executes; assert the attribution headers reached it.
	ap := doJSON(s, http.MethodPost, "/v1/account/mcp-keys/approvals/"+created.ApprovalID+"/approve", tok, nil)
	if ap.Code != http.StatusOK {
		t.Fatalf("approve: %d %s", ap.Code, ap.Body.String())
	}
	if gotKeyID != key.KeyID {
		t.Fatalf("confirm replay missing/wrong X-Mcp-Key-Id: got %q want %q", gotKeyID, key.KeyID)
	}
	if gotUserID != uid.String() {
		t.Fatalf("confirm replay X-User-Id: got %q want %q", gotUserID, uid.String())
	}
	if gotCap != "9" {
		t.Fatalf("confirm replay X-Mcp-Spend-Cap-Usd: got %q want 9", gotCap)
	}
	if gotInternal != mcpInternalTok {
		t.Fatalf("confirm replay X-Internal-Token: got %q", gotInternal)
	}

	// Re-approving an executed row is a conflict (single decision).
	again := doJSON(s, http.MethodPost, "/v1/account/mcp-keys/approvals/"+created.ApprovalID+"/approve", tok, nil)
	if again.Code != http.StatusConflict {
		t.Fatalf("re-approve: expected 409, got %d", again.Code)
	}

	// A second approval can be DENIED (token dropped, never replayed).
	cr2 := createApproval(s, map[string]any{
		"key_id": key.KeyID, "owner_user_id": uid.String(),
		"tool_name": "composition_generate", "domain": "composition", "confirm_token": "tok-2",
	})
	var created2 struct {
		ApprovalID string `json:"approval_id"`
	}
	_ = json.Unmarshal(cr2.Body.Bytes(), &created2)
	dr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys/approvals/"+created2.ApprovalID+"/deny", tok, nil)
	if dr.Code != http.StatusOK {
		t.Fatalf("deny: %d %s", dr.Code, dr.Body.String())
	}
	// Denying again → 404 (no longer pending).
	dr2 := doJSON(s, http.MethodPost, "/v1/account/mcp-keys/approvals/"+created2.ApprovalID+"/deny", tok, nil)
	if dr2.Code != http.StatusNotFound {
		t.Fatalf("re-deny: expected 404, got %d", dr2.Code)
	}
}

func TestMcpApprovals_Expired_PG(t *testing.T) {
	s, pool := approvalsServer(t, "http://unused.invalid")
	uid := mkUser(t, pool)
	tok := bearer(t, uid)

	// A pending row already past its expiry.
	cr := createApproval(s, map[string]any{
		"key_id": uid.String(), "owner_user_id": uid.String(),
		"tool_name": "composition_generate", "domain": "composition", "confirm_token": "tok-old",
		"expires_at": time.Now().Add(-time.Minute).UTC().Format(time.RFC3339),
	})
	if cr.Code != http.StatusCreated {
		t.Fatalf("create: %d %s", cr.Code, cr.Body.String())
	}
	var created struct {
		ApprovalID string `json:"approval_id"`
	}
	_ = json.Unmarshal(cr.Body.Bytes(), &created)

	// It must NOT appear in the pending list (expired excluded).
	lr := doJSON(s, http.MethodGet, "/v1/account/mcp-keys/approvals?status=pending", tok, nil)
	var listed struct {
		Items []json.RawMessage `json:"items"`
	}
	_ = json.Unmarshal(lr.Body.Bytes(), &listed)
	if len(listed.Items) != 0 {
		t.Fatalf("expired pending must be excluded, got %d", len(listed.Items))
	}

	// Approving an expired row → 410 (never reaches the domain).
	ap := doJSON(s, http.MethodPost, "/v1/account/mcp-keys/approvals/"+created.ApprovalID+"/approve", tok, nil)
	if ap.Code != http.StatusGone {
		t.Fatalf("approve expired: expected 410, got %d %s", ap.Code, ap.Body.String())
	}
}
