# Knowledge model-roles settings surface + default fallback (2026-07-03)

**Goal (user):** every knowledge model ROLE gets a GUI setting, and a single
**default model** is used for any LLM role left unset. Today embedding + rerank
are settable and persisted; the extraction LLM is only chosen at build time and
`entity_recovery` is env-only with no GUI at all.

**Origin:** user review of the knowledge GUI after the `cancel_check` extraction
fix (`591e54ad7`). Sits after #1 (cancel_check) + #2 (detail-view edit pen,
`652899564`).

## Current state (verified against code)

| Role | Storage today | GUI today |
|---|---|---|
| Embedding | `knowledge_projects.embedding_model` (column) | ✅ ProjectFormModal / ChangeModelDialog / BuildGraph |
| Rerank | `knowledge_projects.rerank_model` (column) + `extraction_config.rerank_model` | ✅ ProjectFormModal |
| Extraction LLM | `extraction_config.llm_model` (JSON) — also passed at dispatch as `llm_model` | ⚠️ build-time only (BuildGraphDialog); Rebuild reuses prior |
| Precision-filter LLM | `extraction_config.precision_filter` (JSON, per-project — env deliberately dropped, see `D-WX-PRECISION-FILTER-MODEL-ARCH`) | ✅ ExtractionTuningPanel |
| Entity-recovery classifier | **ENV only** (`KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF`) — `extraction_config.entity_recovery` is a listed target but `_load_entity_recovery_config()` reads `os.environ` | ❌ none |
| Summarize LLM | ephemeral per-regen | ⚠️ global-bio only (RegenerateBioDialog) |

Key facts that make this tractable:
- `extraction_config` is a **JSON column** already carrying `llm_model`,
  `precision_filter`, `entity_recovery`, `writer_autocreate`, `rerank_model`.
  **No schema migration needed** — the slots exist.
- `precision_filter` is the **reference pattern**: per-project override object
  (`{enabled, model_ref, model_source, categories, partial_policy}`), FE-set via
  `PUT /projects/{id}/extraction-config`, resolved per-user. `entity_recovery`
  just needs the same treatment (it currently reads env — the same cross-tenant
  smell `D-WX` fixed for precision_filter).

## Design — user-global default + project default + per-role overrides (LOCKED)

**PO decision 2026-07-03: "both" — a user-global default AND a per-project
default, roles override either.** "1 default model" resolves through a chain so
setting it ONCE (user-global) covers every project, while a project or a role can
still override.

**Resolution precedence (per role, per call) — highest wins:**
1. the role's explicit override (`extraction_config.<role>.model_ref/source`)
2. else the **project** default `extraction_config.llm_model` (+ its source)
3. else the **user-global** default — `user_default_models` in provider-registry
   for the `chat` capability, resolved via an `/internal/*` route (BYOK,
   per-user; NEVER a platform env model — provider-gateway + no-hardcoded-model
   invariants). This is the "set once, used everywhere" tier.
4. else (legacy) the role's env var — back-compat floor so existing ops overrides
   don't break; logged as deprecated
5. else the role is **off** (recovery/precision are optional; extraction itself
   still requires a model — dispatch already 400s "model_ref required")

Storage tiers:
- user-global: `provider-registry.user_default_models` (capability=`chat`) — the
  restore-a-removed-knob-as-BYOK-default pattern (`default-model-per-capability-byok`).
- per-project: `knowledge_projects.extraction_config.llm_model` (JSON — exists).
- per-role: `extraction_config.<role>` override object (JSON — precision exists).

A tiny pure resolver `resolve_role_model(config, role) -> (source, ref) | None`
centralizes 1→4 so pass2 + summarize + dispatch all agree. Unit-tested for each
precedence rung (the recurring `nil-tolerant-wrapper-needs-wiring-test` lesson:
a dropped fallback must fail a test, not silently no-op).

### Slice A (BE foundation) — resolver + entity_recovery per-project

- Add `resolve_role_model(extraction_config, role, *, env_fallback)` in a small
  `app/extraction/model_roles.py`. Roles: `extraction`, `precision_filter`,
  `entity_recovery`, `summarize`.
- Rewrite `_load_entity_recovery_config()` to read
  `extraction_config.entity_recovery` first (mirror precision_filter), env only
  as the deprecated floor. Thread the project's `extraction_config` into the
  call site (pass2_orchestrator already has the project).
- `summarize` resolution reads `extraction_config` default when a per-project
  regen doesn't pass an explicit model (global-bio path unchanged).
- **No behavior change when nothing is configured** (env floor + off defaults =
  byte-identical to today). Tests: precedence rungs + the entity_recovery
  env→config migration.

### Slice B (BE contract) — extraction-config accepts the role objects

- `ProjectExtractionConfigUpdate` already forbids-extra; add the
  `entity_recovery` override sub-model (mirror `PrecisionFilterOverride`:
  `{enabled, model_ref, model_source, max_items_per_batch}`) so the FE can PUT
  it. `llm_model` (default) already round-trips. Emit `config_adjusted` for the
  role targets (already listed in `_EXTRACTION_CONFIG_TARGETS`).

### Slice C (FE) — a "Models" section in the tuning panel

- Extend `ExtractionTuningPanel` (already hosts `PrecisionFilterModelPicker`)
  with a **Models** group:
  - **Default LLM** picker (`extraction_config.llm_model`) — labeled "used for
    every extraction step unless overridden below".
  - **Entity-recovery** picker (optional; empty = use default).
  - Precision-filter picker stays (already there); relabel "empty = use default".
- Each picker reuses the shared `ModelPicker` (capability=`chat`) + the
  extraction-config PUT (If-Match). Empty selection ⇒ omit the override ⇒
  resolver falls back to the default.
- Copy makes the fallback explicit so the user sees WHY a blank picker is fine.

### Slice D (verify)

- Unit: resolver precedence (BE) + tuning-panel picker wiring (FE).
- Live smoke: set a default LLM on the POC project via the tuning panel, leave
  entity_recovery blank, re-extract a chapter, confirm the recovery pass (if it
  runs) uses the default model_ref (log/DB), and a set override wins. Rebuild the
  knowledge-service image first (stale-image rule).

## Out of scope (tracked, not this effort)

- Wiki-generation LLM lives in `features/wiki` — a cross-feature picker is a
  separate task.
- A user-level (cross-project) default via `user_default_models` — the
  per-project default covers the stated need; a global default is a later add.
- Rebuild-with-model-change (Rebuild reuses prior models) — a UX add on top of
  this; once the default is persisted, Rebuild can read it instead of the prior
  job. Fast follow after Slice C.
