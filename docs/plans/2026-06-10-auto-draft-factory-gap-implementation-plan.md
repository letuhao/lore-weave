# Plan — Auto-Draft Factory gap fixes (draft-vs-impl)

**Date:** 2026-06-10 · **Branch:** feat/advanced-translation-pipeline
**Source:** `docs/reviews/2026-06-10-auto-draft-factory-draft-vs-impl-review.md`
**Scope of THIS plan:** the in-scope 🔴 gaps + recommended 🟡 polish. ⚪ vision-beyond-MVP items are listed at the end as tracked-defer only.

Ordering principle: backend-first (endpoints + data), then FE wiring, each slice a `/loom` with tests. Most gaps are **read-side/aggregation** (no new saga state) → low risk.

---

## 🔴 G1 — Completion / wake-up report
**Why:** original PO scope listed a "wake-up report"; the draft's Report screen is the run's deliverable summary. A completed/failed campaign currently shows only the live monitor.

**Backend**
- New `GET /v1/campaigns/{id}/report` (owner-scoped) → `CampaignReport`:
  - `status, started_at, finished_at, duration_seconds`
  - `total_chapters`, per-stage `{done, failed, skipped}` (reuse `get_campaign_progress` aggregate)
  - `spent_usd`, `budget_usd`, `estimated_usd_low/high` (persist the launch estimate — see note), `under_over_estimate`
  - `error_groups: [{cause, count, remediable: bool}]` — group `campaign_chapters.last_error` by a normalized cause (regex/prefix: `429|rate-limit`, `empty|body`, `circuit`, `0-output`, other). Pure SQL `GROUP BY` on a `cause` expression or fetch+bucket in Python.
  - `glossary_entities`? optional (skip if not cheaply available).
- **Persist the launch estimate:** add `est_usd_low/est_usd_high NUMERIC` columns to `campaigns` (additive migration), set them at create from the estimate (or recompute at report time). MVP: recompute is fine; persist is cleaner.
- Tests: report aggregate (real-PG behavioral test like `test_progress_db`); error-group bucketing unit test (the cause-normalizer is the load-bearing pure fn — test it).

**Frontend**
- `CampaignReport.tsx` (rendered by `CampaignMonitor` when status is terminal `completed|failed|cancelled`): results grid (done/errors/spent-vs-estimate), error-group table, **"Review draft"** CTA (→ the reader/flywheel route for the book) + (if G2) "Re-run failed".
- `campaignsApi.report(id)` + `useCampaignReport(id)` (no polling; terminal).
- Tests: vitest for the report view (grid + error groups + CTA).

**Size:** M (BE endpoint + aggregate + FE view). Cross-service: no.

---

## 🔴 G2 — User-triggered re-run of failed chapters
**Why:** the draft's headline failure-recovery flow. Today, gating auto-re-dispatches `failed` within `max_attempts`; once exhausted there is **no user re-run** — exhausted-failed chapters are stuck.

