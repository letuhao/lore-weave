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

// ── Phase 3b-followup: per-operation JSON-merging aggregators ────────

func feedJSON(a Aggregator, chunkIdx int, jsonContent string, inputTokens, outputTokens int) {
	a.StartChunk(chunkIdx)
	a.Accept(provider.StreamChunk{
		Kind: provider.StreamChunkToken, Delta: jsonContent,
	})
	a.Accept(provider.StreamChunk{
		Kind: provider.StreamChunkUsage, InputTokens: inputTokens, OutputTokens: outputTokens,
	})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkDone, FinishReason: "stop"})
	a.EndChunk(chunkIdx)
}

func TestEntityAggregator_MergesAcrossChunks(t *testing.T) {
	a := NewAggregator("entity_extraction")
	feedJSON(a, 0, `{"entities":[
		{"name":"Holmes","kind":"person","aliases":["Sherlock"],"confidence":0.9},
		{"name":"Watson","kind":"person","aliases":[],"confidence":0.85}
	]}`, 100, 30)
	feedJSON(a, 1, `{"entities":[
		{"name":"Holmes","kind":"person","aliases":["Mr. Holmes"],"confidence":0.95},
		{"name":"London","kind":"place","aliases":[],"confidence":0.7}
	]}`, 100, 25)

	result, in, out := a.Finalize()
	if in != 200 || out != 55 {
		t.Errorf("usage summed wrong: in=%d out=%d", in, out)
	}
	entities, ok := result["entities"].([]any)
	if !ok || len(entities) != 3 {
		t.Fatalf("expected 3 deduped entities, got %d: %#v", len(entities), result["entities"])
	}
	// Holmes appears once with higher confidence kept + aliases unioned.
	for _, item := range entities {
		row := item.(map[string]any)
		if row["name"] != "Holmes" {
			continue
		}
		if floatOrZero(row["confidence"]) != 0.95 {
			t.Errorf("Holmes confidence should be 0.95 (chunk 1's), got %v", row["confidence"])
		}
		aliases, _ := row["aliases"].([]any)
		got := map[string]bool{}
		for _, a := range aliases {
			if s, ok := a.(string); ok {
				got[s] = true
			}
		}
		if !got["Sherlock"] || !got["Mr. Holmes"] {
			t.Errorf("aliases not unioned: %v", aliases)
		}
	}
}

func TestRelationAggregator_DedupsByTuple(t *testing.T) {
	a := NewAggregator("relation_extraction")
	feedJSON(a, 0, `{"relations":[
		{"subject":"Holmes","predicate":"works_at","object":"221B","polarity":"affirm","confidence":0.9},
		{"subject":"Watson","predicate":"helps","object":"Holmes","polarity":"affirm","confidence":0.85}
	]}`, 50, 20)
	feedJSON(a, 1, `{"relations":[
		{"subject":"Holmes","predicate":"works_at","object":"221B","polarity":"affirm","confidence":0.95},
		{"subject":"Holmes","predicate":"investigates","object":"crime","polarity":"affirm","confidence":0.8}
	]}`, 50, 15)

	result, _, _ := a.Finalize()
	relations := result["relations"].([]any)
	if len(relations) != 3 {
		t.Errorf("expected 3 deduped relations, got %d: %#v", len(relations), relations)
	}
	// Holmes works_at 221B should keep confidence 0.95 (chunk 1 won).
	for _, item := range relations {
		r := item.(map[string]any)
		if r["subject"] == "Holmes" && r["predicate"] == "works_at" {
			if floatOrZero(r["confidence"]) != 0.95 {
				t.Errorf("works_at confidence should be 0.95, got %v", r["confidence"])
			}
		}
	}
}

func TestRelationAggregator_DistinctPolarityNotDeduped(t *testing.T) {
	// `(A loves B, affirm)` and `(A loves B, negate)` are distinct
	// — polarity is part of the dedup key.
	a := NewAggregator("relation_extraction")
	feedJSON(a, 0, `{"relations":[
		{"subject":"A","predicate":"loves","object":"B","polarity":"affirm","confidence":0.9},
		{"subject":"A","predicate":"loves","object":"B","polarity":"negate","confidence":0.7}
	]}`, 10, 5)

	result, _, _ := a.Finalize()
	if len(result["relations"].([]any)) != 2 {
		t.Errorf("polarity-distinct relations should not dedup")
	}
}

