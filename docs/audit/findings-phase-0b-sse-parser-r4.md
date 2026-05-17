# Adversary Findings -- phase-0b-sse-parser -- Round 4 (final design round -- hard cap)

Design under review: docs/specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md (REVISED, post-r3)
Phase: review-design / Agent: adversary / Round: 4
Status: APPROVED_WITH_WARNINGS (0 BLOCK, 3 WARN)

## Round-3 revision check (all three genuinely closed)

- r3 BLOCK-1 (D3 "next to existing tools pass-through" false for ollama/lm_studio Stream()):
  D3 (spec lines 122-130) now states explicitly that ONLY openaiAdapter.Stream forwards
  input["tools"] today (cites adapters.go:398-400), that lmStudioAdapter.Stream and
  ollamaAdapter.Stream read neither tools nor tool_choice, and that this batch must add
  BOTH tools AND tool_choice pass-through to lmStudioAdapter.Stream + ollamaAdapter.Stream.
  Verified against adapters.go: lmStudioAdapter.Stream (lines 858-883) and
  ollamaAdapter.Stream (lines 671-695) build body from model/messages/temperature/max_tokens
  only -- the spec claim is factually correct, and the harness PoC path (AC-5 -> lm_studio
  adapter) now has an explicit instruction to wire tools. ADEQUATELY RESOLVED.
- r3 WARN-2 (D8 SupportsTools enumerated for 4 adapters, ResolveAdapter default returns a 5th):
  D8 Open-set note (spec lines 198-202) now documents that ResolveAdapter default case
  routes unknown kinds to openaiAdapter (SupportsTools()==true by inheritance), states this
  is the intended safe default, and adds the AC-7 Go test covering both an explicit
  Anthropic-kind reject and an unknown-kind allow. Verified against adapters.go ResolveAdapter
  lines 903-909. ADEQUATELY RESOLVED.
- r3 WARN-3 (no per-index terminal marker; accumulator must handle interleaved indices):
  D4 (spec lines 141-151) now specifies the accumulator is an index-keyed
  BTreeMap<u32, PartialToolCall>, NOT a monotonic list, explicitly handles interleaved /
  non-monotonic / out-of-order index, first-write-wins id/name, and finalizes only at Done.
  AC-3 (lines 226-229) adds the interleaved/out-of-order-index test plus the id/name-on-first-
  fragment test. ADEQUATELY RESOLVED.

The core D1-D8 design is stable since r1; r2/r3/r4 are precision passes. This round raises
three fresh WARNs, none a correctness defect.

---

## Finding 1 -- WARN -- D3: StreamChunk.Index (json:"index,omitempty") is reused for the tool-call index, but that field existing semantics (a monotonic per-stream COUNTER for token/reasoning) differs from the tool-call index (a SEMANTIC call identifier from delta.tool_calls[i].index) -- the spec never flags the dual meaning

D3 (spec line 99) says reuse the existing Index field for the tool-call index -- do NOT add
a second field. That avoids the duplicate-JSON-key bug correctly. But streamer.go:53 shows
StreamChunk.Index int json:"index,omitempty" is today written ONLY as a monotonic counter:
streamOpenAICompat does Index: tokenIdx then tokenIdx++ (lines 192-207), and
streamAnthropicSSE does the same with reasoningIdx (lines 132-151). For token/reasoning the
index is "ordering verification" (openapi TokenEvent.index description, line 536). For
tool_call the same field carries delta.tool_calls[i].index -- which tool call in the turn
(D1, spec line 67). These are unrelated meanings sharing one struct field and one wire key.
No correctness bug -- a tool_call chunk and a token chunk never collide since Kind
discriminates -- but a maintainer reading StreamChunk.Index has no signal that its meaning
is Kind-dependent, and a future change to the token counter logic could be mis-applied to
the tool-call path.

Question for the designer: Should D3 add a one-line note that StreamChunk.Index is
semantically overloaded -- a monotonic ordering counter for Kind=token/reasoning, but the
upstream-supplied call identifier for Kind=tool_call -- so a maintainer does not assume the
tool-call index is also a 0,1,2,... counter the streamer increments?

