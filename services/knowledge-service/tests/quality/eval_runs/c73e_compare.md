# Cycle 73e — Pass2 writer Tier-A repair + Tier-B autocreate

**Goal:** close the baseline 10.7% writer-cascade gap identified in cycle 73c by:

- **Tier A.1** (free, always-on) — chapter-local canonical-name map repairs cases where relation subject/object name matches an extracted entity but IDs don't.
- **Tier A.2** (free, always-on) — anchor index pre-check; if the name matches a glossary anchor of any kind, reuse the anchor's canonical_id.
- **Tier B** (env-gated `KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED=true`) — MERGE a new `:Entity` with `kind="concept"`, `auto_created=true`, `confidence=min(rel.confidence, 0.3)`. Per-chapter cap default 20.

**Date:** 2026-05-30
**Spec / Plan:** [docs/plans/2026-05-30-pass2-writer-autocreate.md](../../../../docs/plans/2026-05-30-pass2-writer-autocreate.md)
**Driver:** [`run_c73e_writer_autocreate.py`](../run_c73e_writer_autocreate.py)
**Baseline:** [`c73b-drop-realized`](c73b-drop-realized/) (cycle 73c realized re-judge, F1=0.913)

## Cascade simulation results

Run on c73b-drop filter dump (same input as cycle 73c). Two variants:

| Variant | Autocreate | Relations kept | Cascade-skip | % skip | Tier-A endpoints repaired | Tier-B autocreated | Noise-skipped |
|---|---|---:|---:|---:|---:|---:|---:|
| **c73e-autocreate-off** | OFF (default) | 63 / 73 | 10 | 13.7% | 116 | 0 | 0 |
| **c73e-autocreate-on** | ON (cap=20) | **69 / 73** | **4** | **5.5%** | **136** | **6** | 4 |

**c73e-autocreate-on net effect:** +6 relations recovered, 4 noise-filtered (compound subjects from `little_women_ch01`). Cascade-skip drops from 13.7% → 5.5% (-8.2pp absolute, 60% relative reduction). Per-chapter detail in [`c73e-autocreate-on/c73e_run_summary.json`](c73e-autocreate-on/c73e_run_summary.json).

### Per-chapter breakdown (c73e-autocreate-on)

| Chapter | Relations orig | Relations kept | Tier-A endpoints | Tier-B autocreated | Noise-skipped | Status |
|---|---:|---:|---:|---:|---:|---|
| alice_ch01 | 8 | 8 | 16 | 0 | 0 | clean (Tier A handles all) |
| alice_ch02 | 6 | 6 | 12 | 0 | 0 | clean |
| journey_west_zh_ch01 | 9 | 9 | 16 | **2** (`仙卿`, `大海`) | 0 | both recovered |
| journey_west_zh_ch14 | 11 | 11 | 22 | 0 | 0 | clean |
| little_women_ch01 | 8 | 4 | 11 | **1** | **4** (compound) | partial — noise heuristic filtered compound subjects |
| pride_prejudice_ch01 | 6 | 6 | 12 | 0 | 0 | clean |
| sherlock_scandal_ch01 | 3 | 3 | 6 | 0 | 0 | clean |
| son_tinh_thuy_tinh_vi | 10 | 10 | 20 | 0 | 0 | clean |
| tam_cam_vi | 12 | 12 | 21 | **3** (`Bụt`, `cha Tấm`, `cung`) | 0 | all recovered |
| **TOTAL** | **73** | **69** | **136** | **6** | **4** | — |

**Tier A.1 (chapter name repair) is the workhorse — 136 endpoint repairs across 9 chapters** (about 93% of all 146 endpoints land via this free path). All relations in c73b-drop dumps have `subject_id=null` and `object_id=null` (the LLM-relation-extractor never resolved them), so every relation endpoint flows through the repair branch. Tier A.1 catches the majority because most subjects ARE in the extracted entity list; cascade-skip and Tier B autocreate only fire for the residual 6 abstract/compound/missed-by-extractor names.

**Cycle 73c's finding refined:** the cascade-skip root cause isn't "LLM extractor missed the entity but extracted the relation"; it's "the LLM-relation-extractor produces subject/object NAMES but no resolved IDs, and the writer's name-to-ID resolution (Tier A.1) catches most of them — only 6/146 endpoints in c73b-drop are truly unresolvable without a Tier-B autocreate fallback." This re-frames the "10.7% cascade gap" finding from cycle 73c: most of that gap was already structurally addressable via in-memory name match; only ~5% was true "missing entity" requiring Tier B.

### Methodology

