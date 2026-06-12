# D-WX-PRECISION-FILTER-MODEL-ARCH — precision-filter model must be user-resolved, not env-hardcoded

**Found:** 2026-06-13, by the D-WX decoupled-extraction live-smoke.
**Severity:** HIGH (breaks decoupled extraction for all-but-one user) + invariant violation.
**Status:** interim mitigation shipped (env default emptied → filter disabled); proper fix = this spec.

## The bug (root cause)

The Pass-2 precision filter (relation-precision LLM refinement, WX Wave 4) resolves its
model **entirely from a platform env var**:

- `services/worker-ai/app/runner.py::_load_precision_filter_config()` reads
  `WORKER_AI_PRECISION_FILTER_MODEL_REF` / `_MODEL_SOURCE`.
- `infra/docker-compose.yml` defaulted that env to a **hardcoded `user_model` UUID**
  (`019e5650-…` = one specific user's `huihui-qwen3.6-35b-a3b-claude-4.7-opus` model),
  for both `worker-ai` and `knowledge-service`.

When the decoupled filter stage submits its LLM job, it passes
`model_source="user_model"` + the **env** `model_ref`, scoped to the **campaign's
user**. `provider-registry ModelPricing(user_model, <campaign_user>, 019e5650)` →
`found=false` → **404 "model not found"** for every user who doesn't own `019e5650`.
In the decoupled path that 404 leaves the terminal event un-acked (PEL `pending=1`)
and the chapter stalls forever at `processed=0/1` — the LLM "stops being called".

It only ever worked for the single user whose model UUID happened to be in compose.

This also violates **CLAUDE.md → "No hardcoded model names"** (a user-model UUID,
cross-tenant, literal in config).

## Why env is the wrong layer

A model is a **per-user, BYOK, UI-selected, DB-persisted** resource resolved through
provider-registry — exactly like the campaign's knowledge / translation / verifier /
eval-judge models. The precision-filter model must flow the same way, NOT a platform env.

## The fix (5 layers — flows like the other campaign models)

1. **FE** — add an optional "precision-filter model" picker to the campaign wizard
   (same Model-Matrix component as knowledge/translation), defaulting to "off"
   (no filter) or "same as extraction model".
2. **campaign-service** — `precision_filter_model_source` / `precision_filter_model_ref`
   on `CreateCampaignPayload` + `Campaign` + DB columns; owner-verify the ref like the
   other model refs; dispatch them to the extraction job.
3. **knowledge-service** — accept + persist the filter model on `extraction_jobs`
   (additive migration); pass into the extraction config.
4. **worker-ai** — **delete `_load_precision_filter_config()`'s env reading**; build
   `PrecisionFilterConfig` from the **job config** → carried in `resume_state._filter_cfg`
   (already the resume shape), resolved per-user. A filter model that doesn't resolve
   must **degrade (skip the filter) — never 404-stall** the fold (defensive backstop).
5. **compose** — remove the `*_PRECISION_FILTER_MODEL_REF/_SOURCE` env entirely.

## Interim (shipped now)

`WORKER_AI_PRECISION_FILTER_MODEL_REF` + `KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF`
defaults emptied → filter disabled platform-wide → extraction runs for every user
(degraded: relations not LLM-filtered, ~identical F1 per c72c, +latency saved) and the
cross-tenant hardcoded UUID is gone. The 5-layer fix above restores the filter as a
proper per-campaign, per-user model.

## Acceptance (proper fix)

- A campaign created by user A with a filter model A-owns runs the decoupled filter
  end-to-end (no 404); a campaign with **no** filter model skips the filter cleanly.
- No `*_PRECISION_FILTER_MODEL_*` env in compose; provider-gate clean (no hardcoded UUID).
- A filter model that fails to resolve degrades (skips filter), never stalls the fold.
- Cross-service live-smoke: A's extraction with filter ON completes; B's (no filter) completes.
