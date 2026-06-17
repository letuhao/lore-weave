# Plan — Retry-per-kind extension + B4b reconciliation (2026-06-17)

Scope from a verify-first triage of `D-JOBS-P4-RETRY-*` (B1 residual) + B4b. The
debt list overstated both: B4b is mostly done; retry has 2 clean kinds + 2 blocked.

## Retry-per-kind (D-JOBS-P4-RETRY-*)

Reference: translation `_retry_job_core` ([internal_dispatch.py:479](../../services/translation-service/app/routers/internal_dispatch.py#L479)) +
jobs-service `_RETRYABLE_KINDS` ([contract.py:41](../../services/jobs-service/app/contract.py#L41)).
Pattern: `failed` job → re-submit a FRESH job from stored params, owner-scoped
(404 if not owned), 409 unless `failed`, 409 if campaign-managed. The FE Retry
button is data-driven off `derive_control_caps` → **no SDK/FE change** for new kinds.

| Kind | Verdict | Why |
|---|---|---|
| translation | ✅ shipped (reference) | — |
| **knowledge/extraction** | 🟢 DO — clean | `extraction_jobs` row has all `StartJobRequest` fields; reconstruct + call `_start_extraction_job_core` (re-gates benchmark/budget, emits running, wakes worker) |
| **composition** | 🟢 DO — clean | `generation_job.input` JSONB + model refs carry the create params; reconstruct + call the create core |
| video_gen | 🔴 BLOCKED | `video_gen_jobs` persists NO input params → needs a schema migration + backfill (defer: `D-JOBS-P4-RETRY-VIDEOGEN`, migration → /amaw) |
| lore_enrichment | 🔴 BLOCKED | runs synchronously in-process → incompatible with the deferred-control contract; needs the async-decouple refactor (defer: `D-JOBS-P4-RETRY-LORE`, XL) |

### Steps (per clean kind)
1. jobs-service `contract.py`: `_RETRYABLE_KINDS += {kind}` (+ confirm `derive_control_caps` `failed`→[RETRY] for it).
2. Owning service: add `_retry_*_core(pool, job_id, owner_user_id)` mirroring translation's guards; reconstruct the create request from the failed row; call the existing create/start core (which emits `running`).
3. Owning service control endpoint: route the `retry` action → the core.
4. Tests: retry happy-path (new job_id + `retried_from`), 404 not-owned, 409 not-failed, 409 campaign-managed.
5. VERIFY (service pytest) + jobs-service caps test for the new kind.

Order: **knowledge first** (1:1 row→payload, well-understood), then **composition** (JSONB unpack) if context allows.

## B4b — Auto-Draft Factory (reconciliation, mostly done)
- ✅ already shipped: `D-CAMPAIGN-CANCEL-PROP`, `D-CAMPAIGN-BREAKER-PAUSE`, `D-CAMPAIGN-KPROJECT-OWNERSHIP` → mark resolved.
- 🟡 open but low/gated: `D-S4-SUMMARY-ATTRIBUTION` (S, perf-later — inert under-count), `D-S5BEVAL-LEARNING-OUTBOX` (S but needs an outbox-table migration → /amaw).

## Out of scope (need you / stack)
- `D-S4C-ACCOUNTBALANCES-DROP` (migration → /amaw), `D-K19e-α-03` (chrono design call),
  `D-K19e-γa-02`/`D-PHASE5E` (backend-gated), B4a/B5 live-smokes (campaign/wiki stack + browser).
