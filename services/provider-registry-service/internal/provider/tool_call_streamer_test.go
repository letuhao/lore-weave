package provider

// Phase 0b — unit tests for tool-call re-framing in both SSE streamers.
// Pure helper tests: feed a reconstructed provider SSE stream into the
// streamer and assert the canonical StreamChunkToolCall emissions.
// Reuses collectChunks / collectAnthropicChunks from the sibling test files.

import "testing"

// ── OpenAI-compat tool-call streaming ─────────────────────────────────

func TestStreamOpenAICompat_ToolCallMultiFragment(t *testing.T) {
	// OpenAI streams a tool call as: first fragment carries id + name with
	// empty arguments, later fragments carry only argument string slices.
	body := `data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc","type":"function","function":{"name":"submit_zone_classifications","arguments":""}}]},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"clas"}}]},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"sifications\":[]}"}}]},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"tool_calls"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	// Expect: 3 tool_call fragments + done.
	if len(chunks) != 4 {
		t.Fatalf("expected 4 chunks, got %d: %#v", len(chunks), chunks)
	}
	// First fragment MUST be emitted even though arguments_delta == "" —
	// it carries the only id + name.
	if chunks[0].Kind != StreamChunkToolCall || chunks[0].ToolCallID != "call_abc" ||
		chunks[0].ToolName != "submit_zone_classifications" || chunks[0].ArgumentsDelta != "" ||
		chunks[0].Index != 0 {
		t.Errorf("chunk[0] = %+v", chunks[0])
	}
	if chunks[1].Kind != StreamChunkToolCall || chunks[1].ArgumentsDelta != `{"clas` {
		t.Errorf("chunk[1] = %+v", chunks[1])
	}
	if chunks[2].Kind != StreamChunkToolCall || chunks[2].ArgumentsDelta != `sifications":[]}` {
		t.Errorf("chunk[2] = %+v", chunks[2])
	}
	if chunks[3].Kind != StreamChunkDone || chunks[3].FinishReason != "tool_calls" {
		t.Errorf("chunk[3] = %+v", chunks[3])
	}
	// Reassembled arguments round-trip to the full JSON.
	full := chunks[0].ArgumentsDelta + chunks[1].ArgumentsDelta + chunks[2].ArgumentsDelta
	if full != `{"classifications":[]}` {
		t.Errorf("reassembled args = %q", full)
	}
}

func TestStreamOpenAICompat_ToolCallIndexVerbatim(t *testing.T) {
	// The streamer must set Index from the provider's tool_calls[].index
	// verbatim (NOT a local counter). A call reported at index 2 stays 2.
	body := `data: {"choices":[{"delta":{"tool_calls":[{"index":2,"id":"call_z","function":{"name":"t","arguments":"x"}}]}}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	if len(chunks) != 2 || chunks[0].Kind != StreamChunkToolCall || chunks[0].Index != 2 {
		t.Fatalf("expected tool_call at index 2, got %#v", chunks)
	}
}

func TestStreamOpenAICompat_ToolCallEmptyFragmentSkipped(t *testing.T) {
	// A fully-empty tool-call fragment (no id, no name, no arguments)
	// carries no information and must be skipped.
	body := `data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"y"}}]}}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	if len(chunks) != 2 {
		t.Fatalf("expected 1 tool_call + 1 done, got %d: %#v", len(chunks), chunks)
	}
	if chunks[0].Kind != StreamChunkToolCall || chunks[0].ArgumentsDelta != "y" {
		t.Errorf("chunk[0] = %+v", chunks[0])
	}
}

// ── Anthropic tool_use streaming ──────────────────────────────────────

