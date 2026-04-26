package provider

// Phase 1a unit tests for the OpenAI-compat SSE streamer. Pure helper
// tests — no live HTTP call, no provider connection. Tests feed a
// reconstructed SSE wire stream into streamOpenAICompat() and assert
// the canonical StreamChunk emissions.

import (
	"context"
	"strings"
	"testing"
)

func collectChunks(t *testing.T, body string) []StreamChunk {
	t.Helper()
	var chunks []StreamChunk
	emit := func(c StreamChunk) error {
		chunks = append(chunks, c)
		return nil
	}
	if err := streamOpenAICompat(context.Background(), strings.NewReader(body), emit); err != nil {
		t.Fatalf("streamOpenAICompat: %v", err)
	}
	return chunks
}

func TestStreamOpenAICompat_BasicTokens(t *testing.T) {
	body := `data: {"choices":[{"delta":{"content":"Hello"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":" world"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	// Expect: token Hello, token " world", done
	if len(chunks) != 3 {
		t.Fatalf("expected 3 chunks, got %d: %#v", len(chunks), chunks)
	}
	if chunks[0].Kind != StreamChunkToken || chunks[0].Delta != "Hello" || chunks[0].Index != 0 {
		t.Errorf("chunk[0] = %+v", chunks[0])
	}
	if chunks[1].Kind != StreamChunkToken || chunks[1].Delta != " world" || chunks[1].Index != 1 {
		t.Errorf("chunk[1] = %+v", chunks[1])
	}
	if chunks[2].Kind != StreamChunkDone || chunks[2].FinishReason != "stop" {
		t.Errorf("chunk[2] = %+v", chunks[2])
	}
}

func TestStreamOpenAICompat_UsageEvent(t *testing.T) {
	body := `data: {"choices":[{"delta":{"content":"hi"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}

data: [DONE]

`
	chunks := collectChunks(t, body)
	// Expect: token hi, usage, done
	if len(chunks) != 3 {
		t.Fatalf("expected 3 chunks, got %d: %#v", len(chunks), chunks)
	}
	if chunks[0].Kind != StreamChunkToken {
		t.Errorf("chunk[0] should be token, got %+v", chunks[0])
	}
	if chunks[1].Kind != StreamChunkUsage {
		t.Errorf("chunk[1] should be usage, got %+v", chunks[1])
	}
	if chunks[1].InputTokens != 10 || chunks[1].OutputTokens != 2 {
		t.Errorf("usage tokens wrong: %+v", chunks[1])
	}
	if chunks[2].Kind != StreamChunkDone {
		t.Errorf("chunk[2] should be done, got %+v", chunks[2])
	}
}

func TestStreamOpenAICompat_ReasoningTokens(t *testing.T) {
	// LM Studio thinking-model usage payload (qwen3.x format).
	body := `data: {"choices":[{"delta":{"content":"answer"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}],"usage":{"prompt_tokens":24,"completion_tokens":575,"total_tokens":599,"completion_tokens_details":{"reasoning_tokens":567}}}

data: [DONE]

`
	chunks := collectChunks(t, body)
	var usage *StreamChunk
	for i := range chunks {
		if chunks[i].Kind == StreamChunkUsage {
			usage = &chunks[i]
			break
		}
	}
	if usage == nil {
		t.Fatalf("no usage chunk: %#v", chunks)
	}
	if usage.ReasoningTokens == nil || *usage.ReasoningTokens != 567 {
		t.Errorf("reasoning_tokens not propagated: %+v", usage.ReasoningTokens)
	}
}

func TestStreamOpenAICompat_FinishReasonOnly(t *testing.T) {
	// Some providers send finish_reason in a chunk but no usage.
	// We should still emit a `done` event with the finish_reason.
	body := `data: {"choices":[{"delta":{"content":"hi"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"length"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	last := chunks[len(chunks)-1]
	if last.Kind != StreamChunkDone || last.FinishReason != "length" {
		t.Errorf("expected done with finish_reason=length, got %+v", last)
	}
}

func TestStreamOpenAICompat_MalformedChunkEmitsError(t *testing.T) {
	body := `data: not-valid-json

data: [DONE]

`
	chunks := collectChunks(t, body)
	// Should see error chunk + done (the parser stops on error but the
	// outer wrapper still emits a terminal done).
	hasError := false
	for _, c := range chunks {
		if c.Kind == StreamChunkError && c.Code == "LLM_DECODE_ERROR" {
			hasError = true
		}
	}
	if !hasError {
		t.Errorf("expected LLM_DECODE_ERROR chunk on malformed JSON: %#v", chunks)
	}
}

func TestStreamOpenAICompat_EmptyDeltaSkipped(t *testing.T) {
	// Some providers send keepalive chunks with empty delta.content.
	// We should NOT emit a token chunk for those.
	body := `data: {"choices":[{"delta":{"content":""},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"real"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	var tokens []string
	for _, c := range chunks {
		if c.Kind == StreamChunkToken {
			tokens = append(tokens, c.Delta)
		}
	}
	if len(tokens) != 1 || tokens[0] != "real" {
		t.Errorf("expected exactly one non-empty token, got %v", tokens)
	}
}

func TestStreamOpenAICompat_SSECommentsIgnored(t *testing.T) {
	body := `: keep-alive comment

data: {"choices":[{"delta":{"content":"x"},"index":0,"finish_reason":null}]}

: another keep-alive

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	if len(chunks) != 2 || chunks[0].Delta != "x" {
		t.Errorf("comments must be ignored; got %#v", chunks)
	}
}

func TestStreamOpenAICompat_EmitErrorStopsStreaming(t *testing.T) {
	// If emit returns an error (caller disconnected), the streamer must
	// stop and propagate the error up.
	body := `data: {"choices":[{"delta":{"content":"a"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"b"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"c"},"index":0,"finish_reason":null}]}

data: [DONE]

`
	count := 0
	emit := func(c StreamChunk) error {
		count++
		if count >= 2 {
			return context.Canceled
		}
		return nil
	}
	err := streamOpenAICompat(context.Background(), strings.NewReader(body), emit)
	if err != context.Canceled {
		t.Errorf("expected context.Canceled, got %v", err)
	}
	// We stop after the 2nd emit (token "b"); the third token "c" should
	// not be processed. The streamer also tries to emit a final `done`
	// which counts as the (failing) emit, so we expect count >= 2.
	if count < 2 {
		t.Errorf("expected at least 2 emits before cancel, got %d", count)
	}
}

func TestReadSSELines_HandlesEventNamePrefix(t *testing.T) {
	// Anthropic-style SSE has event: lines that we don't use yet but
	// shouldn't crash on.
	body := `event: content_block_delta
data: {"hello":"world"}

`
	var seenEvents []string
	var seenData []string
	err := readSSELines(context.Background(), strings.NewReader(body), func(eventName, data string) error {
		seenEvents = append(seenEvents, eventName)
		seenData = append(seenData, data)
		return nil
	})
	if err != nil {
		t.Fatalf("readSSELines: %v", err)
	}
	if len(seenEvents) != 1 || seenEvents[0] != "content_block_delta" {
		t.Errorf("event name not parsed: %v", seenEvents)
	}
	if len(seenData) != 1 || seenData[0] != `{"hello":"world"}` {
		t.Errorf("data not parsed: %v", seenData)
	}
}
