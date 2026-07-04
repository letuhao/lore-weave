# BUG — extraction pipeline: silent no-op (observability + data-validation gap)

**Found:** 2026-07-04, during the T5 audit's KG-seeding (user-identified: "no LLM call
means extraction won't work — this should be an observability and data-validation bug").
**Severity:** MED (no data corruption; but extraction can silently do nothing while
reporting success, so a user/agent trusts a graph that was never built).
**Gate:** #2 (large/structural — the finalization is distributed across worker + saga +
event pipeline; a correct fix needs that flow understood, not a quick edit).

## The bug

An extraction job can reach `status = complete` (success) having done **no real work**,
with nothing surfacing the anomaly. Evidence from project `019f2be0` (Dracula, T5 audit):

| job | scope | items_processed | items_skipped | **llm_calls_made** | reported status |
|---|---|---:|---:|---:|---|
| 019f2bed | chapters 0-2 | 2 | 0 | 8 | complete — but persisted **entities=0** every source |
| 019f2bef | chat | 12 | 0 | **0** | complete |
| 019f2bf4/5/b/c/d | chat | 1-2 | 0 | **0** | complete |
| 019f2bfe | chapters 2-7 | 0 | 0 | 1 | stuck in `pipeline_stage=entity`, no stall signal (had to cancel by hand) |

**Three distinct gaps:**

1. **No OUTPUT validation.** A job that completes with `llm_calls_made = 0` (over
   non-skipped items) did no extraction — extraction REQUIRES the LLM. Yet it is
   `complete`, byte-identical to a real run. Likewise a chapters job that makes 8 LLM
   calls but persists `entities=0 relations=0 facts=0` for every source is reported as a
   clean success — the caller cannot tell "nothing to extract" from "extraction failed".

2. **No INPUT validation.** Dispatch validates `embedding_model` + `model_ref` (429
   benchmark gate, 422 no-model) but NOT that the project has an effective graph schema
   with entity kinds. A project created without a schema resolves a *system default* and
   proceeds; if that default's kinds don't fit the book, extraction yields 0 with no
   warning. (The T5 seed hit exactly this — SQL-created project, no project schema.)

3. **No STALL detection.** A `running` job stuck in a stage (`entity`, 1 LLM call, 0
   progress) stays "running" indefinitely and looks healthy; only a human reading the row
   notices. No heartbeat / progress-timeout watchdog.

## Why it matters
The whole point of extraction is to build a graph the agent then grounds on. A silent
no-op means the agent later grounds on an **empty graph while the UI/job says "done"** —
the failure surfaces far downstream (thin grounding, wrong answers), exactly the class the
T5 audit itself tripped over.

## STATUS (2026-07-04)

- ✅ **Gap #1 (output validation) — FIXED.** The finalizer is `worker-ai/app/runner.py::_complete_job`
  (it already flagged the all-skipped case; I extended the SAME honesty CASE): a job that
  PROCESSED items but made **0 LLM calls** now completes with
  `error_message = 'completed but made 0 LLM calls over N processed item(s) — no extraction
  performed (no usable graph schema kinds, or the extraction provider was unreachable)'` +
  a loud `logger.warning`, instead of a bare silent `complete`. Status stays `complete`
  (skips/no-ops are terminal by design; `failed` would trip campaign breakers) but the row
  says so out loud. Test: `test_complete_job_flags_zero_llm_call_noop`.
- ⚪ **Gap #2 (input validation) — MOOT as framed.** `GraphSchemaRepo.resolve_for_project`
  ALWAYS resolves (fallback_code="general"), so "no schema" can't be rejected at dispatch.
  The real issue (the general schema's kinds don't fit the book) now surfaces DOWNSTREAM via
  gap #1's completion flag. A dispatch-time "do the resolved kinds fit this book" heuristic is
  a deeper, lower-priority nicety.
- ⏳ **Gap #1b (advisory) — 0 GRAPH WRITES despite LLM calls** (job 019f2bed: 8 calls,
  entities=0). Deliberately NOT flagged: a front-matter chapter legitimately yields 0, so a
  0-entities flag would false-positive. Catching a WHOLE-scope 0-write extraction as advisory
  needs a cumulative entity-write counter on the job (thread the persist-pass2 counts through)
  — a follow-up.
- ⏳ **Gap #3 (stall detection) — still open.** A `running` job stuck in a stage with no
  progress needs a `last_progress_at` + a sweeper flip to `stalled`. Separate change.

## Proposed fix (original — for the remaining gaps)
- **Output signal at finalization:** compute `entities_written + relations + facts` and
  `llm_calls_made`; if a non-skipped, entity-producing scope finalizes with **0 LLM calls
  OR 0 graph writes**, set a distinct terminal signal — a `completed_empty` status, or a
  `warning`/`no_output` field on the job + a loud log + a metric counter. NEVER let it be
  indistinguishable from a productive run.
- **Input pre-flight at dispatch:** resolve the effective schema; if it has no entity
  kinds (or none applicable), 422 with a clear message ("no graph schema — author one
  first") — the same UX the `benchmark_missing` gate already models.
- **Stall watchdog:** a per-job `last_progress_at`; a sweeper flips a job with no progress
  for N minutes to `stalled` (recoverable/resumable), not silent-`running`.

## Chokepoint notes (partial — for the fix effort)
- `extraction_jobs.complete()` (repo) is a wrapper on `update_status(..,"complete")` but
  is NOT the extraction finalizer (only wiki uses its analog). The real transition to
  `complete` is in the worker/saga/event pipeline — NOT located this session; find it
  before editing.
- Dispatch route + existing pre-flight: `internal_dispatch.py:83-124` (add the schema
  check alongside the embedding/model checks).
- `resolve-schema` succeeds with a system default (log: "resolve-schema 200"), so the
  input check must assert *entity kinds exist*, not merely *a schema resolved*.
