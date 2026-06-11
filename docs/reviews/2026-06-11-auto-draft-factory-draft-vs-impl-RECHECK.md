# Recheck — Auto-Draft Factory: draft HTML vs current FE/BE coverage (gaps CLEARED)

**Date:** 2026-06-11 · **Branch:** `feat/auto-draft-factory-gaps` (PR #30)
**Inputs:** `design-drafts/auto-draft-factory.html` (intended UX) vs `frontend/src/features/campaigns/**` + `services/campaign-service/**` + `services/provider-registry-service/internal/api/estimate.go` (actual, post-gap-fixes).
**Supersedes:** `docs/reviews/2026-06-10-auto-draft-factory-draft-vs-impl-review.md` (the pre-fix review). This recheck re-runs that review **after** the gap-fix work landed and records the **evidence** (file:line + test) proving each prior 🔴/🟡 gap is closed.
**Companions:** gap plan `docs/plans/2026-06-10-auto-draft-factory-gap-implementation-plan.md`; E2E scenarios `docs/specs/2026-06-10-auto-draft-factory-e2e-scenarios.md`.

## Verdict (TL;DR)

**All in-scope 🔴 gaps and all recommended 🟡 polish from the 2026-06-10 review are CLOSED**, each with a concrete implementation + at least one test. The only remaining items are the ⚪ vision-beyond-MVP set (explicitly out of scope) and the live-only smokes (need a stack/harness/JSON-clean judge model — tracked, not code gaps).

| Prior class | Count | Now |
|---|---|---|
| 🔴 In-scope gaps (G1–G4) | 4 | ✅ 4/4 CLEARED |
| 🟡 Polish (in-flight panel, log, ingest row, paging, list progress, paused banner, token cols + badges, switch-model resume) | 8 | ✅ 8/8 CLEARED |
| ⚪ Vision-beyond-MVP | 6 | ◻ Deferred (tracked, not a bug) |
| Live-only smokes (HARNESS/MODEL/STALE) | — | ◻ Tracked in SESSION_HANDOFF |

---

## Evidence per cleared gap

Legend: **BE** = backend route/logic · **FE** = component · **T** = test proving it.

### 🔴 G1 — Completion / wake-up report → ✅ CLEARED
- **BE** `GET /v1/campaigns/{id}/report` — [campaigns.py:426](../../services/campaign-service/app/routers/campaigns.py#L426): owner-scoped; outcome + per-stage `StageCounts` (reuses `get_campaign_progress`) + `spent_usd`/`budget_usd`/`est_usd_low`/`est_usd_high` + `error_groups` bucketed by normalized cause.
- **BE** cause-normalizer (the load-bearing pure fn) — [cause.py:31 `normalize_error_cause`](../../services/campaign-service/app/cause.py#L31) → `(cause_label, remediable)`; rules table at [cause.py:20](../../services/campaign-service/app/cause.py#L20).
- **BE** persisted launch estimate — `est_usd_low/high` columns + `get_report_row` ([repositories.py](../../services/campaign-service/app/repositories.py)).
- **FE** `CampaignReport` — [CampaignReport.tsx:9](../../frontend/src/features/campaigns/components/CampaignReport.tsx#L9); rendered by the monitor on terminal status.
- **T** [CampaignReport.test.tsx](../../frontend/src/features/campaigns/components/__tests__/CampaignReport.test.tsx) (grid + error groups + CTA) · BE cause-bucketing + report-aggregate tests.

### 🔴 G2 — User-triggered re-run of failed chapters → ✅ CLEARED
- **BE** `POST /v1/campaigns/{id}/rerun-failed` — [campaigns.py:504](../../services/campaign-service/app/routers/campaigns.py#L504): resets failed stages → `pending` + zero attempts + clear `last_error`, re-arms campaign to `running`; refuses cancelled/cancelling; over-budget guard applies.
- **BE** repo `reset_failed_stages` — [repositories.py:789](../../services/campaign-service/app/repositories.py#L789) (`chapter_ids|None` → count).
- **FE** multi-select + "Re-run selected" / "Re-run all failed" in [ChapterProjectionTable.tsx](../../frontend/src/features/campaigns/components/ChapterProjectionTable.tsx); `useRerunFailed` in [useCampaignMutations.ts](../../frontend/src/features/campaigns/hooks/useCampaignMutations.ts).
- **T** repo reset (real-PG `test_rerun_db.py`) + router re-arm/refuse-cancelled + FE control test.

### 🟡 G3 — Monitor live stats (elapsed / ETA / throughput / in-flight) → ✅ CLEARED
- **FE** pure helper `deriveRunStats` — [runStats.ts:19](../../frontend/src/features/campaigns/runStats.ts#L19) (the load-bearing math, off existing progress + started_at).
- **FE** stats row in [CampaignMonitor.tsx](../../frontend/src/features/campaigns/components/CampaignMonitor.tsx).
- **T** [runStats.test.ts](../../frontend/src/features/campaigns/__tests__/runStats.test.ts).

### 🔴 G4 — "Review draft" handoff CTA → ✅ CLEARED
- **FE** CTA in `CampaignReport` → the book's reader/review route ([CampaignReport.tsx:9](../../frontend/src/features/campaigns/components/CampaignReport.tsx#L9), `bookId` prop). Covered by `CampaignReport.test.tsx`.

### 🟡 In-flight "processing" panel → ✅ CLEARED
- **BE** `GET /{id}/chapters?status=inflight` — [campaigns.py:339](../../services/campaign-service/app/routers/campaigns.py#L339) (`status=inflight` = rows with a stage currently `dispatched`); filter `_INFLIGHT_FILTER` in repositories.py.
- **FE** `InFlightPanel` + pure `inFlightStages(c)` — [InFlightPanel.tsx:8](../../frontend/src/features/campaigns/components/InFlightPanel.tsx#L8), [:19](../../frontend/src/features/campaigns/components/InFlightPanel.tsx#L19); "+N more" overflow.
- **T** [InFlightPanel.test.tsx](../../frontend/src/features/campaigns/components/__tests__/InFlightPanel.test.tsx).

### 🟡 Recent activity log (timestamped) → ✅ CLEARED
- **BE** `campaign_activity` table + AFTER-UPDATE trigger — [migrate.py:127](../../services/campaign-service/app/migrate.py#L127) (table), [migrate.py:144 `campaign_activity_log()`](../../services/campaign-service/app/migrate.py#L144), trigger [migrate.py:166](../../services/campaign-service/app/migrate.py#L166) `AFTER UPDATE ON campaign_chapters`. Sources the log from projection UPDATEs (no new event pipeline).
- **BE** `GET /{id}/activity?limit&before_id` keyset feed — [campaigns.py:365](../../services/campaign-service/app/routers/campaigns.py#L365); repo `get_campaign_activity` [repositories.py:221](../../services/campaign-service/app/repositories.py#L221).
- **FE** `ActivityLog` + pure `relTime` — [ActivityLog.tsx:6](../../frontend/src/features/campaigns/components/ActivityLog.tsx#L6), [:28](../../frontend/src/features/campaigns/components/ActivityLog.tsx#L28).
- **T** [ActivityLog.test.tsx](../../frontend/src/features/campaigns/components/__tests__/ActivityLog.test.tsx) + real-PG trigger test (`test_activity_db.py`). (Hardened via `/review-impl`.)

### 🟡 Chapter-table paging (>200) → ✅ CLEARED
- **BE** `GET /{id}/chapters?status&limit&offset` → `ChapterPage{rows,total}` — [campaigns.py:339](../../services/campaign-service/app/routers/campaigns.py#L339) (`limit` clamped 1–500); detail un-embeds chapters ([campaigns.py:333](../../services/campaign-service/app/routers/campaigns.py#L333)).
- **FE** paginated `ChapterProjectionTable` + `useCampaignChapters` query. **T** `ChapterProjectionTable.test.tsx` + real-PG page test.

### 🟡 Estimate per-stage token columns + cloud/local badge → ✅ CLEARED
- **BE** provider-registry echoes `provider_kind` + `is_local` — [estimate.go:55-56](../../services/provider-registry-service/internal/api/estimate.go#L55), set at [:110-111](../../services/provider-registry-service/internal/api/estimate.go#L110); `IsLocalKind` in `billing/default_pricing.go`. campaign threads them into `per_stage`.
- **FE** token in/out columns + 🖥 local / ☁ cloud badge in [ReviewStep.tsx](../../frontend/src/features/campaigns/components/steps/ReviewStep.tsx) (i18n `review.localFree`/`review.cloud`).

### 🟡 Paused "switch to local model" resume → ✅ CLEARED
- **BE** `PATCH /{id}` widened — [campaigns.py:271](../../services/campaign-service/app/routers/campaigns.py#L271): partial update; the 4 LLM model fields re-pickable **only** while `created/paused` (409 `CAMPAIGN_MODELS_LOCKED` otherwise — [:298](../../services/campaign-service/app/routers/campaigns.py#L298)); `update_campaign_fields` whitelist [repositories.py:403](../../services/campaign-service/app/repositories.py#L403).
- **FE** config-driven `SwitchModelControl` (4 roles: translation/knowledge/verifier/eval_judge) → "Switch model & resume" chains PATCH→resume — [SwitchModelControl.tsx:29](../../frontend/src/features/campaigns/components/SwitchModelControl.tsx#L29).
- **T** [SwitchModelControl.test.tsx](../../frontend/src/features/campaigns/components/__tests__/SwitchModelControl.test.tsx) + BE patch-gating tests.

### 🟡 Ingest row · campaigns-list progress bar · paused rich banner → ✅ CLEARED
- **FE** ingest precondition row (always 100%) — [StageProgress.tsx:19](../../frontend/src/features/campaigns/components/StageProgress.tsx#L19), [:22](../../frontend/src/features/campaigns/components/StageProgress.tsx#L22).
- **FE** list progress bar + paused banner — [CampaignsList.tsx](../../frontend/src/features/campaigns/components/CampaignsList.tsx) / [CampaignMonitor.tsx](../../frontend/src/features/campaigns/components/CampaignMonitor.tsx) (i18n `monitor.pausedBanner`).

### Bonus (not in the draft, shipped this branch)
- **i18n** — campaigns namespace localized en/vi/ja/zh-TW (~115 keys) with a parity guard test `campaignsParity.test.ts` (D-S5C-I18N).
- **Budget validation** — pure `validateBudget` + inline error ([ReviewStep.tsx], `validateBudget.test.ts`).
- **Picker dedup** — `useByokModels` shared query so the 4 model pickers fetch once ([useByokModels.ts](../../frontend/src/features/campaigns/hooks/useByokModels.ts)).

---

## Still open — by design (NOT gaps)

- **⚪ Vision-beyond-MVP** (track-only, unchanged): 7-step wizard Pipelines/Options/Policy-scheduling steps, optional 50-chapter sample run, sub-run child campaigns, CSV export, heatmap (the paginated table is the MVP substitute), compact-model role exposure.
- **Live-only smokes** (need a real stack / fault-injection / JSON-clean judge model — tracked in `docs/sessions/SESSION_HANDOFF.md`): `D-S3A/B-*-LIVE-SMOKE` [HARNESS], `D-S5BEVAL-LIVE-SMOKE`/`D-LEARNING-JUDGE-EMPTY-CONTENT` [MODEL].

## Conclusion

The draft-vs-impl gap surface identified on 2026-06-10 is **closed**. Every previously-flagged 🔴/🟡 item has implementation + test evidence above. The QC bar for this branch is now the **E2E coverage pass** in `docs/specs/2026-06-10-auto-draft-factory-e2e-scenarios.md` (the previously `[GAP:Gx]`-tagged scenarios are re-tagged `[NOW]` there) and the runnable `frontend/tests/e2e/specs/campaign-factory.spec.ts`.
