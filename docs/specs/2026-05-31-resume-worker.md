# Spec — Wired Job Resume via Background Worker (F-C14-1 / DEFERRED-051)

> Created 2026-05-31 · Track lore-enrichment (Cluster 2) · Branch `lore-enrichment/foundation`
> Origin: QC F-C14-1 (MED, "built-but-not-wired"). A cost-cap-PAUSED job cannot be completed:
> `/{job_id}/resume` only flips status paused→running (jobs.py:317-326), `load_spent_so_far` has
> zero callers, the request (targets+model_refs) isn't persisted, and the pipeline runs only inside
> the synchronous create POST. So a paused job is stuck.
> Status: **BUILT + LIVE-VERIFIED 2026-05-31.** PO approved: separate table · new lore-enrichment-worker · existing cap · full live verify. Live proof: resume API 202 → worker `resume … → completed (skipped_done=1, new_proposals=0, spent=1.5)` → job completed (no LLM call on the done gap, prior spend seeded). 465 unit tests pass incl. runner skip-done.
> Size: **XL** (new execution architecture). PO CLARIFY (2026-05-31): persist = **separate
> `job_request` table**; execution = **background worker**; skip = **skip-before-run_gap (token-safe)**.

## 1. Problem
A cost-cap pause is the autonomous "stop before overspending" path, but recovery is unwired:
- the request (gaps/targets + model_refs + technique + params) is not persisted → the runner can't be rebuilt at resume;
- resume flips status only — it does not re-drive the pipeline;
- a naive re-drive re-spends LLM tokens: `run_gap` (the LLM call, runner.py:206) runs BEFORE the idempotent persist-dedupe (246), so re-processing from gap 0 re-charges + re-calls the model on already-done gaps → non-converging (a job paused near its cap re-pauses with no progress).

## 2. Goal
A PAUSED job can be RESUMED to completion: re-drive ONLY the not-yet-persisted gaps, seeded with the prior spend, without re-spending tokens on done gaps — via a background worker (non-blocking resume), reusing the existing JobRunner/build_live_runner.

## 3. Design

### 3a. Persist the request — `enrichment_job_request` table (PO: separate table)
```sql
CREATE TABLE IF NOT EXISTS enrichment_job_request (
  job_id        UUID PRIMARY KEY REFERENCES enrichment_job(job_id) ON DELETE CASCADE,
  request_json  JSONB NOT NULL,   -- {targets:[...], embedding_model_ref, generation_model_ref,
                                  --  technique, top_k, eval_reserve_fraction, max_spend_usd}
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
Written at create_job (one row per job). Model_refs are provider-registry user_model UUIDs (not secrets). Read by the worker to rebuild the runner. No enriched content stored — only the request shape.

### 3b. Skip-done in the runner (token-safe, the core fix)
- `ProposalStore.existing_gap_refs(job_id) -> set[str]` (SELECT gap_ref FROM enrichment_proposal WHERE job_id=…).
- `run_job(..., skip_gap_refs: set[str] = frozenset())`: at the top of the per-gap loop, if `gap_ref in skip_gap_refs`, record it (outcome.deduped_gaps / a new `resumed_skipped`) and `continue` BEFORE `charge_or_pause` + `run_gap` — so a done gap costs neither budget nor an LLM call. Convergence: each resume processes strictly fewer gaps.
- create_job passes an empty set (unchanged behavior); the worker passes `existing_gap_refs(job_id)`.

### 3c. Background worker — `lore-enrichment-worker` (PO: background worker)
- **Where:** a NEW compose service built from the SAME `services/lore-enrichment-service/Dockerfile` with a different CMD (`python -m app.worker`), mirroring the `translation-worker` precedent (shares the app code: runner, store, build_live_runner). Reuses worker-ai's consumer shape (XREADGROUP + consumer group + BLOCK timeout + XACK on success / NACK-by-not-acking on retryable error).
- **Trigger stream:** the resume endpoint `XADD loreweave:events:lore-enrichment-resume {job_id, user_id, project_id}` then flips status paused→running (the C8 transition it already does) and returns 202 (non-blocking).
- **Worker loop (`app/worker/resume_consumer.py`):** XREADGROUP the resume stream → for each msg: load the job_request + `existing_gap_refs` → rebuild via `build_live_runner(spent_so_far=load_spent_so_far(...))` → reconstruct gaps + StrategyContext from request_json → `run_job(..., skip_gap_refs=done)` → XACK on a clean terminal outcome (completed/paused/failed); leave un-acked on a transient infra error so it redelivers. Idempotent end-to-end (UNIQUE(job_id,gap_ref) + skip-done + seeded spend), so at-least-once redelivery is safe.
- **Flag-gated** (`RESUME_CONSUMER_ENABLED`, default true) like worker-ai's `summary_consumer_enabled`, so it can be disabled in envs that don't want it.

### 3d. Resume endpoint rewire
`POST /v1/lore-enrichment/jobs/{job_id}/resume`: keep the C8 paused→running transition, ADD the XADD enqueue, return `202 {status:"running", resume:"enqueued"}`. (Still no in-request pipeline drive — the worker does it.)

## 4. Acceptance
- A job paused mid-run (cost cap) → POST resume → worker re-drives ONLY the remaining gaps (done gaps skipped before run_gap: 0 extra LLM spend on them), seeded with prior spend, to `completed` (or re-`paused` if still over cap, but with FORWARD progress). Live-proven with a low cap that forces a pause then a raised cap on resume.
- No duplicate proposals (UNIQUE persist) and no double-charge (seeded budget) — re-asserted.
- create_job behavior unchanged (empty skip set, no worker dependency for the happy path).
- Worker is flag-gated + idempotent under at-least-once redelivery.

## 5. Out of scope / deferred
- Making create_job itself async via the worker (this task only moves RESUME off the request thread; create stays synchronous as today).
- A general job-queue / priority / retry-backoff framework (single resume stream, consumer-group redelivery is enough).
- Auto-raising the cost cap on resume (resume re-drives within the EXISTING cap unless the author raised max_spend — cap policy unchanged).

## 6. Open confirmations for PO (before BUILD)
1. **Worker placement:** a NEW `lore-enrichment-worker` compose service (same Dockerfile, CMD `python -m app.worker`) — recommended — vs folding the consumer into the existing `worker-ai` (couples lore-enrichment app code into worker-ai)?
2. **Resume cap semantics:** resume re-drives within the existing `max_spend_usd` (a still-capped job re-pauses with forward progress); the author raises the cap by… (a) re-creating with a higher cap, or (b) a `max_spend_usd` override on the resume call? Recommend (b)-later; v1 = existing cap.
3. **Live-verify feasibility:** the live proof needs the worker container up + a forced cost-cap pause (tiny max_spend) then resume. Confirm we run the full live verify now, or unit/integration-prove + defer the live worker run if the stack can't host the new container at dev time.
