package provider

import (
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
