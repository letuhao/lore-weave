package provider

import "testing"

func TestCapabilitiesFor(t *testing.T) {
	cases := []struct {
		kind                                        string
		cacheControl, responsesAPI, autoPrefixCache bool
	}{
		{"anthropic", true, false, false},
		{"openai", false, true, true},
		{"lm_studio", false, true, true},
		{"ollama", false, false, true},
		// custom / vLLM / openai-compat: auto prefix cache only, no Responses API.
		{"vllm", false, false, true},
		{"my-custom-endpoint", false, false, true},
		{"", false, false, true},
	}
	for _, c := range cases {
		got := CapabilitiesFor(c.kind)
		if got.PromptCacheControl != c.cacheControl ||
			got.ResponsesAPI != c.responsesAPI ||
			got.AutoPrefixCache != c.autoPrefixCache {
			t.Errorf("CapabilitiesFor(%q) = %+v; want cacheControl=%v responsesAPI=%v autoPrefix=%v",
				c.kind, got, c.cacheControl, c.responsesAPI, c.autoPrefixCache)
		}
	}
}

func TestCapabilities_AsMap_LockstepWithStruct(t *testing.T) {
	// The wire map keys are the contract chat-service reads — assert all three are present.
	m := ProviderCapabilities{PromptCacheControl: true, ResponsesAPI: true, AutoPrefixCache: true}.AsMap()
	for _, k := range []string{"prompt_cache_control", "responses_api", "auto_prefix_cache"} {
		if v, ok := m[k]; !ok || !v {
			t.Errorf("AsMap missing/false key %q: %+v", k, m)
		}
	}
	if len(m) != 3 {
		t.Errorf("AsMap should carry exactly 3 keys, got %d: %+v", len(m), m)
	}
}
