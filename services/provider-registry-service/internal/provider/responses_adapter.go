package provider

// responses_adapter.go — Provider Context Strategy §5 (Phase 2). The stateful
// `/v1/responses` transport is not a separate Adapter; it is a BRANCH inside the
// adapters that own the responses_api capability (openai, lm_studio). When the
// request carries the stateful marker (gated in the handler by capability +
// LLM_STATEFUL_CACHE), the adapter builds a Responses body and streams it here
// instead of chat/completions. Everything is co-located with the owning provider so
// the stateless path stays byte-identical.

import (
	"context"
	"errors"
	"net/http"
	"os"
	"strings"
)

// StatefulCacheEnabled — the deploy flag for the stateful strategy (default OFF;
// staged rollout per spec §11). Enable with LLM_STATEFUL_CACHE=1/true/on. Independent
// of LLM_PROMPT_CACHE (which gates the Anthropic cache_control path). Exported so the
// gateway handler applies the SAME gate before forwarding the stateful marker.
func StatefulCacheEnabled() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("LLM_STATEFUL_CACHE")))
	return v == "1" || v == "true" || v == "on"
}

// isStatefulRequest reports whether the input asks for the stateful transport. The
// handler is responsible for having already verified the capability + flag; this is
// the adapter-local switch.
func isStatefulRequest(input map[string]any) bool {
	v, ok := input["stateful"].(bool)
	return ok && v && StatefulCacheEnabled()
}

// buildResponsesBody converts an OpenAI-shaped chat request (messages + tools) into a
// `/v1/responses` body. `previous_response_id` chains onto the prior turn (the server
// holds that context, so we send only the new/delta messages the caller supplied).
func buildResponsesBody(modelName string, input map[string]any) map[string]any {
	// System → `instructions`, NOT a chained input item (spec §5). The Responses API
	// does not inherit instructions across previous_response_id, so sending the CURRENT
	// system every call makes a mid-session system change take effect with no re-chain,
	// and keeps the `input` delta purely conversational. Split it out of the messages.
	instructions, msgs := splitSystemInstructions(extractMessages(input))
	body := map[string]any{
		"model": modelName,
		"input": messagesToResponsesInput(msgs),
		// store the response server-side so previous_response_id can chain it.
		"store": true,
	}
	if instructions != "" {
		body["instructions"] = instructions
	}
	if v, ok := input["previous_response_id"].(string); ok && v != "" {
		body["previous_response_id"] = v
	}
	if v, ok := input["temperature"]; ok {
		body["temperature"] = v
	}
	if v, ok := input["max_tokens"]; ok && toFloat(v) > 0 {
		body["max_output_tokens"] = v
	}
	// Forward reasoning controls so thinking-off still works on reasoning models in
	// stateful mode (same intent as forwardOptionalChatFields on the chat path).
	if v, ok := input["reasoning_effort"]; ok {
		body["reasoning_effort"] = v
	}
	if v, ok := input["chat_template_kwargs"]; ok {
		body["chat_template_kwargs"] = v
	}
	if tools := toolsToResponsesTools(input["tools"]); len(tools) > 0 {
		body["tools"] = tools
		if tc, ok := input["tool_choice"]; ok {
			body["tool_choice"] = tc
		}
	}
	return body
}

// splitSystemInstructions pulls system message(s) out of the message list into one
// instructions string (blank-line joined), returning the remaining non-system
// messages. Flattens a structured (cache_control block-list) system content too —
// the responses `instructions` is a plain string.
func splitSystemInstructions(messages []map[string]any) (string, []map[string]any) {
	var sys []string
	rest := make([]map[string]any, 0, len(messages))
	for _, m := range messages {
		if r, _ := m["role"].(string); r == "system" {
			if s := stringifyContent(m["content"]); s != "" {
				sys = append(sys, s)
			}
			continue
		}
		rest = append(rest, m)
	}
	return strings.Join(sys, "\n\n"), rest
}

