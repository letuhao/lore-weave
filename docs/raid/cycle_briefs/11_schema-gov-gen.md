# Cycle 11: Schema-gov gen + H0 tag

> RAID cycle brief. Cold-start runner: read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY. No carry-over from prior cycles.

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Schema-governed generation layer for `lore-enrichment-service`: take a scaffolded/retrieval-grounded proposal (C9+C10 output) and produce game-ready, schema-validated fact records. Add a normalization-repair pass (malformed LLM output → repaired-or-rejected, never silently dropped) and the **H0 enforcement point**: stamp `origin='enriched'` (or `enriched:<technique>`) + `provenance` + `confidence<1.0` + `pending_validation=true` on EVERY emitted fact. This is the chokepoint where enriched lore is permanently marked NOT-canon before it can reach any store.
- **Acceptance gate:** `scripts/raid/verify-cycle-11.sh` exits 0 (created by this runner; forward ref is fine).
- **Top 3 LOCKED decisions consumed:** H0, Q-R1, Q2
- **DPS count:** 3
- **Estimated wall time:** 4–6 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C9, C10
- Files expected to exist (grep-able paths): `services/lore-enrichment-service/` (schema/models from C2; proposal store from C8), C9 template strategy (`strategies/template*`), C10 retrieval strategy + `cultural_grounding_ref` field populated on proposals.

## Scope (IN)
- **Generation module** (`generation/`): consumes a strategy proposal draft + retrieval context, emits a list of typed `EnrichedFact` records per the C2 proposal schema (dimensions 历史/地理/文化/features/inhabitants; output language = Chinese, source-faithful).
- **Schema-governed output**: structured-output contract (JSON schema / Pydantic) the LLM must conform to; generation is rejected if it does not validate.
- **Normalization-repair pass** (`generation/repair.py`): given malformed LLM output (missing fields, wrong types, extra prose, fenced JSON, trailing commas), deterministically repair to schema OR reject with a typed error. Game-ready normalization (canonical field shapes, trimmed/typed values). NO silent data loss.
- **H0 tagging** (`generation/provenance.py`): single chokepoint stamping EVERY fact with `origin` (`'enriched'` or `'enriched:<technique>'`), `provenance` (strategy id, technique, source refs, model ref from registry, timestamp), `confidence` (float < 1.0), `pending_validation=true`, lifecycle state `proposed`. A fact with no origin/provenance MUST be impossible to construct (enforce in constructor/factory, not by caller discipline).
- **Model/embedding refs resolved via provider-registry** (Qwen 3.6 via LM Studio, bge-m3) — never hardcoded.
- **Unit tests** + `scripts/raid/verify-cycle-11.sh` (clone `verify-cycle-template.sh`).

## Scope (OUT — explicitly)
- NO write-back to glossary/Neo4j/KG (that is C13 — write-through SSOT + quarantine + promotion). This cycle stops at producing tagged in-memory/proposal-store records.
- NO contradiction/anachronism/injection-defense checks (C12).
- NO job orchestration, Redis events, or end-to-end demo (C14).
- NO P2 fabrication / P3 re-cook (C16/C17 — behind C15 gate). P1 only.
- NO edits to `world-service`/`game-server`/`tilemap`/`infra/existing-prod/`, climate/geo eval files, or other agents' files.
- NO new RAG framework / langchain / llamaindex; reuse knowledge-service `/internal/embed` already wired in C10.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `services/lore-enrichment-service/tests/test_generation_repair.py`, `tests/test_provenance_h0.py` (and existing suite stays green) via `pytest`.
- **Unit — malformed → repaired:** a fixture of malformed LLM outputs each repairs to a schema-valid record OR raises a typed rejection (no silent drop). At least one un-repairable case asserts the reject path.
- **Unit — H0 on every fact:** property-style test over generated facts asserts EVERY record carries non-null `origin` ∈ {`enriched`, `enriched:*`}, non-empty `provenance`, `confidence` strictly `< 1.0`, `pending_validation == true`. Constructing a fact without these raises.
- **No hardcoded model names:** grep gate — model/embedding refs resolve through provider-registry, not string literals.
- Lints pass: `scripts/raid/secret-scan-cycle.sh`, `scripts/raid/prod-isolation-lint.sh` clean.
- `scripts/raid/verify-cycle-11.sh` exits 0. (Cross-service = NO → no live-smoke token required; unit + mocked embed is sufficient here.)

