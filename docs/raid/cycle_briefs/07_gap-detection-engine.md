# Cycle 7: Gap-detection engine (M1b)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Build the gap-detection engine (M1b) — a deterministic, pure-Python component that consumes the gap-MODEL spec + fixtures from C6, reads KG **graph-stats** through the C1 `KnowledgeReadPort`, joins against `enrichment_template` dimension definitions, and emits a **typed, ranked `Gap` list**. For the demo, gaps anchor on entity-kind = LOCATION and the 5 dimensions 历史/地理/文化/features/inhabitants. A gap = a canon-mentioned location missing one of these dimensions; ranking orders gaps by the C6 ranking rule (e.g. canon-mention-count × missing-dimension severity). This cycle is **engine + unit tests only** — no LLM calls, no DB writes, no strategy execution.
- **Acceptance gate:** `scripts/raid/verify-cycle-7.sh` exits 0
- **Top 3 LOCKED decisions consumed:** Demo-scope (LOCATION-anchored, 4 places), Q6 (thin KG-read port + graceful degradation), No-hardcoded-model-names (engine stays LLM-free)
- **DPS count:** 2
- **Estimated wall time:** 2–3 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C6
- Files expected to exist (grep-able paths):
  - `services/lore-enrichment-service/app/` (C0 skeleton)
  - C6 gap-model spec + fixtures (gap dimensions for LOCATION, ranking rule, locked 4-place fixtures 玉虛宮 / 碧遊宮·金鰲島 / 蓬萊 / 陳塘關 with expected gaps)
  - `app/clients/` + `KnowledgeReadPort` Protocol from C1 (graph-stats read)
  - `enrichment_template` model/migration from C2 (dimension definitions)