**Backend**
- New `POST /v1/campaigns/{id}/rerun-failed` (owner-scoped), body `{chapter_ids?: UUID[]}` (omit = all settled-failed):
  - Reset the **failed** stages of the targeted chapters: `*_status='failed'` → `'pending'` AND **reset that stage's `*_attempts` to 0** (so gating re-dispatches them); clear `last_error`.
  - Re-arm the campaign: if terminal (`completed`/`failed`) flip back to `running` (set_started preserved); the driver then re-dispatches. Guard: refuse if `cancelled`.
  - **Idempotency / spend-safety:** translation re-dispatch is skip-gated (already-fresh chapters skipped); knowledge re-extraction re-spends — acceptable for an explicit user re-run. Document.
  - Decision (MVP): re-run in the **same** campaign (NOT a child sub-run #41-r1 — that's ⚪ vision). The projection already isolates per-chapter state.
  - Repo: `reset_failed_stages(pool, campaign_id, chapter_ids|None) -> int`.
- Tests: repo reset (real-PG) — exhausted-failed → pending + attempts 0; router re-arm transition; refuse-when-cancelled.

**Frontend**
- In `ChapterProjectionTable` / report: multi-select failed rows + "Re-run selected" + "Re-run all failed" → `campaignsApi.rerunFailed(id, ids?)` → invalidate queries.
- `useRerunFailed()` mutation.
- Tests: vitest control + mutation.

**Size:** M. Cross-service: no (re-dispatch is the existing driver path).

---

## 🟡 G3 — Monitor live stats: elapsed / ETA / throughput / parallel
**Why:** the draft monitor's stat grid; useful operator signal on a long run.

**Backend** (extend `CampaignProgress` / progress endpoint — read-side aggregate, cheap)
- `elapsed_seconds` = `now() - started_at` (when running) or `finished_at - started_at`.
- `chapters_per_min` = settled-this-run / elapsed (compute FE-side from progress deltas is also fine).
- `in_flight` = count of `dispatched` across stages (already have `count_inflight`).
- `eta_seconds` = remaining settled-work / throughput (rough; FE can compute). Keep server-side optional; **prefer FE-derived** from progress + started_at to avoid new BE state.

**Frontend**
- Add a stats row to `CampaignMonitor`: elapsed (from `started_at`), throughput + ETA (derived from progress + elapsed), in-flight (from progress `in_progress` sum). Pure presentation off existing data.
- Tests: a small pure helper `deriveRunStats(progress, startedAt, now)` + unit test (the math is the load-bearing bit).

**Size:** S–M (mostly FE + a derive helper). Cross-service: no.

---

## 🟡 G4 — "Review draft" handoff CTA
**Why:** the draft → flywheel review handoff (the whole point of the factory output).
- FE only: a CTA (in the report + on a completed monitor) linking to the book's reader/translation-review route (e.g. `/books/{book_id}/...` reader or the existing M5/M6 review surface). Wire to the existing route; no BE.
- **Size:** XS. Confirm the target route exists before wiring.

---

## 🟡 Polish batch (recommended, each small)
1. **Chapter-table paging** (`D-S6-CHAPTER-PAGING`): server-side paging for `chapters[]` (the table caps at 200; a 4000-chapter run can't see the tail). Add `?limit&offset` to `GET /{id}` chapters OR a dedicated `GET /{id}/chapters?status=&limit=&offset=`. FE: paginate. **Size:** M.
2. **Campaigns-list progress + ETA + quick-actions**: list rows fetch lightweight progress (or include done-count in the list query) → progress bar + ETA; add inline Resume (paused) / Re-run-failed (terminal-with-errors). **Size:** M.
3. **Paused-state rich banner + stats** (done / remaining / spent=cap / elapsed) + clearer graceful-pause copy. **Size:** S (FE).
4. **In-flight "processing" panel** + **recent log**: requires a per-chapter recent-activity feed. MVP cheap version: derive "in-flight" from `dispatched` rows (chapter + stage); a true timestamped log needs an event tap (defer the log, do the in-flight list). **Size:** S (in-flight) / M (log → defer).
5. **Estimate per-model token columns + cloud/local badges**: the oracle already computes per-stage token workload; surface `tok_in/tok_out` + provider-kind badge in `EstimateResponse.per_stage` + ReviewStep table. **Size:** S.
6. **Ingest row in StageProgress** (always 100% precondition) — cosmetic parity. **Size:** XS.
7. **Paused "switch to local model" resume**: allow re-picking translation/knowledge model on resume (PATCH model + resume). Heavier (model mutation on a live campaign) — **defer unless desired** (workaround: cancel + new campaign).

---

## ⚪ Vision-beyond-MVP — tracked-defer (NOT in this plan's build)
- 7-step wizard **Pipelines** (choose subset of 4) + **Options/presets** (Balanced/two_pass) + **Policy/scheduling** ("run at night"). Scheduling needs a scheduler — out of current scope.
- **Optional 50-chapter sample run** (estimator heuristic→sampling): a real pre-launch sample campaign + quality preview. Sizeable; deferred (`D-S5A` sampling).
- **Sub-run / child campaign (#41-r1)** for re-runs (G2 does it in-place instead).
- **CSV export** of the report.
- **Heatmap** visualization (table is the MVP substitute; revisit at scale).
- **Compact-model role** in the matrix (currently internal to V3).

---

## Suggested build order (post-merge)
1. G1 report (BE aggregate + FE view) — highest user value, low risk.
2. G2 re-run-failed (BE reset + re-arm + FE) — completes the failure-recovery loop.
3. G3 monitor stats + G4 review CTA (FE-mostly) — quick wins.
4. Polish 1–6 as capacity allows; 7 + ⚪ deferred.

Each slice: `/loom`, tests-first, ≥2-service slices get a live-smoke token (most are single-service read-side → unit + real-PG behavioral test).