## DPS parallelism plan
- DPS 1: Schema-governed generation module + structured-output contract (`generation/__init__.py`, `generation/generate.py`, schema defs). Resolves model ref via registry. (return budget: 1500 tokens summary)
- DPS 2: Normalization-repair pass (`generation/repair.py`) + `tests/test_generation_repair.py` malformed-fixture corpus.
- DPS 3: H0 provenance/confidence tagging chokepoint (`generation/provenance.py`, fact factory) + `tests/test_provenance_h0.py` + `scripts/raid/verify-cycle-11.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak (highest priority):** can any code path emit a fact WITHOUT `origin`/`provenance`/`pending_validation`/`confidence<1.0`? Look for a default-constructed dataclass, a `dict` bypass, a `confidence=1.0` default, or a code path that builds facts outside the factory. H0 must be impossible to forget, not merely documented.
- **Repair silently drops data:** does the repair pass ever discard a malformed record and return success? Every malformed input must repair-or-reject explicitly. Check the un-repairable branch actually raises, not returns `None`/`[]`.
- **Hardcoded model names:** grep for `qwen`, `bge`, `gpt`, literal model strings — must come from provider-registry.
- **Scope creep into C12/C13:** any write to glossary/Neo4j/pending_facts, any contradiction/injection check, is OUT.
- **Confidence semantics:** confidence must be `<1.0` (enriched ≠ authored canon at conf 1.0). A `>=1.0` value is an H0 violation.
- **Mock-only false-green:** since this is intra-service, confirm the LLM client and embed call are seam-mocked deterministically and tests don't accidentally hit live LM Studio.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All Scope (IN) artifacts present: generation module, repair pass, H0 provenance chokepoint, tests, verify-cycle-11.sh.
- No Scope (OUT) items touched (no write-back, no C12 checks, no orchestration, no P2/P3, no forbidden dirs).
- All acceptance criteria met; `verify-cycle-11.sh` exits 0.
- Cross-cycle invariant intact: EVERY fact carries `origin='enriched'`/`enriched:*` + provenance + confidence<1.0 + pending_validation=true; no model names hardcoded.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle map + C11 row: [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md) (§ Cycles C11; § Notes H0 invariant)
- LOCKED decisions (full): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md) — H0, Q-R1, Q-R2, Q1, Q2, Q3
- Plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) · [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): H0, Q-R1, Q-R2, Q1, Q2, Q3

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1 — H0 (CORE):** enriched ≠ canon. EVERY fact this cycle emits MUST carry `origin='enriched'`/`enriched:<technique>` + `provenance` + `confidence<1.0` + `pending_validation=true`, state `proposed`. This cycle IS the H0 enforcement point — make it impossible to construct an untagged fact.
- 🔴 **Top LOCKED 2 — Q-R1:** all code lives in the isolated `lore-enrichment-service` (Python/FastAPI, own DB `loreweave_lore_enrichment`); do not reach into other services.
- 🔴 **Top LOCKED 3 — Q2 / no hardcoded models:** generation stops BEFORE any write-back; model/embedding refs (Qwen 3.6 via LM Studio, bge-m3) resolve via provider-registry, never hardcoded.
- 🔴 **Acceptance MUST include:** unit proves malformed→repaired-or-typed-reject (no silent drop) AND every fact carries origin/provenance/confidence<1.0; `scripts/raid/verify-cycle-11.sh` exits 0.
- 🔴 **Do NOT touch:** no glossary/Neo4j/KG write-back (C13), no contradiction/injection check (C12), no orchestration (C14), no P2/P3, no `world-service`/`game-server`/`infra/existing-prod/`/climate-geo eval files.
- 🔴 **Fresh session reminder:** this is a new `/raid 11` invocation; no carry-over. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