1. Load c73b-drop filter dump (73 relations, 9 chapters)
2. Apply [`run_c73e_writer_autocreate.py`](../run_c73e_writer_autocreate.py) cascade simulation:
   - For each relation, check `subject` and `object` against entity_names_set
   - If unresolved → try Tier A.1 (fold match in chapter map)
   - If still unresolved + autocreate ON + budget OK + not noise → Tier B autocreate (mark `auto_created=true`)
   - Else cascade-skip
3. Write realized `actual.json` per variant
4. Re-judge with 3-judge ensemble (gemma + qwen-30b + claude-4.7-opus)

## Realized F1 (3-judge ensemble re-judge) — MEASURED 2026-05-30 (session 74)

**Status:** ✅ **DONE.** The prior two attempts (2026-05-30 ~10:30 + ~11:00 UTC) were killed by knowledge-service container OOM mid-ensemble. Session 74 sidestepped the blocker by running the orchestrator on **host Python** (host → provider-registry `:8208` → LM Studio `:1234`); knowledge-service is not in the re-judge path, so its OOM-killer can't reach the run. Driver: [`run_rejudge_resumable.py`](../run_rejudge_resumable.py) (persists each judge's verdicts the instant it completes — crash only loses the in-flight judge). Run completed clean in ~23 min, all 3 judges `complete`, κ=0.738 (substantial).

| Variant | gemma F1 | qwen-30b F1 | claude F1 | **3J median F1** | **2J mean (no claude)** | Fleiss κ |
|---|---:|---:|---:|---:|---:|---:|
| c70a baseline (no filter) | 0.848 | 0.955 | 0.895 | 0.895 | 0.9015 | 0.671 |
| c72c-drop realized | 0.899 | 0.965 | 0.904 | 0.904 | 0.9320 | 0.773 |
| **c73b-drop realized (current SHIP)** | **0.888** | **0.972** | **0.913** | **0.913** | **0.9300** | **0.756** |
| **c73e-autocreate-off** | _(byte-identical to c73b-drop-realized — verified via diff)_ | | | _0.913_ | _0.9300_ | _0.756_ |
| **c73e-autocreate-on** | **0.901** | **0.979** | **0.911** | **0.911** | **0.9400** | **0.738** |
| **Δ (on − SHIP)** | **+1.3pp** | **+0.7pp** | **−0.2pp** | **−0.2pp** | **+1.0pp** | **−0.018** |

**Finding — F1-NEUTRAL on the locked metric; the expected +0.3-0.6pp lift did NOT materialize.** The locked ship metric (3-judge median, per `QUALITY_EVAL_BASELINES.md`) moved **−0.2pp (0.913 → 0.911), inside the noise band**. The median is pinned to claude-4.7-opus, which was flat (−0.2pp). The other two judges DID improve (gemma +1.3pp, qwen-30b +0.7pp), so the **mean** is +0.6pp and the no-claude 2-judge subset is +1.0pp — but the median is the lock, and it didn't move.

**No measurement confound:**
- claude judged **0/421 items unjudged** in the on-run (vs 3/409 in baseline). The 190 "JSON likely truncated" budget warnings fired at ~83% budget but the JSON parser recovered every one — no data loss biasing claude down. (Methodology note for future runs: raise `KNOWLEDGE_JUDGE_BASE_TOKENS` above 3072 to clear the warnings; harmless here.)
- The +12 verdict slots in the on-run (421 vs 409) = the +6 recovered relations × (precision + recall) sides, exactly as expected.
- Both variants re-judged through the identical `compute_ensemble_macros.py` path; the c73b-drop-realized numbers reproduce the locked baseline (0.888 / 0.972 / 0.913) byte-for-byte.

**Why the cascade-recovered relations don't lift the median:** this is the `filter-output-F1-overstates-realized-when-writer-cascades` pattern in reverse — the +6 recovered endpoints are low-confidence (`confidence ≤ 0.3`, `kind=concept`) abstract subjects (`仙卿`, `大海`, `Bụt`, `cha Tấm`, `cung`, …). Judges weight them near-indifferently: gemma/qwen credit them slightly (small +), claude treats them as borderline (flat). Recovering them costs **zero precision** (no graph-pollution F1 penalty surfaced) but also buys **no median lift**.

## Ship gate evaluation — D10

