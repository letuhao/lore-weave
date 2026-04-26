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
