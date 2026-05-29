# Cycle 8: Strategy core

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Build the `EnrichmentStrategy` interface + a strategy **registry** (lookup/select by technique key), **feature-flags** that gate which techniques are active (P1 `template`+`retrieval` only), a **per-job cost guardrail** (estimate → enforce cap → pause when exceeded), and the **job state machine** (estimate/start/pause/resume/cancel) over the `enrichment_job` rows from C2. Pure in-service Python/FastAPI scaffolding in `lore-enrichment-service`; no real strategy bodies, no LLM calls yet.
- **Acceptance gate:** `scripts/raid/verify-cycle-8.sh` exits 0
- **Top 3 LOCKED decisions consumed:** Q-R1, Q-R2, H0
- **DPS count:** 3
- **Estimated wall time:** 3-4 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C2, C3
- Files expected to exist (grep-able paths): migrations for `enrichment_job` + lifecycle columns (C2); `contracts/api/lore-enrichment/` OpenAPI + stub job/proposal handlers (C3) inside `services/lore-enrichment-service/`.

## Scope (IN)
- `EnrichmentStrategy` ABC/Protocol: `key` (e.g. `template`, `retrieval`, `fabrication`, `recook`), `tier` (P1/P2/P3), `estimate_cost(gap_batch) -> CostEstimate`, `run(...)` (signature only — bodies land in C9/C10/C16/C17).
- **Registry**: register-by-key, `select(key)`, `list_active()` filtered by feature-flags; raises on unknown/inactive key.
- **Feature-flags**: config-driven enable map; default ACTIVE = `template`, `retrieval` (P1). `fabrication`/`recook` registered but **INACTIVE** until C15/C16/C17 gate.
- **Per-job cost guardrail**: accumulate spend against a per-job cap; `would_exceed()` check before each unit; when projected spend > cap → transition job to `paused` (cost_cap reason). Conservative defaults.
- **Job state machine**: states `estimated → running ⇄ paused → (completed|cancelled)` with explicit `estimate/start/pause/resume/cancel` transitions; illegal transitions raise; persists state to `enrichment_job` (C2 schema).
- Unit tests: registry select (active vs inactive vs unknown) + cost-cap-triggered pause.

## Scope (OUT — explicitly)
- NO real strategy implementations (template scaffolds → C9, retrieval/embed → C10).
- NO LLM or embedding calls; NO model-name strings anywhere (resolved later via provider-registry).
- NO Redis Streams job runner / end-to-end orchestration (→ C14); state machine here is in-process only.
- NO new DB migrations (reuse C2 tables); NO contract changes (reuse C3 spec).
- NO write-back to glossary/KG, NO proposal review/promote logic (→ C11/C13).
- NEVER touch world-service / game-server / tilemap / `infra/existing-prod/`, nor knowledge-service or glossary code.
- NO eval-framework edits (climate/geo files untouched).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `services/lore-enrichment-service/tests/test_strategy_registry.py` (active/inactive/unknown select) and `.../tests/test_cost_guardrail.py` (cap breach → `paused`) and `.../tests/test_job_state_machine.py` (legal transitions + illegal-raise).
- Lints pass: ruff/black/mypy clean on changed files in `services/lore-enrichment-service/`.
- Integration smoke: in-process — register P1 strategies, select one, feed a cost batch that overruns the cap, assert job lands in `paused`; assert inactive technique not selectable. No live cross-service call required (this cycle is single-service; no live-smoke token needed).

## DPS parallelism plan
- DPS 1: Strategy interface + registry + feature-flags — `app/strategies/base.py`, `app/strategies/registry.py`, `app/config/feature_flags.py` + `tests/test_strategy_registry.py`. (return budget: 1500 tokens summary)
- DPS 2: Job state machine — `app/jobs/state_machine.py` (transitions, persistence to C2 `enrichment_job`) + `tests/test_job_state_machine.py`.
- DPS 3: Cost guardrail — `app/jobs/cost_guardrail.py` (`CostEstimate`, accumulator, `would_exceed`, pause hook into state machine) + `tests/test_cost_guardrail.py`. Depends on DPS 2's pause transition; integrate last.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Feature-flag bypass:** confirm an INACTIVE technique (`fabrication`/`recook`) truly cannot be selected/run — registry must not leak it via `list_active()` or `select()`. P2/P3 must stay dark until the C15 gate.
- **Cost-cap off-by-one:** is the cap checked BEFORE incurring the next unit (projected) or only after? It must pause before exceeding, not report overrun retroactively. Verify boundary equality (spend == cap) behavior is defined and tested.
- **State-machine integrity:** every illegal transition raises (e.g. resume-from-completed, start-from-cancelled). No silent no-ops. Persisted state matches in-memory state.
- **Hardcoded model names / secrets:** grep the diff — any model string or provider URL is a violation; strategy bodies are deferred precisely to avoid this here.
- **H0 leakage:** ensure nothing in this cycle marks output as canon or sets confidence=1.0; strategies only produce *proposals* later — no `source_type='glossary'` paths introduced.
- **Scope creep:** no Redis runner, no real strategy logic, no migrations — flag any of these.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present: strategy interface, registry, feature-flags, cost guardrail, job state machine, the three unit suites.
- No OUT items touched (no LLM/embed calls, no migrations, no contract edits, no glossary/KG/world-service/infra-prod changes, no eval edits).
- All acceptance criteria met (`verify-cycle-8.sh` exits 0; lints clean).
- Cross-cycle invariants intact: P2/P3 inactive; no model names hardcoded; cost-cap pauses before overrun.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C8 row + C2/C3 deps): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- Locked decisions: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md) — Q-R1, Q-R2, H0
- Parent plan: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) and [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): Q-R1 (separate service + own DB), Q-R2 (4 pluggable strategies, phased P1→P2→P3, cost-cap + quality-gate promote), H0 (enriched != canon; proposals only).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1 — Q-R2:** 4 techniques are pluggable strategies; only P1 `template`+`retrieval` ACTIVE now. `fabrication`/`recook` register but stay INACTIVE behind feature-flags until the C15 cost/quality gate.
- 🔴 **Top LOCKED 2 — Q-R1:** All code lives in the separate `lore-enrichment-service` (Python/FastAPI, DB `loreweave_lore_enrichment`). Do NOT edit other services.
- 🔴 **Top LOCKED 3 — H0:** This cycle produces NO canon. Strategies emit *proposals* later; never set `source_type='glossary'` or confidence=1.0 here.
- 🔴 **Acceptance MUST include:** the cost-cap-pause unit test — registry select alone is NOT enough; the easiest-to-forget gate is "cap breach → job `paused`".
- 🔴 **Do NOT touch:** no migrations (reuse C2), no contract edits (reuse C3), no LLM/embed calls, no hardcoded model names, no glossary/KG/world-service/game-server/`infra/existing-prod/`, no eval files.
- 🔴 **Fresh session reminder:** this is a new `/raid 8` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
