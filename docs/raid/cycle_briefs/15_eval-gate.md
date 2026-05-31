# Cycle 15: Eval (EXTEND framework) + gate

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** EXTEND the existing eval framework ADDITIVELY (separate files, zero edits to climate/geo). Ship `scripts/enrichment_eval.py` + `eval/enrichment-eval-suite.toml` with weighted sub-scores (schema / canon / anachronism / provenance / usefulness), regression thresholds, and baseline-diff; freeze `eval/baselines/enrichment-v1.json`; persist runs in-service as `enrichment_eval_runs` (mirror knowledge-service `benchmark_runs`). REUSE the judge-ENSEMBLE methodology from `services/knowledge-service/tests/quality/` (multi-judge majority + Fleiss κ + partial-credit; gemma/qwen-30b/claude judges) for subjective cultural-fidelity. This gate AUTO-BLOCKS higher-cost C16 (fabrication) / C17 (re-cook).
- **Acceptance gate:** `scripts/raid/verify-cycle-15.sh` exits 0
- **Top 3 LOCKED decisions consumed:** Cost-discipline (P1-only until this gate), Eval-EXTEND-additive (never edit climate/geo), Model-via-registry (Qwen 3.6 + bge-m3, no hardcoded names)
- **DPS count:** 3
- **Estimated wall time:** ~5–7h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C14
- Files expected to exist (grep-able paths): `services/lore-enrichment-service/app/` (C0+), `scripts/raid/verify-cycle-14.sh`, `services/knowledge-service/tests/quality/judge_ensemble.py` + `eval_harness.py` + `test_judge_eval.py` (judge-ensemble to reuse), `services/knowledge-service/app/db/repositories/benchmark_runs.py` + `app/routers/internal_benchmark.py` (persist pattern to mirror), C14 end-to-end P1 job runner emitting promotable proposals.

## Scope (IN)
- `scripts/enrichment_eval.py` — CLI eval driver: load suite TOML, run the C14 P1 pipeline (or replay a fixed proposal set), score each proposal, aggregate weighted total, diff vs baseline, emit scorecard JSON + human-readable table, exit non-zero when any threshold regresses.
- `eval/enrichment-eval-suite.toml` — NEW file. Weighted sub-scores: `schema` (game-ready normalization valid), `canon` (no contradiction vs KG/glossary, M2 consistency), `anachronism` (no post-Shang/Zhou intrusions), `provenance` (every fact carries origin/confidence/grounding ref), `usefulness` (cultural-fidelity + dimension coverage 历史/地理/文化/features/inhabitants). Encodes weights, per-sub-score regression thresholds, baseline-diff tolerance.
- `eval/baselines/enrichment-v1.json` — versioned frozen baseline (`enrichment-v<X>`), distinct namespace from climate `v5.x.json`.
- Judge-ensemble integration: reuse `tests/quality/judge_ensemble.py` (majority vote + Fleiss κ + partial-credit) for the subjective `usefulness`/cultural-fidelity sub-score over Chinese output; judges (gemma/qwen-30b/claude) resolved via PROVIDER-REGISTRY.
- In-service persistence: `enrichment_eval_runs` table + repository + internal route in `lore-enrichment-service`, mirroring `benchmark_runs.py` / `internal_benchmark.py` (run_id, suite_version, baseline_version, sub-scores, weighted_total, pass/fail, κ, timestamp).
- `scripts/raid/verify-cycle-15.sh` — runs the eval on the locked-4-locations fixture, asserts scorecard produced, asserts gate logic blocks below threshold, asserts run persisted.
- Gate hook: a pass/fail signal C16/C17 read (e.g. latest `enrichment_eval_runs.passed=true` for current suite_version) so fabrication/re-cook cannot activate below threshold.

## Scope (OUT — explicitly)
- **NEVER edit** `eval/climate-eval-suite.toml`, `eval/baselines/v*.json` (climate/geo), `scripts/climate_eval.py`, `scripts/climate_eval_sweep.py`, or anything under `eval/compare-*`.
- Do NOT implement Strategy (c) fabrication (C16) or (d) re-cook (C17) — this cycle only builds the gate that guards them.
- Do NOT modify `services/knowledge-service/tests/quality/` judge-ensemble code — import/reuse only; no in-place edits.
- Do NOT touch `world-service`/`game-server`/`tilemap` or `infra/existing-prod/`.
- Do NOT hardcode model names (Qwen 3.6, bge-m3, judge models) — resolve via provider-registry.
- No new RAG/eval framework, no langchain/llamaindex; no Neo4j canonical writes.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `services/lore-enrichment-service/tests/` unit suite — sub-score scorers (schema/canon/anachronism/provenance/usefulness), weighted aggregation, baseline-diff regression detection, gate pass/fail boundary (at-threshold = pass, below = fail), κ computation; `enrichment_eval_runs` repo round-trip (persist + read-back).
- Lints pass: `scripts/raid/prod-isolation-lint.sh` (no prod/world-service drift); `scripts/raid/secret-scan-cycle.sh` clean; git-diff confirms ZERO changes to climate/geo eval files.
- Gate behavior: run on a deliberately-bad proposal fixture → exit non-zero + `passed=false`; run on good fixture → exit 0 + `passed=true`. Both persist a row.
- Integration smoke: `scripts/raid/verify-cycle-15.sh` exits 0 — eval scorecard vs `enrichment-v1.json` baseline produced, gate blocks below threshold, run persisted in `enrichment_eval_runs`.
- Not a cross-service cycle (eval reads C14 outputs in-service); no live-smoke token required. If the judge-ensemble run needs live LM Studio judges and the stack is unavailable, record `live infra unavailable: <reason>` and gate on the deterministic sub-scores (schema/canon/anachronism/provenance) only for the smoke.