func TestEventAggregator_DedupsByNameAndTimeCue(t *testing.T) {
	a := NewAggregator("event_extraction")
	feedJSON(a, 0, `{"events":[
		{"name":"murder","kind":"crime","participants":["X"],"time_cue":"midnight","summary":"old summary","confidence":0.7}
	]}`, 30, 10)
	feedJSON(a, 1, `{"events":[
		{"name":"murder","kind":"crime","participants":["X","Y"],"time_cue":"midnight","summary":"new summary","confidence":0.9},
		{"name":"murder","kind":"crime","participants":["Z"],"time_cue":"dawn","summary":"different event","confidence":0.8}
	]}`, 30, 12)

	result, _, _ := a.Finalize()
	events := result["events"].([]any)
	if len(events) != 2 {
		t.Errorf("expected 2 events (murder@midnight + murder@dawn), got %d: %#v", len(events), events)
	}
	// midnight murder should win with confidence=0.9 + new summary.
	for _, item := range events {
		ev := item.(map[string]any)
		if ev["time_cue"] == "midnight" {
			if floatOrZero(ev["confidence"]) != 0.9 {
				t.Errorf("midnight murder confidence should be 0.9, got %v", ev["confidence"])
			}
			if ev["summary"] != "new summary" {
				t.Errorf("higher-confidence summary should win, got %v", ev["summary"])
			}
		}
	}
}

func TestJSONListAggregator_MalformedChunkSurfacedAsErrorAndOthersStillMerge(t *testing.T) {
	// Phase 4a goal: knowledge-service still completes a chapter even
	// if one chunk's LLM output was malformed.
	a := NewAggregator("entity_extraction")
	feedJSON(a, 0, `{"entities":[{"name":"A","kind":"person","aliases":[],"confidence":0.9}]}`, 10, 5)
	feedJSON(a, 1, `not-valid-json{{`, 10, 5)
	feedJSON(a, 2, `{"entities":[{"name":"B","kind":"person","aliases":[],"confidence":0.9}]}`, 10, 5)

	result, _, _ := a.Finalize()
	entities := result["entities"].([]any)
	if len(entities) != 2 {
		t.Errorf("expected 2 entities (A from chunk 0, B from chunk 2), got %d: %#v", len(entities), entities)
	}
	errors, ok := result["chunk_errors"].([]string)
	if !ok || len(errors) != 1 {
		t.Errorf("expected 1 chunk_errors entry for chunk 1, got %#v", result["chunk_errors"])
	}
}

func TestJSONListAggregator_MissingListFieldSurfacedAsError(t *testing.T) {
	a := NewAggregator("entity_extraction")
	feedJSON(a, 0, `{"wrong_field":[]}`, 10, 5)
	result, _, _ := a.Finalize()
	if errs, ok := result["chunk_errors"].([]string); !ok || len(errs) != 1 {
		t.Errorf("expected chunk_errors for missing list field, got %#v", result["chunk_errors"])
	}
}

func TestJSONListAggregator_UnchunkedSingleParseStillWorks(t *testing.T) {
	// Backward-compat: caller skips StartChunk/EndChunk (Phase 2b
	// pattern). Aggregator should treat the entire token stream as
	// one implicit chunk and parse on Finalize.
	a := NewAggregator("entity_extraction")
	a.Accept(provider.StreamChunk{
		Kind: provider.StreamChunkToken,
		Delta: `{"entities":[{"name":"X","kind":"person","aliases":[],"confidence":0.5}]}`,
	})
	a.Accept(provider.StreamChunk{Kind: provider.StreamChunkDone, FinishReason: "stop"})
	result, _, _ := a.Finalize()
	entities := result["entities"].([]any)
	if len(entities) != 1 {
		t.Errorf("unchunked path should parse 1 entity, got %d: %#v", len(entities), entities)
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
