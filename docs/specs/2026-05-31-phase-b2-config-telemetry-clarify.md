# CLARIFY — Phase B2: Axis-2 config telemetry (scope-locked; DESIGN next session)

**Date:** 2026-05-31 · **Status:** CLARIFY complete; DESIGN deferred to a fresh session · **Workflow:** AMAW · **Size:** XL+
**Plan ref:** [`docs/plans/2026-05-31-extraction-accuracy-and-eval-plan.md`](../plans/2026-05-31-extraction-accuracy-and-eval-plan.md) §2.1 (Axis 2) / §2.4 (mining) · **Deferred:** D#055
**Predecessor:** Phase B (Axis-1 correction capture) — shipped session 75 (learning-service + corrections spine).

## 0 · Why this doc
Phase B2 was started (CLARIFY) at the tail of session 75. The code surface was mapped and PO locked scope. The DESIGN (content-addressed schema + per-novel tuning surface + AMAW review + checkpoint-commit) is a fresh-session effort — this doc hands it everything needed to start.

## 1 · CLARIFY findings — plan-vs-code reality (code-derived)

The plan's Axis-2 prose presumes surfaces that **do not exist today**. Re-derived from code (3 exploration agents):

1. **No per-novel extraction-config tuning exists.** Precision-filter, entity-recovery, writer-autocreate, prompts, temperature/max_tokens/thinking are all **GLOBAL** — env-driven module-level singletons (`pass2_orchestrator._load_precision_filter_config` etc., worker-ai `runner.py` parallel copies) or hard-coded SDK constants. **Per-job/per-project: only the extractor `llm_model` + `embedding_model`.** `knowledge_projects.extraction_config JSONB` ([migrate.py:37](../../services/knowledge-service/app/db/migrate.py)) exists but is **UNUSED by extraction** (only a context-path `rerank_model` read in `app/context/modes/full.py`). → the "every user tunes per-novel" premise is **aspirational**.
2. **No per-run record / config_hash / outcome.** A "run" is a multi-chapter **job** (`extraction_jobs`, [migrate.py:272](../../services/knowledge-service/app/db/migrate.py)). No per-chapter id, **no `config_hash`, no outcome label, no persisted per-run metrics** (counts → `job_logs.context` + Prometheus aggregates only; cost = flat `$0.004/item` estimate, `runner.py:309` — no real tokens). The plan's "run plumbing" dependency (§4) is **unbuilt**.
3. **Prompts ALREADY have a content-hash version** — `sdks/python/loreweave_extraction/_version.py`: global `__extractor_version__ = "v1-<8hex>"` (sha256 of `prompts/*.md`) + per-op `get_extractor_version(op)`. Used today only as the `extraction_leaves` cache key, NOT stored per-run. → a ready foundation for `config_registry`'s prompt-hash.
4. **Config resolution is scattered, not unified.** No single "resolved config" object: extractor model from the job row; filter/recovery/autocreate from process-global env singletons (filter alone has a runtime Redis-pubsub reload); SDK constants for temp/tokens. → B2 must introduce the *assembly* of a resolved-config object at run time.
5. **Adjustment surface today = thin.** The only per-project user-mutable knobs ([projects.py](../../services/knowledge-service/app/routers/public/projects.py) `PATCH /projects/{id}`, `PUT .../embedding-model`): `embedding_model`, `instructions`, `tool_calling_enabled`, `memory_remember_confirm`, `save_raw_extraction`, archive/name/desc. Plus the **global admin** `POST /internal/admin/precision-filter/reload` (internal-token, not per-user). No prompt/temperature/precision-filter per-project editing exists.
6. **Transport (plan §2.1):** `config_adjustment_events` is **async / lossy-OK (NOT the transactional outbox)** — explicitly analytics, not truth. Different from Phase B's durable corrections spine. learning-service's existing consumer (`learning-collector`, outbox-backed, DLQ, outbox_id dedup) is built for truth-grade events — heavier than adjustment-logging needs.

## 2 · Locked scope (PO decisions, session 75)

| Decision | Choice |
|---|---|
| **B2 core** | ✅ **Run plumbing** — `extraction_runs` + content-addressed `config_registry` + `config_hash`/outcome emission from the job-completion path. Outcome = **IMPLICIT at cold-start** (derive from: did the user later correct the output / re-run / discard — joinable against the Phase-B `corrections` log + job history). No new UI for this slice. This is the dependency everything else needs (plan §4). |
| **config_adjustment_events** | ✅ **ALSO build per-novel config tuning** — the user-facing per-project extraction-config tuning surface (model / prompt / params per novel) that the plan assumes but which doesn't exist. BE (extend `knowledge_projects.extraction_config` to actually drive the pipeline + per-project override resolution + edit endpoints) **+ FE** (a project-settings tuning UI), then log each change as an adjustment event. **This makes B2 XL+** (mirrors Phase B's "build the producers too" expansion). |
| **Session scope** | Stop at CLARIFY (this doc); DESIGN + AMAW review + design-checkpoint-commit in a fresh session. |

