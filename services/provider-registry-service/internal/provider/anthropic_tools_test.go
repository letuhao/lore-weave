package provider

// anthropic_tools_test.go — Phase K21-B / D12. Coverage for the
// OpenAI→Anthropic tools / tool_choice / messages conversion.

import (
	"reflect"
	"testing"
)

// ── tools array conversion ────────────────────────────────────────────

func TestConvertAnthropicTools_OpenAIShape(t *testing.T) {
	t.Parallel()

	// []any is the common JSON-decoded shape.
	in := []any{
		map[string]any{
			"type": "function",
			"function": map[string]any{
				"name":        "memory_search",
				"description": "Search the knowledge graph",
				"parameters": map[string]any{
					"type":       "object",
					"properties": map[string]any{"query": map[string]any{"type": "string"}},
				},
			},
		},
	}
	got := convertAnthropicTools(in)
	if len(got) != 1 {
		t.Fatalf("expected 1 tool, got %d: %v", len(got), got)
	}
	tool := got[0]
	if tool["name"] != "memory_search" {
		t.Errorf("name = %v, want memory_search", tool["name"])
	}
	if tool["description"] != "Search the knowledge graph" {
		t.Errorf("description = %v", tool["description"])
	}
	schema, ok := tool["input_schema"].(map[string]any)
	if !ok {
		t.Fatalf("input_schema not a map: %T", tool["input_schema"])
	}
	if schema["type"] != "object" {
		t.Errorf("input_schema.type = %v, want object", schema["type"])
	}
	// The OpenAI key `parameters` must NOT survive — Anthropic uses input_schema.
	if _, leaked := tool["parameters"]; leaked {
		t.Error("`parameters` key leaked into the Anthropic tool")
	}
	if _, leaked := tool["type"]; leaked {
		t.Error("`type` key leaked into the Anthropic tool")
	}
}

func TestConvertAnthropicTools_TypedMapSlice(t *testing.T) {
	t.Parallel()

	// []map[string]any must work identically to []any.
	in := []map[string]any{
		{"type": "function", "function": map[string]any{"name": "t1"}},
		{"type": "function", "function": map[string]any{"name": "t2"}},
	}
	got := convertAnthropicTools(in)
	if len(got) != 2 || got[0]["name"] != "t1" || got[1]["name"] != "t2" {
		t.Fatalf("unexpected conversion: %v", got)
	}
	// Missing `parameters` → default empty-object schema.
	if s, _ := got[0]["input_schema"].(map[string]any); s["type"] != "object" {
		t.Errorf("default input_schema = %v", got[0]["input_schema"])
	}
}

func TestConvertAnthropicTools_AbsentOrBad(t *testing.T) {
	t.Parallel()

	if got := convertAnthropicTools(nil); got != nil {
		t.Errorf("nil input → %v, want nil", got)
	}
	if got := convertAnthropicTools("not a slice"); got != nil {
		t.Errorf("string input → %v, want nil", got)
	}
	if got := convertAnthropicTools([]any{}); got != nil {
		t.Errorf("empty slice → %v, want nil", got)
	}
	// A malformed entry (no function object, or empty name) is skipped;
	// an all-malformed array yields nil.
	bad := []any{
		map[string]any{"type": "function"},                              // no function
		map[string]any{"type": "function", "function": map[string]any{}}, // empty name
	}
	if got := convertAnthropicTools(bad); got != nil {
		t.Errorf("all-malformed array → %v, want nil", got)
	}
}

// ── tool_choice conversion (all four mappings) ────────────────────────

func TestConvertAnthropicToolChoice_AllMappings(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name      string
		in        any
		want      map[string]any
		omitTools bool
	}{
		{"auto", "auto", map[string]any{"type": "auto"}, false},
		{"required", "required", map[string]any{"type": "any"}, false},
		{"none", "none", nil, true},
		{
			"explicit function",
			map[string]any{"type": "function", "function": map[string]any{"name": "memory_search"}},
			map[string]any{"type": "tool", "name": "memory_search"},
			false,
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got, omit := convertAnthropicToolChoice(tc.in)
			if !reflect.DeepEqual(got, tc.want) {
				t.Errorf("choice = %v, want %v", got, tc.want)
			}
			if omit != tc.omitTools {
				t.Errorf("omitTools = %v, want %v", omit, tc.omitTools)
			}
		})
	}
}