## Finding 2 -- WARN -- section 2.1 / AC-1: the spec says add ToolCallEvent to StreamEventEnvelope but no D-decision enumerates the discriminator.mapping entry, and adding the schema without the mapping line is a silently-incomplete openapi change

Section 2.1 (spec line 34) and AC-1 (line 222) require ToolCallEvent present in the
StreamEventEnvelope. But openapi.yaml shows StreamEventEnvelope is a oneOf list (lines
497-503) PLUS a separate hand-maintained discriminator.mapping block (lines 504-512). The
audio-chunk precedent proves the mapping is a distinct manual step: AudioChunkEvent has both
a oneOf entry (line 503) AND a mapping entry audio-chunk -> AudioChunkEvent (line 512).
No D-decision spells out add tool_call -> ToolCallEvent to discriminator.mapping AND to the
oneOf array. AC-1 (ToolCallEvent present with the section 3 shape) would pass a YAML that
defines the ToolCallEvent schema and adds it to oneOf but omits the mapping entry -- in which
a strict discriminator-aware code generator (or the Rust serde tag=event / Python
Field(discriminator=event_type) parsers the spec calls locked by wire_format tests)
cannot route a data: {"event":"tool_call",...} frame.

Question for the designer: Should AC-1 explicitly require BOTH the oneOf entry AND the
discriminator.mapping entry tool_call -> ToolCallEvent (mirroring how audio-chunk appears in
both places), so a YAML that adds the schema but forgets the mapping line does not pass
acceptance?

## Finding 3 -- WARN -- D4: the accumulator finalizes only at Done (or stream end) but stream end is undefined for an ERROR-terminated stream -- the harness (AC-5, live lmstudio) has no defined contract for salvaging a partial tool call when the SSE connection drops before a Done event

D4 (spec lines 148-151) says ToolCallAccumulator.finish() finalizes only at Done (or stream
end) and a still-empty arguments at Done is surfaced to the caller. The Go side reliably
emits a terminal StreamChunkDone even on [DONE] or ctx-cancel: streamOpenAICompat emits Done
unconditionally at streamer.go:236 after readSSELines returns, including when readSSELines
returns scanner.Err() from a dropped connection. But the canonical-event consumer is the
Rust SDK (D4, client.rs), and its stream() is impl Stream<Item = Result<StreamEvent,
LlmError>> -- on a reqwest transport error mid-stream the parser yields Err(LlmError) and
the iteration ends WITHOUT a StreamEvent::Done. The spec (or stream end) parenthetical
never says whether an Err-terminated iteration counts as a finalize trigger. If the harness
loop is written while-let-Some(Ok(ev)) it breaks on the Err and never calls
accumulator.finish(), silently discarding a partially-assembled tool call; if it is
while-let-Some(res) and finalizes on all exit paths, it salvages it. D6 harness is described
only as accumulates the tool_call stream with no error-path contract.

Question for the designer: What is the accumulator defined behavior when the SSE stream
ends with an Err(LlmError) rather than a Done event -- does D4/D6 require the harness to call
finish() on the error exit path (salvaging a partial tool call to record as a tool-use
failure, consistent with D4 empty-arguments-surfaced-not-a-panic stance), or is an
error-terminated stream defined to discard accumulator state entirely?

---

Lessons consulted: 5 (3 guardrail + 2 adversary-rejection general_note)
Step 0 query strings used:
  - search_lessons "llm gateway tool-use SSE streaming" --type guardrail --limit 10 --format json
  - search_lessons "streamer.go openapi SDK" --tags adversary-rejection --limit 5 --format json
Guardrails relevant: (none directly -- the 3 guardrails returned are git-push / force-push /
  DB-migration scope rules, not SSE/contract rules; informational context only, not promoted
  to findings)
Prior REJECTED patterns: rdy-rejected-test review-design REJECTED with 2 BLOCK on contract
  holes (informs Finding 2 -- the discriminator.mapping is a hand-maintained block that an
  incomplete openapi edit can leave un-wired, a latent contract hole); amaw-task-slug-
  validation review-code REJECTED for a fix closing only one of two entry points (this
  pattern was the basis of r3 BLOCK-1, now closed in D3 -- no longer applicable). r3 BLOCK-1,
  WARN-2, WARN-3 verified resolved against adapters.go / streamer.go this round and NOT
  re-raised.
