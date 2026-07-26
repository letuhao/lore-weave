package api

// Public MCP P3 (H-C/PUB-11) — getMcpKeyUsage input validation. The owner_user_id
// arg is parsed BEFORE any DB access, so the 400 paths are unit-testable with a
// pool-less server; the aggregation itself (GROUP BY mcp_key_id) is proven by the
// VERIFY live-smoke (Server.pool is a concrete *pgxpool.Pool, not mockable here —
// same constraint as the guardrail integration tests).

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGetMcpKeyUsageValidation(t *testing.T) {
	t.Parallel()
	srv := testServer("12345678901234567890123456789012")

	// Missing owner_user_id → 400, no DB touched (nil pool would panic otherwise).
	req := httptest.NewRequest(http.MethodGet, "/internal/billing/mcp-key-usage", nil)
	rr := httptest.NewRecorder()
	srv.getMcpKeyUsage(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("missing owner_user_id: expected 400, got %d body=%s", rr.Code, rr.Body.String())
	}

	// Malformed owner_user_id → 400.
	req2 := httptest.NewRequest(http.MethodGet, "/internal/billing/mcp-key-usage?owner_user_id=not-a-uuid", nil)
	rr2 := httptest.NewRecorder()
	srv.getMcpKeyUsage(rr2, req2)
	if rr2.Code != http.StatusBadRequest {
		t.Fatalf("bad owner_user_id: expected 400, got %d body=%s", rr2.Code, rr2.Body.String())
	}
}