func TestConvertAnthropicToolChoice_AbsentOrUnknown(t *testing.T) {
	t.Parallel()

	// Absent / unrecognized → (nil, false): forward tools, no explicit choice.
	for _, in := range []any{nil, "bogus", map[string]any{"type": "function"}, 42} {
		got, omit := convertAnthropicToolChoice(in)
		if got != nil || omit {
			t.Errorf("convertAnthropicToolChoice(%v) = (%v, %v), want (nil, false)", in, got, omit)
		}
	}
}

// ── inbound message conversion ────────────────────────────────────────

func TestConvertAnthropicMessages_AssistantWithToolCalls(t *testing.T) {
	t.Parallel()

	in := map[string]any{
		"messages": []any{
			map[string]any{"role": "user", "content": "What do we know about Kai?"},
			map[string]any{
				"role":    "assistant",
				"content": "Let me check the knowledge graph.",
				"tool_calls": []any{
					map[string]any{
						"id":   "call_abc",
						"type": "function",
						"function": map[string]any{
							"name":      "memory_search",
							"arguments": `{"query":"Kai"}`,
						},
					},
				},
			},
		},
	}
	got := convertAnthropicMessages(in)
	if len(got) != 2 {
		t.Fatalf("expected 2 messages, got %d: %v", len(got), got)
	}
	// Plain user message passes through unchanged.
	if got[0]["role"] != "user" || got[0]["content"] != "What do we know about Kai?" {
		t.Errorf("user message altered: %v", got[0])
	}
	// Assistant message → content is a block array: text preamble + tool_use.
	asst := got[1]
	if asst["role"] != "assistant" {
		t.Fatalf("role = %v, want assistant", asst["role"])
	}
	blocks, ok := asst["content"].([]any)
	if !ok || len(blocks) != 2 {
		t.Fatalf("content should be 2 blocks, got %T %v", asst["content"], asst["content"])
	}
	text, _ := blocks[0].(map[string]any)
	if text["type"] != "text" || text["text"] != "Let me check the knowledge graph." {
		t.Errorf("text block = %v", text)
	}
	tu, _ := blocks[1].(map[string]any)
	if tu["type"] != "tool_use" || tu["id"] != "call_abc" || tu["name"] != "memory_search" {
		t.Errorf("tool_use block = %v", tu)
	}
	// `arguments` JSON STRING → parsed object in `input`.
	input, ok := tu["input"].(map[string]any)
	if !ok {
		t.Fatalf("input not a parsed object: %T %v", tu["input"], tu["input"])
	}
	if input["query"] != "Kai" {
		t.Errorf("input.query = %v, want Kai", input["query"])
	}
}

func TestConvertAnthropicMessages_AssistantToolCallsNoPreamble(t *testing.T) {
	t.Parallel()

	// Empty preamble → no {type:"text"} block, only the tool_use block.
	in := map[string]any{
		"messages": []any{
			map[string]any{
				"role":    "assistant",
				"content": "",
				"tool_calls": []any{
					map[string]any{
						"id":       "call_1",
						"function": map[string]any{"name": "memory_get", "arguments": ""},
					},
				},
			},
		},
	}
	got := convertAnthropicMessages(in)
	blocks, _ := got[0]["content"].([]any)
	if len(blocks) != 1 {
		t.Fatalf("empty preamble should yield 1 block, got %d: %v", len(blocks), blocks)
	}
	tu, _ := blocks[0].(map[string]any)
	if tu["type"] != "tool_use" {
		t.Errorf("block = %v, want tool_use", tu)
	}
	// Empty `arguments` string → empty object input (still valid for Anthropic).
	if input, ok := tu["input"].(map[string]any); !ok || len(input) != 0 {
		t.Errorf("empty-args input = %v, want empty object", tu["input"])
	}
}

func TestConvertAnthropicMessages_ToolResultToBlock(t *testing.T) {
	t.Parallel()

	in := map[string]any{
		"messages": []any{
			map[string]any{
				"role":         "tool",
				"tool_call_id": "call_abc",
				"content":      `{"entities":["Kai"]}`,
			},
		},
	}
	got := convertAnthropicMessages(in)
	if len(got) != 1 {
		t.Fatalf("expected 1 message, got %d: %v", len(got), got)
	}
	// A role:"tool" message → a role:"user" message carrying a tool_result block.
	if got[0]["role"] != "user" {
		t.Fatalf("role = %v, want user", got[0]["role"])
	}
	blocks, ok := got[0]["content"].([]map[string]any)
	if !ok || len(blocks) != 1 {
		t.Fatalf("content should be 1 tool_result block, got %T %v", got[0]["content"], got[0]["content"])
	}
	tr := blocks[0]
	if tr["type"] != "tool_result" || tr["tool_use_id"] != "call_abc" {
		t.Errorf("tool_result block = %v", tr)
	}
	if tr["content"] != `{"entities":["Kai"]}` {
		t.Errorf("tool_result.content = %v", tr["content"])
	}
}

