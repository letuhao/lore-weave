# Context Budget Law — Open-Items Closeout (spec + plan)

**Date:** 2026-07-05 · **Branch:** `feat/context-budget-law` · **Size:** L (cross-service:
book-service Go + knowledge-service + chat-service + worker-ai + docs) · **Owner:** this session.

**Parent spec:** [`2026-07-03-context-budget-law.md`](2026-07-03-context-budget-law.md) (the XL track;
functionally complete — T0/T1/T2 shipped, T4/T5/T6·D13a built + eval-proven-inert → default-OFF,
Inspector GUI shipped). This doc closes the **genuinely-still-open** tail the parent left behind.

> **Framing (honest):** the blind-judge eval proved the memory/gating tiers add **zero measurable
> quality** on the books we can measure (compaction never fires), so they ship default-OFF. The
> parent's headline finding was that the **#1 lever is grounding COVERAGE, not the tiers** — which
> is exactly why the one open item that *matters* here is a coverage bug (chapter summaries never
> generate), not a tier. The rest are small enforcement/observability gaps or conscious
> won't-finish records so the defer list stops re-surfacing resolved noise.

---

## The seven open items — verified status + disposition

Each row was **re-verified against code this session** (the [[debt-batches-list-is-stale-verify-first]]
rule: debt lists overstate real debt). `file:line` evidence inline.

| # | Item | Verified root cause | Disposition |
|---|------|---------------------|-------------|
| 1 | **D-KG-SUMMARIES-TARGET-NOOP** | Legacy/undecomposed chapters (NULL `structural_path`/`part_id`) are **silently skipped** by the part-gated P3 summary pipeline | **FIX NOW** (M1) |
| 2 | **T3 `Compiler` class** | Mechanism complete (`build_system_message` + `compact_messages` + `Planner` seam, 2 consumers); only a *named* `Compiler` wrapper is absent — cosmetic | ✅ **CLEARED 2026-07-06 — FIRM WON'T-FIX.** A wrapper no caller needs is make-work; the render+compact mechanism + the `Planner` policy seam are open and consumed by chat + voice. Reopen only if a 3rd consumer needs a reusable `compile()` entrypoint. Not a debt — a closed decision. |
| 3 | **D-T1-SMALLRETURN-ENFORCE** | `@small_return:` is a self-report comment; nothing asserts the size | ✅ **CLEARED 2026-07-06 — mitigated + pinned.** The **D7 runtime cap** (default 8000, ON) now backstops the pathological case: a heavy field on any small-return tool is withheld + logged at runtime, no longer silent. Added `test_small_return_claims.py` (closed-set pin — a new `@small_return` claim turns it red, forcing review). Residual sub-cap bloat is low-risk; a bespoke byte-histogram is out of proportion. |
| 4 | **Inspector D7-trace surfacing** | D7 cap trips silently to the GUI (log-only) | ✅ **CLEARED 2026-07-06 — BUILT.** New `tool_result_content_capped_ex` returns the over-cap token count; `_stream_with_tools` gained a `trace` param and records a `T6/results/d7_overflow:<tool>` span so the Inspector shows *why* a result was withheld. |
| 5 | **D13b resume-monotonicity** | Correctness invariant, only live when the tiers are ON | ✅ **CLEARED 2026-07-06 — satisfied by construction.** With auto-detect (2026-07-06-long-work), the gate decision is computed ONCE in the main path; `resume_stream_response` reuses the frozen assembly and never re-gates. Verified, not deferred. |
| 6 | **D7 reasoning-budget half** | Budgeting the model's *reasoning* tokens; reasoning is disabled repo-wide | ✅ **CLEARED 2026-07-06 — FIRM WON'T-FIX (trigger recorded).** The single-item tool-result cap (the other half) shipped. Budgeting reasoning tokens is speculative while reasoning is OFF platform-wide + untestable against real behavior. Reopen trigger: reasoning re-enabled by default AND profiling shows reasoning bloat. A closed decision, not an open task. |
| 7 | **D-LONG-WORK-CONTEXT-MODE** | Per-session `context.mode` (off/auto/on) shipped (Chat&AI M4); "smart auto-detect" unbuilt | ~~park~~ → **UNPARKED 2026-07-06 (essential).** See [`2026-07-06-long-work-auto-detect.md`](2026-07-06-long-work-auto-detect.md). My earlier "dead code" reasoning was circular — "tiers inert" came from THIN-book evals, which is exactly the case auto-detect doesn't target; large books were never measured. Building it now (full auto-enable, user's call). |

---

## M1 — D-KG-SUMMARIES-TARGET-NOOP (the one that matters)

### Root cause (code-verified)

