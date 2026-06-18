# Plan — `D-FACTORY-INFLIGHT-PANEL`: live "Now processing" panel

**Date:** 2026-06-11 · **Branch:** feat/auto-draft-factory-gaps · **Size:** L (campaign-service + FE; single service → no live-smoke token)

**Goal:** the active monitor shows *which* chapters are dispatched to a provider right now (the G3 stat shows only the count). MVP = stage-level list (chapter sort# + in-flight stage); per-chapter sub-step state (batch/verify/backoff) and the timestamped recent-log stay deferred (no activity event feed).

## Slices

### 1. campaign-service (Python)
- `app/repositories.py`: add `_INFLIGHT_FILTER = "AND 'dispatched' IN (knowledge_status, translation_status)"`; `get_campaign_chapters_page` picks the filter from a whitelisted `status` (`attention` | `inflight` | `all`). Same paged query, same columns.
- `app/routers/campaigns.py`: widen the `GET /{id}/chapters` status clamp to `("attention", "all", "inflight")` (unknown → "attention", unchanged default).
- `tests/test_campaigns_api.py`: a router test that `status=inflight` is accepted + forwarded (mock the repo, assert the status arg).
- `tests/integration/test_progress_db.py`: real-PG case — seed chapters with a `dispatched` stage + settled ones → `status=inflight` returns only the dispatched rows; `attention`/`all` unchanged.

### 2. FE (TS)
- `api.ts` + `hooks/useCampaignQueries.ts`: widen the `status` union to include `'inflight'`. Add `useInFlightChapters(campaignId, active)` — calls `chapters(status='inflight', limit=50, offset=0)`, polls 6s while active (matches the live cadence; bounded result set).
- `components/InFlightPanel.tsx` (new, view): renders `ch.{sort} — {stage}` chips for in-flight chapters; returns null when none or not active. Stage = whichever of knowledge/translation is `dispatched`.
- `components/CampaignMonitor.tsx`: mount `<InFlightPanel>` for an active campaign (near the G3 stats / above the projection table).
- `components/__tests__/InFlightPanel.test.tsx` (new): renders the in-flight rows; empty → nothing.

## Verify
- campaign `pytest tests/test_campaigns_api.py tests/integration/test_progress_db.py` (+ full suite for regression)
- FE `tsc --noEmit` + `vitest run src/features/campaigns`
- Single service (only `services/campaign-service/`) → no cross-service live-smoke token required.

## Out of scope / deferred (stays)
- Per-chapter sub-step state (batch N/M, verify, 429-backoff) — not projected.
- `D-FACTORY-INFLIGHT-LOG` (the timestamped recent-activity log) — needs a per-chapter activity event tap.