func TestConvertAnthropicMessages_ConsecutiveToolMerge(t *testing.T) {
	t.Parallel()

	// Three consecutive role:"tool" messages MUST merge into ONE user
	// message with three tool_result blocks.
	in := map[string]any{
		"messages": []any{
			map[string]any{"role": "user", "content": "Compare Kai and Lyra."},
			map[string]any{"role": "assistant", "content": "Checking.", "tool_calls": []any{
				map[string]any{"id": "c1", "function": map[string]any{"name": "memory_search", "arguments": "{}"}},
				map[string]any{"id": "c2", "function": map[string]any{"name": "memory_search", "arguments": "{}"}},
			}},
			map[string]any{"role": "tool", "tool_call_id": "c1", "content": "result-1"},
			map[string]any{"role": "tool", "tool_call_id": "c2", "content": "result-2"},
			map[string]any{"role": "tool", "tool_call_id": "c3", "content": "result-3"},
		},
	}
	got := convertAnthropicMessages(in)
	// user, assistant(tool_use), merged-user(3 tool_result) → 3 messages.
	if len(got) != 3 {
		t.Fatalf("expected 3 messages after merge, got %d: %v", len(got), got)
	}
	merged := got[2]
	if merged["role"] != "user" {
		t.Fatalf("merged message role = %v, want user", merged["role"])
	}
	blocks, ok := merged["content"].([]map[string]any)
	if !ok || len(blocks) != 3 {
		t.Fatalf("merged content should be 3 tool_result blocks, got %T %v", merged["content"], merged["content"])
	}
	for i, want := range []string{"c1", "c2", "c3"} {
		if blocks[i]["tool_use_id"] != want {
			t.Errorf("block %d tool_use_id = %v, want %v", i, blocks[i]["tool_use_id"], want)
		}
		if blocks[i]["type"] != "tool_result" {
			t.Errorf("block %d type = %v, want tool_result", i, blocks[i]["type"])
		}
	}
}

func TestConvertAnthropicMessages_NonConsecutiveToolRunsSeparate(t *testing.T) {
	t.Parallel()

	// Two tool runs separated by a non-tool message → two distinct user
	// messages (the run is broken by the intervening assistant turn).
	in := map[string]any{
		"messages": []any{
			map[string]any{"role": "tool", "tool_call_id": "c1", "content": "r1"},
			map[string]any{"role": "assistant", "content": "thinking more"},
			map[string]any{"role": "tool", "tool_call_id": "c2", "content": "r2"},
		},
	}
	got := convertAnthropicMessages(in)
	if len(got) != 3 {
		t.Fatalf("expected 3 messages, got %d: %v", len(got), got)
	}
	b0, _ := got[0]["content"].([]map[string]any)
	b2, _ := got[2]["content"].([]map[string]any)
	if got[0]["role"] != "user" || len(b0) != 1 || b0[0]["tool_use_id"] != "c1" {
		t.Errorf("first tool run wrong: %v", got[0])
	}
	if got[1]["role"] != "assistant" || got[1]["content"] != "thinking more" {
		t.Errorf("intervening assistant message altered: %v", got[1])
	}
	if got[2]["role"] != "user" || len(b2) != 1 || b2[0]["tool_use_id"] != "c2" {
		t.Errorf("second tool run wrong: %v", got[2])
	}
}

func TestConvertAnthropicMessages_PlainPassthrough(t *testing.T) {
	t.Parallel()

	// Plain user / assistant / system text messages pass through verbatim.
	in := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "You are helpful."},
			map[string]any{"role": "user", "content": "Hello"},
			map[string]any{"role": "assistant", "content": "Hi there"},
		},
	}
	got := convertAnthropicMessages(in)
	want := []map[string]any{
		{"role": "system", "content": "You are helpful."},
		{"role": "user", "content": "Hello"},
		{"role": "assistant", "content": "Hi there"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("plain messages altered:\n got  %v\n want %v", got, want)
	}
}

func TestConvertAnthropicMessages_TypedMapSlice(t *testing.T) {
	t.Parallel()

	// []map[string]any must convert identically to []any.
	in := map[string]any{
		"messages": []map[string]any{
			{"role": "user", "content": "hi"},
			{"role": "tool", "tool_call_id": "c1", "content": "r1"},
		},
	}
	got := convertAnthropicMessages(in)
	if len(got) != 2 || got[0]["role"] != "user" || got[1]["role"] != "user" {
		t.Fatalf("typed-slice conversion wrong: %v", got)
	}
	blocks, _ := got[1]["content"].([]map[string]any)
	if len(blocks) != 1 || blocks[0]["type"] != "tool_result" {
		t.Errorf("typed-slice tool_result wrong: %v", got[1])
	}
}