func TestStreamAnthropicSSE_ToolUseBlock(t *testing.T) {
	// Anthropic emits tool_use as content_block_start (id + name) then
	// input_json_delta fragments then content_block_stop.
	body := `event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_xyz","name":"submit_zone_classifications","input":{}}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"clas"}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"sifications\":[]}"}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":20}}

event: message_stop
data: {"type":"message_stop"}

`
	chunks := collectAnthropicChunks(t, body)
	// Expect: tool_call (start) + 2 tool_call (deltas) + usage + done.
	if len(chunks) != 5 {
		t.Fatalf("expected 5 chunks, got %d: %#v", len(chunks), chunks)
	}
	if chunks[0].Kind != StreamChunkToolCall || chunks[0].ToolCallID != "toolu_xyz" ||
		chunks[0].ToolName != "submit_zone_classifications" || chunks[0].Index != 1 ||
		chunks[0].ArgumentsDelta != "" {
		t.Errorf("chunk[0] = %+v", chunks[0])
	}
	if chunks[1].Kind != StreamChunkToolCall || chunks[1].Index != 1 ||
		chunks[1].ArgumentsDelta != `{"clas` {
		t.Errorf("chunk[1] = %+v", chunks[1])
	}
	if chunks[2].Kind != StreamChunkToolCall || chunks[2].ArgumentsDelta != `sifications":[]}` {
		t.Errorf("chunk[2] = %+v", chunks[2])
	}
	if chunks[3].Kind != StreamChunkUsage {
		t.Errorf("chunk[3] = %+v (want usage)", chunks[3])
	}
	if chunks[4].Kind != StreamChunkDone || chunks[4].FinishReason != "tool_calls" {
		t.Errorf("chunk[4] = %+v", chunks[4])
	}
	full := chunks[0].ArgumentsDelta + chunks[1].ArgumentsDelta + chunks[2].ArgumentsDelta
	if full != `{"classifications":[]}` {
		t.Errorf("reassembled args = %q", full)
	}
}

func TestStreamAnthropicSSE_TextBlockStartNotMistakenForToolCall(t *testing.T) {
	// content_block_start for a plain text block must NOT emit a tool_call.
	body := `event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hi"}}

event: message_stop
data: {"type":"message_stop"}

`
	chunks := collectAnthropicChunks(t, body)
	for _, c := range chunks {
		if c.Kind == StreamChunkToolCall {
			t.Errorf("text block produced a tool_call chunk: %+v", c)
		}
	}
}

// ── SupportsTools capability ──────────────────────────────────────────

func TestAdapterSupportsTools(t *testing.T) {
	cases := []struct {
		adapter Adapter
		want    bool
	}{
		{&openaiAdapter{}, true},
		{&lmStudioAdapter{}, true},
		{&ollamaAdapter{}, true},
		// anthropicAdapter flipped to true in Phase K21-B / D12 — the
		// adapter now converts the OpenAI tool shape to Anthropic's.
		{&anthropicAdapter{}, true},
	}
	for _, c := range cases {
		if got := c.adapter.SupportsTools(); got != c.want {
			t.Errorf("%T.SupportsTools() = %v, want %v", c.adapter, got, c.want)
		}
	}
}

// TestStreamOpenAICompat_MultipleToolCalls — DEFERRED #012. A turn with TWO
// tool calls streamed with interleaved / non-monotonic tool_calls[].index.
// The streamer must emit each fragment with Index taken verbatim from the
// provider (no local counter), so a downstream accumulator can separate them.
func TestStreamOpenAICompat_MultipleToolCalls(t *testing.T) {
	body := `data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_a","function":{"name":"alpha","arguments":""}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":1,"id":"call_b","function":{"name":"beta","arguments":""}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":1,"function":{"arguments":"{\"b\":2}"}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"a\":1}"}}]}}]}

data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	// 4 tool_call fragments + done.
	if len(chunks) != 5 {
		t.Fatalf("expected 5 chunks, got %d: %#v", len(chunks), chunks)
	}
	// Index is verbatim from the provider, in wire order (0, 1, 1, 0) — NOT
	// a monotonic counter.
	wantIndex := []int{0, 1, 1, 0}
	for i, want := range wantIndex {
		if chunks[i].Kind != StreamChunkToolCall || chunks[i].Index != want {
			t.Errorf("chunk[%d] = %+v, want tool_call Index=%d", i, chunks[i], want)
		}
	}
	// Reassemble per index — call 0 and call 1 stay separate.
	args := map[int]string{}
	for _, c := range chunks[:4] {
		args[c.Index] += c.ArgumentsDelta
	}
	if args[0] != `{"a":1}` || args[1] != `{"b":2}` {
		t.Errorf("reassembled per-index args = %#v", args)
	}
	if chunks[4].Kind != StreamChunkDone || chunks[4].FinishReason != "tool_calls" {
		t.Errorf("chunk[4] = %+v", chunks[4])
	}
}
