package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

type Adapter interface {
	ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error)
	Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error)
	HealthCheck(ctx context.Context, endpointBaseURL, secret string) error
}

type ModelInventory struct {
	ProviderModelName string         `json:"provider_model_name"`
	ContextLength     *int           `json:"context_length,omitempty"`
	CapabilityFlags   map[string]any `json:"capability_flags"`
}

type Usage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
}

// ── helpers ───────────────────────────────────────────────────────────────────

func postJSON(ctx context.Context, client *http.Client, url string, headers map[string]string, body any) (map[string]any, error) {
	b, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(b))
	if err != nil {
		return nil, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	res, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http: %w", err)
	}
	defer res.Body.Close()
	raw, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("unmarshal (status %d): %s", res.StatusCode, string(raw))
	}
	if res.StatusCode >= 400 {
		msg := ""
		if e, ok := out["error"]; ok {
			msg = fmt.Sprintf("%v", e)
		}
		return nil, fmt.Errorf("provider error %d: %s", res.StatusCode, msg)
	}
	return out, nil
}

func extractMessages(input map[string]any) []map[string]any {
	if v, ok := input["messages"]; ok {
		if msgs, ok := v.([]map[string]any); ok {
			return msgs
		}
		// handle []any (from JSON decode)
		if raw, ok := v.([]any); ok {
			out := make([]map[string]any, 0, len(raw))
			for _, item := range raw {
				if m, ok := item.(map[string]any); ok {
					out = append(out, m)
				}
			}
			return out
		}
	}
	return []map[string]any{{"role": "user", "content": "Hi"}}
}

// ── OpenAI adapter ────────────────────────────────────────────────────────────

type openaiAdapter struct {
	client         *http.Client
	staticInventory []ModelInventory
}

const openaiBaseURL = "https://api.openai.com"

func (a *openaiAdapter) ListModels(_ context.Context, _ string, _ string) ([]ModelInventory, error) {
	return a.staticInventory, nil
}

func (a *openaiAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	payload := map[string]any{
		"model":      modelName,
		"messages":   extractMessages(input),
		"max_tokens": 512,
	}
	out, err := postJSON(ctx, a.client, base+"/v1/chat/completions",
		map[string]string{"Authorization": "Bearer " + secret},
		payload,
	)
	if err != nil {
		return nil, Usage{}, err
	}
	var usage Usage
	if u, ok := out["usage"].(map[string]any); ok {
		usage.InputTokens = int(toFloat(u["prompt_tokens"]))
		usage.OutputTokens = int(toFloat(u["completion_tokens"]))
	}
	return out, usage, nil
}

func (a *openaiAdapter) HealthCheck(ctx context.Context, endpointBaseURL, secret string) error {
	_, _, err := a.Invoke(ctx, endpointBaseURL, secret, "gpt-4o-mini",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "Hi"}}})
	return err
}

// ── Anthropic adapter ─────────────────────────────────────────────────────────

type anthropicAdapter struct {
	client         *http.Client
	staticInventory []ModelInventory
}

const anthropicBaseURL = "https://api.anthropic.com"

func (a *anthropicAdapter) ListModels(_ context.Context, _ string, _ string) ([]ModelInventory, error) {
	return a.staticInventory, nil
}

func (a *anthropicAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = anthropicBaseURL
	}
	payload := map[string]any{
		"model":      modelName,
		"messages":   extractMessages(input),
		"max_tokens": 512,
	}
	out, err := postJSON(ctx, a.client, base+"/v1/messages",
		map[string]string{
			"x-api-key":         secret,
			"anthropic-version": "2023-06-01",
		},
		payload,
	)
	if err != nil {
		return nil, Usage{}, err
	}
	var usage Usage
	if u, ok := out["usage"].(map[string]any); ok {
		usage.InputTokens = int(toFloat(u["input_tokens"]))
		usage.OutputTokens = int(toFloat(u["output_tokens"]))
	}
	return out, usage, nil
}

