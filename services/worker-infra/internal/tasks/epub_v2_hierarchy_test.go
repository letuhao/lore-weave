package tasks

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/loreweave/worker-infra/internal/config"
)

func TestEPUBV2HierarchyCompositionOutagePersistsRetryableWarning(t *testing.T) {
	var warningCalls atomic.Int32
	book := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]any{
				"book_id": "11111111-1111-1111-1111-111111111111",
				"user_id": "22222222-2222-2222-2222-222222222222",
				"nodes":   []any{map[string]any{"source_key": "chapter-1", "role": "chapter", "title": "One", "ordinal": 0, "depth": 0}},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/internal/epub-import-jobs/job-1/warnings":
			warningCalls.Add(1)
			w.WriteHeader(http.StatusAccepted)
		default:
			t.Fatalf("unexpected Book request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer book.Close()
	composition := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/composition/books/11111111-1111-1111-1111-111111111111/epub-import-hierarchy" {
			t.Fatalf("unexpected Composition path %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer composition.Close()
	processor := &ImportProcessor{Cfg: &config.Config{BookServiceURL: book.URL, CompositionServiceURL: composition.URL, InternalToken: "token"}}
	err := processor.materializeEPUBV2Hierarchy(context.Background(), importRequestedPayload{JobID: "job-1"})
	if err != nil {
		t.Fatalf("outage should be best effort, got %v", err)
	}
	if warningCalls.Load() != 1 {
		t.Fatalf("warning calls = %d, want 1", warningCalls.Load())
	}
}

func TestEPUBV2HierarchyRetryForwardsCompositionMappings(t *testing.T) {
	var mappingCalls atomic.Int32
	var compositionOrdinal atomic.Int32
	book := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]any{
				"book_id": "11111111-1111-1111-1111-111111111111",
				"user_id": "22222222-2222-2222-2222-222222222222",
				"nodes":   []any{map[string]any{"source_key": "chapter-1", "role": "chapter", "title": "One", "ordinal": 0, "depth": 0}},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/internal/epub-import-jobs/job-2/hierarchy-mappings":
			mappingCalls.Add(1)
			w.WriteHeader(http.StatusOK)
		default:
			t.Fatalf("unexpected Book request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer book.Close()
	composition := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Nodes []struct {
				Ordinal int `json:"ordinal"`
			} `json:"nodes"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatalf("decode Composition request: %v", err)
		}
		if len(request.Nodes) != 1 {
			t.Fatalf("Composition nodes = %d, want 1", len(request.Nodes))
		}
		compositionOrdinal.Store(int32(request.Nodes[0].Ordinal))
		_ = json.NewEncoder(w).Encode(map[string]any{"mappings": []any{map[string]any{"source_key": "chapter-1", "hierarchy_node_id": "33333333-3333-3333-3333-333333333333"}}})
	}))
	defer composition.Close()
	processor := &ImportProcessor{Cfg: &config.Config{BookServiceURL: book.URL, CompositionServiceURL: composition.URL, InternalToken: "token"}}
	if err := processor.materializeEPUBV2Hierarchy(context.Background(), importRequestedPayload{JobID: "job-2"}); err != nil {
		t.Fatalf("retry should succeed, got %v", err)
	}
	if mappingCalls.Load() != 1 {
		t.Fatalf("mapping calls = %d, want 1", mappingCalls.Load())
	}
	if compositionOrdinal.Load() != 1 {
		t.Fatalf("Composition ordinal = %d, want normalized 1", compositionOrdinal.Load())
	}
}