The chapter-summary pipeline is fully built and wired end-to-end:
- **Producer** `enqueue_chapter_and_maybe_book_summaries` — [`pass2_orchestrator.py:1188`](../../services/knowledge-service/app/extraction/pass2_orchestrator.py)
- **Enqueue gate** — [`internal_extraction.py:865`](../../services/knowledge-service/app/routers/internal_extraction.py):
  fires only when `summaries_requested AND hierarchy_paths is not None AND embedding_model_uuid is not None AND embedding_dimension is not None`.
- **Stream** `extraction.summarize` → **consumer** `SummaryConsumer` ([`worker-ai/app/summary_consumer.py`](../../services/worker-ai/app/summary_consumer.py), `summary_consumer_enabled=True` default) → **processor** `process_summarize_message`.
- `summaries` **is** in `DEFAULT_TARGETS` ([`extraction_jobs.py:159`](../../services/knowledge-service/app/db/repositories/extraction_jobs.py)) — not an opt-in gap.

**The no-op** is upstream, in the worker's request construction —
[`runner.py:2073-2077`](../../services/worker-ai/app/runner.py):

```python
if (hierarchy is not None
    and hierarchy.part is not None          # ← traps every chapter with no part
    and hierarchy.chapter_path is not None
    and job.embedding_dimension is not None):
    p3_hierarchy_paths = {...}              # else stays None → summary enqueue SKIPPED
```

`hierarchy.part` / `hierarchy.chapter_path` are **NULL for any chapter that was never run through
the structural decomposer** (imported/created without parts + `structural_path`) —
[`book-service hierarchy.go:67`](../../services/book-service/internal/api/hierarchy.go): *"Legacy
chapters (NULL part_id, NULL structural_path) get part=null + chapter.path=null — worker-ai treats
that as opt-out of P3 summary enqueue."* This is the **common case** for imported novels (incl. the
Dracula POC book), so those books get **zero** chapter/book summaries → `summary_chapters` /
`summary_books` stay 0 → "where is X at chapter N" recall punts (parent eval §6.2).

Two defects compound:
- **(functional)** undecomposed books can't produce summaries at all;
- **(observability)** the skip is **totally silent** — no log/metric even though summaries were
  requested. Classic [[silent-success-is-a-bug-not-environment]].

### Fix

**(a) Synthesize a deterministic implicit part** at the book-service hierarchy endpoint so the
existing Book→Part→Chapter→Scene pipeline runs unchanged for undecomposed chapters. When
`part == nil`: mint `part = {id: uuidv5(book_id,"part-1"), path:"book/part-1", index:1}`, inject it
into `book_parts` (so the `is_last` book-summary tail aggregates it), and synthesize
`chapter.path = "book/part-1/chapter-{sort_order}"` when `structural_path` is NULL. MERGE-on-path is
idempotent + deterministic, so a later real decomposition **reuses** the same node (no graph drift).
This keeps every downstream aggregation (part→book roll-up, D9 defensive check) byte-identical —
no part-optional surgery across three services.

**(b) De-silence the skip.** Emit a `logger.warning` + metric when an extraction requests
`summaries` but the P3 enqueue is skipped for a missing dep (no hierarchy, or
`embedding_dimension is None` — e.g. a project with no embedding model). Turns an invisible no-op
into a one-line diagnosis. Sites: worker-ai `runner.py` (hierarchy None despite `summaries` target)
+ knowledge `internal_extraction.py` (guard-false branch).

### Verification

- book-service Go: unit test the endpoint synthesizes a deterministic part + chapter_path for an
  undecomposed chapter, passes a real decomposed chapter through unchanged, and the synthetic part
  UUID is stable across calls.
- worker-ai: the relaxed path builds `p3_hierarchy_paths` (part now non-nil from book-service) +
  the de-silence warn fires when `embedding_dimension is None`.
