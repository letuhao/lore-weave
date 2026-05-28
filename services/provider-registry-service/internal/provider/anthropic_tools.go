package provider

// anthropic_tools.go — Phase K21-B / decision D12. Request-side tool
// support for the Anthropic adapter.
//
// chat-service always speaks the OpenAI tool-calling shape on the wire
// (see KNOWLEDGE_SERVICE_K21B_DESIGN.md D5): OpenAI-compatible adapters
// forward `tools` / `tool_choice` / `messages` raw, but Anthropic's
// /v1/messages API uses a materially different shape. The conversions
// here translate the OpenAI shape → Anthropic so tool-calling works on
// Anthropic-backed chats too.
//
// Shape differences:
//
//   tools:
//     OpenAI     [{type:"function", function:{name, description, parameters}}]
//     Anthropic  [{name, description, input_schema}]
//
//   tool_choice:
//     OpenAI     "auto" | "required" | "none" | {type:"function",function:{name}}
//     Anthropic  {type:"auto"} | {type:"any"} | (omit tools) | {type:"tool",name}
//
//   messages — assistant turn that called tools:
//     OpenAI     {role:"assistant", content:"<preamble>",
//                 tool_calls:[{id, type:"function", function:{name, arguments}}]}
//     Anthropic  {role:"assistant", content:[
//                   {type:"text", text:"<preamble>"},          (omitted if empty)
//                   {type:"tool_use", id, name, input}]}
//                 — `arguments` is a JSON STRING in OpenAI shape; Anthropic
//                   `input` is the parsed object.
//
//   messages — tool results:
//     OpenAI     {role:"tool", tool_call_id, content}   (one per call)
//     Anthropic  {role:"user", content:[{type:"tool_result", tool_use_id, content}]}
//                 — consecutive role:"tool" messages MUST merge into ONE
//                   user message carrying all the tool_result blocks.
//
// The OUTPUT side (anthropic_streamer.go, which maps tool_use blocks →
// ToolCallEvent) is unchanged. OpenAI-compatible adapters are untouched.

import "encoding/json"

