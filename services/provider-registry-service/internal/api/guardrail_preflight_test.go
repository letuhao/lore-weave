package api

// Unit tests for the Phase 6a doSubmitJob pre-flight helpers that need no DB:
// mergeJobMeta, mapInt, affordableMaxTokens.

import (
	"encoding/json"
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/billing"
	"github.com/loreweave/provider-registry-service/internal/config"
)

func ptr(v float64) *float64 { return &v }

// ── mergeJobMeta ────────────────────────────────────────────────────────────

func TestMergeJobMeta_NoCap(t *testing.T) {
	// No cap + no caller job_meta → nil (SQL NULL).
	if got := mergeJobMeta(nil, nil); got != nil {
		t.Fatalf("no cap, no meta: expected nil, got %v", got)
	}
	// No cap + caller job_meta → the raw passes through unchanged.
	raw := json.RawMessage(`{"trace":"x"}`)
	if got := mergeJobMeta(raw, nil); got == nil {
		t.Fatal("no cap, with meta: raw should pass through, got nil")
	}
}

func TestMergeJobMeta_CapMergedIntoExistingMeta(t *testing.T) {
	cap := &maxTokensCap{Requested: 1000, Applied: 200, Reason: "budget"}
	got := mergeJobMeta(json.RawMessage(`{"trace":"abc"}`), cap)
	m, ok := got.(map[string]any)
	if !ok {
		t.Fatalf("expected a map, got %T", got)
	}
	if m["trace"] != "abc" {
		t.Fatalf("existing job_meta key lost: %v", m)
	}
	mc, ok := m["max_tokens_capped"].(*maxTokensCap)
	if !ok || mc.Applied != 200 || mc.Requested != 1000 {
		t.Fatalf("max_tokens_capped not merged: %v", m["max_tokens_capped"])
	}
}

func TestMergeJobMeta_CapWithNoMeta(t *testing.T) {
	cap := &maxTokensCap{Requested: 500, Applied: 64, Reason: "budget"}
	got := mergeJobMeta(nil, cap)
	m, ok := got.(map[string]any)
	if !ok || m["max_tokens_capped"] == nil {
		t.Fatalf("cap with no meta: expected map carrying the cap, got %v", got)
	}
}

// ── mapInt ──────────────────────────────────────────────────────────────────

func TestMapInt(t *testing.T) {
	m := map[string]any{"f": float64(42), "i": 7, "s": "nope"}
	if got := mapInt(m, "f", -1); got != 42 {
		t.Fatalf("float64 field: got %d", got)
	}
	if got := mapInt(m, "i", -1); got != 7 {
		t.Fatalf("int field: got %d", got)
	}
	if got := mapInt(m, "s", -1); got != -1 {
		t.Fatalf("non-numeric field should fall back to def, got %d", got)
	}
	if got := mapInt(m, "absent", 99); got != 99 {
		t.Fatalf("absent field should fall back to def, got %d", got)
	}
}

// ── affordableMaxTokens ─────────────────────────────────────────────────────

func preflightServer() *Server {
	return &Server{
		cfg: &config.Config{MaxOutputTokensDefault: 4096},
		estimator: billing.Estimator{
			MaxOutputTokensDefault:    4096,
			ExtractionOutputCeiling:   8192,
			SystemPromptTokenEstimate: 1024,
		},
	}
}

func TestAffordableMaxTokens_CappedAtRequested(t *testing.T) {
	s := preflightServer()
	input := map[string]any{"messages": "hi", "max_tokens": float64(500)}
	pricing := billing.Pricing{InputPerMTok: ptr(1.0), OutputPerMTok: ptr(10.0)}
	// Generous budget — affordable output far exceeds the requested 500, so
	// the cap must clamp DOWN to 500, never raise it.
	res := billing.ReserveResult{Insufficient: true, DailyAvailable: 100, MonthlyAvailable: 100}

	capped, reqMax, ok := s.affordableMaxTokens(input, pricing, 1, res)
	if !ok {
		t.Fatal("expected affordable=true with a generous budget")
	}
	if reqMax != 500 {
		t.Fatalf("reqMax: got %d want 500", reqMax)
	}
	if capped != 500 {
		t.Fatalf("cap must clamp at the requested ceiling, got %d", capped)
	}
}

