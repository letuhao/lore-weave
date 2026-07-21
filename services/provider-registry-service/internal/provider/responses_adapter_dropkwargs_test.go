package provider

import "testing"

// Regression: the Responses API path must NOT forward chat_template_kwargs. Real
// OpenAI's /v1/responses REJECTS it (HTTP 400 "Unknown parameter") — this broke
// EVERY OpenAI chat — and LM Studio's /v1/responses ignores it, so dropping it is
// correct for every provider (the /v1/chat/completions adapter already drops it).
func TestBuildResponsesBody_DropsChatTemplateKwargs(t *testing.T) {
	input := map[string]any{
		"messages":             []any{map[string]any{"role": "user", "content": "hi"}},
		"reasoning_effort":     "none",
		"chat_template_kwargs": map[string]any{"enable_thinking": false, "thinking": false},
	}
	body := buildResponsesBody("gpt-4o-mini", input)

	if _, present := body["chat_template_kwargs"]; present {
		t.Fatalf("chat_template_kwargs must NOT reach the Responses API (OpenAI 400s): %v", body)
	}
	// thinking-off still expressed via the NESTED reasoning.effort (the Responses way)
	rz, ok := body["reasoning"].(map[string]any)
	if !ok || rz["effort"] == nil {
		t.Errorf("reasoning.effort should carry thinking-off, got reasoning=%v", body["reasoning"])
	}
}