## 3 · Design direction (for next session — not final)

Three tables in **learning-service** (`loreweave_learning`, reserved in Phase B per [corrections migrate.py:11-14](../../services/learning-service/app/db/migrate.py)):
1. **`config_registry(config_hash PK, resolved_config JSONB, base_default_version, created_at)`** — content-addressed effective config (extractor model_ref + model_source + precision-filter {model,policy,categories} + entity-recovery + writer-autocreate + prompt version-hash from `_version.py` + embedding_model). N runs → 1 row. `config_hash` = stable hash of the canonicalized resolved_config (mirror the Phase-B `_stable_hash` discipline — sorted keys, hashlib not `hash()`).
2. **`extraction_runs(run_id PK, user_id, project_id, book_id, scope/chapter_ref, config_hash → registry, model_ref, metrics JSONB, outcome, outcome_source, ts)`** — emitted at job/chapter completion. `corrections.source_extraction_run_id` is the forward FK already reserved. metrics = the per-item `Pass2WriteResult` counts (currently discarded after logging — must thread an accumulator through the worker-ai loop) + latency + cost. outcome implicit-derivable.
3. **`config_adjustment_events(id, user_id, project_id, actor, base_default_version, target, op, before, after, reason?, ts)`** — append-only, **async/lossy-OK** ingest (a non-outbox Redis stream OR a direct fire-and-forget HTTP endpoint on learning-service — per plan, NOT the durable outbox). Privacy split like corrections: structural diff free, prompt *content* hashed.

**Where things slot / get built:**
- **config resolution + hash:** introduce a "resolve effective config" assembly in `pass2_orchestrator` / worker-ai `runner` that merges global defaults + per-project `extraction_config` overrides into one object + hashes it. THIS is also the unlock for per-novel tuning (the JSONB column finally drives the pipeline).
- **run emission:** worker-ai `_complete_job` (`runner.py:527`) is the emit point (job-level); per-chapter granularity needs threading config_hash + an accumulated metrics counter through the item loop (`_extract_and_persist` returns `Pass2WriteResult` — currently dropped).
- **per-novel tuning BE:** make `knowledge_projects.extraction_config` actually drive precision-filter/recovery/model/prompt-selection (per-project override of the global default) + `PATCH /projects/{id}` (or a new sub-resource) to edit it + emit a `config_adjustment_event`.
- **per-novel tuning FE:** a project-settings extraction-tuning panel (mirror the existing `ChangeModelDialog`/project-settings patterns in `frontend/src/features/knowledge`).
- **default versioning:** defaults become content-addressed templates + a semver `base_default_version`; adjustments record the version they diffed from.

**Two guardrails (plan §2.4) baked into the eventual mining, NOT this build:** popularity≠quality (every insight JOINs `outcome`, never raw change-frequency); explore/exploit + selection-bias weighting. Mining itself is Phase E2 (depends on B2 + volume) — out of B2 scope.

## 4 · Likely BUILD sub-session seam (XL+, multi-session — for the PLAN phase)
- **B2-A (foundation):** config-resolution assembly + `config_hash` + `config_registry` + `extraction_runs` emission at job completion (run plumbing, no UI). Live-smoke: run a job → an `extraction_runs` row + `config_registry` row appear.
- **B2-B (per-novel tuning BE):** `extraction_config` drives the pipeline (per-project override resolution) + edit endpoint + `config_adjustment_events` emission + the async ingest in learning-service.
- **B2-C (FE):** project extraction-tuning UI + browser smoke.

## 5 · Open questions for DESIGN
- **Run granularity:** per-job vs per-chapter `extraction_runs`? Per-chapter is the useful unit for outcome-vs-config (a job spans chapters with one config), but needs accumulator threading. Lean per-chapter; confirm.
- **Outcome derivation:** exact implicit-outcome rule (correction within N days on a run's output = "negative"; clean re-use = "positive"; re-run/discard = "rejected"). Define the join.
- **Adjustment transport:** non-outbox Redis stream vs direct HTTP fire-and-forget to learning-service. Plan leans lossy; pick at DESIGN.
- **Per-project override semantics:** which global tunables become per-project-overridable (all? a safe subset — model + filter categories + prompt-pack selection, but NOT raw prompt text at first?). Raw prompt editing = copyright/PII + injection surface; likely a later tier.
- **Privacy:** prompt content (may embed novel text) → hash + retention, mirror corrections' redact-by-default.
- The worker-ai vs knowledge-service config-singleton DUPLICATION (two parallel `_PRECISION_FILTER_CONFIG` copies) — the resolve-config refactor should unify or both must hash identically.
