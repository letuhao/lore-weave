# Composition retry — design (D-JOBS-P4-RETRY-COMPOSITION)

**Date:** 2026-06-17 · **Branch:** feat/auto-draft-factory-gaps · **Status:** DESIGN (awaiting PO sign-off before BUILD)
**Epic:** Unified Job Control Plane → P4 retry extension (last cleanly-reconstructible kind after translation/extraction/video_gen)

## 1. Problem

The unified Jobs GUI offers a **Retry** button for failed jobs of kinds the owning service can
re-submit (`_RETRYABLE_KINDS = {translation, extraction, video_gen}` in
`jobs-service/app/contract.py`). The retry routes `POST /v1/jobs/{service}/{job_id}/retry` →
`forward_control` → the owning service's `/internal/{service}/jobs/{job_id}/retry`, which
reconstructs a create-request from the failed row and re-runs it as a **new** job (the failed row
stays as history).

Composition was deferred (`D-JOBS-P4-RETRY-COMPOSITION`) because its params live in an opaque
`generation_job.input` JSONB. The earlier triage concluded "not reconstructable (bifurcated)". That
is **half right** — the precise boundary is below.

## 2. The bifurcation (precise)

`composition/app/routers/engine.py` — `generate`, `selection_edit`, `generate_chapter` each branch
on `settings.composition_worker_enabled`:

- **Worker path** (`worker_auto` for generate; `composition_worker_enabled` for the others):
  the endpoint resolves ALL bearer-only context (`pack()` output, message list, scene signals,
  critic refs, `max_out`) INTO `job.input`, creates the job `pending`, and enqueues it on the
  `composition_jobs` Redis stream. `worker/job_consumer.py::run_job` → `_run_operation` reconstructs
  everything from `job.input`. These jobs carry `input.worker_op ∈ SUPPORTED_OPERATIONS`
  (`generate` / `chapter_generate` / `selection_edit`), or `operation ∈ {decompose_preview,
  stitch_chapter}` (those store the op directly in the `operation` column).
- **Inline/streamed path** (worker off, or cowrite mode for generate): the LLM call runs inline in
  the request handler — cowrite/selection-edit **stream** the result via SSE. `job.input` stores
  ONLY metadata, NOT the packed prompt. **Cannot** be reconstructed server-side.

**Reconstructable ⟺ worker-drivable ⟺ `_worker_op(job) ∈ SUPPORTED_OPERATIONS`.** This is a
**per-job** property. The projection's `kind` (= the free-form `operation`, e.g. `"draft_scene"`)
is IDENTICAL for the worker and inline paths, so a kind-based allowlist cannot express it.

The inline-streamed jobs are intentionally NOT retried server-side: the author is live in the
editor and the FE's own re-generate is the right surface (no persisted prompt to replay).

## 3. Design

### 3.1 jobs-service — per-job retryable signal (NO migration)

`job_projection.params` (JSONB, COALESCE-merged) already exists and is exposed on the job dict as
`job["params"]`. Composition's emit will stamp `params.retryable: true` on worker-drivable jobs.

- **`contract.py::derive_control_caps(status, kind, *, retryable: bool | None = None)`** — on
  `FAILED`, offer `RETRY` iff `kind in _RETRYABLE_KINDS OR retryable is True`. The existing three
  kinds keep their kind-based behavior (callers pass `retryable=None`); composition is gated purely
  on the per-job flag (it is NOT added to `_RETRYABLE_KINDS`).
- **`routers/jobs.py`** — both call sites (`_with_caps` and the `control_job` gate at L182) read
  the flag off the job dict: `retryable = (job.get("params") or {}).get("retryable")` and pass it
  through. `control_job` already has the full `job` from `store.get_job`.
