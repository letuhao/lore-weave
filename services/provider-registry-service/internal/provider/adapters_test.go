package provider

import (
	"net/http"
	"testing"
)

func TestResolveAdapter(t *testing.T) {
	t.Parallel()

	client := &http.Client{}
	kinds := []string{"openai", "anthropic", "ollama", "lm_studio"}
	for _, kind := range kinds {
		kind := kind
		t.Run(kind, func(t *testing.T) {
			t.Parallel()
			adapter, err := ResolveAdapter(kind, client)
			if err != nil {
				t.Fatalf("expected adapter for %s, got error: %v", kind, err)
			}
			if adapter == nil {
				t.Fatalf("adapter is nil for %s", kind)
			}
		})
	}
}

func TestResolveAdapterCustomFallsBackToOpenAI(t *testing.T) {
	t.Parallel()

	// Custom/unknown provider kinds should resolve to OpenAI-compatible adapter
	adapter, err := ResolveAdapter("groq", &http.Client{})
	if err != nil {
		t.Fatalf("custom provider kind should not error: %v", err)
	}
	if adapter == nil {
		t.Fatal("adapter must not be nil for custom provider kind")
	}
}

func TestExtractMessages_ExplicitMessages(t *testing.T) {
	t.Parallel()

	msgs := extractMessages(map[string]any{
		"messages": []map[string]any{{"role": "user", "content": "hello"}},
	})
	if len(msgs) != 1 || msgs[0]["content"] != "hello" {
		t.Fatalf("unexpected messages: %v", msgs)
	}
}

func TestExtractMessages_Fallback(t *testing.T) {
	t.Parallel()

	msgs := extractMessages(map[string]any{})
	if len(msgs) != 1 || msgs[0]["role"] != "user" {
		t.Fatalf("expected fallback message, got: %v", msgs)
	}
}

func TestForwardOptionalChatFields_ChatTemplateKwargs(t *testing.T) {
	t.Parallel()
	// D-EXTRACTION-CONTEXT-FIX-STAGE-4 regression-lock — the
	// chat_template_kwargs passthrough MUST survive SDK → gateway →
	// adapter. Local thinking-capable models (Qwen3-thinking,
	// DeepSeek-R1, abliterated variants) rely on
	// {thinking:false} to disable reasoning-mode generation.
	input := map[string]any{
		"messages": []any{},
		"chat_template_kwargs": map[string]any{
			"thinking":         false,
			"enable_thinking":  false,
		},
	}
	body := map[string]any{}
	forwardOptionalChatFields(input, body)
	got, ok := body["chat_template_kwargs"].(map[string]any)
	if !ok {
		t.Fatalf("chat_template_kwargs missing from body: %v", body)
	}
	if got["thinking"] != false || got["enable_thinking"] != false {
		t.Errorf("unexpected chat_template_kwargs: %v", got)
	}
}

func TestForwardOptionalChatFields_ResponseFormat(t *testing.T) {
	t.Parallel()
	input := map[string]any{
		"response_format": map[string]any{"type": "json_object"},
	}
	body := map[string]any{}
	forwardOptionalChatFields(input, body)
	got, ok := body["response_format"].(map[string]any)
	if !ok || got["type"] != "json_object" {
		t.Errorf("response_format not forwarded: %v", body)
	}
}

func TestForwardOptionalChatFields_AllSamplingControls(t *testing.T) {
	t.Parallel()
	input := map[string]any{
		"reasoning_effort":  "low",
		"top_p":             0.9,
		"top_k":             40,
		"presence_penalty":  0.2,
		"frequency_penalty": 0.1,
		"seed":              42,
	}
	body := map[string]any{}
	forwardOptionalChatFields(input, body)
	for k, want := range input {
		if body[k] != want {
			t.Errorf("field %s missing or wrong: got %v want %v", k, body[k], want)
		}
	}
}

