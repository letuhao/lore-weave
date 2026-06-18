# B2 — Jobs control completeness (P3) — plan

**Batch:** B2 (DEBT-BATCHES.md) · **Size:** M · **Date:** 2026-06-17 · **Branch:** `feat/auto-draft-factory-gaps`
**Goal:** close all 3 P3 control-surface rows — **no new deferrals**.

PO checkpoint (CLARIFY): close all 3; item ③ = cheap status-only cancel (option a).

---

## M1 — `D-JOBS-P3-TRANSLATION-PAUSE` (med) — stop-dispatch pause/resume

Translation runs as a coordinator → per-chapter-unit fan-out (P5 WFQ or direct publish);
both route every chapter unit through `chapter_worker._process_chapter`'s start-of-work
status gate (the same place `cancelled` is honored today). Pause = stop NEW chapter work +
let in-flight drain; resume = re-drive the un-done chapters.

**Key realization:** the `translation_jobs` row persists every field the `translation.job`
message needs (`system_prompt`, `user_prompt_tpl`, `compact_*`, `chunk_size_tokens`,
`invoke_timeout_secs`, model, qa, verifier, …) — so resume rebuilds the job message DIRECTLY
from the row; no `eff` re-resolution / no `_resolve_and_create_job` refactor.

1. **`jobs-service/app/contract.py`** — add `"translation"` to `_MULTI_UNIT_KINDS`; update the
   comment (drop the "not yet" note). `derive_control_caps('running','translation')` then offers
   PAUSE; `paused` already yields RESUME+CANCEL.
2. **`translation-service/app/routers/jobs.py`** — two new cores beside `_cancel_job_core`:
   - `_pause_job_core(db, job_id, owner)`: tx — `UPDATE … SET status='paused' WHERE job_id AND
     owner_user_id AND status='running' RETURNING owner_user_id`; emit `paused` on the same conn
     (H1). No row → owner-scoped presence check → 404 (not owned/found) vs 409 (not running).
   - `_resume_job_core(db, job_id, owner)`: tx — `UPDATE … SET status='running' WHERE … AND
     status='paused' RETURNING *`; emit `running`. Then compute the un-done set = this job's
     `chapter_translations` rows in `('pending','failed')` (a `running` row is in-flight or
     crash-swept — excluded, so resume never races a live chapter). Re-publish `translation.job`
     for the EXISTING job_id with `chapter_ids = un-done`, built from the row columns. None → 404/409.
3. **`translation-service/app/routers/internal_dispatch.py` `control_job`** — route `pause`/`resume`
   to the new cores (keep `cancel`/`retry`); drop the "cancel-only" 400 for these two. Update docstring.
4. **`translation-service/app/workers/chapter_worker.py` `_process_chapter`** — at the existing status
   gate: add a `paused` branch → release the P5 lease (`fair_sched.release_chapter_lease(msg)`) and
   return WITHOUT failing the chapter, WITHOUT `_check_job_completion` (job not terminal); the ct row
   stays `pending` for resume. Message is ACKed (no requeue loop).
5. **Guarded claim (dup-safety)** — change the worker's "mark chapter running" UPDATE to a stale-aware
   claim mirroring compose-task `_claim_for_run`: `… WHERE job_id AND chapter_id AND status <>
   'completed' AND (status <> 'running' OR started_at < now() - <window>) RETURNING id`. No row →
   a fresh-running dup (a parked-unit/redrive overlap) → release lease + return. Preserves
   crash-recovery (stale-running re-claims) + transient retry (failed re-claims).

**Tests:** contract caps (`test_control_caps.py`) — running translation offers pause; paused offers
resume+cancel. Pause/resume cores (`test_internal_dispatch.py`) — 409 from non-running/non-paused,
404 not-owned, emit on transition, resume re-publishes only un-done. Worker paused-drop + guarded
claim (`test_chapter_worker*` / a focused unit). FE: `_MULTI_UNIT_KINDS` already drives the button.

## M2 — `D-JOBS-P3-VIDEOGEN-PROVIDER-ABORT` (med) — clean wiring

`provider-registry` already exposes `DELETE /internal/llm/jobs/{id}?user_id=` (aborts the in-flight
goroutine + releases the spend reservation); the SDK `loreweave_llm.Client.cancel_job()` calls it
(idempotent: 204/409 → None, 404 → `LLMJobNotFound`). video-gen stores `provider_job_id` and already
builds an internal-auth `Client`.

- **`video-gen-service/app/routers/internal_job_control.py`** — after the local CAS cancel wins and
  `job.provider_job_id` is set, best-effort `Client(...internal...).cancel_job(provider_job_id,
  user_id=owner)`; wrap in try/except (log, swallow — the local row is canonical; abort is slot/cost
  reclaim, not correctness). Reuse `provider_registry_internal_url` + `internal_service_token`.
- **Tests** (`test_internal_job_control*`) — cancel calls provider abort with the stored
  provider_job_id; a provider-abort failure still returns 200 cancelled (best-effort); no
  provider_job_id → no call.

## M3 — `D-JOBS-P3-LORE-COMPOSE-TASK-CONTROL` (low) — cheap status-only cancel (option a)

`enrichment_compose_task` is a one-shot single-LLM-call task (profile_suggest / intent_resolve).
Cancel = stop a still-QUEUED task from running + don't persist a mid-flight result.

- **`lore-enrichment-service/app/api/internal_job_control.py`** — when the job_id isn't an
  `enrichment_job` (existing 404 path), look it up in `enrichment_compose_task` (owner-scoped);
  if found + action `cancel`: `UPDATE … SET status='cancelled' WHERE task_id AND user_id AND
  status IN ('pending','running')` + emit `cancelled` (H1); 409 if already terminal; pause/resume → 400.
- **`lore-enrichment-service/app/compose/compose_task.py`** — `_claim_for_run` WHERE: add
  `AND status <> 'cancelled'` (a cancelled task is never claimed/run) + disambiguation read returns a
  `cancelled` verdict; guard `_mark` final write so a mid-flight terminal can't clobber a `cancelled`
  row (`… WHERE task_id AND status <> 'cancelled'`).
- jobs-service contract: NO change — a non-multi-unit running/pending job already derives `[CANCEL]`.
- **Tests** — endpoint cancels a pending compose task (emit cancelled); claim skips a cancelled task;
  `_mark` won't overwrite cancelled; 409 on already-completed.

## Cross-cutting
- Live-smoke: the 3 cancel/pause paths land in **B3** (`D-JOBS-P3-KNOWLEDGE-CANCEL-SUCCESS-LIVE-SMOKE`
  cluster + the P5 sweep) — unit + real-PG proven here; cross-service stack-up deferred to B3 per the batch plan.
- DEBT-BATCHES.md: tick B2 ✅, all 3 rows resolved, no new deferrals.
