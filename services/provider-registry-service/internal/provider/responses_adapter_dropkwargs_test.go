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

// realOpenAICloud must match BOTH the pre-default empty URL AND the openaiBaseURL the
// openai adapter defaults it to before streaming. The first pass at the reasoning-strip
// fix tested base=="" only — but adapters.go rewrites "" → openaiBaseURL, so the strip
// never fired and real OpenAI kept 400ing on gpt-4o-mini. This locks that regression.
func TestRealOpenAICloud(t *testing.T) {
	for _, c := range []struct {
		base string
		want bool
	}{
		{"", true},                             // pre-default (other callers)
		{openaiBaseURL, true},                  // what the openai adapter actually passes
		{"https://api.openai.com/", true},      // trailing slash tolerated
		{"http://192.168.1.50:1234/v1", false}, // LM Studio local
		{"https://myorg.openai.azure.com", false},
	} {
		if got := realOpenAICloud(c.base); got != c.want {
			t.Errorf("realOpenAICloud(%q) = %v, want %v", c.base, got, c.want)
		}
	}
}

// The end-to-end strip decision streamViaResponses applies: drop the nested reasoning
// object ONLY for real OpenAI + a non-reasoning model. o-series keeps it (they require
// it); LM Studio keeps it (thinking control). This is the exact predicate whose wrong
// base check let the gpt-4o-mini /responses 400 persist.
func TestResponsesReasoningStripDecision(t *testing.T) {
	strip := func(base, model string) bool {
		return realOpenAICloud(base) && !openaiIsReasoningModel(model)
	}
	if !strip(openaiBaseURL, "gpt-4o-mini") {
		t.Error("real OpenAI + gpt-4o-mini MUST strip reasoning (the 400 fix)")
	}
	if strip(openaiBaseURL, "o3-mini") {
		t.Error("o-series reasoning model must KEEP reasoning even on real OpenAI")
	}
	if strip("http://localhost:1234/v1", "gpt-4o-mini") {
		t.Error("LM Studio custom base must KEEP reasoning for thinking control")
	}
}
