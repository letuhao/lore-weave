# Cycle 9: Strategy (a) template

## 🎯 TL;DR (30 seconds — TOP critical info)
Build the **first of the 4 enrichment techniques (Q-R2 P1): template scaffolding**. A `TemplateStrategy` plugs into the C8 strategy registry, consumes a typed `Gap` (from C7), and emits an **entity-kind dimension scaffold** — a structured, un-filled proposal skeleton keyed on the LOCATION dimension set (历史/地理/文化/features/inhabitants) defined in C6. NO content generation, NO retrieval, NO LLM call yet — this cycle only scaffolds the proposal shape that later cycles (C10 retrieval, C11 generation) fill.
- **First technique of the phased P1 rollout** (template → retrieval). Lowest cost/effort tier; ships before any LLM-backed work.
- **Output language = Chinese**: scaffold dimension labels/keys are the Chinese dimension names; placeholders are empty, NOT English stubs.
- **H0 invariant**: every scaffolded proposal is born `origin='enriched'`, `review_status='proposed'`, `confidence<1.0`, quarantined. NEVER canon.
- **Acceptance gate:** `scripts/raid/verify-cycle-9.sh` exits 0 (created by this cycle's runner) — proves `gap → scaffolded proposal` unit path is green.

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C7, C8
- C7 (Gap-detection engine) provides the typed ranked `Gap` list this strategy consumes.
- C8 (Strategy core) provides the `EnrichmentStrategy` interface, registry, feature-flags, per-job cost guardrail, and job state machine this strategy registers into.
- Transitive (already DONE via C7/C8): C6 gap MODEL / dimension set, C2 data model + H0 proposal columns, C3 API contract.

## Scope (IN)
- `TemplateStrategy` implementing the `EnrichmentStrategy` interface from C8 (`estimate`, `generate`/`scaffold` per the C8 contract); registered in the C8 registry under a `template` technique id.
- Entity-kind → dimension scaffold map. Demo anchor = **LOCATION**: dimensions 历史 / 地理 / 文化 / features / inhabitants (the C6 set). Map is data-driven (reads the C6 gap-model spec/fixtures), not hardcoded per-place.
- Transform a `Gap` (entity + missing dimensions) into an `enrichment_proposal` skeleton: one structured slot per missing dimension, empty placeholder values, dimension keys in Chinese.
- H0 stamping at construction: `origin='enriched'`, `technique='template'`, `review_status='proposed'`, `confidence<1.0`, `pending_validation=true`, `provenance_json` noting the template technique + source gap id. Per-user/per-project scope (Q3) carried through from the gap.
- Feature-flag gating via C8 so the strategy can be enabled/disabled per job.
- Unit tests: known `Gap` fixture (for a locked demo place, e.g. 玉虛宮) → expected scaffolded proposal with the right dimension slots, all H0 fields set, scope preserved.
- `scripts/raid/verify-cycle-9.sh` running the unit slice and exiting 0.

## Scope (OUT — explicitly)
- **NO content generation / LLM call** — scaffolds are empty; filling them is C11 (and retrieval-grounding is C10). Do not call Qwen here.
- **NO retrieval** — `source_corpus` / `cultural_grounding_ref` population is C10.
- **NO canon-verify** (contradiction/anachronism) — that is C12.
- **NO write-back to glossary/KG, NO promotion** — that is C13. This cycle produces an in-memory/persisted proposal only; nothing leaves the enrichment service.
- **NO new migrations** — reuse the C2 `enrichment_proposal` schema as-is. If a column is missing, STOP and escalate (do not silently add one here).
- **NO P2/P3 techniques** (fabrication/recook = C16/C17, behind the C15 gate).
- **NO edits** to world-service / game-server / glossary / knowledge-service / climate-geo eval files / `infra/existing-prod/`.

## Acceptance criteria (CI gates — exit code 0 = pass)
- `scripts/raid/verify-cycle-9.sh` exits 0.
- Unit: a `Gap` fixture for a locked demo LOCATION (历史/地理/文化/features/inhabitants missing) → strategy returns a scaffolded proposal with exactly one slot per missing dimension; dimension keys are the Chinese names.
- Unit: every scaffolded proposal carries H0 fields — `origin='enriched'`, `technique='template'`, `review_status='proposed'`, `confidence<1.0`, `pending_validation=true`; assert no proposal is ever stamped `source_type='glossary'` / confidence=1.0.
- Unit: per-user/per-project scope (Q3) on the input gap is preserved on the output proposal.
- Unit: strategy resolves through the C8 registry by `template` technique id and respects the feature-flag (disabled flag → not selectable).
- Service unit suite green; lint/type-check clean.
- Cross-service: **N/A** — single service (lore-enrichment-service). No live-smoke token required for this cycle.

## DPS parallelism plan
Low DPS (2–3), per locked cost posture. Single service, single new module — limited fan-out. Suggested split:
- **DPS-1 (lead):** `TemplateStrategy` class + registry registration + entity-kind→dimension scaffold map + H0 stamping.
- **DPS-2:** unit fixtures (load/derive from C6 locked-place fixtures) + unit tests + `scripts/raid/verify-cycle-9.sh`.
Merge point: DPS-2 tests must run green against DPS-1 implementation before VERIFY. Serialize if only 2 workers available; the scaffold-map and the tests share the dimension-key source of truth (C6), so coordinate that constant first.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
Hunt for, in priority order:
1. **H0 leak** — any path where a scaffolded proposal could be born without `origin='enriched'` / with `confidence=1.0` / as `source_type='glossary'`. Default-field omission is the classic failure. Assert the negative.
2. **Hardcoded model/technique drift** — no LLM call should exist here at all; if one snuck in, it is scope creep AND a hardcoded-model-name risk. Flag any `qwen`/model literal.
3. **Hardcoded dimension set** — dimension keys must derive from the C6 gap-model spec, not be copy-pasted English/Chinese literals that drift from C6. Check the single-source-of-truth.
4. **Chinese-output violation** — placeholders/keys in English instead of source-faithful Chinese.
5. **Scope creep** — retrieval, generation, verify, or write-back logic appearing here (belongs to C10/C11/C12/C13).
6. **Registry/feature-flag bypass** — strategy instantiated directly rather than via the C8 registry, or ignoring the disable flag.
7. **Scope-field loss** — per-user/per-project scope dropped between gap and proposal.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR only if ALL hold:
- Diff touches ONLY lore-enrichment-service files + `scripts/raid/verify-cycle-9.sh` + test fixtures. Zero edits to glossary/knowledge-service/world-service/game-server/climate-geo eval/infra-existing-prod.
- No new DB migration; no LLM/retrieval/write-back code.
- Every constructed proposal stamped H0 (`origin='enriched'`, `confidence<1.0`, `review_status='proposed'`).
- `scripts/raid/verify-cycle-9.sh` present and exits 0.
Otherwise BLOCKED with the one-line reason.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- C9 row + dependency graph: `docs/plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md`
- Locked decisions (H0, Q-R2 phased techniques, Q3 scoping, Chinese output, isolation): `docs/plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md`
- Plan + ground truth: `docs/03_planning/lore-enrichment/PLAN.md` · `docs/03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md`

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **H0 (CORE):** every scaffolded proposal is born `origin='enriched'`, `technique='template'`, `review_status='proposed'`, `confidence<1.0`, quarantined — NEVER `source_type='glossary'` / confidence=1.0. Only the author's later PROMOTE (C13) canonizes. Assert the negative in tests.
- 🔴 **Q-R2 P1 scope-lock:** this is template scaffolding ONLY — NO LLM call, NO retrieval, NO generation, NO write-back. Filling/grounding/verifying belong to C10/C11/C12; promotion to C13. Empty Chinese-keyed dimension slots only.
- 🔴 **Acceptance gate:** `scripts/raid/verify-cycle-9.sh` exits 0 — `Gap → scaffolded proposal` unit path green, H0 fields asserted, scope preserved, registry/flag respected.
- 🔴 **Do-not-touch:** no migrations, no model-name literals (provider-registry resolves models — and nothing here even calls one), no edits to glossary/knowledge-service/world-service/game-server/climate-geo eval/infra-existing-prod. Dimension set derives from C6, not hardcoded.
