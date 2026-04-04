package provider

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

//go:embed preconfig_openai.json
var openaiPreconfigJSON []byte

//go:embed preconfig_anthropic.json
var anthropicPreconfigJSON []byte

func loadPreconfig(data []byte) []ModelInventory {
	type entry struct {
		ProviderModelName string         `json:"provider_model_name"`
		DisplayName       string         `json:"display_name"`
		Capability        string         `json:"capability"`
		ContextLength     *int           `json:"context_length"`
		IsRecommended     bool           `json:"is_recommended"`
		CapabilityFlags   map[string]any `json:"capability_flags"`
	}
	var entries []entry
	if err := json.Unmarshal(data, &entries); err != nil {
		return nil
	}
	out := make([]ModelInventory, len(entries))
	for i, e := range entries {
		flags := e.CapabilityFlags
		if flags == nil {
			flags = map[string]any{}
		}
		flags["_capability"] = e.Capability
		flags["_display_name"] = e.DisplayName
		flags["_is_recommended"] = e.IsRecommended
		out[i] = ModelInventory{
			ProviderModelName: e.ProviderModelName,
			ContextLength:     e.ContextLength,
			CapabilityFlags:   flags,
		}
	}
	return out
}

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

func getJSON(ctx context.Context, client *http.Client, url string, headers map[string]string) (map[string]any, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("new request: %w", err)
	}
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
		return nil, fmt.Errorf("provider error %d", res.StatusCode)
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

func (a *openaiAdapter) ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	out, err := getJSON(ctx, a.client, base+"/v1/models", headers)
	if err != nil {
		// Fallback to static inventory if API call fails
		return a.staticInventory, nil
	}
	data, ok := out["data"].([]any)
	if !ok || len(data) == 0 {
		return a.staticInventory, nil
	}
	return parseOpenAIModels(data), nil
}

func parseOpenAIModels(data []any) []ModelInventory {
	var models []ModelInventory
	for _, item := range data {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		id, _ := m["id"].(string)
		if id == "" {
			continue
		}
		cap := classifyOpenAIModel(id)
		flags := map[string]any{
			"_capability":   cap,
			"_display_name": id,
		}
		// Detect thinking models
		if strings.HasPrefix(id, "o1") || strings.HasPrefix(id, "o3") || strings.HasPrefix(id, "o4") {
			flags["thinking"] = true
		}
		models = append(models, ModelInventory{
			ProviderModelName: id,
			CapabilityFlags:   flags,
		})
	}
	return models
}

func classifyOpenAIModel(id string) string {
	switch {
	case strings.Contains(id, "embedding") || strings.Contains(id, "ada-002"):
		return "embedding"
	case strings.Contains(id, "dall-e") || strings.Contains(id, "gpt-image") || strings.Contains(id, "sora") || id == "chatgpt-image-latest":
		return "image_gen"
	case strings.Contains(id, "tts") || strings.Contains(id, "whisper"):
		return "tts"
	case strings.Contains(id, "audio") || strings.Contains(id, "realtime"):
		return "audio"
	case strings.Contains(id, "transcribe"):
		return "stt"
	case strings.Contains(id, "moderation"):
		return "moderation"
	case strings.HasPrefix(id, "davinci") || strings.HasPrefix(id, "babbage"):
		return "completion"
	default:
		return "chat"
	}
}

func (a *openaiAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	payload := map[string]any{
		"model":      modelName,
		"messages":   extractMessages(input),
		"max_tokens": 8192,
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

func (a *anthropicAdapter) ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = anthropicBaseURL
	}
	headers := map[string]string{
		"x-api-key":         secret,
		"anthropic-version": "2023-06-01",
	}
	out, err := getJSON(ctx, a.client, base+"/v1/models", headers)
	if err != nil {
		return a.staticInventory, nil
	}
	data, ok := out["data"].([]any)
	if !ok || len(data) == 0 {
		return a.staticInventory, nil
	}
	return parseAnthropicModels(data), nil
}

func parseAnthropicModels(data []any) []ModelInventory {
	var models []ModelInventory
	for _, item := range data {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		id, _ := m["id"].(string)
		displayName, _ := m["display_name"].(string)
		if id == "" {
			continue
		}
		if displayName == "" {
			displayName = id
		}
		flags := map[string]any{
			"_capability":   "chat",
			"_display_name": displayName,
		}
		// Parse context length
		var ctxLen *int
		if v, ok := m["max_input_tokens"].(float64); ok && v > 0 {
			n := int(v)
			ctxLen = &n
		}
		// Parse rich capabilities
		if caps, ok := m["capabilities"].(map[string]any); ok {
			if isSupported(caps, "thinking") {
				flags["thinking"] = true
			}
			if isSupported(caps, "image_input") {
				flags["vision"] = true
			}
			if isSupported(caps, "pdf_input") {
				flags["pdf"] = true
			}
			if isSupported(caps, "code_execution") {
				flags["code_execution"] = true
			}
			if isSupported(caps, "structured_outputs") {
				flags["structured_outputs"] = true
			}
		}
		models = append(models, ModelInventory{
			ProviderModelName: id,
			ContextLength:     ctxLen,
			CapabilityFlags:   flags,
		})
	}
	return models
}

