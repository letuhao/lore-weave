package provider

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func toolsWith(names ...string) []map[string]any {
	out := make([]map[string]any, 0, len(names))
	for _, n := range names {
		out = append(out, map[string]any{"name": n, "input_schema": map[string]any{"type": "object"}})
	}
	return out
}

// bigTools returns a tool set whose marshaled JSON clears anthropicCacheMinChars,
// so applyAnthropicPromptCache actually marks it (the small toolsWith is used for
// the below-minimum no-op case).
func bigTools(names ...string) []map[string]any {
	pad := strings.Repeat("x", 4200) // one padded tool alone clears anthropicCacheMinChars
	out := make([]map[string]any, 0, len(names))
	for _, n := range names {
		out = append(out, map[string]any{
			"name":         n,
			"description":  pad,
			"input_schema": map[string]any{"type": "object"},
		})
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
		"tools":  bigTools("glossary_search", "glossary_list", "book_get"),
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
	body := map[string]any{"tools": bigTools("a", "b"), "system": "s"}
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
		"tools": bigTools("a"),
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

func TestAnthropicCache_BelowMinimumTools_NotMarked(t *testing.T) {
	// a trivially small tool set is below the cache minimum → don't spend a breakpoint
	body := map[string]any{
		"tools":  toolsWith("a"), // tiny — well under anthropicCacheMinChars
		"system": "short system",
	}
	applyAnthropicPromptCache(body)
	tools := body["tools"].([]map[string]any)
	if hasCacheControl(tools[len(tools)-1]) {
		t.Fatal("below-minimum tools must NOT be marked (no-op breakpoint)")
	}
	if _, ok := body["system"].(string); !ok {
		t.Fatal("below-minimum: system must stay an untouched string")
	}
}

// #4 wiring — prove the ADAPTERS actually call the cache helpers (not just that
// the helpers work in isolation). A mock upstream captures the outgoing body.

func captureRequestBody(t *testing.T, handler func(body map[string]any)) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		var body map[string]any
		_ = json.Unmarshal(raw, &body)
		handler(body)
		w.Header().Set("Content-Type", "text/event-stream")
		// minimal Anthropic-style stream so the adapter finishes cleanly
		_, _ = io.WriteString(w, "event: message_start\ndata: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":1}}}\n\nevent: message_delta\ndata: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"end_turn\"},\"usage\":{\"output_tokens\":1}}\n\nevent: message_stop\ndata: {\"type\":\"message_stop\"}\n\n")
	}))
}

func TestAnthropicAdapter_Stream_WiresCacheControl(t *testing.T) {
	var got map[string]any
	srv := captureRequestBody(t, func(b map[string]any) { got = b })
	defer srv.Close()

	a := &anthropicAdapter{client: srv.Client()}
	toolsIn := make([]any, 0)
	for _, td := range bigTools("glossary_search", "book_get") {
		toolsIn = append(toolsIn, map[string]any{"type": "function", "function": map[string]any{
			"name": td["name"], "description": td["description"],
			"parameters": map[string]any{"type": "object"},
		}})
	}
	input := map[string]any{
		"messages": []any{map[string]any{"role": "user", "content": "hi"}},
		"system":   "sys",
		"tools":    toolsIn,
	}
	_ = a.Stream(context.Background(), srv.URL, "sk", "claude-x", input, func(StreamChunk) error { return nil })

	tools, _ := got["tools"].([]any)
	if len(tools) == 0 {
		t.Fatal("adapter did not forward tools")
	}
	last, _ := tools[len(tools)-1].(map[string]any)
	if _, ok := last["cache_control"]; !ok {
		t.Fatal("adapter did not wire cache_control onto the last tool")
	}
	if _, ok := got["system"].([]any); !ok {
		t.Fatal("adapter did not convert system into a cache_control block list")
	}
}

func TestLmStudioAdapter_Stream_NeverSendsCachePrompt(t *testing.T) {
	// LM Studio caches automatically server-side and IGNORES cache_prompt on its
	// chat endpoint (live-verified) — so we send nothing, same as OpenAI/vLLM.
	var got map[string]any
	srv := captureRequestBody(t, func(b map[string]any) { got = b })
	defer srv.Close()

	a := &lmStudioAdapter{client: srv.Client()}
	input := map[string]any{"messages": []any{map[string]any{"role": "user", "content": "hi"}}}
	_ = a.Stream(context.Background(), srv.URL, "", "local-model", input, func(StreamChunk) error { return nil })

	if _, ok := got["cache_prompt"]; ok {
		t.Fatal("LM Studio ignores cache_prompt on chat/completions — must not send it")
	}
}

func TestOpenAIAdapter_Stream_NeverSendsCachePrompt(t *testing.T) {
	// vLLM / OpenAI go through openaiAdapter and 400 on unknown fields — it must
	// NEVER send cache_prompt, even to a custom (local) base_url.
	var got map[string]any
	srv := captureRequestBody(t, func(b map[string]any) { got = b })
	defer srv.Close()

	a := &openaiAdapter{client: srv.Client()}
	input := map[string]any{"messages": []any{map[string]any{"role": "user", "content": "hi"}}}
	_ = a.Stream(context.Background(), srv.URL, "sk", "gpt-x", input, func(StreamChunk) error { return nil })

	if _, ok := got["cache_prompt"]; ok {
		t.Fatal("openai adapter must never send cache_prompt (vLLM/OpenAI 400 on it)")
	}
}
