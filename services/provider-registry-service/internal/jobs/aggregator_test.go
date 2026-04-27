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

// Phase 4a-β — fact_extraction aggregator tests.

func TestFactAggregator_DedupsByTypeAndNormalizedContent(t *testing.T) {
	a := NewAggregator("fact_extraction")
	// Chunk 0 emits a trait-type fact about Holmes.
	feedJSON(a, 0, `{"facts":[
		{"content":"Holmes is a detective","type":"trait","subject":"Holmes","polarity":"affirm","modality":"asserted","confidence":0.7}
	]}`, 20, 8)
	// Chunk 1 emits the SAME content (whitespace/case variation) +
	// SAME type → must dedup, higher confidence wins.
	// Plus a profession-type fact about same content → distinct row
	// (type is part of the key).
	feedJSON(a, 1, `{"facts":[
		{"content":"Holmes  IS a Detective","type":"trait","subject":"Holmes","polarity":"affirm","modality":"asserted","confidence":0.95},
		{"content":"Holmes is a detective","type":"profession","subject":"Holmes","polarity":"affirm","modality":"asserted","confidence":0.9}
	]}`, 20, 10)

	result, _, _ := a.Finalize()
	facts := result["facts"].([]any)
	if len(facts) != 2 {
		t.Errorf("expected 2 facts (trait + profession), got %d: %#v", len(facts), facts)
	}
	for _, item := range facts {
		f := item.(map[string]any)
		if f["type"] == "trait" {
			if floatOrZero(f["confidence"]) != 0.95 {
				t.Errorf("trait fact confidence should be 0.95 (chunk 1 wins), got %v", f["confidence"])
			}
		}
	}
}

func TestFactAggregator_PolarityCollapsesByDesign(t *testing.T) {
	// Phase 4a-β /review-impl MED#1 — factKey EXCLUDES polarity by
	// design, so contradicting polarities (affirm/negate) of the same
	// (type, content) MERGE into a single row. This matches knowledge-
	// service's `_postprocess` which derives fact_id from content
	// alone — the two layers stay consistent end-to-end.
	//
	// Conflict detection is downstream's concern (Pass 2 writer or
	// quality-eval), NOT this aggregator's. If a future cycle decides
	// to surface contradictions at aggregator-level, it MUST also
	// migrate Python's _normalize_content + fact_id derivation to keep
	// the layers in sync — tracked as D-PHASE6-FACT-POLARITY-IN-KEY.
	//
	// This test pins the design choice so a future change that adds
	// polarity to the key (without migrating Python) flips this test
	// loud.
	a := NewAggregator("fact_extraction")
	feedJSON(a, 0, `{"facts":[
		{"content":"Holmes is a detective","type":"trait","polarity":"affirm","modality":"asserted","confidence":0.9}
	]}`, 10, 5)
	feedJSON(a, 1, `{"facts":[
		{"content":"Holmes is a detective","type":"trait","polarity":"negate","modality":"asserted","confidence":0.8}
	]}`, 10, 5)

	result, _, _ := a.Finalize()
	facts := result["facts"].([]any)
	if len(facts) != 1 {
		t.Errorf("regression-lock: factKey currently excludes polarity so "+
			"affirm+negate MERGE to 1 row, got %d. If this fails, polarity "+
			"may have been added to factKey — confirm Python _normalize_content "+
			"+ fact_id were migrated in the same cycle (D-PHASE6-FACT-POLARITY-IN-KEY).",
			len(facts))
	}
}

func TestFactAggregator_NoSubjectStillDedupsByContent(t *testing.T) {
	// Universal claims have no subject; factKey is (type, content) only
	// so subjectless facts dedup correctly.
	a := NewAggregator("fact_extraction")
	feedJSON(a, 0, `{"facts":[
		{"content":"The Empire was vast","type":"world","polarity":"affirm","modality":"asserted","confidence":0.7}
	]}`, 10, 5)
	feedJSON(a, 1, `{"facts":[
		{"content":"The empire was vast","type":"world","polarity":"affirm","modality":"asserted","confidence":0.85}
	]}`, 10, 5)

	result, _, _ := a.Finalize()
	facts := result["facts"].([]any)
	if len(facts) != 1 {
		t.Errorf("expected 1 deduped subjectless fact, got %d: %#v", len(facts), facts)
	}
	if floatOrZero(facts[0].(map[string]any)["confidence"]) != 0.85 {
		t.Errorf("higher-confidence chunk should win, got %v", facts[0].(map[string]any)["confidence"])
	}
}