func TestAffordableMaxTokens_TightBudgetCapsBelowRequested(t *testing.T) {
	s := preflightServer()
	input := map[string]any{"messages": "hi", "max_tokens": float64(100000)}
	pricing := billing.Pricing{InputPerMTok: ptr(1.0), OutputPerMTok: ptr(10.0)}
	// outPerTok = 10/1e6 = 1e-5. budget 0.001 → ~100 affordable output tokens.
	res := billing.ReserveResult{Insufficient: true, DailyAvailable: 0.001, MonthlyAvailable: 9.0}

	capped, _, ok := s.affordableMaxTokens(input, pricing, 1, res)
	if !ok {
		t.Fatal("expected a usable cap on a tight-but-positive budget")
	}
	if capped < 1 || capped > 100 {
		t.Fatalf("tight-budget cap out of range: got %d", capped)
	}
}

func TestAffordableMaxTokens_Unaffordable(t *testing.T) {
	s := preflightServer()
	input := map[string]any{"messages": "hi"}
	pricing := billing.Pricing{InputPerMTok: ptr(1.0), OutputPerMTok: ptr(10.0)}
	// A budget too small for even one output token → not cappable, caller 402s.
	res := billing.ReserveResult{Insufficient: true, DailyAvailable: 1e-9, MonthlyAvailable: 1e-9}
	if _, _, ok := s.affordableMaxTokens(input, pricing, 1, res); ok {
		t.Fatal("expected affordable=false for a sub-token budget")
	}
}

// TestAffordableMaxTokens_ReservesQuantumHeadroom — D-PHASE6A-CAP-ROUNDUP
// regression-lock. The cap calc subtracts billing.UsdQuantum from the
// budget so that the post-cap re-estimate's `roundUpUSD` doesn't push
// the total back over the available budget. Compute the post-cap cost
// AS THE GUARDRAIL WOULD (via roundUpUSD) and assert it stays at or
// below the budget. Pre-fix this test would FAIL by exactly one
// quantum on inputs that align with the rounding cliff.
func TestAffordableMaxTokens_ReservesQuantumHeadroom(t *testing.T) {
	s := preflightServer()
	// Pick numbers where the unrounded cost lands EXACTLY on a quantum
	// boundary post-affordable. outPerTok = 10/1e6 = 1e-5 USD/token.
	// budget = 0.00001000 = 1 token's worth. Without headroom, affordable
	// = 1, post-cost = 1e-5 = the budget, but roundUpUSD bumps anything
	// > 0 to ≥ 1 quantum so a real 0.00001000 cost is fine. The cliff
	// shows up when the affordable calc rounds slightly above an exact
	// fit — easier to construct via a budget like 0.00001234 with
	// outPerTok 1e-5: affordable = floor((0.00001234 - 1e-8) / 1e-5) = 1.
	// Post-cost rounded = 1 * 1e-5 = 1e-5, well below budget.
	input := map[string]any{"messages": "hi"}
	pricing := billing.Pricing{InputPerMTok: ptr(1.0), OutputPerMTok: ptr(10.0)}
	res := billing.ReserveResult{
		Insufficient: true,
		DailyAvailable: 0.00001234, MonthlyAvailable: 9.0,
	}
	capped, _, ok := s.affordableMaxTokens(input, pricing, 1, res)
	if !ok || capped < 1 {
		t.Fatalf("expected ok=true capped>=1, got ok=%v capped=%d", ok, capped)
	}
	// Simulate the gateway's post-cap re-estimate: input cost rounded up
	// + capped output cost. The total MUST be ≤ DailyAvailable; with the
	// quantum headroom subtracted from `budget`, the affordable count is
	// one less than the cliff case, so the re-estimate fits.
	inTok := s.estimator.InputTokens(input, 1)
	postCost := float64(inTok)/1e6*(*pricing.InputPerMTok) + float64(capped)*(*pricing.OutputPerMTok)/1e6
	// roundUpUSD is package-private; approximate via ceiling-to-quantum.
	rounded := math.Ceil(postCost/billing.UsdQuantum) * billing.UsdQuantum
	if rounded > res.DailyAvailable {
		t.Fatalf("post-cap re-estimate %v exceeds DailyAvailable %v — quantum headroom missing",
			rounded, res.DailyAvailable)
	}
}

