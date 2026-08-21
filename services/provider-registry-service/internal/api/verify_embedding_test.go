package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestDetectPrimaryCapabilityEmbedding(t *testing.T) {
	t.Parallel()
	for name, caps := range map[string]map[string]any{
		"boolean":  {"embedding": true},
		"metadata": {"_capability": "embedding"},
		"legacy":   {"_capability": "embed"},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			if got := detectPrimaryCapability(caps); got != "embedding" {
				t.Fatalf("detectPrimaryCapability() = %q; want embedding", got)
			}
		})
	}
}

func TestVerifyEmbeddingUsesEmbeddingsEndpoint(t *testing.T) {
	t.Parallel()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method = %s; want POST", r.Method)
		}
		if r.URL.Path != "/v1/embeddings" {
			t.Errorf("path = %q; want /v1/embeddings", r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer test-secret" {
			t.Errorf("Authorization = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"object": "list",
			"data": []any{map[string]any{
				"object": "embedding", "index": 0,
				"embedding": []float64{0.1, 0.2, 0.3},
			}},
			"model": "qwen3-embedding-4b",
			"usage": map[string]any{"prompt_tokens": 4, "total_tokens": 4},
		})
	}))
	defer upstream.Close()

	s := &Server{}
	result := s.verifyEmbedding(context.Background(), "neuraldeep", upstream.URL+"/v1", "test-secret", "qwen3-embedding-4b")
	if verified, _ := result["verified"].(bool); !verified {
		t.Fatalf("verification failed: %#v", result)
	}
	if got := result["dimension"]; got != 3 {
		t.Fatalf("dimension = %#v; want 3", got)
	}
}