func isSupported(caps map[string]any, key string) bool {
	if v, ok := caps[key].(map[string]any); ok {
		if sup, ok := v["supported"].(bool); ok {
			return sup
		}
	}
	return false
}

func (a *anthropicAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = anthropicBaseURL
	}
	payload := map[string]any{
		"model":      modelName,
		"messages":   extractMessages(input),
		"max_tokens": 8192,
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

func (a *ollamaAdapter) ListModels(ctx context.Context, endpointBaseURL, _ string) ([]ModelInventory, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = ollamaDefaultBase
	}
	// Ollama exposes GET /api/tags to list local models
	out, err := getJSON(ctx, a.client, base+"/api/tags", nil)
	if err != nil {
		return nil, fmt.Errorf("list models: %w", err)
	}
	// Response: {"models": [{"name": "llama3:latest", "size": N, "parameter_size": "8B", ...}]}
	var models []ModelInventory
	if mList, ok := out["models"].([]any); ok {
		for _, item := range mList {
			m, ok := item.(map[string]any)
			if !ok {
				continue
			}
			name, _ := m["name"].(string)
			if name == "" {
				continue
			}
			cap := "chat"
			if strings.Contains(name, "embed") {
				cap = "embedding"
			}
			inv := ModelInventory{
				ProviderModelName: name,
				CapabilityFlags:   map[string]any{"_capability": cap, "_display_name": name},
			}
			models = append(models, inv)
		}
	}
	return models, nil
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

func (a *lmStudioAdapter) ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = lmStudioDefaultBase
	}
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	// Try LM Studio native API first (richer data: context_length, type, capabilities)
	// GET /api/v1/models → {"models": [{key, type, display_name, max_context_length, ...}]}
	out, err := getJSON(ctx, a.client, base+"/api/v1/models", headers)
	if err == nil {
		if mList, ok := out["models"].([]any); ok && len(mList) > 0 {
			return parseLMStudioNativeModels(mList), nil
		}
	}
	// Fallback to OpenAI-compatible GET /v1/models → {"data": [{id, ...}]}
	out, err = getJSON(ctx, a.client, base+"/v1/models", headers)
	if err != nil {
		return nil, fmt.Errorf("list models: %w", err)
	}
	var models []ModelInventory
	if data, ok := out["data"].([]any); ok {
		for _, item := range data {
			m, ok := item.(map[string]any)
			if !ok {
				continue
			}
			id, _ := m["id"].(string)
			if id == "" {
				continue
			}
			models = append(models, ModelInventory{
				ProviderModelName: id,
				CapabilityFlags:   map[string]any{"_capability": "chat", "_display_name": id},
			})
		}
	}
	return models, nil
}

func parseLMStudioNativeModels(mList []any) []ModelInventory {
	var models []ModelInventory
	for _, item := range mList {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		key, _ := m["key"].(string)
		if key == "" {
			continue
		}
		modelType, _ := m["type"].(string)
		displayName, _ := m["display_name"].(string)
		if displayName == "" {
			displayName = key
		}
		var ctxLen *int
		if mcl, ok := m["max_context_length"].(float64); ok && mcl > 0 {
			v := int(mcl)
			ctxLen = &v
		}
		cap := "chat"
		if modelType == "embedding" || modelType == "text-embedding" {
			cap = "embedding"
		} else if strings.Contains(modelType, "rerank") || strings.Contains(key, "rerank") {
			cap = "reranker"
		}
		flags := map[string]any{
			"_capability":   cap,
			"_display_name": displayName,
		}
		// Parse capabilities from LM Studio native format
		if caps, ok := m["capabilities"].(map[string]any); ok {
			if v, ok := caps["vision"].(bool); ok && v {
				flags["vision"] = true
			}
			if v, ok := caps["trained_for_tool_use"].(bool); ok && v {
				flags["tool_use"] = true
			}
		}
		if params, ok := m["params_string"].(string); ok && params != "" {
			flags["_params"] = params
		}
		models = append(models, ModelInventory{
			ProviderModelName: key,
			ContextLength:     ctxLen,
			CapabilityFlags:   flags,
		})
	}
	return models
}

func (a *lmStudioAdapter) Invoke(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any) (map[string]any, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = lmStudioDefaultBase
	}
	payload := map[string]any{
		"model":      modelName,
		"messages":   extractMessages(input),
		"max_tokens": 8192,
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
	switch providerKind {
	case "openai":
		return &openaiAdapter{
			client:          client,
			staticInventory: loadPreconfig(openaiPreconfigJSON),
		}, nil
	case "anthropic":
		return &anthropicAdapter{
			client:          client,
			staticInventory: loadPreconfig(anthropicPreconfigJSON),
		}, nil
	case "ollama":
		return &ollamaAdapter{client: client}, nil
	case "lm_studio":
		return &lmStudioAdapter{client: client}, nil
	default:
		// Custom providers: use OpenAI-compatible adapter with empty inventory
		// (user adds models manually or inventory syncs via /v1/models endpoint)
		return &openaiAdapter{
			client:          client,
			staticInventory: []ModelInventory{},
		}, nil
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