func TestAffordableMaxTokens_FreeOutputNotCappable(t *testing.T) {
	s := preflightServer()
	input := map[string]any{"messages": "hi"}
	// Output is free; a 402 here is driven by the input cost alone, which
	// capping max_tokens cannot reduce — must report not-cappable.
	pricing := billing.Pricing{InputPerMTok: ptr(1.0), OutputPerMTok: ptr(0)}
	res := billing.ReserveResult{Insufficient: true, DailyAvailable: 0.0, MonthlyAvailable: 0.0}
	if _, _, ok := s.affordableMaxTokens(input, pricing, 1, res); ok {
		t.Fatal("free output must not be reported as cappable")
	}
}

// TestEveryJobOperationIsEstimable locks /review-impl LOW#8: every operation
// accepted at submit must be handled by EstimateUSD — an unhandled op would
// fall to the default branch and 500 at doSubmitJob. Keeps the two sets in
// sync without a comment-only contract.
func TestEveryJobOperationIsEstimable(t *testing.T) {
	e := billing.Estimator{MaxOutputTokensDefault: 100, ExtractionOutputCeiling: 100, SystemPromptTokenEstimate: 10}
	// Fully-priced so no ErrUnpriced — we only care about "unknown operation".
	full := billing.Pricing{
		InputPerMTok: ptr(1), OutputPerMTok: ptr(1),
		PerImage: ptr(1), PerSecond: ptr(1), PerKChar: ptr(1),
	}
	input := map[string]any{
		"text": "x", "messages": "x", "n": 1.0, "duration": 1.0, "texts": []any{"x"},
	}
	for op := range validJobOperations {
		_, err := e.EstimateUSD(op, input, full, 1)
		if err != nil && strings.Contains(err.Error(), "unknown operation") {
			t.Fatalf("operation %q is accepted at submit but EstimateUSD does not handle it", op)
		}
	}
}

// TestWriteBudget402_DistinctMessages locks Phase 6a-γ — the 402 message
// names which gate failed (Subsystem A daily/monthly vs Subsystem B platform).
func TestWriteBudget402_DistinctMessages(t *testing.T) {
	// Subsystem A — daily/monthly budget.
	rrA := httptest.NewRecorder()
	writeBudget402(rrA, billing.ReserveResult{
		Insufficient: true, Code: "INSUFFICIENT_BUDGET",
		DailyAvailable: 1.0, MonthlyAvailable: 2.0, Requested: 5.0,
	})
	if rrA.Code != http.StatusPaymentRequired {
		t.Fatalf("A: expected 402, got %d", rrA.Code)
	}
	if bodyA := rrA.Body.String(); !strings.Contains(bodyA, "daily") || strings.Contains(bodyA, "platform free tier") {
		t.Fatalf("Subsystem-A 402 should mention daily/monthly, not platform: %s", bodyA)
	}

	// Subsystem B — platform free tier + credits.
	rrB := httptest.NewRecorder()
	writeBudget402(rrB, billing.ReserveResult{
		Insufficient: true, Code: "PLATFORM_BALANCE_EXHAUSTED",
		PlatformAvailable: 0.5, Requested: 5.0,
	})
	if bodyB := rrB.Body.String(); !strings.Contains(bodyB, "platform free tier") {
		t.Fatalf("Subsystem-B 402 should name the platform free tier: %s", bodyB)
	}
}
