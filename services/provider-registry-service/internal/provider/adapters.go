package provider

import (
	"context"
	"fmt"
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

type staticAdapter struct {
	models []ModelInventory
}

func (a *staticAdapter) ListModels(_ context.Context, _ string, _ string) ([]ModelInventory, error) {
	return a.models, nil
}

func (a *staticAdapter) Invoke(_ context.Context, _ string, _ string, modelName string, input map[string]any) (map[string]any, Usage, error) {
	userText := ""
	if v, ok := input["prompt"].(string); ok {
		userText = v
	}
	if userText == "" {
		if v, ok := input["input"].(string); ok {
			userText = v
		}
	}
	output := map[string]any{
		"model":  modelName,
		"result": fmt.Sprintf("simulated response for: %s", userText),
	}
	inTokens := len(strings.Fields(userText))
	if inTokens == 0 {
		inTokens = 1
	}
	outTokens := inTokens + 8
	return output, Usage{InputTokens: inTokens, OutputTokens: outTokens}, nil
}

func (a *staticAdapter) HealthCheck(_ context.Context, _ string, _ string) error {
	return nil
}

func OpenAIAdapter() Adapter {
	ctx16 := 16384
	ctx32 := 32768
	return &staticAdapter{models: []ModelInventory{
		{ProviderModelName: "gpt-4o-mini", ContextLength: &ctx16, CapabilityFlags: map[string]any{"chat": true, "tool_calling": true}},
		{ProviderModelName: "gpt-4.1", ContextLength: &ctx32, CapabilityFlags: map[string]any{"chat": true, "tool_calling": true}},
	}}
}

func AnthropicAdapter() Adapter {
	ctx200 := 200000
	return &staticAdapter{models: []ModelInventory{
		{ProviderModelName: "claude-3-5-sonnet", ContextLength: &ctx200, CapabilityFlags: map[string]any{"chat": true, "tool_calling": true}},
	}}
}

func OllamaAdapter() Adapter {
	return &staticAdapter{models: []ModelInventory{}}
}

func LMStudioAdapter() Adapter {
	return &staticAdapter{models: []ModelInventory{}}
}

func ResolveAdapter(providerKind string) (Adapter, error) {
	switch providerKind {
	case "openai":
		return OpenAIAdapter(), nil
	case "anthropic":
		return AnthropicAdapter(), nil
	case "ollama":
		return OllamaAdapter(), nil
	case "lm_studio":
		return LMStudioAdapter(), nil
	default:
		return nil, fmt.Errorf("unknown provider_kind")
	}
}
