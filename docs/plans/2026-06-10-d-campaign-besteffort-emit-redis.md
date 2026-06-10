# Plan — D-CAMPAIGN-BESTEFFORT-EMIT-REDIS (stuck-`dispatched` self-heal)

**Date:** 2026-06-10 · **Size:** XL (3 services, ~11 files) · **Mode:** /loom v2.2 + /review-impl
**Branch:** feat/advanced-translation-pipeline

## Problem (investigated, not assumed)

The Auto-Draft Factory live-smoke (2026-06-10) saw campaigns stall at
`knowledge=dispatched` and **never recover** (>10 min). The deferred row blamed
"redis times out, dropping the best-effort emit". Investigation corrected this:

1. **The emit is already durable.** worker-ai does NOT XADD redis directly — it
   `INSERT`s into `outbox_events` (Postgres) ([outbox_emit.py:80](../../services/worker-ai/app/outbox_emit.py#L80)).
   The Go relay ([outbox_relay.go](../../services/worker-infra/internal/tasks/outbox_relay.go))
   is durable: it only `SET published_at` on XADD success; a redis error bumps
   `retry_count` and retries the next 30s tick. A relay redis-timeout **self-heals
   in ≤30s** — it cannot cause a 10-min stall.

2. **The REAL gap: the "S3 stuck-`dispatched` timeout reconcile" was never
   implemented.** Four comments promise it
   ([driver.py:19](../../services/campaign-service/app/saga/driver.py#L19),
   [driver.py:119](../../services/campaign-service/app/saga/driver.py#L119),
   [consumer.py:21](../../services/campaign-service/app/events/consumer.py#L21),
   [consumer.py:258](../../services/campaign-service/app/events/consumer.py#L258)),
   but `gating` never re-dispatches `dispatched` ([gating.py:28](../../services/campaign-service/app/saga/gating.py#L28))
   and `repositories.py` has **no reset function**. Any lost/never-emitted
   completion leaves the row `dispatched` **forever**. That is the ∞ stall.

3. **Secondary narrow gap:** worker-ai's `emit_chapter_extracted_best_effort`
   runs as a separate best-effort insert AFTER the cursor-advance transaction
   ([runner.py:1551](../../services/worker-ai/app/runner.py#L1551)) — unlike the
   run-telemetry emit right beside it, which is atomic ([runner.py:407](../../services/worker-ai/app/runner.py#L407)).
   If that insert fails (PG blip under load) the cursor still advances → the
   event is never created → permanent loss.

## Decisions (PO-locked at CLARIFY)

- **Scope = both** (defense-in-depth): (A) implement the missing reconcile;
  (B) make the worker-ai emit transactional.
- **Reconcile strategy = reconcile-by-truth** (ask downstream whether the work
  actually completed; mark `done` if so, else reset to `failed` for re-dispatch).
  - Knowledge re-dispatch is **NOT spend-safe** (a fresh extraction job starts a
    new cursor → re-extracts the scope = re-spend), so by-truth is essential here.
  - Translation re-dispatch IS spend-safe (skip-gate skips fresh-completed
    versions), but a row genuinely in-flight must NOT be double-dispatched →
    by-truth (job status) still distinguishes "slow" from "done, event lost".

## Why `updated_at` is a sound stuck-timer (no new column)

Translation for a chapter only dispatches AFTER that chapter's knowledge is
terminal-success ([gating.py:131](../../services/campaign-service/app/saga/gating.py#L131)).
So the two stages never sit in `dispatched` on the same row simultaneously, and
nothing bumps a row's `updated_at` while its single in-flight stage waits.
`updated_at` therefore reliably marks when the stage entered `dispatched`.

## Design

### Part A — campaign-service reconcile-by-truth

- **`repo.find_stuck_dispatched(pool, campaign_id, timeout_s)`** → rows where a
  stage is `dispatched` and `updated_at < now() - timeout`; returns
  `(chapter_id, stage, knowledge_job_id?, translation_job_id?, project_id)`.
- **Truth clients** (extend `dispatch_clients.py`):
  - `TranslationDispatchClient.chapter_status(user_id, job_id, chapter_id)` →
    `"done" | "failed" | "running" | "gone"` via a NEW internal GET (below).
  - `KnowledgeDispatchClient.extraction_status(user_id, project_id)` →
    `{active: bool, last_outcome: "completed"|"failed"|None}` via a NEW internal GET.
- **`saga/reconcile.py: reconcile_stuck(pool, clients, campaign, timeout_s)`** —
  called from `process_campaign` (after the cancel/complete short-circuits, before
  gating). For each stuck row:
  - **translation** — if no `translation_job_id` → reset to `failed`. Else by
    chapter_status: `done` → `mark_stage_done_by_chapter`; `failed`/`gone` →
    reset to `failed`; `running` → leave.
  - **knowledge** — by extraction_status: `active` → leave; not active +
    `completed` → `mark_stage_done_by_chapter`; `failed`/None → reset to `failed`.
  - **reset** = `repo.reset_stuck_stage(...)` sets the stage `dispatched`→`failed`,
    `last_error='stuck-reconcile: <reason>'` (gating re-dispatches within the
    attempt cap; the downstream skip-gate prevents re-spend on already-done work).
- **Config:** `CAMPAIGN_STUCK_DISPATCH_TIMEOUT_S` (default 900 = 15 min — knowledge
  per-chapter extraction + per-chapter translation finish well within). Gate the
  cross-service calls behind "only rows past timeout" so a healthy campaign makes
  zero extra calls.

### Part A endpoints (downstream truth)

- **translation-service** `GET /internal/translation/jobs/{job_id}/chapters/{chapter_id}`
  (internal-token, body/query `user_id` verified) → `{status}` for that chapter
  translation. Reuses the existing `ChapterTranslation` repo read; 404 → `gone`.
- **knowledge-service** `GET /internal/knowledge/projects/{project_id}/extraction-status`
  (internal-token, `user_id` verified) → `{active, last_outcome}` from
  `ExtractionJobsRepo` (latest job for project + active-job guard).

### Part B — worker-ai transactional emit

Fold `emit_chapter_extracted` INTO `_advance_cursor_and_emit_run`'s transaction
([runner.py:392](../../services/worker-ai/app/runner.py#L392)) so the per-chapter
completion outbox row is written in the SAME tx as the cursor advance — cursor
advances ⟺ event row exists. Keep a best-effort fallback path (matching the
existing run-telemetry fallback) so a tx failure still PROGRESSES the job (the
reconcile is the backstop for the rare loss). Remove the now-redundant separate
best-effort call at [runner.py:1551](../../services/worker-ai/app/runner.py#L1551).

## Files (≈11)

| Service | File | Change |
|---|---|---|
| campaign | `app/repositories.py` | `find_stuck_dispatched`, `reset_stuck_stage` |
| campaign | `app/saga/reconcile.py` | NEW — `reconcile_stuck` |
| campaign | `app/saga/driver.py` | call `reconcile_stuck` in `process_campaign` |
| campaign | `app/clients/dispatch_clients.py` | `chapter_status`, `extraction_status` |
| campaign | `app/config.py` | `stuck_dispatch_timeout_s` |
| campaign | `tests/test_reconcile.py` | NEW — reconcile unit tests |
| campaign | `tests/test_driver.py` | wire-in assertion |
| translation | `app/routers/internal_dispatch.py` | NEW internal GET chapter-status |
| translation | `tests/test_internal_dispatch.py` | endpoint tests |
| knowledge | `app/routers/internal_dispatch.py` | NEW internal GET extraction-status |
| knowledge | `tests/unit/test_internal_dispatch.py` | endpoint tests |
| worker-ai | `app/runner.py` | fold emit into the cursor-advance tx |
| worker-ai | `app/outbox_emit.py` | transactional variant signature (executor=conn) |
| worker-ai | `tests/test_chapter_extracted_emit.py` | tx-emit test |

## Risks / guards

- **Double-dispatch / double-spend** — the whole reason for by-truth. `running`
  truth → leave; only `done`→mark-done and terminal-failure→reset. Translation's
  skip-gate is the second line of defence on any reset.
- **`mark_stage_done_by_chapter` is idempotent** — a reconcile-mark racing a
  late real event is a no-op.
- **Nil-tolerant wiring test** ([[nil-tolerant-decorator-needs-wiring-test]]) —
  the driver MUST assert `reconcile_stuck` is actually called in the tick (spy),
  else a dropped call silently no-ops with all unit tests green.
- **Cross-service normalization** ([[cross-service-normalization-bug-class]]) —
  status string vocab must match across the truth endpoints and the campaign's
  interpretation; assert exact strings in tests.

## VERIFY plan

- Unit: campaign reconcile + driver wiring; translation + knowledge endpoint
  tests; worker-ai tx-emit test. Full suites per touched service.
- Cross-service (≥2 services) → live-smoke token required. Live-smoke: force a
  stuck row (dispatch then drop the event), confirm reconcile marks it done from
  truth within one timeout window. If the heavy-inference stack can't be brought
  up cleanly → `LIVE-SMOKE deferred to D-CAMPAIGN-RECONCILE-LIVE-SMOKE`.
