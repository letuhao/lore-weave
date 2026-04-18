package provider

import (
	"context"
	"fmt"
	"net/http"
	"strings"
)

// EmbedResult is the response from an embedding call.
type EmbedResult struct {
	Embeddings [][]float64 `json:"embeddings"`
	Dimension  int         `json:"dimension"`
	Model      string      `json:"model"`
}

// defaultClient is a package-level HTTP client for embedding calls.
// Reuses the same client for all providers (connection pooling).
var defaultClient = &http.Client{}

// Embed dispatches an embedding call to the correct provider endpoint.
// Each adapter knows its own endpoint shape:
//   - OpenAI/LM Studio: POST /v1/embeddings {model, input}
//   - Ollama:           POST /api/embed {model, input}
//   - Anthropic:        no embedding support → error
func Embed(ctx context.Context, adapter Adapter, endpointBaseURL, secret, model string, texts []string) (*EmbedResult, error) {
	switch adapter.(type) {
	case *openaiAdapter:
		return embedOpenAI(ctx, endpointBaseURL, secret, model, texts)
	case *lmStudioAdapter:
		return embedOpenAI(ctx, endpointBaseURL, secret, model, texts)
	case *ollamaAdapter:
		return embedOllama(ctx, endpointBaseURL, model, texts)
	case *anthropicAdapter:
		return nil, fmt.Errorf("anthropic does not support embeddings")
	default:
		// Custom/unknown adapters: try OpenAI-compatible path
		return embedOpenAI(ctx, endpointBaseURL, secret, model, texts)
	}
}

// embedOpenAI calls POST /v1/embeddings (OpenAI-compatible).
func embedOpenAI(ctx context.Context, endpointBaseURL, secret, model string, texts []string) (*EmbedResult, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	payload := map[string]any{
		"model": model,
		"input": texts,
	}
	out, err := postJSON(ctx, defaultClient, base+"/v1/embeddings", headers, payload)
	if err != nil {
		return nil, fmt.Errorf("embedding call failed: %w", err)
	}
	return parseOpenAIEmbeddingResponse(out, model)
}

// embedOllama calls POST /api/embed (Ollama native).
func embedOllama(ctx context.Context, endpointBaseURL, model string, texts []string) (*EmbedResult, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = ollamaDefaultBase
	}
	payload := map[string]any{
		"model": model,
		"input": texts,
	}
	out, err := postJSON(ctx, defaultClient, base+"/api/embed", nil, payload)
	if err != nil {
		return nil, fmt.Errorf("ollama embedding call failed: %w", err)
	}
	return parseOllamaEmbeddingResponse(out, model)
}

func parseOpenAIEmbeddingResponse(out map[string]any, model string) (*EmbedResult, error) {
	data, ok := out["data"].([]any)
	if !ok || len(data) == 0 {
		return nil, fmt.Errorf("no embedding data in response")
	}
	embeddings := make([][]float64, 0, len(data))
	dim := 0
	for _, item := range data {
		entry, ok := item.(map[string]any)
		if !ok {
			continue
		}
		raw, ok := entry["embedding"].([]any)
		if !ok {
			continue
		}
		vec := make([]float64, len(raw))
		for i, v := range raw {
			vec[i] = toFloat(v)
		}
		if dim == 0 {
			dim = len(vec)
		}
		embeddings = append(embeddings, vec)
	}
	if len(embeddings) == 0 {
		return nil, fmt.Errorf("no valid embeddings parsed")
	}
	if m, ok := out["model"].(string); ok && m != "" {
		model = m
	}
	return &EmbedResult{
		Embeddings: embeddings,
		Dimension:  dim,
		Model:      model,
	}, nil
}

func parseOllamaEmbeddingResponse(out map[string]any, model string) (*EmbedResult, error) {
	raw, ok := out["embeddings"].([]any)
	if !ok || len(raw) == 0 {
		return nil, fmt.Errorf("no embeddings in ollama response")
	}
	embeddings := make([][]float64, 0, len(raw))
	dim := 0
	for _, item := range raw {
		vecRaw, ok := item.([]any)
		if !ok {
			continue
		}
		vec := make([]float64, len(vecRaw))
		for i, v := range vecRaw {
			vec[i] = toFloat(v)
		}
		if dim == 0 {
			dim = len(vec)
		}
		embeddings = append(embeddings, vec)
	}
	if len(embeddings) == 0 {
		return nil, fmt.Errorf("no valid ollama embeddings parsed")
	}
	if m, ok := out["model"].(string); ok && m != "" {
		model = m
	}
	return &EmbedResult{
		Embeddings: embeddings,
		Dimension:  dim,
		Model:      model,
	}, nil
}