## Scope (IN)
- `app/gap/engine.py` — `GapDetectionEngine` that takes (KG graph-stats for an entity, the entity-kind dimension set from `enrichment_template`, the C6 gap-model) and returns a list of typed `Gap` objects.
- `app/gap/models.py` — typed `Gap` dataclass/Pydantic: `entity_id`, `entity_kind`, `dimension` (历史/地理/文化/features/inhabitants), `severity`, `rank`, `evidence` (why it's a gap — e.g. dimension absent in graph-stats), `score`.
- Ranking function: deterministic ordering implementing the C6 ranking rule (stable tie-break so output is reproducible across runs).
- Consume `KnowledgeReadPort` (C1) for graph-stats; tolerate Null/degraded port (return empty/partial gap list, never crash — Q6 graceful degradation).
- Unit tests `tests/test_gap_engine.py`: load the C6 KG fixture → assert the engine returns the **expected ranked gaps** (exact dimensions + exact order) for the locked LOCATION fixtures.
- `scripts/raid/verify-cycle-7.sh` running the unit suite + import check.

## Scope (OUT — explicitly)
- NO LLM / generation calls — this cycle does not enrich, scaffold, or write proposals (that is C9 strategy-template onward).
- NO DB writes, no migrations (C2 owns schema; engine only READS template definitions as plain data/fixtures).
- NO real knowledge-service network call / live-smoke — engine runs against the C6 fixture and the C1 port abstraction (mock/Null impl). Cross-service wiring lives in C1/C14.
- NO changes to the gap-model spec or dimension set (owned by C6) — consume it as-is; if it's wrong, escalate, don't patch here.
- NO edits to `world-service` / `game-server` / `tilemap` / `infra/existing-prod/`, and NO edits to climate/geo eval files.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `pytest services/lore-enrichment-service/tests/test_gap_engine.py` — known C6 KG fixture → expected ranked `Gap` list (dimensions + order match exactly).
- Determinism test: running the engine twice on the same fixture yields byte-identical ranked output (stable sort / tie-break).
- Degradation test: Null/empty graph-stats port → engine returns `[]` (or documented partial) without raising.
- Lints pass: `ruff` + `mypy` (or project equivalent) clean on `app/gap/`.
- `scripts/raid/verify-cycle-7.sh` exits 0 (orchestrates the above).
- (Not a cross-service cycle — no live-smoke token required; the C1 port is exercised via its Null/mock impl.)

## DPS parallelism plan
- DPS 1: Engine + types — `app/gap/models.py` + `app/gap/engine.py` (typed `Gap`, dimension-presence detection over graph-stats, ranking function with stable tie-break, graceful degradation on Null port). (return budget: 1500 tokens summary)
- DPS 2: Tests + verify script — `tests/test_gap_engine.py` (load C6 fixture, assert exact ranked gaps for the 4 locked places, determinism + degradation cases) + `scripts/raid/verify-cycle-7.sh`. (return budget: 1500 tokens summary)
- Sync point: DPS 2 imports the typed `Gap` + engine entrypoint signature from DPS 1; agree the signature `detect_gaps(entity_stats, dimension_set, model) -> list[Gap]` up front so the slices integrate cleanly.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Ranking non-determinism:** is the sort stable with an explicit tie-break? Python `sorted` on equal scores must not depend on dict/iteration order. A flaky rank order is the most likely silent failure here.
- **Test is a tautology:** does the unit test assert against a hand-computed expected ranked list, or did the author copy engine output into the fixture? The expected gaps for the 4 locked places must be independently derivable from the C6 model, not reverse-engineered from the engine.
- **Graceful degradation real?** Confirm Null/empty graph-stats truly returns `[]`/partial and never throws — Q6 invariant. Check for `None` deref on missing dimensions.
- **Scope creep into generation:** verify NO LLM call, NO model-name string, NO proposal/DB write leaked in (those belong to C9+/C11). Any hardcoded model id is an instant flag.
- **Dimension drift:** engine must use exactly the C6/template dimension set (历史/地理/文化/features/inhabitants) — not an invented or hardcoded list that could diverge from the spec.
- **Pitfall:** off-by-one or inverted severity (a location missing MORE dimensions / with MORE canon-mentions should rank higher) — verify ranking direction matches the C6 rule.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (engine, typed `Gap`, ranking, degradation, unit tests, verify script).
- No OUT items touched (no LLM, no DB write, no live-smoke, no edits to gap-model/world-service/game-server/eval-climate-geo).
- All acceptance criteria met (fixture→expected ranked gaps, determinism, degradation, lints, verify exits 0).
- Cross-cycle invariants intact: engine is LLM-free + DB-write-free; consumes C6 model + C1 port as-given.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C7 row + parallelism + isolation notes): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- Locked decisions (demo LOCATION scope, Q6 KG-read port, H0, execution decisions): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md)
- Module plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) · [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): Demo-scope (LOCATION-anchored gap, 4 locked places, dimensions 历史/地理/文化/features/inhabitants), Q6 (thin KG-read port + graceful degradation), Q3 (per-user/per-project scoping carried on entity ids), No-hardcoded-model-names (engine stays LLM-free).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1 — Demo scope:** gaps anchor on entity-kind = LOCATION; dimensions are EXACTLY 历史/地理/文化/features/inhabitants; expected ranked gaps cover the 4 locked places (玉虛宮, 碧遊宮·金鰲島, 蓬萊, 陳塘關). Do not generalize beyond LOCATION here.
- 🔴 **Top LOCKED 2 — Q6 graceful degradation:** consume the C1 `KnowledgeReadPort`; a Null/degraded port MUST yield `[]`/partial, never a crash.
- 🔴 **Top LOCKED 3 — No-hardcoded-model-names / LLM-free engine:** this is a deterministic engine — NO LLM calls, NO model-name strings. Generation starts at C9.
- 🔴 **Acceptance MUST include:** `scripts/raid/verify-cycle-7.sh` exits 0 — known C6 KG fixture → EXACT expected ranked `Gap` list, plus a determinism (stable-sort) assertion. This is the single easiest gate to under-test.
- 🔴 **Do NOT touch:** the C6 gap-model/dimension set (consume as-given — escalate if wrong), C2 schema (no migrations/writes), world-service/game-server/tilemap/infra/existing-prod, and climate/geo eval files.
- 🔴 **Fresh session reminder:** this is a new `/raid 7` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
