# Cycle 6: Gap MODEL spec (M1a)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Define the gap **MODEL** (data spec, NOT the engine) per entity-kind for lore-enrichment. DEMO anchors on entity-kind = `LOCATION`: the dimension set is `历史` (history), `地理` (geography), `文化` (culture), `features`, `inhabitants`. A **gap** = a canon-mentioned LOCATION that is missing one or more of these dimensions. Also define a **ranking model** (deterministic score that orders gaps). Deliver the spec doc + machine-readable schema + **gap fixtures for the 4 locked LOCATIONs** (玉虛宮, 碧遊宮/金鰲島, 蓬萊, 陳塘關) BEFORE the gap-detection engine (C7) is built. Fixture-first so C7 has expected-output to test against.
- **Acceptance gate:** `scripts/raid/verify-cycle-6.sh` exits 0 (created by this cycle's runner).
- **Top 3 LOCKED decisions consumed:** DEMO-LOCATIONS (4 places + 5 dims), Q-R2 (P1-only model), Execution (Chinese output, model-refs via provider-registry).
- **DPS count:** 3
- **Estimated wall time:** 2–3 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C1, C2
- Files expected to exist (grep-able paths): `services/lore-enrichment-service/` skeleton (from C1), enrichment DB migration baseline + proposal/provenance schema (from C2). The gap model spec references the entity/proposal shapes those cycles establish; do NOT redefine them here.

## Scope (IN)
- **Gap model spec doc** — `services/lore-enrichment-service/docs/gap_model.md`: defines `EntityKind` (demo = `LOCATION`), the per-kind `Dimension` set, the definition of a "gap" (canon-mentioned entity missing ≥1 required dimension), and the ranking formula. Each dimension carries: id (`history`/`geography`/`culture`/`features`/`inhabitants`), Chinese label (`历史`/`地理`/`文化`/`features`/`inhabitants`), required-vs-optional flag, expected payload shape.
- **Machine-readable model** — `services/lore-enrichment-service/app/gaps/model.py` (or equivalent): typed `EntityKind`, `Dimension`, `Gap`, `GapRanking` Pydantic/dataclass definitions. Pure data + a deterministic `rank_score(gap) -> float` function. NO graph reads, NO LLM calls, NO DB I/O — that is C7's engine.
- **Ranking model** — deterministic score combining: # missing required dimensions, canon-mention salience (how often the place is referenced), and a fixed dimension-weight table. Documented + unit-tested; same input always yields same score.
- **Gap fixtures for the 4 locked LOCATIONs** — `services/lore-enrichment-service/tests/fixtures/gaps_fengshen.json` (or `.py`): for each of 玉虛宮, 碧遊宮/金鰲島, 蓬萊, 陳塘關, the entity stub + which of the 5 dimensions are present/missing + the expected ranked-gap entry. These are the golden expected-outputs C7's engine must reproduce.
- **Unit tests** — `services/lore-enrichment-service/tests/test_gap_model.py`: schema validation, ranking determinism/ordering on the 4 fixtures, dimension-completeness logic (present vs missing).
- **verify script** — `scripts/raid/verify-cycle-6.sh`: runs the unit suite + asserts the 4 fixtures + spec doc exist.

## Scope (OUT — explicitly)
- **The gap-detection ENGINE** (graph-stats traversal, template matching, producing the live ranked list from a real KG) — that is C7. This cycle ships only the model + fixtures the engine will consume.
- **Any enrichment strategy / generation** (template/retrieval/fabrication) — C8–C11.
- **Writing to glossary SSOT, Neo4j, or knowledge-service** — no write-back path here (Q2). Model is pure in-memory data.
- **`source_type`/`origin='enriched'` tagging & quarantine** (H0) — belongs to generation/write-back (C11/C13); the gap model describes what's MISSING, it does not emit proposals.
- **Other entity-kinds** (CHARACTER, ITEM, FACTION). Define the `EntityKind` enum as extensible, but only `LOCATION` is fleshed out for the demo. Do NOT speculatively model other kinds.
- **Embeddings / retrieval** (knowledge-service `/internal/embed`) — that is C10.
- **world-service / game-server / tilemap / infra/existing-prod/** — never touched.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `pytest services/lore-enrichment-service/tests/test_gap_model.py` — all green.
- Ranking determinism: a test asserts `rank_score` is stable across repeated calls AND the 4 locked fixtures produce a fixed, documented ordering.
- Fixtures complete: all 4 locked LOCATIONs (玉虛宮, 碧遊宮/金鰲島, 蓬萊, 陳塘關) present in the fixture file, each with the 5 dimensions classified present/missing.
- Lints pass: `ruff check services/lore-enrichment-service/app/gaps/ services/lore-enrichment-service/tests/`.
- Spec doc exists and lists all 5 demo dimensions with Chinese labels + the gap definition + the ranking formula.
- `scripts/raid/verify-cycle-6.sh` exits 0.
- **Cross-service:** NONE. This cycle is single-service (lore-enrichment only), pure data model — no live-smoke token required.

## DPS parallelism plan
- **DPS 1: Spec + schema** — author `docs/gap_model.md` + `app/gaps/model.py` (EntityKind/Dimension/Gap/GapRanking types, dimension table). (return budget: 1500 tokens summary)
- **DPS 2: Ranking + tests** — implement `rank_score()` + `test_gap_model.py` (determinism, ordering, completeness). Depends on DPS 1 types.
- **DPS 3: Fixtures + verify** — build `gaps_fengshen.json` for the 4 locked LOCATIONs (sourced from canon mentions, classify each dimension present/missing) + author `scripts/raid/verify-cycle-6.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Scope creep into the engine (C7):** does `model.py` stay pure data? Any graph traversal, DB query, KG read, or LLM call here is a boundary violation — flag it.
- **H0 leak:** confirm the gap model emits NO proposals and carries NO `source_type='enriched'`/canon tagging — it only describes absence. A gap is not enriched content.
- **Ranking non-determinism:** any use of dict ordering, set iteration, floats compared by `==`, `random`, or wall-clock in `rank_score` → non-reproducible scores. Verify the formula + weight table are fixed and documented, and the test actually pins the ordering.
- **Fixture correctness vs canon:** the 4 locked LOCATIONs' present/missing dimension flags must be defensible from 封神演义 canon (these are *under-described* places — most dimensions SHOULD read as missing; if a fixture marks everything present the gap set is empty and the demo is hollow).
- **Hardcoded model names:** there should be NO model name anywhere (this cycle has no LLM call); if one appears, it is wrong — model-refs resolve via provider-registry only.
- **Chinese labels:** dimension labels 历史/地理/文化 must be the actual Chinese strings (source-faithful), not romanized; `features`/`inhabitants` are intentionally English per the locked dimension set.
- **Extensibility vs over-engineering:** `EntityKind` extensible but ONLY `LOCATION` modeled — flag speculative CHARACTER/ITEM scaffolding.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present: spec doc, `model.py`, `rank_score`, 4-LOCATION fixtures, unit tests, verify script.
- No OUT items touched: no engine logic, no glossary/Neo4j/knowledge-service writes, no generation, no other services.
- All acceptance criteria met: tests green, ranking deterministic + ordering pinned, 4 fixtures complete, `verify-cycle-6.sh` exits 0.
- Cross-cycle invariants not violated: pure data model (no I/O), no H0/enriched tagging, no hardcoded model names, isolation respected.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C6 row + parallelism map): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- Locked decisions (full list): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md)
- Service/module plan: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md)
- Ground truth (entity/dimension framing): [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): DEMO-LOCATIONS (4 places + 5 dims 历史/地理/文化/features/inhabitants), Q-R2 (4 techniques pluggable, P1-only now), Q4 (enrichment feeds extractive machinery), Q5 (schema isolated from mmo-rpg), Execution (Chinese output, model-refs via provider-registry).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1 — DEMO-LOCATIONS:** demo entity-kind = `LOCATION`; dimensions are exactly `历史/地理/文化/features/inhabitants`; fixtures cover exactly the 4 locked places 玉虛宮, 碧遊宮/金鰲島, 蓬萊, 陳塘關. Do not add/drop dimensions or places.
- 🔴 **Top LOCKED 2 — H0 (no canon leak):** the gap model describes ABSENCE only; it emits NO proposals, NO content, and NO `source_type`. Enriched-as-canon tagging belongs to C11/C13, not here.
- 🔴 **Top LOCKED 3 — Execution (no hardcoded models):** this cycle has zero LLM calls; if any model name (Qwen/bge-m3/etc.) appears it is a bug — model-refs resolve via provider-registry only. Output labels are Chinese (source-faithful).
- 🔴 **Acceptance MUST include:** ranking is **deterministic** AND the 4-fixture ordering is pinned in a test; the spec doc + all 4 fixtures must exist; `scripts/raid/verify-cycle-6.sh` exits 0.
- 🔴 **Do NOT touch:** the gap-detection ENGINE (C7), any strategy/generation (C8–C11), glossary/Neo4j/knowledge-service write-back (Q2), world-service/game-server/tilemap, infra/existing-prod/. Keep `model.py` pure data — no graph reads, no DB, no embeddings.
- 🔴 **Fresh session reminder:** this is a new `/raid 6` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