// convertAnthropicTools converts the OpenAI-shaped `tools` array into
// Anthropic's `[{name, description, input_schema}]`. It accepts both
// []any (the common JSON-decoded case) and []map[string]any, exactly as
// extractMessages does. Returns nil when the value is absent, the wrong
// shape, or contains no convertible entries — callers omit `tools`
// upstream in that case.
func convertAnthropicTools(v any) []map[string]any {
	raw := asMapSlice(v)
	if len(raw) == 0 {
		return nil
	}
	out := make([]map[string]any, 0, len(raw))
	for _, t := range raw {
		fn, ok := asMap(t["function"])
		if !ok {
			// Forward-compat: skip a tool entry that isn't the
			// {type:"function", function:{…}} shape.
			continue
		}
		name, _ := fn["name"].(string)
		if name == "" {
			continue
		}
		conv := map[string]any{"name": name}
		if desc, ok := fn["description"].(string); ok && desc != "" {
			conv["description"] = desc
		}
		// OpenAI's `function.parameters` is the JSON Schema → Anthropic's
		// `input_schema`. Anthropic requires input_schema to be present
		// and an object; default to an empty object schema when absent.
		if params, ok := asMap(fn["parameters"]); ok {
			conv["input_schema"] = params
		} else {
			conv["input_schema"] = map[string]any{"type": "object"}
		}
		out = append(out, conv)
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

// convertAnthropicToolChoice converts the OpenAI-shaped `tool_choice`
// into Anthropic's shape:
//
//	"auto"                              → {type:"auto"}
//	"required"                          → {type:"any"}
//	"none"                              → nil + omitTools=true
//	{type:"function",function:{name}}   → {type:"tool", name}
//
// The omitTools return reports the D12 rule that tool_choice "none" omits
// the `tools` array entirely. For an absent / unrecognized value it
// returns (nil, false): the caller still forwards `tools` but lets the
// provider apply its default selection behavior.
func convertAnthropicToolChoice(v any) (choice map[string]any, omitTools bool) {
	switch tc := v.(type) {
	case string:
		switch tc {
		case "auto":
			return map[string]any{"type": "auto"}, false
		case "required":
			return map[string]any{"type": "any"}, false
		case "none":
			return nil, true
		default:
			return nil, false
		}
	case map[string]any:
		if fn, ok := asMap(tc["function"]); ok {
			if name, _ := fn["name"].(string); name != "" {
				return map[string]any{"type": "tool", "name": name}, false
			}
		}
		return nil, false
	default:
		return nil, false
	}
}

// applyAnthropicTools sets body["tools"] and body["tool_choice"] from the
// OpenAI-shaped `tools` / `tool_choice` in input, in place. It is the
// single wiring point for both anthropicAdapter.Stream and .Invoke.
//
// Per D12:
//   - tool_choice "none" → omit `tools` entirely (and `tool_choice`).
//   - no convertible tools present → omit both (zero behavior change for
//     tool-free Anthropic requests — body is left exactly as the caller
//     built it).
//   - otherwise → set `tools`, and set `tool_choice` only when it maps to
//     a concrete Anthropic choice ("auto"/"required"/explicit function);
//     an absent / unrecognized tool_choice leaves `tool_choice` unset so
//     Anthropic applies its own default.
func applyAnthropicTools(body, input map[string]any) {
	choice, omitTools := convertAnthropicToolChoice(input["tool_choice"])
	if omitTools {
		// tool_choice:"none" — D12 says omit tools entirely.
		return
	}
	tools := convertAnthropicTools(input["tools"])
	if len(tools) == 0 {
		// No tools on this request — leave the body untouched.
		return
	}
	body["tools"] = tools
	if choice != nil {
		body["tool_choice"] = choice
	}
}

// convertAnthropicMessages converts the OpenAI-shaped `messages` array
// (as carried in input["messages"]) into Anthropic's message shape.
//
//   - {role:"assistant", content, tool_calls:[…]} → an assistant message
//     whose content is an array of blocks: an optional {type:"text",text}
//     (only when the preamble text is non-empty) followed by one
//     {type:"tool_use", id, name, input} per call.
//   - {role:"tool", tool_call_id, content} → a {type:"tool_result",
//     tool_use_id, content} block; CONSECUTIVE role:"tool" messages merge
//     into ONE {role:"user", content:[…tool_result blocks…]} message.
//   - Plain user / assistant / system text messages pass through unchanged.
//
// Accepts both []any and []map[string]any (per extractMessages). Falls
// back to a single user message when `messages` is absent or unusable,
// matching extractMessages's fallback.
func convertAnthropicMessages(input map[string]any) []map[string]any {
	src := extractMessages(input)
	out := make([]map[string]any, 0, len(src))
	// pendingToolResults accumulates tool_result blocks from a run of
	// consecutive role:"tool" messages; flushed as one user message when
	// the run ends.
	var pendingToolResults []map[string]any
	flush := func() {
		if len(pendingToolResults) > 0 {
			out = append(out, map[string]any{
				"role":    "user",
				"content": pendingToolResults,
			})
			pendingToolResults = nil
		}
	}

	for _, m := range src {
		role, _ := m["role"].(string)

		if role == "tool" {
			// Merge into the current consecutive-tool run.
			toolCallID, _ := m["tool_call_id"].(string)
			pendingToolResults = append(pendingToolResults, map[string]any{
				"type":        "tool_result",
				"tool_use_id": toolCallID,
				"content":     m["content"],
			})
			continue
		}

		// Any non-tool message terminates a consecutive role:"tool" run.
		flush()

		if role == "assistant" {
			if calls := asMapSlice(m["tool_calls"]); len(calls) > 0 {
				out = append(out, assistantWithToolCalls(m, calls))
				continue
			}
		}

		// Plain user / assistant / system message — pass through unchanged.
		out = append(out, m)
	}
	flush()
	return out
}

// assistantWithToolCalls builds the Anthropic assistant message for an
// OpenAI {role:"assistant", content, tool_calls:[…]} message. The content
// becomes a block array: an optional {type:"text",text} preamble (only
// when non-empty) followed by one {type:"tool_use"} block per call.
func assistantWithToolCalls(m map[string]any, calls []map[string]any) map[string]any {
	blocks := make([]any, 0, len(calls)+1)
	if text, _ := m["content"].(string); text != "" {
		blocks = append(blocks, map[string]any{"type": "text", "text": text})
	}
	for _, c := range calls {
		id, _ := c["id"].(string)
		fn, _ := asMap(c["function"])
		name, _ := fn["name"].(string)
		blocks = append(blocks, map[string]any{
			"type":  "tool_use",
			"id":    id,
			"name":  name,
			"input": parseToolArguments(fn["arguments"]),
		})
	}
	return map[string]any{"role": "assistant", "content": blocks}
}

// parseToolArguments converts an OpenAI tool-call `arguments` value — a
// JSON STRING — into the object Anthropic expects for `input`. A
// non-string value is passed through (forward-compat: a caller already
// supplying an object). An empty or unparseable string yields an empty
// object so the upstream call still has a valid `input`.
func parseToolArguments(v any) any {
	s, ok := v.(string)
	if !ok {
		if v == nil {
			return map[string]any{}
		}
		return v
	}
	if s == "" {
		return map[string]any{}
	}
	var parsed any
	if err := json.Unmarshal([]byte(s), &parsed); err != nil {
		return map[string]any{}
	}
	return parsed
}

// asMap coerces a value into map[string]any, reporting whether it was a
// map. Mirrors the []any-vs-typed tolerance of extractMessages for the
// nested-object case.
func asMap(v any) (map[string]any, bool) {
	m, ok := v.(map[string]any)
	return m, ok
}

// asMapSlice coerces a value into []map[string]any, accepting both
// []map[string]any and []any (the common JSON-decoded case), exactly as
// extractMessages does for the top-level `messages` array. Non-map
// elements are dropped. Returns nil for an absent / non-slice value.
func asMapSlice(v any) []map[string]any {
	switch s := v.(type) {
	case []map[string]any:
		return s
	case []any:
		out := make([]map[string]any, 0, len(s))
		for _, item := range s {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		return out
	default:
		return nil
	}
}