func TestConvertAnthropicMessages_Fallback(t *testing.T) {
	t.Parallel()

	// Absent `messages` → the extractMessages fallback (single user message).
	got := convertAnthropicMessages(map[string]any{})
	if len(got) != 1 || got[0]["role"] != "user" {
		t.Fatalf("expected fallback user message, got %v", got)
	}
}

// ── parseToolArguments ────────────────────────────────────────────────

func TestParseToolArguments(t *testing.T) {
	t.Parallel()

	// JSON string → parsed object.
	if got := parseToolArguments(`{"a":1}`); !reflect.DeepEqual(got, map[string]any{"a": float64(1)}) {
		t.Errorf("json string → %v", got)
	}
	// Empty string → empty object.
	if got := parseToolArguments(""); !reflect.DeepEqual(got, map[string]any{}) {
		t.Errorf("empty string → %v, want empty object", got)
	}
	// Unparseable string → empty object (don't poison the upstream call).
	if got := parseToolArguments("{not json"); !reflect.DeepEqual(got, map[string]any{}) {
		t.Errorf("bad json → %v, want empty object", got)
	}
	// nil → empty object.
	if got := parseToolArguments(nil); !reflect.DeepEqual(got, map[string]any{}) {
		t.Errorf("nil → %v, want empty object", got)
	}
	// Already-an-object → passthrough (forward-compat).
	obj := map[string]any{"x": "y"}
	if got := parseToolArguments(obj); !reflect.DeepEqual(got, obj) {
		t.Errorf("object passthrough → %v", got)
	}
}

// ── applyAnthropicTools (the wiring point) ────────────────────────────

func TestApplyAnthropicTools_SetsToolsAndChoice(t *testing.T) {
	t.Parallel()

	body := map[string]any{"model": "claude", "max_tokens": 8192}
	input := map[string]any{
		"tools": []any{
			map[string]any{"type": "function", "function": map[string]any{"name": "memory_search"}},
		},
		"tool_choice": "auto",
	}
	applyAnthropicTools(body, input)

	tools, ok := body["tools"].([]map[string]any)
	if !ok || len(tools) != 1 || tools[0]["name"] != "memory_search" {
		t.Fatalf("body.tools = %v", body["tools"])
	}
	if !reflect.DeepEqual(body["tool_choice"], map[string]any{"type": "auto"}) {
		t.Errorf("body.tool_choice = %v", body["tool_choice"])
	}
}

func TestApplyAnthropicTools_NoneOmitsTools(t *testing.T) {
	t.Parallel()

	// tool_choice "none" → omit BOTH tools and tool_choice, even when a
	// tools array is supplied (D12).
	body := map[string]any{"model": "claude"}
	input := map[string]any{
		"tools": []any{
			map[string]any{"type": "function", "function": map[string]any{"name": "memory_search"}},
		},
		"tool_choice": "none",
	}
	applyAnthropicTools(body, input)
	if _, set := body["tools"]; set {
		t.Error("tool_choice:none should omit `tools`")
	}
	if _, set := body["tool_choice"]; set {
		t.Error("tool_choice:none should omit `tool_choice`")
	}
}

func TestApplyAnthropicTools_NoToolsLeavesBodyUntouched(t *testing.T) {
	t.Parallel()

	// No tools on the request → body unchanged (zero behavior change for
	// tool-free Anthropic requests).
	body := map[string]any{"model": "claude", "max_tokens": 8192}
	before := map[string]any{"model": "claude", "max_tokens": 8192}
	applyAnthropicTools(body, map[string]any{})
	if !reflect.DeepEqual(body, before) {
		t.Errorf("tool-free request mutated body: %v", body)
	}
	// tools present but tool_choice absent → tools set, tool_choice unset.
	body2 := map[string]any{"model": "claude"}
	applyAnthropicTools(body2, map[string]any{
		"tools": []any{map[string]any{"type": "function", "function": map[string]any{"name": "t"}}},
	})
	if _, set := body2["tools"]; !set {
		t.Error("tools should be set when present")
	}
	if _, set := body2["tool_choice"]; set {
		t.Error("tool_choice should stay unset when caller omitted it")
	}
}

// SupportsTools() == true after D12 is asserted by the canonical
// capability test TestAdapterSupportsTools in tool_call_streamer_test.go.
