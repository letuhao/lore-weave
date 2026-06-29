package api_test

// PG-gated contract test for the public MCP per-key call audit (P3 / H-O).
// Reuses the mcp_keys_pg_test.go harness (mcpKeysServer/mkUser/bearer/doJSON).
// Gated on AUTH_TEST_PG_URL.

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/loreweave/auth-service/internal/api"
)

func ingestAudit(s *api.Server, rows any) *httptest.ResponseRecorder {
	var buf bytes.Buffer
	_ = json.NewEncoder(&buf).Encode(rows)
	req := httptest.NewRequest(http.MethodPost, "/internal/mcp-keys/audit", &buf)
	req.Header.Set("X-Internal-Token", mcpInternalTok)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func TestMcpAudit_IngestAndOwnerRead_PG(t *testing.T) {
	s, pool := mcpKeysServer(t, true)
	uid := mkUser(t, pool)
	tok := bearer(t, uid)

	// A key to attribute the calls to.
	rr := doJSON(s, http.MethodPost, "/v1/account/mcp-keys", tok, map[string]any{"name": "agent"})
	if rr.Code != http.StatusCreated {
		t.Fatalf("create key: %d %s", rr.Code, rr.Body.String())
	}
	var created struct {
		KeyID string `json:"key_id"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &created); err != nil || created.KeyID == "" {
		t.Fatalf("create body: %v %s", err, rr.Body.String())
	}

	// Ingest a batch (internal-token): 2 valid rows + 1 with a bad outcome (skipped).
	rows := []map[string]any{
		{"key_id": created.KeyID, "owner_user_id": uid.String(), "method": "tools/call", "tool_name": "book_get", "outcome": "relayed", "trace_id": "t1"},
		{"key_id": created.KeyID, "owner_user_id": uid.String(), "method": "tools/call", "tool_name": "kg_graph_query", "outcome": "denied_scope"},
		{"key_id": created.KeyID, "owner_user_id": uid.String(), "method": "tools/list", "outcome": "NOT_A_VALID_OUTCOME"},
	}
	ar := ingestAudit(s, rows)
	if ar.Code != http.StatusOK {
		t.Fatalf("ingest: %d %s", ar.Code, ar.Body.String())
	}
	var ingested struct {
		Inserted int `json:"inserted"`
	}
	_ = json.Unmarshal(ar.Body.Bytes(), &ingested)
	if ingested.Inserted != 2 {
		t.Fatalf("expected 2 inserted (bad outcome skipped), got %d", ingested.Inserted)
	}

	// Internal-token required — no token → 401, nothing ingested.
	noTok := httptest.NewRequest(http.MethodPost, "/internal/mcp-keys/audit", bytes.NewBufferString("[]"))
	nr := httptest.NewRecorder()
	s.Router().ServeHTTP(nr, noTok)
	if nr.Code != http.StatusUnauthorized {
		t.Fatalf("ingest without internal token: expected 401, got %d", nr.Code)
	}

	// Owner read returns the 2 rows, newest first.
	or := doJSON(s, http.MethodGet, "/v1/account/mcp-keys/"+created.KeyID+"/audit", tok, nil)
	if or.Code != http.StatusOK {
		t.Fatalf("owner read: %d %s", or.Code, or.Body.String())
	}
	var got struct {
		Items []struct {
			Method   string  `json:"method"`
			ToolName *string `json:"tool_name"`
			Outcome  string  `json:"outcome"`
		} `json:"items"`
	}
	if err := json.Unmarshal(or.Body.Bytes(), &got); err != nil {
		t.Fatalf("owner read body: %v", err)
	}
	if len(got.Items) != 2 {
		t.Fatalf("expected 2 audit rows, got %d (%s)", len(got.Items), or.Body.String())
	}
	outcomes := map[string]bool{}
	for _, it := range got.Items {
		outcomes[it.Outcome] = true
	}
	if !outcomes["relayed"] || !outcomes["denied_scope"] {
		t.Fatalf("missing expected outcomes: %+v", got.Items)
	}

	// Cross-owner isolation: a DIFFERENT user reading this key's audit gets nothing.
	uid2 := mkUser(t, pool)
	tok2 := bearer(t, uid2)
	cr := doJSON(s, http.MethodGet, "/v1/account/mcp-keys/"+created.KeyID+"/audit", tok2, nil)
	if cr.Code != http.StatusOK {
		t.Fatalf("cross-owner read: %d", cr.Code)
	}
	var cross struct {
		Items []json.RawMessage `json:"items"`
	}
	_ = json.Unmarshal(cr.Body.Bytes(), &cross)
	if len(cross.Items) != 0 {
		t.Fatalf("cross-owner must see 0 audit rows, got %d", len(cross.Items))
	}
}