- knowledge: guard-false branch logs; producer enqueues chapter+book for a single-part book.
- **LIVE-SMOKE — ✅ PASSED** (2026-07-05, full local stack). Confirmed against live data first:
  *every* book in the dev DB has 100% NULL `part_id`/`structural_path` (Dracula 6ch, 万古神帝 4233ch)
  and `summary_chapters` had **1 row total** platform-wide — the part-gate was starving summaries for
  every book. After rebuilding book-service + worker-ai + knowledge: the hierarchy endpoint returns
  the synthesized `part {path:"book/part-1", id:uuidv5}` + `chapter.path`; a real extraction of
  Dracula ch.1 enqueued all 3 summary levels (incl. `level=part node=db749273…`, the synthetic
  part), and `summary_chapters`/`parts`/`books` went **0→1/1/1 with real coherent text** ("Jonathan
  Harker's journey through the diverse landscapes and superstitions of the East…"). Neo4j confirms
  the synthetic `:Part`→`:Chapter` hierarchy.
- **Second bug the smoke EXPOSED (latent, now fixed) — `draft-text` `::bytea` 500.** The
  summary_processor's legacy-chapter text fallback (`_load_scene_leaf_texts` → `get_chapter_draft_text`)
  hit book-service `getInternalChapterDraftText`, which did `SELECT cd.body::text::bytea` — Postgres
  parses text→bytea as an ESCAPE literal, so **any** draft whose JSON contains a backslash escape
  (`\n`, `\"`) raised `invalid input syntax for type bytea` → 500 → the fallback returned empty → the
  chapter summary deferred in an infinite re-enqueue loop. Latent because summaries never ran before
  the part-gate fix. **Fixed** ([`scenes.go`](../../services/book-service/internal/api/scenes.go)):
  `cd.body::text` scanned into a string. DB-gated regression test
  (`scenes_draft_text_db_test.go`, seeds a backslash-bearing draft → asserts 200) passes against real
  Postgres. **This is exactly the value of the live-smoke** — the part-gate fix was necessary but not
  sufficient; only running the real pipeline surfaced the second blocker.

---

## M2 — D7 cap de-silence (SHIPPED); two enforcement remainders decomposed

**Shipped — D7 log de-silence.** `_overflow_error` in
[`tool_result_wire.py`](../../services/chat-service/app/services/tool_result_wire.py) now logs a
`WARNING` on every cap trip (tool + tokens + cap), so a withheld tool result is diagnosable in
ops/eval instead of silent — same philosophy as the M1 summary-skip de-silence. 2 tests
(warns-on-trip / silent-under-cap).

**Decomposed — the two "enforcement" halves were investigated and deferred with cause (NOT
laziness — both real fixes need infra that deserves its own plan):**

- **D-T1-SMALLRETURN-ENFORCE → defer to A5 (gate #2).** Verified: no A5 byte-histogram harness
  exists, and the `@small_return:` notes are free-text comments on ~13 tools across knowledge /
  composition / translation. The stated risk is *payload SIZE* drift ("a heavy field added to a
  small-return tool"), which only a **runtime** per-tool byte-budget assertion catches — that means
  executing each tool against a fixture + histogramming bytes (the A5 harness), an M-sized
  cross-service piece. The cheap static proxies (annotation-parity snapshot, heavy-key source scan)
  do **not** enforce size, so building one would be *theater that reads as "enforced" while the real
  gap stays open*. Trigger: the A5 byte-histogram harness.
- **Inspector D7 GUI-trace surfacing → defer (gate #2).** The `TraceAccumulator` is created deep in
  the turn-emit function ([`stream_service.py:1930`](../../services/chat-service/app/services/stream_service.py))
  and is **not** in scope at the tool-dispatch loop where D7 trips (~L1449, inside a 700+-line
  streaming function). Threading it through is real structural plumbing for **low** value — the cap
  ships default-ON but trips rarely (8000-tok ceiling), the model already gets a self-correcting
  notice, and the trip is **now logged** (above). Trigger: batch it with the next tool-loop refactor
  that already threads turn-scoped state.

---

## M3 — conscious records (so the defer list stops re-surfacing)

- **T3 `Compiler`** — WON'T-FINISH (gate #5). `sdks/python/loreweave_context` exposes the full
  mechanism (`build_system_message`, `compact_messages`/`CompactionStrategy`, `Planner`/`CompilePlan`),
  and chat-service + voice_stream_service both consume it. A separate `Compiler.compile()` class
  wrapper adds **no behavior** — the render+compact steps already run inline off the plan. The T3
  plan itself declares "T3 CORE COMPLETE." Recorded closed; reopen only if a 3rd consumer needs a
  reusable compile entrypoint.
- **D13b resume-monotonicity** — DEFER, trigger = the gated tiers (T5/T4/D13a) flip ON. It's a
  freeze-at-turn-start invariant for suspended→resumed turns that is inert while those tiers are OFF.
- **D7 reasoning-budget half** — DEFER, trigger = reasoning re-enabled repo-wide **and** profiling
  shows reasoning bloat (the single-item tool-result cap — the other half — already shipped).
- **D-LONG-WORK-CONTEXT-MODE** — PARTIAL-RESOLVED. The per-session `context.mode` off/auto/on
  plumbing shipped (Chat&AI M4); **note the honesty caveat**: `mode="auto"` currently == "follow the
  deploy env default" ([`stream_service.py:1799`](../../services/chat-service/app/services/stream_service.py) —
  `_ctx_tiers_allowed = context_mode != "off"`), i.e. no real auto-detection. Building the "smart
  auto-detect" heuristic now would be **dead code**: the tiers are eval-inert and gated behind a
  default-OFF deploy ceiling (`effective = AND(deploy_allows, user_enables)`), so auto could not
  enable anything until the ceiling opens. Park the heuristic; trigger = a large-book (>500k word)
  eval proving the tiers earn their keep when compaction actually fires.
