# Phase 0b — Human-in-loop QA review findings

> **Reviewed:** commit `0e2732ac` — tilemap Phase 0b gateway tool-use contract + SSE
> parser + L3 harness (43 files, produced by an XL `/amaw` batch).
> **Task:** default v2.2 human-in-loop review, size M. **2026-05-15.**
> **Mandate:** assess AMAW output quality + audit the AMAW process; produce a tracked
> bug list. **No code fixes in this task** — actionable items → `DEFERRED.md`.
> **Plan:** [docs/plans/2026-05-15-phase-0b-human-review.md](../plans/2026-05-15-phase-0b-human-review.md).

## Verdict

**AMAW Phase 0b output is sound.** An independent pass over all code/contract/test
files plus full live re-verification found **no HIGH, no MED** — only 2 LOW + 1
COSMETIC (Layer A). The multi-layer AMAW review chain (4 design Adversary rounds + 1
code Adversary + Scope Guard + the human-invoked `/review-impl`) caught every real
correctness bug before commit. Layer B records 3 process observations — one of which
(B-1) is load-bearing for how AMAW is used going forward.

## Layer A — code correctness & quality

### Live re-verification (all 4 checks executed)

| Check | Result |
|---|---|
| Harness re-run (`tilemap-service classify`, live lmstudio) | ✅ `tool_use_success: YES`, 3/3 classified, R1-R5 clean, 890/215 tokens |
| Raw `tool_call` SSE frames from the gateway | ✅ 7 `tool_call` + `usage` + `done`; first frame carries `id`+`name`, omits `index`+`arguments_delta` (omitempty) exactly as designed |
| **D8 reject — live** (`tools` → an Anthropic model) | ✅ `HTTP 400 LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER` — the full handler reject path works end-to-end (empirically closes the AC-7 PARTIAL risk; see L-A finding on #009) |
| Anthropic `tool_use` parse-side | ⚠ not live-testable — `anthropicAdapter.Stream` sends no `tools` by design (deferred #010), so Anthropic never emits `tool_use` through this stack. Covered by the fixture test `TestStreamAnthropicSSE_ToolUseBlock` + code read — both pass. |

### Findings

**LOW-A1 — openapi `tool_choice` uses `nullable: true` alongside `oneOf`.**
`contracts/api/llm-gateway/v1/openapi.yaml` ChatStreamRequest.tool_choice. OpenAPI 3.0
permits `nullable` + `oneOf` but it is unidiomatic and stricter linters flag it; the
field is already optional (not in `required`, SDKs use skip-when-none), so `nullable`
is effectively redundant. *Fix or accept:* drop `nullable`, or express null as a
`oneOf` member. Cosmetic-spec hygiene; no runtime impact.

**LOW-A2 — Go-side coverage gap: no multi-tool-call streamer test.**
`streamer.go` `streamOpenAICompat` emits `tool_call` per `tool_calls[]` entry with
`Index` verbatim, but `tool_call_streamer_test.go` only exercises a single call (one
test uses index 2, still one call). The Rust `ToolCallAccumulator` HAS interleaved /
out-of-order index coverage; the Go streamer does not. Low risk (the streamer emits
per-entry verbatim with no shared state), but a 2-call test would lock it. *Fix:* add
a `streamOpenAICompat` test with two `tool_calls` of distinct index in one stream.

**COSMETIC-A3 — `streamAnthropicSSE` `input_json_delta` has no empty-fragment skip.**
`anthropic_streamer.go` emits a `tool_call` event for every `input_json_delta` even if
`partial_json == ""`, while the OpenAI path skips a fully-empty fragment. Anthropic
does not send empty `input_json_delta` in practice and an empty `arguments_delta`
appended by the accumulator is a no-op — purely a cross-streamer asymmetry. *Accept.*

### Verified clean (specific checks made)

- **SSE parser** (`sse.rs`): chunk-boundary buffering, CRLF, keep-alive comments,
  `[DONE]` skip, error/parse-fail termination, the post-error-leak fix, the 16 MiB
  cap — all have tests; re-read confirms the `feed()` terminate-and-clear path.
- **`ToolCallAccumulator`**: index-keyed `BTreeMap`, first-non-None-write-wins id/name,
  empty-args salvage, finish-on-error — tested.
- **Go gateway**: `streamOpenAICompat` / `streamAnthropicSSE` tool-call parse re-read
  against the live raw SSE — wire shape matches; `Index` set verbatim (no counter
  bleed); `stream_options.include_usage` present; usage-only trailing chunk handled.
- **D8 guard**: `hasToolDefinitions` covers nil / empty `[]` / populated / non-array;
  guard runs after `ResolveAdapter`, before the SSE prelude — live-confirmed 400.
- **harness**: R1-R5 validators correct; L3 prompt/tool schema faithful to TMP_008b
  §3/§9; `tool_choice:"required"` (the lmstudio-correct form); env handling fail-fast.
- **commit hygiene**: 43 files all task-related; `.local/phase0b.env` correctly
  gitignored (not staged).

## Layer B — AMAW process audit

**B-1 — AMAW's own review chain did NOT surface the post-error SSE event leak; only
the human-invoked `/review-impl` did.** The code-review Adversary (1 round) reported 3
real WARNs and stopped at APPROVED_WITH_WARNINGS. The post-error event leak (a 4th,
MED-severity issue) was not among its 3 and was never surfaced by AMAW — `/review-impl`
caught it. The Adversary's "find EXACTLY 3" rule + "stop at APPROVED_WITH_WARNINGS"
structurally caps a single code-review round at 3 issues; a 4th real issue is lost
unless another round is forced. **Implication:** for correctness-critical code, an
independent pass after AMAW (`/review-impl` or a human review like this one) is
**load-bearing, not optional** — AMAW's Adversary + Scope Guard alone would have
shipped the MED leak. This restates and confirms the prior-batch AMAW-trust verdict.

**B-2 — the 4-round design loop converged (no thrash) but rounds 2-3 each caught that
the *previous round's fix* was flawed.** r2's BLOCK was r1's BLOCK-1 reappearing at the
wire-serialize layer (an incomplete r1 fix); r3's BLOCK was a factual error about the
codebase introduced while addressing r1/r2. The Adversary worked correctly each time;
the weak link was the main-session fix quality *between* rounds. 4 rounds were genuinely
needed — but partly inflated by mediocre inter-round fixes. *Lesson:* between Adversary
rounds, re-verify the fix against the actual code, not just the finding text.

**B-3 — finding precision was high: ~0 false positives across 15 AMAW findings**
(r1-r4 design + code-r1), vs the prior batch's 1-in-12. Every design BLOCK (r1-r3) was
real and substantive. The 4-round design loop earned its token cost (~650 K sub-agent
tokens for an XL task) — it caught 4 real BLOCKs that a single pass would very likely
have missed (especially the r1→r2 incomplete-fix chain).

## Bug list → DEFERRED

Actionable items filed for the follow-up fix task: **#011** (LOW-A1 openapi hygiene),
**#012** (LOW-A2 Go multi-tool-call test). COSMETIC-A3 accepted, not filed. Layer B
items are process lessons (RETRO), not code bugs.

## Coverage

All 43 commit files reviewed (code/contract/test under Layer A; the 8 audit artifacts
under Layer B). 4/4 live checks executed. No file skipped.