// messagesToResponsesInput maps chat `messages` to Responses `input` items. Plain
// user/assistant/system messages pass through with role+content; a role:"tool" result
// becomes a function_call_output item keyed by its tool_call_id (Responses' shape).
func messagesToResponsesInput(messages []map[string]any) []any {
	out := make([]any, 0, len(messages))
	for _, msg := range messages {
		role, _ := msg["role"].(string)
		if role == "tool" {
			callID, _ := msg["tool_call_id"].(string)
			out = append(out, map[string]any{
				"type":    "function_call_output",
				"call_id": callID,
				"output":  stringifyContent(msg["content"]),
			})
			continue
		}
		out = append(out, map[string]any{"role": role, "content": stringifyContent(msg["content"])})
	}
	return out
}

// stringifyContent normalizes a message content (string or content-parts) to a string
// for the Responses input (which accepts a plain string per item).
func stringifyContent(c any) string {
	if s, ok := c.(string); ok {
		return s
	}
	// content-parts array → concatenate text parts (best-effort).
	if parts, ok := c.([]any); ok {
		var b strings.Builder
		for _, p := range parts {
			if pm, ok := p.(map[string]any); ok {
				if t, ok := pm["text"].(string); ok {
					b.WriteString(t)
				}
			}
		}
		return b.String()
	}
	return ""
}

// toolsToResponsesTools converts OpenAI chat tools ({type:function, function:{name,
// description, parameters}}) to Responses' FLAT tool shape ({type:function, name,
// description, parameters}). Returns nil when there are no tools.
func toolsToResponsesTools(v any) []any {
	arr, ok := v.([]any)
	if !ok || len(arr) == 0 {
		return nil
	}
	out := make([]any, 0, len(arr))
	for _, t := range arr {
		tm, ok := t.(map[string]any)
		if !ok {
			continue
		}
		if fn, ok := tm["function"].(map[string]any); ok {
			flat := map[string]any{"type": "function"}
			for _, k := range []string{"name", "description", "parameters"} {
				if val, ok := fn[k]; ok {
					flat[k] = val
				}
			}
			out = append(out, flat)
		} else {
			// already flat (or a non-function tool) — pass through
			out = append(out, tm)
		}
	}
	return out
}

// chainNotFoundCode is the canonical error the caller catches to E1-re-establish
// (spec §4/§6). chat-service maps this code to "resend full context, fresh chain".
const chainNotFoundCode = "LLM_RESPONSE_CHAIN_NOT_FOUND"

// isChainNotFound reports whether an openResponsesStream error is the provider's
// "previous_response_id not found" rejection. Signature LIVE-PROBED against LM Studio
// 2026-07-06: HTTP 400 with body carrying `"code":"previous_response_not_found"` (and
// `"param":"previous_response_id"`). Matched on the stable machine code, not the prose.
func isChainNotFound(err error) bool {
	var perm *ErrUpstreamPermanent
	if !errors.As(err, &perm) {
		return false
	}
	b := perm.Body
	return strings.Contains(b, "previous_response_not_found") ||
		(strings.Contains(b, "previous_response_id") && strings.Contains(b, "not found"))
}

// streamViaResponses runs a stateful turn over `/v1/responses`. Shared by the
// openai + lm_studio adapters' stateful branch. On an invalid previous_response_id
// it emits the distinct chainNotFoundCode error event (so chat-service re-establishes
// the chain from DB truth — E1) rather than surfacing an opaque 400.
func streamViaResponses(ctx context.Context, client *http.Client, base, secret, modelName string, input map[string]any, emit EmitFn) error {
	body := buildResponsesBody(modelName, input)
	resp, err := openResponsesStream(ctx, client, strings.TrimRight(base, "/"), secret, body)
	if err != nil {
		if isChainNotFound(err) {
			_ = emit(StreamChunk{
				Kind:    StreamChunkError,
				Code:    chainNotFoundCode,
				Message: "previous_response_id not found; re-establish the chain from history",
			})
			return nil // handled as a canonical error event
		}
		return err
	}
	defer resp.Body.Close()
	return streamResponsesSSE(ctx, resp.Body, emit)
}
