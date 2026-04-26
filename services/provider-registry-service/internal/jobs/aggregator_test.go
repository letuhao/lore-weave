package jobs

import (
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

func TestChatAggregator_AccumulatesTokensAndUsage(t *testing.T) {
	a := NewAggregator("chat")
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "Hello"})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: " world"})
	a.Accept(provider.StreamChunk{
		Kind:         provider.StreamChunkUsage,
		InputTokens:  10,
		OutputTokens: 2,
	})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkDone, FinishReason: "stop"})

	result, in, out := a.Finalize()
	if in != 10 || out != 2 {
		t.Errorf("usage wrong: in=%d out=%d", in, out)
	}
	msgs, ok := result["messages"].([]any)
	if !ok || len(msgs) != 1 {
		t.Fatalf("messages shape wrong: %#v", result["messages"])
	}
	msg := msgs[0].(map[string]any)
	if msg["role"] != "assistant" || msg["content"] != "Hello world" {
		t.Errorf("message wrong: %#v", msg)
	}
	if result["finish_reason"] != "stop" {
		t.Errorf("finish_reason wrong: %v", result["finish_reason"])
	}
}

func TestChatAggregator_ReasoningSurfacedSeparately(t *testing.T) {
	a := NewAggregator("chat")
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkReasoning, Delta: "thinking"})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "answer"})
	rt := 50
	a.Accept(provider.StreamChunk{
		Kind:            provider.StreamChunkUsage,
		InputTokens:     1,
		OutputTokens:    1,
		ReasoningTokens: &rt,
	})

	result, _, _ := a.Finalize()
	msgs := result["messages"].([]any)
	msg := msgs[0].(map[string]any)
	if msg["reasoning_content"] != "thinking" {
		t.Errorf("reasoning_content lost: %#v", msg)
	}
	if msg["content"] != "answer" {
		t.Errorf("content lost: %#v", msg)
	}
	usage := result["usage"].(map[string]any)
	if usage["reasoning_tokens"] != 50 {
		t.Errorf("reasoning_tokens not propagated: %v", usage["reasoning_tokens"])
	}
}

func TestChatAggregator_NoReasoningOmitsField(t *testing.T) {
	a := NewAggregator("chat")
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "hi"})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkDone, FinishReason: "stop"})
	result, _, _ := a.Finalize()
	msgs := result["messages"].([]any)
	msg := msgs[0].(map[string]any)
	if _, ok := msg["reasoning_content"]; ok {
		t.Errorf("reasoning_content should be omitted when empty: %#v", msg)
	}
	usage := result["usage"].(map[string]any)
	if _, ok := usage["reasoning_tokens"]; ok {
		t.Errorf("reasoning_tokens should be omitted when zero: %#v", usage)
	}
}

func TestNewAggregator_UnknownOpFallsBackToChat(t *testing.T) {
	// Unknown operations should still accumulate gracefully (we'll
	// implement per-op aggregators in Phase 3+; for now the chat path
	// is a safe default).
	a := NewAggregator("embedding")
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "x"})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkDone})
	result, _, _ := a.Finalize()
	if _, ok := result["messages"]; !ok {
		t.Errorf("fallback aggregator must produce a result envelope: %#v", result)
	}
}

func TestChatAggregator_MultiChunkConcatsContent(t *testing.T) {
	// Phase 3b — chunked job: each StartChunk/EndChunk pair receives
	// its own stream events. Final content is concatenated with
	// chunkSeparator between non-empty chunks.
	a := NewAggregator("chat")

	a.StartChunk(0)
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "Hello"})
	a.Accept(provider.StreamChunk{
		Kind: provider.StreamChunkUsage, InputTokens: 5, OutputTokens: 1,
	})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkDone, FinishReason: "stop"})
	a.EndChunk(0)

	a.StartChunk(1)
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "World"})
	a.Accept(provider.StreamChunk{
		Kind: provider.StreamChunkUsage, InputTokens: 6, OutputTokens: 1,
	})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkDone, FinishReason: "length"})
	a.EndChunk(1)

	result, in, out := a.Finalize()
	// Usage SUMMED across chunks
	if in != 11 || out != 2 {
		t.Errorf("multi-chunk usage not summed: in=%d out=%d (want 11, 2)", in, out)
	}
	// Content joined with chunkSeparator
	msg := result["messages"].([]any)[0].(map[string]any)
	wantContent := "Hello\n\nWorld"
	if msg["content"] != wantContent {
		t.Errorf("content = %q, want %q", msg["content"], wantContent)
	}
	// Last chunk's finish reason wins
	if result["finish_reason"] != "length" {
		t.Errorf("finish_reason should be from last chunk, got %v", result["finish_reason"])
	}
}

