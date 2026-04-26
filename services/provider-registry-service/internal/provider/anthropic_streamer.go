package provider

// anthropic_streamer.go — Phase 1c-anthropic (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN).
// Closes the deferred regression D-PHASE-1C-ANTHROPIC where chat-service
// users selecting an Anthropic model received LLM_STREAM_NOT_SUPPORTED
// because the original Phase 1a only shipped openai-compat parsing.
//
// Anthropic's SSE format differs materially from OpenAI:
//
//   event: message_start
//   data: {"type":"message_start","message":{"id":"...","model":"...","usage":{"input_tokens":N}}}
//
//   event: content_block_start
//   data: {"type":"content_block_start","index":0,"content_block":{"type":"text"|"thinking","text":""|"thinking":""}}
//
//   event: content_block_delta
//   data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}
//   (or {"type":"thinking_delta","thinking":"Let me think..."} for extended-thinking models like Claude 3.7+)
//
//   event: content_block_stop
//   data: {"type":"content_block_stop","index":0}
//
//   event: message_delta
//   data: {"type":"message_delta","delta":{"stop_reason":"end_turn"|"max_tokens"|...},"usage":{"output_tokens":M}}
//
//   event: message_stop
//   data: {"type":"message_stop"}
//
// Mapping to canonical envelope:
//   text_delta      → StreamChunkToken
//   thinking_delta  → StreamChunkReasoning   (Claude 3.7+ extended thinking)
//   message_delta   → StreamChunkUsage  + capture stop_reason
//   message_stop    → StreamChunkDone   (with captured stop_reason)
//   error events    → StreamChunkError

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

const (
	anthropicAPIVersion       = "2023-06-01"
	anthropicMessagesEndpoint = "/v1/messages"
)

// streamAnthropicSSE parses Anthropic's SSE wire format into canonical
// StreamChunk events via emit. Caller owns body close + ctx cancellation.
func streamAnthropicSSE(ctx context.Context, body io.Reader, emit EmitFn) error {
	tokenIdx := 0
	reasoningIdx := 0
	finishReason := ""
	inputTokens := 0
	outputTokens := 0
	usageEmitted := false

	err := readSSELines(ctx, body, func(eventName, data string) error {
		// Anthropic uses event-name lines AND a `type` field inside the
		// data payload — they're redundant; we trust the inner type.
		var parsed struct {
			Type    string `json:"type"`
			Index   int    `json:"index"`
			Delta   struct {
				Type       string `json:"type"`
				Text       string `json:"text"`
				Thinking   string `json:"thinking"`
				StopReason string `json:"stop_reason"`
			} `json:"delta"`
			ContentBlock struct {
				Type     string `json:"type"`
				Text     string `json:"text"`
				Thinking string `json:"thinking"`
			} `json:"content_block"`
			Message struct {
				Usage struct {
					InputTokens int `json:"input_tokens"`
				} `json:"usage"`
			} `json:"message"`
			Usage struct {
				InputTokens  int `json:"input_tokens"`
				OutputTokens int `json:"output_tokens"`
			} `json:"usage"`
			Error struct {
				Type    string `json:"type"`
				Message string `json:"message"`
			} `json:"error"`
		}
		if err := json.Unmarshal([]byte(data), &parsed); err != nil {
			_ = emit(StreamChunk{
				Kind:    StreamChunkError,
				Code:    "LLM_DECODE_ERROR",
				Message: fmt.Sprintf("malformed Anthropic stream chunk: %v", err),
			})
			return errStreamDone
		}

		// Some payloads only carry an `error` block (per Anthropic
		// streaming docs). Surface as canonical error event then stop.
		if parsed.Error.Type != "" || parsed.Error.Message != "" {
			_ = emit(StreamChunk{
				Kind:    StreamChunkError,
				Code:    "LLM_UPSTREAM_ERROR",
				Message: parsed.Error.Message,
			})
			return errStreamDone
		}

		// Use the inner `type` first; fall back to SSE event name.
		kind := parsed.Type
		if kind == "" {
			kind = eventName
		}

		switch kind {
		case "message_start":
			// Anthropic includes input_tokens in message_start.usage.
			inputTokens = parsed.Message.Usage.InputTokens
		case "content_block_start":
			// No-op — the first delta within the block does the work.
			// (Could capture block.type to validate text vs thinking,
			// but the delta carries that info too.)
		case "content_block_delta":
			switch parsed.Delta.Type {
			case "text_delta":
				if parsed.Delta.Text == "" {
					return nil
				}
				if err := emit(StreamChunk{
					Kind:  StreamChunkToken,
					Delta: parsed.Delta.Text,
					Index: tokenIdx,
				}); err != nil {
					return err
				}
				tokenIdx++
			case "thinking_delta":
				if parsed.Delta.Thinking == "" {
					return nil
				}
				if err := emit(StreamChunk{
					Kind:  StreamChunkReasoning,
					Delta: parsed.Delta.Thinking,
					Index: reasoningIdx,
				}); err != nil {
					return err
				}
				reasoningIdx++
			default:
				// Unknown delta type — ignore. Anthropic adds new types
				// (input_json_delta for tool use, etc.) which a future
				// follow-up cycle can map.
			}
		case "content_block_stop":
			// No-op. Inner blocks just close.
		case "message_delta":
			// Carries terminal usage + stop_reason.
			if parsed.Delta.StopReason != "" {
				finishReason = mapAnthropicStopReason(parsed.Delta.StopReason)
			}
			if !usageEmitted {
				outputTokens = parsed.Usage.OutputTokens
				if err := emit(StreamChunk{
					Kind:         StreamChunkUsage,
					InputTokens:  inputTokens,
					OutputTokens: outputTokens,
				}); err != nil {
					return err
				}
				usageEmitted = true
			}
		case "message_stop":
			return errStreamDone
		case "ping":
			// Keep-alive heartbeat — ignore.
		default:
			// Forward-compat: unknown event types are ignored so future
			// Anthropic additions don't crash us.
		}
		return nil
	})

	// Emit terminal done event with captured finish_reason. Mirror the
	// streamOpenAICompat behavior so callers see a uniform terminal.
	_ = emit(StreamChunk{
		Kind:         StreamChunkDone,
		FinishReason: finishReason,
	})
	if err != nil && err != context.Canceled {
		return err
	}
	return nil
}

