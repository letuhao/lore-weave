# Spec + Plan — `D-FACTORY-SWITCH-MODEL-RESUME`

**Date:** 2026-06-11 · **Branch:** feat/auto-draft-factory-gaps · **Size:** XL (campaign-service + FE; single service → no live-smoke token)

## Why
A paused campaign (cloud provider rate-limited overnight, or budget auto-pause) can only be cancelled + rebuilt to change models today. This lets the user **re-pick the LLM model and resume** so the remaining chapters finish — typically on a local ($0) model.

**Mechanism (verified):** the saga driver reads `campaign.{translation,knowledge,verifier,eval_judge}_model_{source,ref}` *fresh from the row each tick* (driver.py:153-195). So a PATCH to those columns while paused takes effect on the next dispatch after resume. Already-completed chapters keep their version (the translation skip-gate prevents re-spend); only pending/failed chapters dispatch with the new model.

## Contract

`PATCH /v1/campaigns/{id}` — today budget-only (`UpdateBudgetPayload`). Widen to `UpdateCampaignPayload` (all fields optional; only *explicitly-provided* fields update, via Pydantic `model_fields_set`):
- `budget_usd` — unchanged (any non-terminal status).
- `translation_model_source/ref`, `knowledge_model_source/ref`, `verifier_model_source/ref`, `eval_judge_model_source/ref` — **allowed only when status ∈ {created, paused}** → else `409 CAMPAIGN_MODELS_LOCKED`.
- **Excluded:** embedding + rerank (knowledge-project SSOT; embedding change is destructive to the graph). Not on the campaign row.

## Slices

### 1. campaign-service (Python)
- `app/models.py`: `UpdateCampaignPayload` (optional budget + 8 model fields; reuse `_BUDGET_USD_MAX` validation on budget). Keep `UpdateBudgetPayload` removed/replaced — endpoint switches to the new payload (a budget-only body still validates: only `budget_usd` in `model_fields_set`).
- `app/repositories.py`: `update_campaign_fields(pool, campaign_id, owner, fields: dict) -> Optional[Record]` — dynamic SET over a **column whitelist** (`budget_usd` + the 8 model columns); owner-scoped WHERE; `RETURNING _CAMPAIGN_COLS`. Returns None if not owned / no fields. Keep `update_budget` or route it through the new fn.
- `app/routers/campaigns.py`: PATCH handler — fetch campaign (owner-scoped, 404 if None); if any **model** field provided AND status ∉ {created, paused} → 409 `CAMPAIGN_MODELS_LOCKED`; build the update dict from `model_fields_set`; call `update_campaign_fields`; return `_campaign_model`.
- `tests/test_campaigns_api.py`: budget-only PATCH still works; model PATCH on a paused campaign applies; model PATCH on a running campaign → 409; not-owned → 404.
- `tests/integration/test_progress_db.py`: real-PG — `update_campaign_fields` updates only the provided columns, leaves others intact, owner-scoped.

### 2. FE (TS)
- `types.ts`: `UpdateCampaignPayload` (optional budget + model fields).
- `api.ts`: `updateCampaign(id, patch, token)` general PATCH; keep `updateBudget` (delegates).
- `hooks/useCampaignMutations.ts`: `useUpdateCampaign` mutation (invalidates campaign + progress keys).
- `components/SwitchModelControl.tsx` (new, paused-only): two `ModelRolePicker`s (capability=chat) pre-filled from the campaign's current translation + knowledge model refs; a **"Switch model & resume"** button → `useUpdateCampaign` then chain `useResumeCampaign` on success (explicit callback, no useEffect). Renders only when status ∈ {paused, created}.
- `components/CampaignMonitor.tsx`: mount `<SwitchModelControl>` under the paused banner, passing current model picks from `c`.
- `components/__tests__/SwitchModelControl.test.tsx` (new): renders pickers pre-filled; save chains resume; hidden when running.

## Verify
- campaign `pytest` (unit + integration; full suite for regression)
- FE `tsc --noEmit` + `vitest run src/features/campaigns`
- Single service (`services/campaign-service/` only) → no cross-service live-smoke token.

## Out of scope / deferred (stays)
- Embedding/rerank switch (destructive / SSOT).
- Re-running already-completed chapters on the new model (that's G2 force-rerun, separate).
- Switching model mid-**run** (must pause first — deliberate).
