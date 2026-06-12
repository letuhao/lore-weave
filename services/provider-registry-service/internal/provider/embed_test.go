package provider

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestParseOpenAIEmbeddingResponse(t *testing.T) {
	out := map[string]any{
		"data": []any{
			map[string]any{
				"embedding": []any{0.1, 0.2, 0.3},
				"index":     0,
			},
			map[string]any{
				"embedding": []any{0.4, 0.5, 0.6},
				"index":     1,
			},
		},
		"model": "text-embedding-3-small",
	}

	result, err := parseOpenAIEmbeddingResponse(out, "fallback-model")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Embeddings) != 2 {
		t.Fatalf("expected 2 embeddings, got %d", len(result.Embeddings))
	}
	if result.Dimension != 3 {
		t.Fatalf("expected dimension 3, got %d", result.Dimension)
	}
	if result.Model != "text-embedding-3-small" {
		t.Fatalf("expected model from response, got %s", result.Model)
	}
}

func TestParseOpenAIEmbeddingResponse_SurfacesUsagePromptTokens(t *testing.T) {
	// LE-059b: an OpenAI/LM Studio `usage.prompt_tokens` is surfaced so the caller
	// can meter the embed leg on a real count.
	out := map[string]any{
		"data":  []any{map[string]any{"embedding": []any{0.1, 0.2}, "index": 0}},
		"model": "bge-m3",
		"usage": map[string]any{"prompt_tokens": float64(42), "total_tokens": float64(42)},
	}
	result, err := parseOpenAIEmbeddingResponse(out, "fallback")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.PromptTokens != 42 {
		t.Fatalf("expected PromptTokens 42, got %d", result.PromptTokens)
	}
}

func TestParseOpenAIEmbeddingResponse_NoUsageIsZero(t *testing.T) {
	// no usage block → 0 (caller falls back to a char-estimate; wire stays clean).
	out := map[string]any{
		"data":  []any{map[string]any{"embedding": []any{0.1, 0.2}, "index": 0}},
		"model": "bge-m3",
	}
	result, err := parseOpenAIEmbeddingResponse(out, "fallback")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.PromptTokens != 0 {
		t.Fatalf("expected PromptTokens 0 when usage absent, got %d", result.PromptTokens)
	}
}

func TestParseOpenAIEmbeddingResponseEmpty(t *testing.T) {
	out := map[string]any{
		"data": []any{},
	}
	_, err := parseOpenAIEmbeddingResponse(out, "m")
	if err == nil {
		t.Fatal("expected error for empty data")
	}
}

func TestParseOllamaEmbeddingResponse(t *testing.T) {
	out := map[string]any{
		"embeddings": []any{
			[]any{0.1, 0.2, 0.3, 0.4},
		},
		"model": "nomic-embed-text",
	}

	result, err := parseOllamaEmbeddingResponse(out, "fallback")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Embeddings) != 1 {
		t.Fatalf("expected 1 embedding, got %d", len(result.Embeddings))
	}
	if result.Dimension != 4 {
		t.Fatalf("expected dimension 4, got %d", result.Dimension)
	}
	if result.Model != "nomic-embed-text" {
		t.Fatalf("expected model from response, got %s", result.Model)
	}
}

func TestParseOllamaEmbeddingResponseEmpty(t *testing.T) {
	out := map[string]any{}
	_, err := parseOllamaEmbeddingResponse(out, "m")
	if err == nil {
		t.Fatal("expected error for missing embeddings")
	}
}

func TestParseOpenAIFallbackModel(t *testing.T) {
	// When response doesn't include model, use the fallback
	out := map[string]any{
		"data": []any{
			map[string]any{
				"embedding": []any{1.0, 2.0},
			},
		},
	}
	result, err := parseOpenAIEmbeddingResponse(out, "my-fallback")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Model != "my-fallback" {
		t.Fatalf("expected fallback model, got %s", result.Model)
	}
}

// TestEmbedOpenAI_V1SuffixStripped verifies that an endpointBaseURL ending in
// "/v1" does NOT produce a doubled "/v1/v1/embeddings" path.  LM Studio and
// other local providers store their base URL as "http://host:port/v1", so
// embedOpenAI must strip the trailing /v1 before appending /v1/embeddings.
func TestEmbedOpenAI_V1SuffixStripped(t *testing.T) {
	var capturedPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"data":[{"embedding":[0.1,0.2,0.3],"index":0}],"model":"bge-m3"}`))
	}))
	defer srv.Close()

	// Credential stored as "http://host:port/v1" — the typical LM Studio form.
	endpointWithV1 := srv.URL + "/v1"
	result, err := embedOpenAI(t.Context(), srv.Client(), endpointWithV1, "", "bge-m3", []string{"probe"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if capturedPath != "/v1/embeddings" {
		t.Fatalf("expected path /v1/embeddings, got %s (double-prefix bug)", capturedPath)
	}
	if result.Dimension != 3 {
		t.Fatalf("expected dim 3, got %d", result.Dimension)
	}
}
