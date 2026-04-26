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

	// Stream — Phase 1a (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). Open a
	// streaming chat completion against the provider and emit canonical
	// StreamChunk events via emit. Adapters that don't support streaming
	// return ErrStreamNotSupported; the route handler maps that to 501.
	//
	// emit returning an error means the downstream caller is gone; the
	// adapter MUST stop streaming and return that error.
	Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error
}

// ErrStreamNotSupported — returned by adapters that don't yet implement
// Stream(). Route handler maps this to HTTP 501 Not Implemented.
var ErrStreamNotSupported = fmt.Errorf("streaming not supported by this provider adapter")

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
	// Limit response size to 10MB to prevent OOM
	raw, err := io.ReadAll(io.LimitReader(res.Body, 10<<20))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	if res.StatusCode >= 400 {
		return nil, fmt.Errorf("provider error %d: %s", res.StatusCode, string(raw[:min(len(raw), 200)]))
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("unmarshal: expected JSON, got %s", string(raw[:min(len(raw), 100)]))
	}
	return out, nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
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
		"model":    modelName,
		"messages": extractMessages(input),
	}
	// Policy: include max_tokens only when caller passes a positive
	// value. Caller-omitted / 0 → let the model decide (no upstream
	// cap). OpenAI accepts requests without max_tokens.
	if v, ok := input["max_tokens"]; ok {
		if mt := int(toFloat(v)); mt > 0 {
			payload["max_tokens"] = mt
		}
	}
	if v, ok := input["temperature"]; ok {
		payload["temperature"] = v
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

func (a *openaiAdapter) Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	body := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	if v, ok := input["temperature"]; ok {
		body["temperature"] = v
	}
	// Policy: max_tokens=0 means omit (let the model decide). Phase 3c
	// enforced at SDK + gateway-handler; this is the final guard for
	// callers posting directly to /internal/proxy or future SDKs.
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		body["max_tokens"] = v
	}
	if v, ok := input["tools"]; ok {
		body["tools"] = v
	}
	resp, err := openCompletionStream(ctx, a.client, base+"/v1/chat/completions", headers, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return streamOpenAICompat(ctx, resp.Body, emit)
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
	// Anthropic requires max_tokens (returns 400 if missing). Keep
	// the 8192 default for caller-omitted/0; honor positive caller
	// value when supplied.
	maxTokens := 8192
	if v, ok := input["max_tokens"]; ok {
		if mt := int(toFloat(v)); mt > 0 {
			maxTokens = mt
		}
	}
	payload := map[string]any{
		"model":      modelName,
		"messages":   extractMessages(input),
		"max_tokens": maxTokens,
	}
	if v, ok := input["temperature"]; ok {
		payload["temperature"] = v
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

// Stream — Anthropic streaming uses different SSE event names
// (content_block_delta, message_delta, message_stop) than OpenAI. Deferred
// to a follow-up cycle (Phase 1a-followup); for now this returns 501 so
// chat-service migration in Phase 1c can target lm_studio + openai-compat
// providers first.
func (a *anthropicAdapter) Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error {
	return ErrStreamNotSupported
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
	options := map[string]any{}
	if v, ok := input["temperature"]; ok {
		options["temperature"] = v
	}
	// Policy: include num_predict (Ollama's max_tokens equivalent)
	// only on positive caller value. Caller-omitted / 0 → Ollama
	// streams to natural stop.
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		options["num_predict"] = v
	}
	if len(options) > 0 {
		payload["options"] = options
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

// Stream — Ollama supports streaming via its OpenAI-compatible
// /v1/chat/completions endpoint (separate from the /api/chat NDJSON path
// used by Invoke). This implementation uses the OpenAI-compat path so it
// shares the SSE parser with openai/lm_studio.
func (a *ollamaAdapter) Stream(ctx context.Context, endpointBaseURL, _ string, modelName string, input map[string]any, emit EmitFn) error {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = ollamaDefaultBase
	}
	body := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	if v, ok := input["temperature"]; ok {
		body["temperature"] = v
	}
	// Policy: max_tokens=0 means omit (let the model decide). Phase 3c
	// enforced at SDK + gateway-handler; this is the final guard for
	// callers posting directly to /internal/proxy or future SDKs.
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		body["max_tokens"] = v
	}
	resp, err := openCompletionStream(ctx, a.client, base+"/v1/chat/completions", nil, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return streamOpenAICompat(ctx, resp.Body, emit)
}

// ── LM Studio adapter (OpenAI-compatible) ────────────────────────────────────

type lmStudioAdapter struct {
	client *http.Client
}

const lmStudioDefaultBase = "http://localhost:1234"

// NormalizeLmStudioBase strips the trailing slash AND a trailing "/v1" segment.
// Users frequently paste full OpenAI-style URLs like http://localhost:1234/v1
// into the ProvidersTab UI, but the adapter appends "/v1/chat/completions" or
// "/api/v1/models" itself. Without normalization the request becomes
// /v1/v1/chat/completions which 404s and LM Studio returns {"error": ...} body
// that downstream extract_content() can't parse. Empty input → default base.
//
// Exported so the transparent proxy in api/server.go (doProxy) can apply the
// same normalization — the proxy builds URLs as `baseURL + "/" + targetPath`
// where targetPath already starts with "v1/...", so the same /v1/v1/ duplication
// happens via that code path too.
func NormalizeLmStudioBase(endpointBaseURL string) string {
	base := strings.TrimRight(endpointBaseURL, "/")
	base = strings.TrimSuffix(base, "/v1")
	if base == "" {
		return lmStudioDefaultBase
	}
	return base
}

func (a *lmStudioAdapter) ListModels(ctx context.Context, endpointBaseURL, secret string) ([]ModelInventory, error) {
	base := NormalizeLmStudioBase(endpointBaseURL)
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
	base := NormalizeLmStudioBase(endpointBaseURL)
	payload := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	// Policy: include max_tokens only on positive caller value. Caller-
	// omitted / 0 → let the model decide. LM Studio accepts requests
	// without max_tokens (defaults to model's natural stop).
	if v, ok := input["max_tokens"]; ok {
		if mt := int(toFloat(v)); mt > 0 {
			payload["max_tokens"] = mt
		}
	}
	if v, ok := input["temperature"]; ok {
		payload["temperature"] = v
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

// Stream — LM Studio is OpenAI-compatible on /v1/chat/completions, so this
// delegates to the shared streamOpenAICompat parser. Uses NormalizeLmStudioBase
// to strip a possible trailing /v1 (mirrors Invoke).
func (a *lmStudioAdapter) Stream(ctx context.Context, endpointBaseURL, secret, modelName string, input map[string]any, emit EmitFn) error {
	base := NormalizeLmStudioBase(endpointBaseURL)
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	body := map[string]any{
		"model":    modelName,
		"messages": extractMessages(input),
	}
	if v, ok := input["temperature"]; ok {
		body["temperature"] = v
	}
	// Policy: max_tokens=0 means omit (let the model decide). Phase 3c
	// enforced at SDK + gateway-handler; this is the final guard for
	// callers posting directly to /internal/proxy or future SDKs.
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		body["max_tokens"] = v
	}
	resp, err := openCompletionStream(ctx, a.client, base+"/v1/chat/completions", headers, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return streamOpenAICompat(ctx, resp.Body, emit)
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
