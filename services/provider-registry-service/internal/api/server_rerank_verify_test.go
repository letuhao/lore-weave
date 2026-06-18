package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// C3 (BL-10) — rerank-aware verify: detectPrimaryCapability must route rerank
// models to the rerank verify path, and verifyRerank must perform a REAL
// /v1/rerank round-trip (via the canonical provider.Rerank gateway path, using
// the BYOK-resolved baseURL/secret/model) returning ranked scores + latency.

func TestDetectPrimaryCapability_Rerank(t *testing.T) {
	// boolean flag form (C1 manual / C2 discovery canonical)
	if got := detectPrimaryCapability(map[string]any{"rerank": true}); got != "rerank" {
		t.Errorf("boolean rerank flag: got %q want rerank", got)
	}
	// metadata string form (inventory _capability)
	if got := detectPrimaryCapability(map[string]any{"_capability": "rerank"}); got != "rerank" {
		t.Errorf("_capability rerank: got %q want rerank", got)
	}
	// non-rerank stays chat
	if got := detectPrimaryCapability(map[string]any{"chat": true}); got != "chat" {
		t.Errorf("chat: got %q want chat", got)
	}
	// the divergent 'reranker' must NOT be recognized (canonical token only)
	if got := detectPrimaryCapability(map[string]any{"_capability": "reranker"}); got == "rerank" {
		t.Errorf("divergent 'reranker' should not route to rerank verify")
	}
}

func TestVerifyRerank_RealRoundTrip(t *testing.T) {
	var gotPath, gotModel, gotQuery string
	var gotDocs int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		gotModel, _ = body["model"].(string)
		gotQuery, _ = body["query"].(string)
		if d, ok := body["documents"].([]any); ok {
			gotDocs = len(d)
		}
		w.Header().Set("Content-Type", "application/json")
		// upstream returns UNSORTED; verifyRerank/provider.Rerank must sort desc
		_ = json.NewEncoder(w).Encode(map[string]any{
			"results": []any{
				map[string]any{"index": 0, "relevance_score": 0.02},
				map[string]any{"index": 1, "relevance_score": 0.95},
				map[string]any{"index": 2, "relevance_score": 0.40},
			},
		})
	}))
	defer srv.Close()

	s := &Server{} // verifyRerank does not touch the pool
	out := s.verifyRerank(context.Background(), srv.URL, "sekret", "bge-reranker-v2-m3")

	if gotPath != "/v1/rerank" {
		t.Fatalf("expected POST /v1/rerank, got %q", gotPath)
	}
	if gotModel != "bge-reranker-v2-m3" {
		t.Errorf("model not forwarded: %q", gotModel)
	}
	if gotQuery == "" || gotDocs < 2 {
		t.Errorf("rerank-shaped request missing (query=%q docs=%d)", gotQuery, gotDocs)
	}
	if v, _ := out["verified"].(bool); !v {
		t.Fatalf("expected verified=true, got %+v", out)
	}
	// top result must be the highest score (index 1, 0.95) after sort
	if ti, _ := out["top_index"].(int); ti != 1 {
		t.Errorf("top_index = %v, want 1 (highest score)", out["top_index"])
	}
	scores, ok := out["scores"].([]map[string]any)
	if !ok || len(scores) != 3 {
		t.Fatalf("expected 3 scores, got %+v", out["scores"])
	}
	// sorted descending
	if scores[0]["relevance_score"].(float64) < scores[1]["relevance_score"].(float64) {
		t.Errorf("scores not sorted descending: %+v", scores)
	}
}

func TestVerifyRerank_UpstreamError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"bad model"}`, http.StatusBadRequest)
	}))
	defer srv.Close()
	s := &Server{}
	out := s.verifyRerank(context.Background(), srv.URL, "", "x")
	if v, _ := out["verified"].(bool); v {
		t.Errorf("expected verified=false on upstream error, got %+v", out)
	}
	if out["error"] == nil {
		t.Errorf("expected error field on failure")
	}
}
