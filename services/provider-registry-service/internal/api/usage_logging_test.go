package api

// P0-2 (B4) — unit tests for the shared synchronous usage-record path used by the
// embed / rerank / web-search handlers, plus the payload-bounding helper.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/billing"
)

// TestRecordSyncUsage_LogsEmbedLikeCall proves an embed/rerank/web-search call
// records a usage row carrying the request + response payloads, the model identity,
// the provider token count, and request_status=success — the audit hole B4 closes.
func TestRecordSyncUsage_LogsEmbedLikeCall(t *testing.T) {
	got := make(chan map[string]any, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/record") {
			raw, _ := io.ReadAll(r.Body)
			m := map[string]any{}
			_ = json.Unmarshal(raw, &m)
			got <- m
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()

	s := &Server{guardrail: billing.NewGuardrailClient(srv.URL, "tok", nil)}
	userID, modelRef := uuid.New(), uuid.New()
	cost := 0.0025 // P2·B2(c) — the authoritative cost must reach the ledger wire
	s.recordSyncUsage(context.Background(), userID, modelRef, "embed", "success", 12, 0, &cost,
		map[string]any{"texts": []any{"alpha", "beta"}},
		map[string]any{"count": 2, "dimension": 1024})

	select {
	case body := <-got:
		if body["purpose"] != "embed" {
			t.Errorf("purpose: got %v want embed", body["purpose"])
		}
		if body["request_status"] != "success" {
			t.Errorf("request_status: got %v want success", body["request_status"])
		}
		if body["owner_user_id"] != userID.String() {
			t.Errorf("owner_user_id: got %v want %v", body["owner_user_id"], userID)
		}
		if body["model_ref"] != modelRef.String() {
			t.Errorf("model_ref: got %v want %v", body["model_ref"], modelRef)
		}
		if body["model_source"] != "user_model" {
			t.Errorf("model_source: got %v want user_model", body["model_source"])
		}
		if in, _ := body["input_tokens"].(float64); int(in) != 12 {
			t.Errorf("input_tokens: got %v want 12", body["input_tokens"])
		}
		if c, _ := body["total_cost_usd"].(float64); c != 0.0025 {
			t.Errorf("total_cost_usd: got %v want 0.0025", body["total_cost_usd"])
		}
		ip, ok := body["input_payload"].(map[string]any)
		if !ok || ip["texts"] == nil {
			t.Errorf("input_payload must carry texts, got %v", body["input_payload"])
		}
		op, ok := body["output_payload"].(map[string]any)
		if !ok || op["dimension"] == nil {
			t.Errorf("output_payload must carry dimension, got %v", body["output_payload"])
		}
	case <-time.After(2 * time.Second):
		t.Fatal("recordSyncUsage did not POST /record within 2s")
	}
}

// TestRecordSyncUsage_NilGuardrailNoPanic — a router-only Server (no guardrail)
// must silently no-op, never panic.
func TestRecordSyncUsage_NilGuardrailNoPanic(t *testing.T) {
	s := &Server{} // guardrail nil
	s.recordSyncUsage(context.Background(), uuid.New(), uuid.New(), "embed", "success", 1, 0, nil, nil, nil)
}

// TestRecordSyncUsage_ProviderErrorStatus — MED-1: a FAILED sync call records an
// audit row with request_status="provider_error" (previously the status was
// hardcoded "success" and error paths recorded nothing at all).
func TestRecordSyncUsage_ProviderErrorStatus(t *testing.T) {
	got := make(chan map[string]any, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var m map[string]any
		if raw, _ := io.ReadAll(r.Body); raw != nil {
			_ = json.Unmarshal(raw, &m)
			got <- m
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()

	s := &Server{guardrail: billing.NewGuardrailClient(srv.URL, "tok", nil)}
	s.recordSyncUsage(context.Background(), uuid.New(), uuid.New(), "rerank", "provider_error", 0, 0, nil,
		map[string]any{"query": "q"}, map[string]any{"error": "rerank upstream 502"})

	select {
	case body := <-got:
		if body["request_status"] != "provider_error" {
			t.Errorf("request_status: got %v want provider_error", body["request_status"])
		}
		op, ok := body["output_payload"].(map[string]any)
		if !ok || op["error"] == nil {
			t.Errorf("output_payload must carry the error, got %v", body["output_payload"])
		}
	case <-time.After(2 * time.Second):
		t.Fatal("recordSyncUsage did not POST /record within 2s")
	}
}

// TestBoundedPayload_PassesThroughUnderCap keeps a small payload intact.
func TestBoundedPayload_PassesThroughUnderCap(t *testing.T) {
	m := map[string]any{"query": "hello"}
	got := boundedPayload(m)
	if got["query"] != "hello" {
		t.Fatalf("small payload must pass through unchanged, got %v", got)
	}
	if _, truncated := got["_truncated"]; truncated {
		t.Fatal("small payload must not be marked truncated")
	}
}

// TestBoundedPayload_ReferenceStubWhenHuge replaces an over-cap payload with a
// compact reference stub (reference-first, not inline).
func TestBoundedPayload_ReferenceStubWhenHuge(t *testing.T) {
	big := strings.Repeat("x", usagePayloadCapBytes+1000)
	got := boundedPayload(map[string]any{"blob": big})
	if trunc, _ := got["_truncated"].(bool); !trunc {
		t.Fatalf("over-cap payload must be a reference stub, got keys %v", keysOf(got))
	}
	if _, ok := got["_preview"].(string); !ok {
		t.Fatal("reference stub must carry a _preview")
	}
	if b, _ := got["_bytes"].(float64); int(b) == 0 {
		// _bytes is an int in-process (not yet JSON round-tripped) — assert via any.
		if bi, _ := got["_bytes"].(int); bi == 0 {
			t.Fatal("reference stub must record the original byte size")
		}
	}
}

// TestBoundedPayload_NilIsNil — nil in, nil out (record omits the field).
func TestBoundedPayload_NilIsNil(t *testing.T) {
	if boundedPayload(nil) != nil {
		t.Fatal("nil payload must map to nil")
	}
}

func keysOf(m map[string]any) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}
