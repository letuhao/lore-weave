# Spec + Plan — `D-FACTORY-INFLIGHT-LOG`: timestamped activity log

**Date:** 2026-06-11 · **Branch:** feat/auto-draft-factory-gaps · **Size:** XL (campaign-service + FE; single service → no cross-service live-smoke, but the trigger MUST be real-PG tested)

## Why
The in-flight panel (shipped) shows *what's running now*; this adds *what happened over time* — a recent-activity log (ch.5 · translation · done · 12:03:45, ch.7 · knowledge · failed (429)). Completes the deferred half of polish #4.

## Key insight — no new events
Every stage transition is already `UPDATE campaign_chapters SET <stage>_status = …` (driver dispatch, projection consumer done/skipped, reconcile stuck→failed, cancel). A **Postgres AFTER-UPDATE trigger** on `campaign_chapters` captures all of them into an append-only table — zero instrumentation in the app code, can't be forgotten when a new transition site is added.

## Slices

### 1. campaign-service — schema (migrate.py)
- `campaign_activity` table: `id BIGSERIAL PK, campaign_id UUID, chapter_id UUID, chapter_sort INT, stage TEXT, status TEXT, detail TEXT, created_at TIMESTAMPTZ DEFAULT now()`.
- Index `(campaign_id, id DESC)` for recent-first keyset pagination.
- `campaign_activity_log()` trigger function: AFTER UPDATE ON campaign_chapters FOR EACH ROW — for each of the 3 stage columns, `IF NEW.<col> IS DISTINCT FROM OLD.<col> THEN INSERT (…, stage, NEW.<col>, NEW.last_error)`. (Seed INSERTs at 'pending' don't fire — trigger is UPDATE-only.) `detail` = NEW.last_error only when the new status is 'failed' (else NULL).
- `CREATE TRIGGER … AFTER UPDATE ON campaign_chapters`. Idempotent: `CREATE OR REPLACE FUNCTION` + `DROP TRIGGER IF EXISTS` then `CREATE TRIGGER`.

### 2. campaign-service — read + API
- `repositories.py`: `get_campaign_activity(pool, campaign_id, *, limit, before_id) -> list[Record]` — `WHERE campaign_id=$1 [AND id < $before]` `ORDER BY id DESC LIMIT $n` (keyset; recent-first).
- `models.py`: `ActivityEntry` (id, chapter_sort, stage, status, detail, created_at) + `ActivityPage` (items, next_before id|null).
- `routers/campaigns.py`: `GET /{id}/activity?limit&before_id` — owner-scoped (404), clamp limit (1..200, default 50), returns ActivityPage; `next_before` = last item's id when a full page returned (else null).

### 3. FE
- `types.ts`: `ActivityEntry`, `ActivityPage`.
- `api.ts`: `activity(id, {limit, beforeId}, token)`.
- `hooks/useCampaignQueries.ts`: `useCampaignActivity(id, active)` — recent page, polls 6s while active (newest at top); no infinite scroll for MVP (recent N only).
- `components/ActivityLog.tsx` (new, view): list of rows `ch.{sort} · {stage} · {status}` + relative time (a tiny pure `relTime(iso, now)` helper, unit-tested), failures tinted; collapsed/empty → minimal. Renders nothing when no activity.
- `components/CampaignMonitor.tsx`: mount `<ActivityLog>` (below the in-flight panel / projection table).
- `components/__tests__/ActivityLog.test.tsx` (new): rows render newest-first; failure tint; `relTime` pure cases; empty → nothing.

## Verify
- campaign `pytest` incl a **real-PG** integration test (`test_activity_db.py`): UPDATE a chapter's stage statuses → assert the trigger wrote one activity row per transition with the right stage/status/detail; a no-status-change UPDATE (e.g. attempts bump) writes nothing; recent-first paging + `before_id`.
- FE `tsc` + `vitest run src/features/campaigns`.
- Single service → no cross-service live-smoke token; the trigger is real-PG covered.

## Out of scope / deferred
- Campaign-level lifecycle events (pause/resume/budget-pause) — visible via status badge.
- Activity-row retention/trim job — keep-all for MVP (bounded per campaign); `D-FACTORY-ACTIVITY-TRIM` if it ever matters.
- Infinite scroll / full history browser — recent N only.

## /review-impl (accepted findings)
- **#1 FIXED** — added eval + skipped trigger coverage to `test_activity_db.py` (the load-bearing branches the happy path missed).
- **#2 accept** — `get_campaign_activity` is owner-scoped only via the endpoint's preceding `get_campaign` check (identical to `get_campaign_chapters_page`/`get_campaign_progress`).
- **#3 accept/document** — trigger column-coverage is a drift risk: a future migration adding/renaming a stage column must also update `campaign_activity_log()` (no test asserts full coverage; the 3 stages are stable).
- **#4 accept/document** — a campaign cancel terminalizes chapter stages to `'failed'` (no chapter-level `'cancelled'` status), so cancelled work reads as `failed` (empty detail) in the log — faithful to the projection.