func (a *anthropicAdapter) HealthCheck(ctx context.Context, endpointBaseURL, secret string) error {
	_, _, err := a.Invoke(ctx, endpointBaseURL, secret, "claude-3-5-sonnet-20241022",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "Hi"}}})
	return err
}

// ── Ollama adapter ────────────────────────────────────────────────────────────

type ollamaAdapter struct {
	client *http.Client
}

const ollamaDefaultBase = "http://localhost:11434"

func (a *ollamaAdapter) ListModels(_ context.Context, _ string, _ string) ([]ModelInventory, error) {
	return []ModelInventory{}, nil
}

func (a *ollamaAdapter) Invoke(ctx context.Context, endpointBaseURL, _ string, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = ollamaDefaultBase
	}
	payload := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
		"stream":   false,
	}
	out, err := postJSON(ctx, a.client, base+"/api/chat", nil, payload)
	if err != nil {
		return nil, Usage{}, err
	}
	var usage Usage
	usage.InputTokens = int(toFloat(out["prompt_eval_count"]))
	usage.OutputTokens = int(toFloat(out["eval_count"]))
	return out, usage, nil
}

func (a *ollamaAdapter) HealthCheck(ctx context.Context, endpointBaseURL, secret string) error {
	_, _, err := a.Invoke(ctx, endpointBaseURL, secret, "",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "Hi"}}})
	return err
}

// ── LM Studio adapter (OpenAI-compatible) ────────────────────────────────────

type lmStudioAdapter struct {
	client *http.Client
}

const lmStudioDefaultBase = "http://localhost:1234"

func (a *lmStudioAdapter) ListModels(_ context.Context, _ string, _ string) ([]ModelInventory, error) {
	return []ModelInventory{}, nil
}

func (a *lmStudioAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = lmStudioDefaultBase
	}
	payload := map[string]any{
		"model":      modelName,
		"messages":   extractMessages(input),
		"max_tokens": 512,
	}
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	out, err := postJSON(ctx, a.client, base+"/v1/chat/completions", headers, payload)
	if err != nil {
		return nil, Usage{}, err
	}
	var usage Usage
	if u, ok := out["usage"].(map[string]any); ok {
		usage.InputTokens = int(toFloat(u["prompt_tokens"]))
		usage.OutputTokens = int(toFloat(u["completion_tokens"]))
	}
	return out, usage, nil
}

func (a *lmStudioAdapter) HealthCheck(ctx context.Context, endpointBaseURL, secret string) error {
	_, _, err := a.Invoke(ctx, endpointBaseURL, secret, "",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "Hi"}}})
	return err
}

// ── factory ───────────────────────────────────────────────────────────────────

func ResolveAdapter(providerKind string, client *http.Client) (Adapter, error) {
	ctx16 := 16384
	ctx32 := 32768
	ctx200 := 200000
	switch providerKind {
	case "openai":
		return &openaiAdapter{
			client: client,
			staticInventory: []ModelInventory{
				{ProviderModelName: "gpt-4o-mini", ContextLength: &ctx16, CapabilityFlags: map[string]any{"chat": true, "tool_calling": true}},
				{ProviderModelName: "gpt-4.1", ContextLength: &ctx32, CapabilityFlags: map[string]any{"chat": true, "tool_calling": true}},
			},
		}, nil
	case "anthropic":
		return &anthropicAdapter{
			client: client,
			staticInventory: []ModelInventory{
				{ProviderModelName: "claude-3-5-sonnet-20241022", ContextLength: &ctx200, CapabilityFlags: map[string]any{"chat": true, "tool_calling": true}},
			},
		}, nil
	case "ollama":
		return &ollamaAdapter{client: client}, nil
	case "lm_studio":
		return &lmStudioAdapter{client: client}, nil
	default:
		return nil, fmt.Errorf("unknown provider_kind: %s", providerKind)
	}
}

func toFloat(v any) float64 {
	if v == nil {
		return 0
	}
	switch x := v.(type) {
	case float64:
		return x
	case int:
		return float64(x)
	case int64:
		return float64(x)
	}
	return 0
}
