# Adversary Findings -- phase-0b-sse-parser -- Round 3 (final design round)

Design under review: docs/specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md (REVISED, post-r2)
Phase: review-design / Agent: adversary / Round: 3
Status: REJECTED (1 BLOCK, 2 WARN)

Round-1/2 revision check:
- r1 BLOCK-1 / r2 BLOCK-1 (empty-args first fragment + Go omitempty strips arguments_delta:""):
  D3 now specifies ArgumentsDelta string json:"arguments_delta" explicitly WITHOUT omitempty,
  and pins ToolCallEvent.arguments_delta as a required openapi field. Parse-side emit rule
  (D1) and serialize-side tag are now consistent. ADEQUATELY RESOLVED.
- r1 BLOCK-2 / r2 BLOCK-2 (tool_choice contract hole -> closed allowlist hole):
  D8 now relocates capability onto the provider.Adapter interface via SupportsTools() bool,
  co-located with each adapter so it cannot drift from ResolveAdapter. The closed-allowlist
  helper is gone. RESOLVED IN PRINCIPLE -- but see Finding 2 below: the spec own enumeration
  of adapters is now incomplete in a way that interacts with this fix.
- r2 WARN-3 (Rust index serialize asymmetry): D3 parity rule adds the is_zero helper +
  skip_serializing_if = "is_zero" so Rust omit-at-0 matches Go omitempty. ADEQUATELY RESOLVED.

The two prior BLOCKs are genuinely closed. This round raises fresh issues.

---

## Finding 1 -- BLOCK -- D3: "next to the existing tools pass-through" is factually false for ollamaAdapter.Stream and lmStudioAdapter.Stream -- they never wire tools at all; the harness (AC-5, live lmstudio) will send tool_choice but NOT tools and the forced tool call fails

D3 says: "The tool_choice pass-through goes in each openai-compat adapter Stream body
builder (openaiAdapter / lmStudioAdapter / ollamaAdapter) next to the existing tools
pass-through." That instruction assumes all three openai-compat Stream() methods already
forward input["tools"]. They do not. In adapters.go:

- openaiAdapter.Stream (lines 398-400): if v, ok := input["tools"]; ok { body["tools"] = v }
  -- the ONLY adapter that forwards tools on the streaming path.
- lmStudioAdapter.Stream (lines 858-883): body is built from model, messages,
  temperature, max_tokens ONLY. No tools read. No tool_choice.
- ollamaAdapter.Stream (lines 671-695): same -- model, messages, temperature,
  max_tokens only. No tools.

So a literal implementation of D3 "add tool_choice next to the existing tools pass-through"
has nowhere to land in two of the three adapters, because the referenced anchor line does not
exist. A careless implementer adds only tool_choice to lmStudioAdapter.Stream and the
streamed request to lmstudio carries tool_choice but still no tools array. lmstudio (or
any OpenAI-compat server) given tool_choice without tools either 400s or ignores the
forced call -- and AC-5 mandates the harness run against live lmstudio via the lm_studio
provider kind, which dispatches through exactly this lmStudioAdapter.Stream. The entire
Phase 0b empirical goal (parse a real tool call) cannot succeed: the gateway never sends the
tool definitions. streamChat builds input["tools"] from in.Tools (stream_handler.go
lines 254-256), so the data reaches the adapter input map -- it is then silently dropped by
lmStudioAdapter.Stream / ollamaAdapter.Stream because neither reads input["tools"].

This is the same partial-closure pattern the amaw-task-slug-validation review-code REJECTION
flagged (a fix that covers one entry point and leaves a sibling path broken): D3 fixes the
tool_choice story on the openaiAdapter path while the lmStudioAdapter path -- the actual
PoC target -- is left wiring neither tools nor tool_choice.

Question for the designer: Where in D3 does the design state that lmStudioAdapter.Stream
and ollamaAdapter.Stream must FIRST gain a tools pass-through (which they lack today --
only openaiAdapter.Stream has one), before a tool_choice pass-through can be added "next
to" it -- and given AC-5 runs the harness against the lm_studio adapter, how does a forced
tool call reach lmstudio when lmStudioAdapter.Stream body builder forwards neither field?

---

## Finding 2 -- WARN -- D8: SupportsTools() is enumerated for 4 named adapters, but ResolveAdapter default branch returns a 5th, unnamed openaiAdapter for ALL unknown provider kinds -- the spec never states this path tool-capability, and it is the path a custom openai-compat provider takes

