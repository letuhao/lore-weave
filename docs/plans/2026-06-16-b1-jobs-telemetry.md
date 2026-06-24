# B1 — Jobs GUI telemetry completeness (P4)

**Batch:** DEBT-BATCHES B1 · **Size:** L · **Date:** 2026-06-16 · **Branch:** `feat/auto-draft-factory-gaps`

Decisions (PO, CLARIFY): **retry = re-submit (new job)**; **translation cost = add `cost_usd` column**.

**Linchpin (verified):** `job_projection` upsert COALESCE-merges `model`/`cost_usd`/`tokens`/`params`
(`services/jobs-service/app/projection/store.py:53-57`). So a value emitted on the CREATE event
is retained across later status events — model NAMES only need emitting **once at create, out-of-tx**
(mirrors composition `clients/model_name.py`: `GET /internal/models/{src}/{ref}/info`, best-effort).

## Milestones (each a commit at a risk boundary)

### M1 — model-name resolution + campaign spend emit (telemetry)
- **composition** `D-JOBS-P4-COMPOSITION-GUARDED-MODEL`: add `model_name` param to `create` +
  `create_chapter_job_guarded`; resolve out-of-tx at the 4 `engine.py` guarded call sites, pass in.
- **lore-enrichment** `D-JOBS-P4-LORE-MODEL`: add `clients/model_name.py`; resolve at job-create
  (out-of-tx) → pass `model=` into the create emit. Status-transition emits stay model-None (COALESCE).
- **campaign** `D-JOBS-P4-CAMPAIGN-MODEL-NAMES`: resolve the ≤2 stage refs (knowledge/translation)
  out-of-tx in the router before the create-tx → put NAMES in `params` (+ optional top-level `model`).
- **campaign** `D-JOBS-CAMPAIGN-SPEND-EMIT`: `spend_consumer` emits `emit_job_event_safe` (best-effort,
  pool, out-of-tx) with the new `cost_usd` after `accumulate_and_maybe_pause`.

### M2 — translation cost column (migration)
- `D-JOBS-P4-TRANSLATION-COST`: add `cost_usd` to `translation_jobs` (additive migration); capture
  per-chapter cost + accumulate; emit `cost_usd` at finalize (alongside the existing token-SUM).
- `D-JOBS-P4-TRANSL-TOKENS-PG`: add a real-PG test for the token-SUM (and new cost) aggregation.

### M3 — projection summary + FE overlay
- `D-JOBS-P4-SUMMARY-TOPLEVEL`: `count_summary` (`store.py:376`) undercounts a completed parent with a
  running child (filters `parent_job_id IS NULL`). Count active regardless of hierarchy (or parent
  active if any child active) + real-PG test.
- `D-JOBS-P4-OVERLAY-EVICT`: FE `JobsStreamProvider` overlay Map only `.set()`s — evict terminal jobs
  (completed/failed/cancelled) after the invalidate settles.

### M4 — retry = re-submit (new job), end-to-end
- SDK `ControlCap.RETRY`; jobs-service `VALID_ACTIONS` + `derive_control_caps` (valid only from `failed`);
  forward to owning service; each owning service re-submits a fresh job from stored request params
  (translation/knowledge/composition/lore_enrichment); FE `ControlCap`+button. Cross-service seam.

**Live-smoke:** B1 telemetry/control folds into B3 (Job-Control+P5 sweep) unless smoked inline.
