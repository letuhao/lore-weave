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

func TestSettleReservation_NilGuardrail_IsNoOp(t *testing.T) {
	// A worker built without a guardrail client (router-only tests, dev
	// without usage-billing) must settle nothing and never panic. Also a
	// completed/failed job that carried no reservation (resID nil) is a no-op.
	w := &Worker{}
	w.settleReservation(context.Background(), uuid.New(), "completed", nil, nil)
	w.settleReservation(context.Background(), uuid.New(), "failed", nil, nil)
}

func TestParseJobMetaCampaignID(t *testing.T) {
	// S4b: the campaign tag is parsed from job_meta inside the finalize tx. It
	// must be nil-tolerant on EVERY malformed input — a bad tag can never fail a
	// billing-critical finalize; it just yields an un-attributed usage row.
	valid := uuid.New()
	cases := []struct {
		name string
		raw  string
		want *uuid.UUID
	}{
		{"valid", `{"campaign_id":"` + valid.String() + `"}`, &valid},
		{"valid with other keys", `{"attempt":1,"campaign_id":"` + valid.String() + `","x":"y"}`, &valid},
		{"absent key", `{"attempt":1}`, nil},
		{"empty string value", `{"campaign_id":""}`, nil},
		{"non-string value", `{"campaign_id":42}`, nil},
		{"bad uuid", `{"campaign_id":"not-a-uuid"}`, nil},
		{"empty bytes", ``, nil},
		{"null literal", `null`, nil},
		{"non-object", `"just a string"`, nil},
		{"malformed json", `{not json`, nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := parseJobMetaCampaignID([]byte(tc.raw))
			switch {
			case tc.want == nil && got != nil:
				t.Fatalf("expected nil, got %v", *got)
			case tc.want != nil && got == nil:
				t.Fatalf("expected %v, got nil", *tc.want)
			case tc.want != nil && *got != *tc.want:
				t.Fatalf("expected %v, got %v", *tc.want, *got)
			}
		})
	}
}

func TestParseJobMetaMcpKeyID(t *testing.T) {
	// H-C/PUB-11: the mcp_key_id attribution tag is parsed from job_meta with the
	// SAME nil-tolerance contract as campaign_id — a malformed tag must never fail a
	// billing-critical finalize; it just yields an un-attributed (NULL) usage row.
	// The PUB-12 gate also relies on this returning non-nil ONLY for a real key.
	valid := uuid.New()
	cases := []struct {
		name string
		raw  string
		want *uuid.UUID
	}{
		{"valid", `{"mcp_key_id":"` + valid.String() + `"}`, &valid},
		{"valid with other keys", `{"campaign_id":"` + uuid.New().String() + `","mcp_key_id":"` + valid.String() + `"}`, &valid},
		{"absent key", `{"campaign_id":"` + uuid.New().String() + `"}`, nil},
		{"empty string value", `{"mcp_key_id":""}`, nil},
		{"non-string value", `{"mcp_key_id":42}`, nil},
		{"bad uuid", `{"mcp_key_id":"not-a-uuid"}`, nil},
		{"empty bytes", ``, nil},
		{"null literal", `null`, nil},
		{"non-object", `"just a string"`, nil},
		{"malformed json", `{not json`, nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := ParseJobMetaMcpKeyID([]byte(tc.raw))
			switch {
			case tc.want == nil && got != nil:
				t.Fatalf("expected nil, got %v", *got)
			case tc.want != nil && got == nil:
				t.Fatalf("expected %v, got nil", *tc.want)
			case tc.want != nil && *got != *tc.want:
				t.Fatalf("expected %v, got %v", *tc.want, *got)
			}
		})
	}
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