D8 (revised) says openaiAdapter, lmStudioAdapter, ollamaAdapter return true and
anthropicAdapter returns false. But ResolveAdapter (adapters.go lines 887-911) has FIVE
outcomes, not four: the default: case -- hit by any provider_kind that is not one of the
four literals (azure_openai, together, groq, deepseek, a custom user-registered kind,
a typo in seed data) -- returns &openaiAdapter{...} with an empty static inventory. Because
capability now lives on the adapter type, that default openaiAdapter inherits
SupportsTools() == true. That is arguably the intended and correct behavior (the r2 fix
whole point was that a new openai-compat provider is never spuriously rejected). But D8 prose
enumerates capability against four named adapter structs and never acknowledges that
ResolveAdapter routes the open set of unknown kinds through openaiAdapter -- so a reader
verifying AC-7 ("an Anthropic model returns 400 ... openai-compat providers are unaffected")
has no spec statement covering the unknown-kind case. The behavior is right by construction;
the spec coverage of it is absent. A test author writing the AC-7 unit test has no design
line telling them to also assert that provider_kind = "some_custom_kind" is permitted.

Question for the designer: Does the design intend the ResolveAdapter default-case
openaiAdapter (the route for every provider kind outside the four literals) to report
SupportsTools() == true -- and if so, why does D8 enumerate capability only against the four
named adapters rather than stating the rule as "capability is whatever the resolved adapter
reports, and the default route resolves to openaiAdapter"? As written, the open set of
custom/unknown openai-compat kinds has correct runtime behavior but zero spec/test coverage.

---

## Finding 3 -- WARN -- D1/D4: the canonical tool_call event has no per-index terminal marker; the ToolCallAccumulator cannot know an index is complete until stream end, and AC-3 does not test interleaved out-of-order indices that OpenAI legitimately streams

D1 deliberately makes ToolCallEvent a pure delta with {event,index,id?,name?,arguments_delta}
and no "final"/"stop" flag -- the gateway stays a stateless re-framer. Reassembly is the SDK
ToolCallAccumulator job (D4, tool.rs). But there is no per-index completion signal in the
canonical stream: Anthropic emits content_block_stop per tool-use block, which the gateway
streamer (D3, "parse-side only") consumes and does NOT re-emit as any canonical event; OpenAI
emits no per-call terminator at all. So the SDK accumulator only signal that tool call index
k is fully assembled is the terminal DoneEvent (finish_reason: "tool_calls") -- meaning a
caller cannot act on a completed early tool call until the WHOLE turn ends. For the single-tool
harness (D6: "1 zone, ~3 placeholder objects", one submit_zone_classifications call) this is
benign. But D1/D4 describe the accumulator generically ("folds ToolCall deltas by index") and
AC-3 says "ToolCallAccumulator reassembles fragmented deltas" -- with no acceptance criterion
for the interleaved / out-of-order index case. OpenAI delta.tool_calls[] for a multi-call
turn can stream index 1 id/name fragment before index 0 arguments finish, and can emit
tool_calls array entries in non-monotonic order across chunks. An accumulator that assumes
index arrives monotonically (0 fully, then 1 fully) -- a natural first implementation --
silently mis-assembles. AC-3 as written ("reassembles fragmented deltas") would pass against a
single-index fixture and never exercise this.

Question for the designer: Since the canonical tool_call event carries no per-index
terminal marker and the gateway drops Anthropic content_block_stop without re-emitting it,
what is the accumulator defined contract for (a) knowing an individual index is complete
before DoneEvent, and (b) interleaved deltas where index 1 first fragment arrives before
index 0 last -- and should AC-3 add an explicit multi-tool-call, out-of-order-index fixture
rather than only "fragmented deltas" for a single call?

---

Lessons consulted: 5 (3 guardrail + 2 adversary-rejection general_note)
Step 0 query strings used:
  - search_lessons "llm gateway tool-use SSE streaming" --type guardrail --limit 10 --format json
  - search_lessons "streamer.go openapi SDK" --tags adversary-rejection --limit 5 --format json
Guardrails relevant: (none directly -- the 3 guardrails returned are git-push / force-push /
  DB-migration scope rules, not SSE/contract rules; informational context only, not promoted
  to findings)
Prior REJECTED patterns: rdy-rejected-test review-design REJECTED with 2 BLOCK on contract
  holes (informs Finding 2 -- D8 adapter-capability rule is correct by construction but the
  spec under-documents the open default-route case, a latent contract-coverage gap);
  amaw-task-slug-validation review-code REJECTED for a fix that closed only one of two entry
  points (directly informs Finding 1 -- D3 fixes the tool_choice/tools story on the
  openaiAdapter path while lmStudioAdapter.Stream / ollamaAdapter.Stream, the actual PoC
  target, wire neither field; same partial-closure pattern).
