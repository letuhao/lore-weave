package provider

import "testing"

func toolsWith(names ...string) []map[string]any {
	out := make([]map[string]any, 0, len(names))
	for _, n := range names {
		out = append(out, map[string]any{"name": n, "input_schema": map[string]any{"type": "object"}})
	}
	return out
}

func hasCacheControl(m map[string]any) bool {
	cc, ok := m["cache_control"].(map[string]any)
	return ok && cc["type"] == "ephemeral"
}

func TestAnthropicCache_MarksLastToolAndSystem_ByDefault(t *testing.T) {
	// default: LLM_PROMPT_CACHE unset ⇒ enabled
	body := map[string]any{
		"tools":  toolsWith("glossary_search", "glossary_list", "book_get"),
		"system": "You are a helpful writing assistant.",
	}
	applyAnthropicPromptCache(body)

	tools := body["tools"].([]map[string]any)
	if hasCacheControl(tools[0]) || hasCacheControl(tools[1]) {
		t.Fatal("only the LAST tool should carry cache_control")
	}
	if !hasCacheControl(tools[len(tools)-1]) {
		t.Fatal("last tool must carry cache_control (caches the whole tools array)")
	}
	// system string → converted to a block list with cache_control on it
	sysBlocks, ok := body["system"].([]map[string]any)
	if !ok || len(sysBlocks) != 1 || !hasCacheControl(sysBlocks[0]) {
		t.Fatalf("system must become a cache_control-marked text block, got %#v", body["system"])
	}
	if sysBlocks[0]["text"] != "You are a helpful writing assistant." {
		t.Fatal("system text must be preserved")
	}
}

func TestAnthropicCache_NoTools_NoOp(t *testing.T) {
	body := map[string]any{"system": "hi"}
	applyAnthropicPromptCache(body)
	if _, ok := body["system"].([]map[string]any); ok {
		t.Fatal("with no tools there is no reusable prefix — system must be left untouched")
	}
}

func TestAnthropicCache_KillSwitchDisables(t *testing.T) {
	t.Setenv("LLM_PROMPT_CACHE", "0")
	body := map[string]any{"tools": toolsWith("a", "b"), "system": "s"}
	applyAnthropicPromptCache(body)
	tools := body["tools"].([]map[string]any)
	if hasCacheControl(tools[len(tools)-1]) {
		t.Fatal("LLM_PROMPT_CACHE=0 must disable caching")
	}
	if _, ok := body["system"].(string); !ok {
		t.Fatal("kill-switch: system must stay an untouched string")
	}
}

func TestAnthropicCache_SystemBlockList_MarksLast(t *testing.T) {
	body := map[string]any{
		"tools": toolsWith("a"),
		"system": []map[string]any{
			{"type": "text", "text": "one"},
			{"type": "text", "text": "two"},
		},
	}
	applyAnthropicPromptCache(body)
	sys := body["system"].([]map[string]any)
	if hasCacheControl(sys[0]) || !hasCacheControl(sys[1]) {
		t.Fatal("only the last system block should be marked")
	}
}

func TestLocalCache_OptInAndLocalOnly(t *testing.T) {
	// default (LOCAL_PROMPT_CACHE unset) → never set, even for a local base_url
	body := map[string]any{}
	applyLocalPromptCache(body, "http://localhost:1234")
	if _, ok := body["cache_prompt"]; ok {
		t.Fatal("local cache is OPT-IN — must not set cache_prompt by default")
	}

	// opt-in ON + local base_url → set
	t.Setenv("LOCAL_PROMPT_CACHE", "1")
	body = map[string]any{}
	applyLocalPromptCache(body, "http://localhost:1234")
	if body["cache_prompt"] != true {
		t.Fatal("opt-in + local base_url must set cache_prompt=true")
	}

	// opt-in ON but EMPTY base_url (real OpenAI) → must NOT set (OpenAI 400s on unknown fields)
	body = map[string]any{}
	applyLocalPromptCache(body, "")
	if _, ok := body["cache_prompt"]; ok {
		t.Fatal("must never send cache_prompt to the real OpenAI cloud (empty base_url)")
	}
}