// mapAnthropicStopReason translates Anthropic's stop_reason values to
// the openapi DoneEvent.finish_reason enum (stop|length|content_filter|
// tool_calls|error). Unknown values pass through.
func mapAnthropicStopReason(r string) string {
	switch r {
	case "end_turn":
		return "stop"
	case "max_tokens":
		return "length"
	case "stop_sequence":
		return "stop"
	case "tool_use":
		return "tool_calls"
	default:
		return r
	}
}

// openAnthropicStream POSTs the chat-completion-equivalent body to
// Anthropic's /v1/messages with stream:true forced.
func openAnthropicStream(
	ctx context.Context,
	client *http.Client,
	baseURL, secret string,
	body map[string]any,
) (*http.Response, error) {
	body["stream"] = true
	headers := map[string]string{
		"x-api-key":         secret,
		"anthropic-version": anthropicAPIVersion,
	}
	url := baseURL + anthropicMessagesEndpoint
	return doStreamPOST(ctx, client, url, headers, body)
}

// doStreamPOST is a thin generalization of openCompletionStream for
// providers with non-OpenAI-compat URLs/headers. Marshals body, sets
// Accept: text/event-stream, returns the response (caller owns Close).
func doStreamPOST(
	ctx context.Context,
	client *http.Client,
	url string,
	headers map[string]string,
	body map[string]any,
) (*http.Response, error) {
	raw, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(raw))
	if err != nil {
		return nil, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http: %w", err)
	}
	if resp.StatusCode >= 400 {
		buf := make([]byte, 512)
		n, _ := resp.Body.Read(buf)
		_ = resp.Body.Close()
		return nil, fmt.Errorf("provider %d: %s", resp.StatusCode, string(buf[:n]))
	}
	return resp, nil
}