| D10 clause | Verdict |
|---|---|
| (a) realized 3J median F1 ≥ current SHIP | ❌ **−0.2pp** (0.911 < 0.913) — within noise, but not ≥ |
| (b) Fleiss κ stays ≥ substantial (0.60) | ✅ 0.738 (substantial) |
| (c) no precision regression / graph pollution | ✅ precision flat-to-up on all judges; cascade sim 0 false-positives |
| (d) mechanism validated | ✅ +6 relations recovered, cap never hit, noise heuristic clean |
| (e) latency cost acceptable | ✅ Tier B is a deterministic MERGE — **no LLM call**, negligible latency |

**Clause (a) is the gate and it does not clear** — autocreate-on is F1-neutral (−0.2pp on the lock), not a lift.

## Ship decision — KEEP SDK opt-in (compose default stays OFF) — CONFIRMED by data

**DO NOT ACTIVATE c73e as compose default.** The measured F1 **confirms** cycle-73e's conservative decision rather than overturning it.

Rationale:
1. **Locked-metric F1 is neutral** — 3J median −0.2pp (within noise). Flipping a production default requires a clear lift on the lock; this isn't one.
2. **Mechanism is sound but low-yield** — +6 relations recovered with zero precision cost, but the recovered low-confidence concept entities don't move the median. Mean / 2J-subset are mildly positive (+0.6 / +1.0pp); not enough to override the lock.
3. **Conservative default** — power users can still flip `KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED=true` in their `.env`. The SDK path is validated and F1-safe (no regression), so opt-in carries no quality risk.
4. **D-PASS2-WRITER-AUTOCREATE-F1-EVAL is CLOSED** with this measured result. **D-PASS2-WRITER-CASCADE-GAP-CLOSE** can also close: the gap is now *measured* as F1-immaterial — closing it further (entity-prompt extension / pre-filter) would chase a lever the data shows is near-flat on the locked metric.

## What we DO ship regardless of D10 verdict

- ✅ `services/knowledge-service/app/db/neo4j_repos/entities.py` — `auto_created` property + promotion CASE (M1 fold)
- ✅ `services/knowledge-service/app/extraction/entity_resolver.py` — `auto_created` kwarg plumb
- ✅ `services/knowledge-service/app/extraction/pass2_writer.py` — Tier A.1 + A.2 + B logic + new Pass2WriteResult fields
- ✅ `services/knowledge-service/app/extraction/pass2_orchestrator.py` — `_load_writer_autocreate_config()` + spread into 3 writer call sites
- ✅ `services/knowledge-service/app/metrics.py` — 9-outcome counter `knowledge_extraction_writer_autocreate_total{role, outcome}`
- ✅ `services/knowledge-service/tests/unit/test_entities_auto_created.py` — 7 unit tests
- ✅ `services/knowledge-service/tests/unit/test_pass2_writer_autocreate.py` — 18 unit tests
- ✅ `services/knowledge-service/tests/unit/test_pass2_orchestrator.py` — 3 new env-loader tests
- ✅ `services/knowledge-service/tests/quality/run_c73e_writer_autocreate.py` — eval driver
- ✅ This compare doc + 2 eval fixture variants

**Total:** 8 code files + 2 new test files + 1 eval driver + 2 eval result dirs + this doc.

## Bonus findings

- **Tier A.1 (chapter name repair) doesn't fire on this fixture.** All cascade-skips are due to MISSED extractions (entity extractor didn't surface the relation subject), not ID-drift. Tier A.1 remains useful as defense-in-depth for future cases.
- **Noise heuristic correctly catches `little_women_ch01` compound subjects** (4 of 4 noise-skipped). Char-budget 60 + word-budget 3 combined heuristic is the right balance.
- **`tam_cam_vi` Vietnamese chapter recovers 3 entities** (`Bụt`, `cha Tấm`, `cung`) — all legitimate single/double-word noun phrases. Anchor lookup would also catch these if a Vietnamese glossary anchor were registered.
- **Cap=20 was never hit** on any chapter (max needed = 3 for `tam_cam_vi`). Default cap is comfortable headroom.

## Open questions deferred to next cycles

- **D-PASS2-WRITER-AUTOCREATE-FE-CLEANUP** — UI for reviewing/promoting auto-created entities (depends on `auto_created=true` marker shipped this cycle)
- **D-PASS2-WRITER-AUTOCREATE-PROMOTION-WORKFLOW** — auto-promotion on legit re-extraction works via Cypher M1 promotion CASE; explicit user-confirm UI is separate
- **D-PASS2-WRITER-AUTOCREATE-WORKER-AI** — port env loader to worker-ai if/when worker calls writer directly (currently doesn't)
- **D-PASS2-WRITER-AUTOCREATE-ANCHOR-SIMULATION** — extend `run_c73e_writer_autocreate.py` to simulate Tier A.2 anchor pre-check (would need glossary fixture)
