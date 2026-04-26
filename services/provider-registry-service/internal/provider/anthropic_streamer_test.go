package provider

// Phase 1c-anthropic — unit tests for streamAnthropicSSE. Mirrors the
// streamer_test.go pattern but with Anthropic's SSE shape.

import (
	"context"
	"strings"
	"testing"
)

func collectAnthropicChunks(t *testing.T, body string) []StreamChunk {
	t.Helper()
	var chunks []StreamChunk
	emit := func(c StreamChunk) error {
		chunks = append(chunks, c)
		return nil
	}
	if err := streamAnthropicSSE(context.Background(), strings.NewReader(body), emit); err != nil {
		t.Fatalf("streamAnthropicSSE: %v", err)
	}
	return chunks
}

func TestStreamAnthropicSSE_BasicTextDelta(t *testing.T) {
	body := `event: message_start
data: {"type":"message_start","message":{"id":"m1","model":"claude","usage":{"input_tokens":12}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}

event: message_stop
data: {"type":"message_stop"}

`
	chunks := collectAnthropicChunks(t, body)
	// Expect: 2 token + 1 usage + 1 done
	var tokens []string
	var usage *StreamChunk
	var done *StreamChunk
	for i := range chunks {
		switch chunks[i].Kind {
		case StreamChunkToken:
			tokens = append(tokens, chunks[i].Delta)
		case StreamChunkUsage:
			usage = &chunks[i]
		case StreamChunkDone:
			done = &chunks[i]
		}
	}
	if len(tokens) != 2 || tokens[0] != "Hello" || tokens[1] != " world" {
		t.Errorf("tokens wrong: %v", tokens)
	}
	if usage == nil || usage.InputTokens != 12 || usage.OutputTokens != 2 {
		t.Errorf("usage wrong: %+v", usage)
	}
	if done == nil || done.FinishReason != "stop" {
		t.Errorf("done wrong: %+v", done)
	}
}

func TestStreamAnthropicSSE_ThinkingDeltaSurfacedSeparately(t *testing.T) {
	// Claude 3.7+ extended-thinking emits content_block_start with
	// type=thinking + content_block_delta with thinking_delta.
	body := `event: message_start
data: {"type":"message_start","message":{"usage":{"input_tokens":5}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"Let me think"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"answer"}}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":3}}

event: message_stop
data: {"type":"message_stop"}

`
	chunks := collectAnthropicChunks(t, body)
	var reasoning, tokens []string
	for _, c := range chunks {
		if c.Kind == StreamChunkReasoning {
			reasoning = append(reasoning, c.Delta)
		}
		if c.Kind == StreamChunkToken {
			tokens = append(tokens, c.Delta)
		}
	}
	if len(reasoning) != 1 || reasoning[0] != "Let me think" {
		t.Errorf("reasoning wrong: %v", reasoning)
	}
	if len(tokens) != 1 || tokens[0] != "answer" {
		t.Errorf("tokens wrong: %v", tokens)
	}
}

func TestStreamAnthropicSSE_StopReasonMapping(t *testing.T) {
	// Anthropic stop_reason values map to canonical finish_reason.
	for _, tc := range []struct{ anthropic, want string }{
		{"end_turn", "stop"},
		{"max_tokens", "length"},
		{"stop_sequence", "stop"},
		{"tool_use", "tool_calls"},
	} {
		body := `event: message_start
data: {"type":"message_start","message":{"usage":{"input_tokens":1}}}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"` + tc.anthropic + `"},"usage":{"output_tokens":1}}

event: message_stop
data: {"type":"message_stop"}

`
		chunks := collectAnthropicChunks(t, body)
		var done *StreamChunk
		for i := range chunks {
			if chunks[i].Kind == StreamChunkDone {
				done = &chunks[i]
			}
		}
		if done == nil {
			t.Errorf("%q: no done event", tc.anthropic)
			continue
		}
		if done.FinishReason != tc.want {
			t.Errorf("%q → %q, want %q", tc.anthropic, done.FinishReason, tc.want)
		}
	}
}

func TestStreamAnthropicSSE_PingEventsIgnored(t *testing.T) {
	body := `event: message_start
data: {"type":"message_start","message":{"usage":{"input_tokens":1}}}

event: ping
data: {"type":"ping"}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"x"}}

event: ping
data: {"type":"ping"}

event: message_stop
data: {"type":"message_stop"}

`
	chunks := collectAnthropicChunks(t, body)
	var tokenCount int
	for _, c := range chunks {
		if c.Kind == StreamChunkToken {
			tokenCount++
		}
	}
	if tokenCount != 1 {
		t.Errorf("ping events polluted token count: got %d, want 1", tokenCount)
	}
}

func TestStreamAnthropicSSE_ErrorEventSurfacedAndStops(t *testing.T) {
	body := `event: error
data: {"type":"error","error":{"type":"overloaded_error","message":"Service overloaded"}}

event: message_stop
data: {"type":"message_stop"}

`
	chunks := collectAnthropicChunks(t, body)
	var hasError bool
	for _, c := range chunks {
		if c.Kind == StreamChunkError && c.Code == "LLM_UPSTREAM_ERROR" && c.Message == "Service overloaded" {
			hasError = true
		}
	}
	if !hasError {
		t.Errorf("error event not surfaced: %#v", chunks)
	}
}

func TestStreamAnthropicSSE_MalformedJSONEmitsDecodeError(t *testing.T) {
	body := `event: content_block_delta
data: not-valid-json

event: message_stop
data: {"type":"message_stop"}

`
	chunks := collectAnthropicChunks(t, body)
	var hasDecode bool
	for _, c := range chunks {
		if c.Kind == StreamChunkError && c.Code == "LLM_DECODE_ERROR" {
			hasDecode = true
		}
	}
	if !hasDecode {
		t.Errorf("malformed JSON should emit LLM_DECODE_ERROR: %#v", chunks)
	}
}

func TestStreamAnthropicSSE_EmptyTextDeltaSkipped(t *testing.T) {
	// Provider keep-alive: content_block_delta with empty text. Should
	// not produce a token chunk.
	body := `event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"real"}}

event: message_stop
data: {"type":"message_stop"}

`
	chunks := collectAnthropicChunks(t, body)
	var tokens []string
	for _, c := range chunks {
		if c.Kind == StreamChunkToken {
			tokens = append(tokens, c.Delta)
		}
	}
	if len(tokens) != 1 || tokens[0] != "real" {
		t.Errorf("empty delta should be skipped, got %v", tokens)
	}
}
