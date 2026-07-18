package provider

// responses_streamer.go — Provider Context Strategy §5 (Phase 2). The STATEFUL
// transport: OpenAI's (and LM-Studio's) `/v1/responses` API, where the server holds
// the prior turn's context keyed by `previous_response_id` so we send only the DELTA
// each turn. This is the fix for the local context-explosion: on the A4B model where
// `/v1/chat/completions` prefix-caching reports 0 (bug #1563), `/v1/responses` +
// `previous_response_id` caches 99% (1711/1727) — live-measured 2026-07-06.
//
// This adapter is capability-gated (responses_api) + flag-gated (LLM_STATEFUL_CACHE)
// upstream; when unused the chat/completions path is byte-identical.
//
// Responses SSE event shape (one `data: <JSON>` per event; `type` discriminates):
//
//	{"type":"response.created","response":{"id":"resp_123",...}}
//	{"type":"response.output_item.added","output_index":0,
//	   "item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"glossary_search"}}
//	{"type":"response.output_text.delta","delta":"Hello"}
//	{"type":"response.function_call_arguments.delta","output_index":0,"delta":"{\"q\":"}
//	{"type":"response.completed","response":{"id":"resp_123",
//	   "usage":{"input_tokens":1727,"output_tokens":16,
//	            "input_tokens_details":{"cached_tokens":1711},
//	            "output_tokens_details":{"reasoning_tokens":0}}}}
//	{"type":"response.failed","response":{"error":{"message":"..."}}}
//	{"type":"error","message":"..."}
//
// Mapping to the canonical envelope:
//	response.output_text.delta            → StreamChunkToken
//	response.reasoning_text.delta         → StreamChunkReasoning
//	response.output_item.added(func_call) → StreamChunkToolCall (id + name, empty args)
//	response.function_call_arguments.delta→ StreamChunkToolCall (args fragment)
//	response.completed                    → StreamChunkUsage (+ cache split) then
//	                                        StreamChunkDone carrying ResponseID (the
//	                                        chain head chat-service persists for E2/next turn)
//	response.failed / error               → StreamChunkError

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// streamResponsesSSE parses `/v1/responses` SSE into canonical StreamChunk events.
// Caller owns body close + ctx. The terminal Done chunk carries ResponseID so the
// caller can chain the next turn (previous_response_id).
func streamResponsesSSE(ctx context.Context, body io.Reader, emit EmitFn) error {
	tokenIdx := 0
	reasoningIdx := 0
	responseID := ""
	finishReason := "stop"
	usageEmitted := false
	sawToolCall := false
	// map output_index → the tool call's id/name, captured on output_item.added so the
	// arguments-delta fragments (which carry only the index) can be attributed.
	toolStarted := map[int]bool{}
	// argsSeen[output_index] — true once ANY argument bytes have been emitted for a
	// tool call (either via streamed `.delta` fragments or a batched `.done`). Guards
	// the batched-`.done` fallback so a compliant provider that BOTH streams deltas
	// and repeats the full args on `.done` never double-appends them.
	argsSeen := map[int]bool{}

	err := readSSELines(ctx, body, func(_event, data string) error {
		var ev struct {
			Type        string `json:"type"`
			Delta       string `json:"delta"`
			OutputIndex int    `json:"output_index"`
			// Arguments — top-level on `response.function_call_arguments.done`: the
			// FULL argument string. OpenAI sends this redundantly after streaming
			// `.delta` fragments; LM Studio's /v1/responses sends NO `.delta` at all
			// and delivers the whole thing ONLY here (bug parity: llama.cpp #20607).
			Arguments string `json:"arguments"`
			Item      struct {
				Type      string `json:"type"`
				ID        string `json:"id"`
				CallID    string `json:"call_id"`
				Name      string `json:"name"`
				Arguments string `json:"arguments"` // full args on output_item.done (function_call)
			} `json:"item"`
			Response struct {
				ID     string `json:"id"`
				Status string `json:"status"` // completed | incomplete | failed
				Error  struct {
					Message string `json:"message"`
				} `json:"error"`
				IncompleteDetails struct {
					Reason string `json:"reason"` // max_output_tokens | content_filter
				} `json:"incomplete_details"`
				Usage struct {
					InputTokens        int `json:"input_tokens"`
					OutputTokens       int `json:"output_tokens"`
					InputTokensDetails struct {
						CachedTokens int `json:"cached_tokens"`
					} `json:"input_tokens_details"`
					OutputTokensDetails struct {
						ReasoningTokens int `json:"reasoning_tokens"`
					} `json:"output_tokens_details"`
				} `json:"usage"`
			} `json:"response"`
			Message string `json:"message"`
		}
		if err := json.Unmarshal([]byte(data), &ev); err != nil {
			_ = emit(StreamChunk{
				Kind:    StreamChunkError,
				Code:    "LLM_DECODE_ERROR",
				Message: fmt.Sprintf("malformed Responses stream chunk: %v", err),
			})
			return errStreamDone
		}

		switch ev.Type {
		case "response.created", "response.in_progress":
			if ev.Response.ID != "" {
				responseID = ev.Response.ID
			}
		case "response.output_text.delta":
			if ev.Delta == "" {
				return nil
			}
			if err := emit(StreamChunk{Kind: StreamChunkToken, Delta: ev.Delta, Index: tokenIdx}); err != nil {
				return err
			}
			tokenIdx++
		case "response.reasoning_text.delta", "response.reasoning_summary_text.delta":
			if ev.Delta == "" {
				return nil
			}
			if err := emit(StreamChunk{Kind: StreamChunkReasoning, Delta: ev.Delta, Index: reasoningIdx}); err != nil {
				return err
			}
			reasoningIdx++
		case "response.output_item.added":
			// The function_call item start is the ONLY carrier of the call id + name.
			if ev.Item.Type == "function_call" {
				callID := ev.Item.CallID
				if callID == "" {
					callID = ev.Item.ID
				}
				toolStarted[ev.OutputIndex] = true
				sawToolCall = true
				if err := emit(StreamChunk{
					Kind:       StreamChunkToolCall,
					Index:      ev.OutputIndex,
					ToolCallID: callID,
					ToolName:   ev.Item.Name,
				}); err != nil {
					return err
				}
			}
		case "response.function_call_arguments.delta":
			if ev.Delta == "" {
				return nil
			}
			argsSeen[ev.OutputIndex] = true
			if err := emit(StreamChunk{
				Kind:           StreamChunkToolCall,
				Index:          ev.OutputIndex,
				ArgumentsDelta: ev.Delta,
			}); err != nil {
				return err
			}
		case "response.function_call_arguments.done", "response.output_item.done":
			// Batched-args fallback. A COMPLIANT provider (OpenAI) streams the args as
			// `.delta` fragments and then repeats the full string here — already
			// accumulated, so we skip. LM Studio's /v1/responses emits NO `.delta` and
			// delivers the WHOLE argument string only on `.done` (llama.cpp #20607); the
			// call would otherwise reach the consumer with EMPTY args (the name arrives on
			// output_item.added, the args nowhere). Emit the full args as one fragment,
			// but ONLY when nothing was streamed for this index — the argsSeen guard makes
			// this idempotent across the two `.done` variants and vs streamed deltas.
			args := ev.Arguments
			if args == "" && ev.Item.Type == "function_call" {
				args = ev.Item.Arguments
			}
			if args == "" || argsSeen[ev.OutputIndex] {
				return nil
			}
			argsSeen[ev.OutputIndex] = true
			if err := emit(StreamChunk{
				Kind:           StreamChunkToolCall,
				Index:          ev.OutputIndex,
				ArgumentsDelta: args,
			}); err != nil {
				return err
			}
		case "response.completed", "response.incomplete":
			if ev.Response.ID != "" {
				responseID = ev.Response.ID
			}
			// Real finish_reason (review H-t): was "stop" hardcoded, hiding truncation +
			// tool-stops. incomplete(max_output_tokens)→length; a turn that emitted a
			// function_call→tool_calls; else stop. Mirrors the chat/completions semantics.
			switch {
			case ev.Response.Status == "incomplete" && ev.Response.IncompleteDetails.Reason == "max_output_tokens":
				finishReason = "length"
			case ev.Response.Status == "incomplete" && ev.Response.IncompleteDetails.Reason == "content_filter":
				finishReason = "content_filter"
			case sawToolCall:
				finishReason = "tool_calls"
			default:
				finishReason = "stop"
			}
			if !usageEmitted {
				chunk := StreamChunk{
					Kind:         StreamChunkUsage,
					InputTokens:  ev.Response.Usage.InputTokens,
					OutputTokens: ev.Response.Usage.OutputTokens,
				}
				// Responses input_tokens INCLUDES cached (like OpenAI chat) → the
				// cached slice is a READ hit; no write charge on this API.
				if c := ev.Response.Usage.InputTokensDetails.CachedTokens; c > 0 {
					chunk.CacheReadTokens = &c
				}
				if rt := ev.Response.Usage.OutputTokensDetails.ReasoningTokens; rt > 0 {
					chunk.ReasoningTokens = &rt
				}
				if err := emit(chunk); err != nil {
					return err
				}
				usageEmitted = true
			}
			return errStreamDone
		case "response.failed", "response.error", "error":
			msg := ev.Message
			if msg == "" {
				msg = ev.Response.Error.Message
			}
			_ = emit(StreamChunk{Kind: StreamChunkError, Code: "LLM_UPSTREAM_ERROR", Message: msg})
			return errStreamDone
		default:
			// Forward-compat: ignore unhandled event types (content_part.added, .done, etc.)
		}
		return nil
	})

	// Terminal done carries the response id (the chain head) so the caller can set
	// previous_response_id on the next turn.
	_ = emit(StreamChunk{Kind: StreamChunkDone, FinishReason: finishReason, ResponseID: responseID})
	if err != nil && err != context.Canceled {
		return err
	}
	return nil
}

// openResponsesStream POSTs the responses body to `/v1/responses` with stream forced.
func openResponsesStream(ctx context.Context, client *http.Client, baseURL, secret string, body map[string]any) (*http.Response, error) {
	body["stream"] = true
	headers := map[string]string{}
	if secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}
	return doStreamPOST(ctx, client, baseURL+"/v1/responses", headers, body)
}
