package api

// P2·B2(a) — route-parity contract for the LLM-usage ledger.
//
// Two routes reach writeUsageLog: Route A (/record HTTP — streaming + the sync
// embed/rerank/web_search ops) via recordUsageParams, and Route B (the usage
// stream consumer — async jobs) via parseUsageEvent. Ledger integrity requires a
// usage_logs row be IDENTICAL in its billing-critical columns regardless of route.
//
// The load-bearing column is CostUSD. Before P2·B2 the routes had drifted:
// Route A dropped the caller's authoritative total_cost_usd and recorded the flat
// fallback (D-S4C-STREAMING-REALCOST), while Route B honored the stream cost_usd —
// so the committed-spend rollup (guardrail SUM(total_cost_usd)) under/over-counted
// every streaming row. This test locks the two routes to the same cost (and the
// other shared columns) so that drift can never silently return.
//
// Not compared (divergent BY DESIGN, documented on each builder): ProviderKind
// (absent on the jobs path) and the payload Go-type (Route A map vs Route B string) —
// both normalize at writeUsageLog's marshalPayload.

import (
	"testing"

	"github.com/google/uuid"
)

// assertLedgerParity fails if the two routes disagree on any billing-critical column.
func assertLedgerParity(t *testing.T, a, b usageLogParams) {
	t.Helper()
	if a.RequestID != b.RequestID {
		t.Errorf("RequestID: A=%v B=%v", a.RequestID, b.RequestID)
	}
	if a.OwnerUserID != b.OwnerUserID {
		t.Errorf("OwnerUserID: A=%v B=%v", a.OwnerUserID, b.OwnerUserID)
	}
	if a.ModelSource != b.ModelSource {
		t.Errorf("ModelSource: A=%q B=%q", a.ModelSource, b.ModelSource)
	}
	if a.ModelRef != b.ModelRef {
		t.Errorf("ModelRef: A=%v B=%v", a.ModelRef, b.ModelRef)
	}
	if a.InputTokens != b.InputTokens {
		t.Errorf("InputTokens: A=%d B=%d", a.InputTokens, b.InputTokens)
	}
	if a.OutputTokens != b.OutputTokens {
		t.Errorf("OutputTokens: A=%d B=%d", a.OutputTokens, b.OutputTokens)
	}
	if a.CostUSD != b.CostUSD {
		t.Errorf("CostUSD parity broken: A=%v B=%v", a.CostUSD, b.CostUSD)
	}
	if a.RequestStatus != b.RequestStatus {
		t.Errorf("RequestStatus: A=%q B=%q", a.RequestStatus, b.RequestStatus)
	}
	if a.Purpose != b.Purpose {
		t.Errorf("Purpose: A=%q B=%q", a.Purpose, b.Purpose)
	}
}

// With an authoritative cost supplied to both routes, both must record it verbatim
// (NOT the flat fallback). This is the D-S4C-STREAMING-REALCOST regression lock:
// remove `in.TotalCostUSD` from recordUsageParams and this test reds.
func TestRouteParity_AuthoritativeCost_HonoredBothRoutes(t *testing.T) {
	reqID, owner, modelRef := uuid.New(), uuid.New(), uuid.New()
	realCost := 0.0123

	a := recordUsageParams(recordUsageRequest{
		RequestID: reqID, OwnerUserID: owner, ModelSource: "user_model", ModelRef: modelRef,
		InputTokens: 120, OutputTokens: 30, RequestStatus: "success", Purpose: "embed",
		TotalCostUSD: &realCost,
	})
	b, err := parseUsageEvent(map[string]any{
		"request_id": reqID.String(), "owner_user_id": owner.String(),
		"model_source": "user_model", "model_ref": modelRef.String(), "operation": "embed",
		"input_tokens": "120", "output_tokens": "30", "cost_usd": "0.0123",
		"request_status": "success",
	})
	if err != nil {
		t.Fatalf("parseUsageEvent: %v", err)
	}
	assertLedgerParity(t, a, b)
	if a.CostUSD != realCost {
		t.Fatalf("Route A recorded %v, not the authoritative %v (flat-cost drift)", a.CostUSD, realCost)
	}
}

// With NO cost supplied, both routes must fall back to the SAME flat cost — parity
// must hold on the fallback path too (a divergent flatCostPerToken would desync).
func TestRouteParity_FlatFallback_MatchesBothRoutes(t *testing.T) {
	reqID, owner, modelRef := uuid.New(), uuid.New(), uuid.New()

	a := recordUsageParams(recordUsageRequest{
		RequestID: reqID, OwnerUserID: owner, ModelSource: "user_model", ModelRef: modelRef,
		InputTokens: 200, OutputTokens: 50, RequestStatus: "success", Purpose: "rerank",
		// TotalCostUSD nil → flat fallback (rerank/web_search carry no per-token cost)
	})
	b, err := parseUsageEvent(map[string]any{
		"request_id": reqID.String(), "owner_user_id": owner.String(),
		"model_source": "user_model", "model_ref": modelRef.String(), "operation": "rerank",
		"input_tokens": "200", "output_tokens": "50", // no cost_usd → flat fallback
		"request_status": "success",
	})
	if err != nil {
		t.Fatalf("parseUsageEvent: %v", err)
	}
	assertLedgerParity(t, a, b)
	if a.CostUSD != recordCostUSD(250, nil) {
		t.Fatalf("flat fallback = %v, want %v", a.CostUSD, recordCostUSD(250, nil))
	}
}
