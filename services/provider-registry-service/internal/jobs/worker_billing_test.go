package jobs

// Unit tests for the Phase 6a worker billing helpers that need no DB.
// The full settleBilling reconcile/release DB path is covered by the
// deferred D-PHASE6A-WORKER-SETTLE-IT integration test (the jobs package
// has no DB harness yet) and by D-PHASE6A-LIVE-SMOKE.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestNumField(t *testing.T) {
	cases := []struct {
		name   string
		val    any
		want   int
		wantOK bool
	}{
		{"int", 42, 42, true},
		{"int64", int64(7), 7, true},
		{"float64 (json round-trip)", float64(13), 13, true},
		{"zero is valid", 0, 0, true},
		{"negative rejected", -1, 0, false},
		{"string rejected", "12", 0, false},
		{"absent rejected", nil, 0, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			m := map[string]any{}
			if tc.val != nil {
				m["k"] = tc.val
			}
			got, ok := numField(m, "k")
			if got != tc.want || ok != tc.wantOK {
				t.Fatalf("numField(%v): got (%d,%v) want (%d,%v)", tc.val, got, ok, tc.want, tc.wantOK)
			}
		})
	}
}

func TestSettleBilling_NilGuardrail_IsNoOp(t *testing.T) {
	// A worker built without a guardrail client (router-only tests, dev
	// without usage-billing) must settle nothing and never panic — even
	// though repo is also nil here.
	w := &Worker{}
	w.settleBilling(context.Background(), uuid.New(), uuid.New(), "chat", "completed", nil)
	w.settleBilling(context.Background(), uuid.New(), uuid.New(), "chat", "failed", nil)
}

func TestActualUSD_NoUsageBlock_ReturnsNil(t *testing.T) {
	// A result with no `usage` block (every media operation) yields nil so
	// the caller reconciles with the reservation's stored estimate.
	w := &Worker{}
	if got := w.actualUSD(context.Background(), uuid.New(), "user_model", uuid.New(), nil); got != nil {
		t.Fatalf("nil result: expected nil actual, got %v", *got)
	}
	noUsage := map[string]any{"messages": []any{}}
	if got := w.actualUSD(context.Background(), uuid.New(), "user_model", uuid.New(), noUsage); got != nil {
		t.Fatalf("result without usage: expected nil actual, got %v", *got)
	}
}

func TestUsageTokens(t *testing.T) {
	in, out, ok := usageTokens(map[string]any{
		"usage": map[string]any{"input_tokens": 120, "output_tokens": 30},
	})
	if !ok || in != 120 || out != 30 {
		t.Fatalf("usageTokens: got (%d,%d,%v) want (120,30,true)", in, out, ok)
	}
	if _, _, ok := usageTokens(nil); ok {
		t.Fatal("nil result → ok must be false")
	}
	if _, _, ok := usageTokens(map[string]any{"messages": []any{}}); ok {
		t.Fatal("result with no usage block → ok must be false")
	}
}