## DPS parallelism plan
- DPS 1: Suite + scorers + baseline — `eval/enrichment-eval-suite.toml`, `scripts/enrichment_eval.py`, deterministic sub-score scorers (schema/canon/anachronism/provenance), weighted aggregation + baseline-diff, `eval/baselines/enrichment-v1.json`. (return budget: 1500 tokens summary)
- DPS 2: Judge-ensemble usefulness sub-score — import `tests/quality/judge_ensemble.py`; wire majority/κ/partial-credit over Chinese output; judges via registry. (return budget: 1500 tokens)
- DPS 3: Persistence + gate + verify — `enrichment_eval_runs` migration/repo/internal route mirroring `benchmark_runs`; gate pass/fail signal; `scripts/raid/verify-cycle-15.sh`. (return budget: 1500 tokens)

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Climate/geo immutability:** `git diff --name-only` MUST show zero changes under `eval/climate-eval-suite.toml`, `eval/baselines/v*.json`, `scripts/climate_eval*.py`, `eval/compare-*`. Any touch = hard fail.
- **Additive, not fork:** new files only (`enrichment-eval-suite.toml`, `enrichment_eval.py`, `enrichment-v1.json`); judge-ensemble REUSED by import, not copied/edited.
- **Gate actually blocks:** confirm below-threshold yields non-zero exit AND a `passed=false` row, and that C16/C17 activation reads this signal — not a no-op that always passes (false-green gate is the worst failure here).
- **Hardcoded model names:** grep scorers/judges for literal `qwen`/`gemma`/`bge-m3`/`claude` model IDs — must come from provider-registry.
- **H0 leakage check (eval-specific):** usefulness/canon scorers must treat enriched proposals as `source_type='enriched'`/quarantined, never score them as authored canon (conf=1.0).
- **Persistence parity:** `enrichment_eval_runs` round-trips (idempotent re-run, no dup baseline rows); migration has clean down + is idempotent.
- **Eval on Chinese:** scorers/judges operate on Chinese source-faithful output (CJK importability), not romanized/translated text.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present: `enrichment_eval.py`, `enrichment-eval-suite.toml`, `enrichment-v1.json`, judge-ensemble usefulness wiring, `enrichment_eval_runs` persistence, gate signal, `verify-cycle-15.sh`.
- No OUT items touched: zero diff to climate/geo eval files and knowledge-service judge-ensemble code; no C16/C17 strategy code; no world-service/prod edits.
- All acceptance criteria met: unit suite green, gate blocks below-threshold + persists, verify-cycle-15.sh exits 0, no hardcoded model names.
- Cross-cycle invariants intact: EXTEND-additive honored; gate guards higher-cost cycles; H0 enriched≠canon respected in scoring.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C15 row + cost-discipline/isolation notes): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- LOCKED decisions (full list): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md)
- Layer plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md), [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- Reuse targets: `services/knowledge-service/tests/quality/judge_ensemble.py`, `eval_harness.py`, `test_judge_eval.py`; persist pattern `services/knowledge-service/app/db/repositories/benchmark_runs.py` + `app/routers/internal_benchmark.py`; methodology `services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md` (Fleiss κ / majority / partial-credit).
- LOCKED consumed: cost-discipline (P1-only pre-gate), Eval=EXTEND-additive (separate files, never edit climate/geo), Q-R2 (gate promotes each higher tier), model-via-registry, output-language=Chinese, H0 (enriched≠canon), isolation (no prod/world-service).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **LOCKED — EXTEND additively, NEVER edit climate/geo:** new files only (`scripts/enrichment_eval.py`, `eval/enrichment-eval-suite.toml`, `eval/baselines/enrichment-v1.json`); zero diff to `eval/climate-eval-suite.toml`, `eval/baselines/v*.json`, `scripts/climate_eval*.py`. Reuse judge-ensemble by IMPORT, not edit.
- 🔴 **LOCKED — gate enforces cost-discipline:** this gate AUTO-BLOCKS the higher-cost C16 (fabrication) / C17 (re-cook). A false-green gate that always passes defeats the whole cycle — below-threshold MUST exit non-zero and persist `passed=false`.
- 🔴 **LOCKED — no hardcoded model names:** Qwen 3.6, bge-m3, and judge models (gemma/qwen-30b/claude) resolve via PROVIDER-REGISTRY; eval operates on Chinese source-faithful output.
- 🔴 **Acceptance MUST include:** `scripts/raid/verify-cycle-15.sh` exits 0 — scorecard vs `enrichment-v1.json`, gate blocks below threshold, run persisted in `enrichment_eval_runs`.
- 🔴 **Do NOT touch:** climate/geo eval files, knowledge-service judge-ensemble source, C16/C17 strategy code, `world-service`/`game-server`/`tilemap`, `infra/existing-prod/`. H0: never score enriched proposals as authored canon.
- 🔴 **Fresh session reminder:** this is a new `/raid 15` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