func TestFactAggregator_DistinctTypesNotMerged(t *testing.T) {
	a := NewAggregator("fact_extraction")
	feedJSON(a, 0, `{"facts":[
		{"content":"Holmes uses cocaine","type":"habit","polarity":"affirm","modality":"asserted","confidence":0.9},
		{"content":"Holmes uses cocaine","type":"backstory","polarity":"affirm","modality":"asserted","confidence":0.8}
	]}`, 20, 10)

	result, _, _ := a.Finalize()
	facts := result["facts"].([]any)
	if len(facts) != 2 {
		t.Errorf("type difference must keep facts distinct, got %d: %#v", len(facts), facts)
	}
}

func TestFactAggregator_NullSubjectFromWinnerFilledByLoser(t *testing.T) {
	// /review-impl Phase 4a-β MED#2 — when the higher-confidence row
	// has subject=null and the lower-confidence row has subject="Holmes"
	// for the same (type, content), the merge MUST keep "Holmes"
	// (loser's non-null beats winner's null). Earlier behavior dropped
	// the subject silently — see mergeKnownKeys docstring.
	a := NewAggregator("fact_extraction")
	feedJSON(a, 0, `{"facts":[
		{"content":"X is brilliant","type":"description","subject":null,"polarity":"affirm","modality":"asserted","confidence":0.95}
	]}`, 10, 5)
	feedJSON(a, 1, `{"facts":[
		{"content":"X is brilliant","type":"description","subject":"Holmes","polarity":"affirm","modality":"asserted","confidence":0.9}
	]}`, 10, 5)

	result, _, _ := a.Finalize()
	facts := result["facts"].([]any)
	if len(facts) != 1 {
		t.Fatalf("expected 1 merged fact, got %d", len(facts))
	}
	merged := facts[0].(map[string]any)
	if merged["subject"] != "Holmes" {
		t.Errorf("MED#2: expected subject='Holmes' (loser non-null beats winner null), got %#v", merged["subject"])
	}
	// Winner's confidence still wins (this is unchanged by the fix).
	if floatOrZero(merged["confidence"]) != 0.95 {
		t.Errorf("expected winner confidence 0.95, got %v", merged["confidence"])
	}
}

func TestEntityAggregator_NullPreferenceAppliesAcrossOps(t *testing.T) {
	// MED#2 fix is in mergeKnownKeys (shared across all jsonListAggregator
	// ops), so verify it also helps entity_extraction. Not strictly
	// needed today (entity has no nullable fields used as identifiers)
	// but pins the cross-op behavior in case a future schema adds one.
	a := NewAggregator("entity_extraction")
	feedJSON(a, 0, `{"entities":[
		{"name":"Holmes","kind":"person","aliases":[],"confidence":0.95,"evidence_passage_id":null}
	]}`, 10, 5)
	feedJSON(a, 1, `{"entities":[
		{"name":"Holmes","kind":"person","aliases":["Sherlock"],"confidence":0.9,"evidence_passage_id":"p-42"}
	]}`, 10, 5)
	result, _, _ := a.Finalize()
	entities := result["entities"].([]any)
	if len(entities) != 1 {
		t.Fatalf("expected 1 merged entity, got %d", len(entities))
	}
	merged := entities[0].(map[string]any)
	if merged["evidence_passage_id"] != "p-42" {
		t.Errorf("MED#2: expected evidence_passage_id='p-42' (loser non-null), got %#v", merged["evidence_passage_id"])
	}
}

func TestFactAggregator_RoutesToJSONListAggregatorViaFactsField(t *testing.T) {
	// Pin the wire contract: fact_extraction op routes through
	// jsonListAggregator and emits result.facts (not result.entities
	// or any other field) so caller's tolerant parser knows where to
	// look.
	a := NewAggregator("fact_extraction")
	feedJSON(a, 0, `{"facts":[{"content":"X","type":"trait","polarity":"affirm","modality":"asserted","confidence":0.8}]}`, 5, 3)
	result, _, _ := a.Finalize()
	if _, ok := result["facts"]; !ok {
		t.Errorf("fact_extraction result must carry 'facts' key, got keys: %v", mapKeys(result))
	}
	if _, ok := result["entities"]; ok {
		t.Errorf("fact_extraction must NOT emit 'entities' key (wrong op routing)")
	}
}

func mapKeys(m map[string]any) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
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