func TestForwardOptionalChatFields_SkipsAbsentFields(t *testing.T) {
	t.Parallel()
	// Empty input → body stays empty. No unknown-key pollution
	// (some OpenAI endpoints 400 on unrecognized fields).
	body := map[string]any{}
	forwardOptionalChatFields(map[string]any{}, body)
	if len(body) != 0 {
		t.Errorf("expected empty body, got: %v", body)
	}
}

func TestOpenAIIsReasoningModel(t *testing.T) {
	t.Parallel()
	for _, m := range []string{"o1", "o1-mini", "o3", "o3-mini", "o4-mini", "O1-preview"} {
		if !openaiIsReasoningModel(m) {
			t.Errorf("%q should be a reasoning (o-series) model", m)
		}
	}
	for _, m := range []string{"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4-turbo", ""} {
		if openaiIsReasoningModel(m) {
			t.Errorf("%q must NOT be treated as a reasoning model", m)
		}
	}
}

func TestStripDefaultOpenAIUnsupportedFields(t *testing.T) {
	t.Parallel()
	// Default endpoint + gpt-4o → strip BOTH reasoning_effort and
	// chat_template_kwargs (real OpenAI 400s on them).
	body := map[string]any{"reasoning_effort": "none", "chat_template_kwargs": map[string]any{}, "temperature": 0.7}
	stripDefaultOpenAIUnsupportedFields(body, "gpt-4o", "")
	if _, ok := body["reasoning_effort"]; ok {
		t.Error("reasoning_effort must be stripped for gpt-4o on the default endpoint")
	}
	if _, ok := body["chat_template_kwargs"]; ok {
		t.Error("chat_template_kwargs must be stripped on the default endpoint")
	}
	if body["temperature"] != 0.7 {
		t.Error("unrelated fields must be preserved")
	}

	// Default endpoint + o-series → KEEP reasoning_effort (the model accepts it).
	oBody := map[string]any{"reasoning_effort": "high"}
	stripDefaultOpenAIUnsupportedFields(oBody, "o3-mini", "")
	if oBody["reasoning_effort"] != "high" {
		t.Error("reasoning_effort must be kept for an o-series model")
	}

	// Custom base_url (local OpenAI-compatible) → keep BOTH (used to suppress thinking).
	cBody := map[string]any{"reasoning_effort": "none", "chat_template_kwargs": map[string]any{"enable_thinking": false}}
	stripDefaultOpenAIUnsupportedFields(cBody, "gpt-4o", "http://localhost:1234/v1")
	if _, ok := cBody["reasoning_effort"]; !ok {
		t.Error("custom base_url must keep reasoning_effort")
	}
	if _, ok := cBody["chat_template_kwargs"]; !ok {
		t.Error("custom base_url must keep chat_template_kwargs")
	}
}

func TestToFloat(t *testing.T) {
	t.Parallel()

	if toFloat(float64(3.5)) != 3.5 {
		t.Fatal("float64")
	}
	if toFloat(int(5)) != 5 {
		t.Fatal("int")
	}
	if toFloat(int64(7)) != 7 {
		t.Fatal("int64")
	}
	if toFloat(nil) != 0 {
		t.Fatal("nil")
	}
}

func TestNormalizeLmStudioBase(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		in   string
		want string
	}{
		{"empty defaults", "", lmStudioDefaultBase},
		{"trailing slash", "http://localhost:1234/", "http://localhost:1234"},
		{"bare host", "http://localhost:1234", "http://localhost:1234"},
		{"trailing v1", "http://localhost:1234/v1", "http://localhost:1234"},
		{"trailing v1 slash", "http://localhost:1234/v1/", "http://localhost:1234"},
		{"docker host", "http://host.docker.internal:1234", "http://host.docker.internal:1234"},
		{"docker host with v1", "http://host.docker.internal:1234/v1", "http://host.docker.internal:1234"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := NormalizeLmStudioBase(tc.in)
			if got != tc.want {
				t.Fatalf("NormalizeLmStudioBase(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}