- Old failed composition jobs (pre-change, no `params.retryable`) → `None` → no retry offered.
  Conservative + correct (they're history).

### 3.2 composition-service — emit the flag

`db/repositories/generation_jobs.py::create` already builds `_job_params` and emits it on every new
job. Add:

```python
_worker_drivable = (_in.get("worker_op") or operation) in _SUPPORTED_OPS
_job_params["retryable"] = _worker_drivable
```

`_SUPPORTED_OPS` = the `worker.operations.SUPPORTED_OPERATIONS` tuple. To avoid a router→worker
import cycle, define the frozenset in a leaf module (e.g. `worker/events.py` or a small constants
module) and import it from both `operations.py` and the repo. (DESIGN open item O1.)

### 3.3 composition-service — the retry core

`routers/internal_job_control.py::control_generation_job` currently 400s any action ≠ `cancel`.
Add a `retry` branch → `_retry_generation_job_core`:

1. `job = await jobs.get(owner_user_id, job_id)` → 404 if None (owner-scoped, M4).
2. 409 unless `job.status == "failed"`.
3. **Reconstructability re-check on the real row** (don't trust the projection flag):
   `_worker_op(job) not in SUPPORTED_OPERATIONS` → 409
   `{code: "JOBS_NOT_RETRYABLE", message: "inline/streamed job has no persisted prompt"}`.
4. 409 if `not settings.composition_worker_enabled` (`{code: "JOBS_WORKER_DISABLED"}`) — a
   re-submitted worker job would sit `pending` with no consumer (honest: don't offer what can't be
   honored right now). (DESIGN open item O2 — alternative: create-pending and let the sweeper drive
   it when the worker returns.)
5. **Re-submit as a NEW job** (mirrors extraction/video_gen — failed row stays as history):
   - copy `operation`, `mode`, `outline_node_id`, `project_id`, and **`input` verbatim** (worker-op
     input is self-contained);
   - `idempotency_key=None` — MUST NOT copy the failed job's key (ON CONFLICT would replay→return
     the SAME failed row, defeating retry);
   - `chapter_generate` (worker_op): use `create_chapter_job_guarded(... chapter_id=input["chapter_id"])`
     so the chapter in-flight guard is honored; all other ops use plain `create`.
   - status `pending`; then `enqueue_job(settings.redis_url, job_id=new.id, user_id, project_id)`.
6. Return `JobControlResponse(job_id=new.id, status=new.status)`.

`_retry_generation_job_core` needs new deps the cancel path doesn't: `settings.redis_url` +
`enqueue_job` (lazy import to keep the cancel path's import surface unchanged).

### 3.4 SDK / FE

ZERO change. The FE Retry button is data-driven off `control_caps`; a new retryable job surfaces it
automatically. The SDK contract is unchanged (retry returns `{job_id, status}` like the others).

## 4. Scope

**IN:** retry for all worker-drivable composition jobs — `generate`(auto), `chapter_generate`,
`selection_edit`(worker), `decompose_preview`, `stitch_chapter`.
**OUT (correctly):** inline-streamed cowrite/selection-edit jobs (no persisted prompt → FE
re-generate is the surface); the inline-auto fallback when the worker is off (same — packed prompt
not persisted on that path).

## 5. Open items — RESOLVED at PO sign-off (2026-06-17)

- **O1 [RESOLVED]** — host the shared `SUPPORTED_OPERATIONS` frozenset in a leaf constants module
  (`app/worker/constants.py`); `worker/operations.py` and the repo both import it. No import cycle.
- **O2 [RESOLVED → 409 honest]** — retry when worker disabled returns 409 `JOBS_WORKER_DISABLED`
  (don't offer a control the owner can't honor right now).
- **O3 [RESOLVED → honor the guard]** — `chapter_generate` retry uses `create_chapter_job_guarded`;
  a concurrent in-flight chapter job → 409 `CHAPTER_JOB_IN_FLIGHT`, consistent with the create path.

## 6. Test plan (BUILD)

- jobs-service `test_control_caps.py`: failed composition job with `params.retryable=true` →
  `[RETRY]`; with `retryable=false`/absent → `[]`; non-failed → unaffected. `control_job` gate
  honors the flag (409 when absent).
- composition `test_internal_job_control.py`: retry happy (worker-op failed → new pending job +
  enqueue called); 404 (not owned); 409 (not failed); 409 (inline job — `_worker_op ∉ SUPPORTED`);
  409 (worker disabled); chapter_generate retry uses the guarded create; idempotency_key NOT copied.
- Live-smoke (≥2 services — jobs + composition): fail a worker `generate` job, hit retry through the
  jobs-service route, confirm a new `generation_job` row runs to `completed`. (Or
  `LIVE-SMOKE deferred` if the full worker stack isn't bootable at dev time.)

## 7. Size

L (control-plane contract change + 2 services + new internal action), load-bearing (job control
plane). `derive_control_caps` signature change is the one shared-surface touch — additive
(keyword-only param, default preserves all existing callers).
