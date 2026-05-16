package api

// Unit tests for the Phase 6a doSubmitJob pre-flight helpers that need no DB:
// mergeJobMeta, mapInt, affordableMaxTokens.

import (
	"encoding/json"
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