func TestChatAggregator_MultiChunkReasoningKeepsLastChunk(t *testing.T) {
	// Per design: thinking-model reasoning is only meaningful for the
	// FINAL chunk (synthesis); earlier chunks' draft thoughts get
	// dropped to keep the surfaced reasoning_content focused.
	a := NewAggregator("chat")
	a.StartChunk(0)
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkReasoning, Delta: "draft thought 1"})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "draft answer"})
	a.EndChunk(0)
	a.StartChunk(1)
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkReasoning, Delta: "final synthesis"})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "final answer"})
	a.EndChunk(1)

	result, _, _ := a.Finalize()
	msg := result["messages"].([]any)[0].(map[string]any)
	if got := msg["reasoning_content"]; got != "final synthesis" {
		t.Errorf("reasoning_content should be last chunk only, got %q", got)
	}
}

func TestChatAggregator_MultiChunkSkipsEmptyChunkSeparator(t *testing.T) {
	// An empty chunk shouldn't produce a stray separator between
	// neighbours.
	a := NewAggregator("chat")
	a.StartChunk(0)
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "first"})
	a.EndChunk(0)
	a.StartChunk(1) // empty chunk
	a.EndChunk(1)
	a.StartChunk(2)
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "third"})
	a.EndChunk(2)

	result, _, _ := a.Finalize()
	msg := result["messages"].([]any)[0].(map[string]any)
	want := "first\n\nthird"
	if msg["content"] != want {
		t.Errorf("content = %q, want %q", msg["content"], want)
	}
}

func TestChatAggregator_UnchunkedPathStillWorks(t *testing.T) {
	// Backward-compat: no Start/End calls = single-chunk behavior
	// preserved exactly.
	a := NewAggregator("chat")
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "Hi"})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkReasoning, Delta: "thinking"})
	a.Accept(provider.StreamChunk{
		Kind: provider.StreamChunkUsage, InputTokens: 3, OutputTokens: 1,
	})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkDone, FinishReason: "stop"})

	result, in, out := a.Finalize()
	if in != 3 || out != 1 {
		t.Errorf("unchunked usage wrong: in=%d out=%d", in, out)
	}
	msg := result["messages"].([]any)[0].(map[string]any)
	if msg["content"] != "Hi" {
		t.Errorf("content wrong: %v", msg["content"])
	}
	if msg["reasoning_content"] != "thinking" {
		t.Errorf("reasoning wrong: %v", msg["reasoning_content"])
	}
}

func TestChatAggregator_FinalizeFlushesUnclosedChunk(t *testing.T) {
	// Defensive: caller forgot EndChunk before Finalize. Aggregator
	// should still emit the in-flight chunk content.
	a := NewAggregator("chat")
	a.StartChunk(0)
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "stuck"})
	// Forget EndChunk(0) — go straight to Finalize.
	result, _, _ := a.Finalize()
	msg := result["messages"].([]any)[0].(map[string]any)
	if msg["content"] != "stuck" {
		t.Errorf("Finalize must flush unclosed chunk; got %q", msg["content"])
	}
}

func TestIsTerminal(t *testing.T) {
	for _, s := range []string{"completed", "failed", "cancelled"} {
		if !IsTerminal(s) {
			t.Errorf("%q should be terminal", s)
		}
	}
	for _, s := range []string{"pending", "running", "unknown"} {
		if IsTerminal(s) {
			t.Errorf("%q should NOT be terminal", s)
		}
	}
}
