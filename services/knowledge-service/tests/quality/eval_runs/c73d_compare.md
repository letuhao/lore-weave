# Cycle 73d — Entity recovery (3-tier glossary → hints → LLM)

**Hypothesis:** baseline writer-cascade gap (10.7% supported-relations cascade-skip per c73c) is closeable by promoting unmatched relation subjects/objects as :Entity nodes (Tier 3 LLM classifier) instead of letting the writer silently drop them. Tier 1 (glossary) + Tier 2 (author hints) make zero-LLM-cost recovery for already-known names.

**Spec:** 5-clause ship gate (see Section "Ship gate" below).
**Date:** 2026-05-30

## c73d filter-output results

### c73d-recov-only (recovery, no precision filter — closes baseline cascade gap)

| Chapter | Pre ent | Post ent | +recovered | abstract-drops | unjudged |
|---|---:|---:|---:|---:|---:|
| alice_ch01 | 11 | 11 | 0 | 0 | 0 |
| alice_ch02 | 13 | 13 | 0 | 0 | 0 |
| journey_west_zh_ch01 | 16 | 19 | 3 | 0 | 0 |
| journey_west_zh_ch14 | 20 | 21 | 1 | 0 | 0 |
| little_women_ch01 | 18 | 19 | 1 | 6 | 0 |
| pride_prejudice_ch01 | 8 | 9 | 1 | 0 | 0 |
| sherlock_scandal_ch01 | 5 | 5 | 0 | 2 | 0 |
| son_tinh_thuy_tinh_vi | 16 | 16 | 0 | 0 | 0 |
| tam_cam_vi | 13 | 16 | 3 | 0 | 0 |

**Aggregate:** 9 entities recovered + 8 abstract relations dropped + 0 unjudged across all 9 chapters. Wall-clock: **18.0s total / 2.0s per chapter avg** — significantly faster than the precision filter's 19s/chapter (recovery LLM call batches 5 names + much shorter per-batch).

### c73d-recov-plus-rel (recovery + cycle-73b relation-only filter — production candidate)

_TBD — pending filter run_

## Empirical comparison vs prior ship variants

| Variant | Filter-output F1 | Cascade-skip rate | Realized F1 | Per-chapter latency |
|---|---:|---:|---:|---:|
| c70a baseline | 0.895 | 10.7% | ~0.88 (est) | — |
| c72c-drop (cycle-72 retired) | 0.917 | 22.5% | 0.904 | 42.5s |
| c73b-drop (current SHIP) | 0.916 | 12.3% | 0.913 | 18.9s |
| c73d-recov-only | 0.898 | **0%** | **0.898** | **2.0s** |
| **c73d-recov-plus-rel** | **0.922** | **0%** | **0.922** | **~30s** |

3-judge median F1: c73d-recov-plus-rel = 0.922, +0.9pp vs c73b-drop-realized.

### 2-judge subset (claude removed — anti-self-reinforcement check)

Recovery + filter both use claude-4.7-opus. Concern: claude judge favorable to claude classifier's output. Recompute median over gemma + qwen-30b only (no LLM calls; per-judge verdict files already exist).

| Variant | gemma F1 | qwen-30b F1 | claude F1 | 3J median | **2J mean (no claude)** | Δ 2J vs c73b-drop |
|---|---:|---:|---:|---:|---:|---:|
| c70a baseline | 0.848 | 0.955 | 0.895 | 0.895 | 0.9015 | -2.85pp |
| c72c-drop realized | 0.899 | 0.965 | 0.904 | 0.904 | 0.9320 | +0.20pp |
| **c73b-drop realized (SHIP)** | **0.888** | **0.972** | **0.913** | **0.913** | **0.9300** | — |
| c73d-recov-only | 0.838 | 0.956 | 0.898 | 0.898 | 0.8970 | -3.30pp |
| **c73d-recov-plus-rel** | **0.884** | **0.973** | **0.922** | **0.922** | **0.9285** | **-0.15pp** |

**The +0.9pp 3-judge lift on c73d-recov-plus-rel came entirely from the claude judge.** On the 2-judge subset, c73d-recov-plus-rel is **slightly WORSE** than c73b-drop (-0.15pp). Classic self-reinforcement.

By contrast, c73b-drop's prior +2.85pp lift over c70a on the 2-judge basis was real (not driven by claude — gemma + qwen both saw the lift independently).

## Ship gate evaluation — c73d-recov-plus-rel

| Clause | Threshold | Actual | PASS/FAIL |
|---|---|---|---|
| (a) realized F1 lift vs c73b-drop-realized (0.913) | ≥ +1.5pp | +0.9pp (3-judge); **-0.15pp (2-judge)** | **FAIL** |
| (b) min judge F1 lift | ≥ -0.5pp | -0.4pp (gemma) | PASS (borderline) |
| (c) entity graph pollution | recovered ≤ 0.2× pre-recovery entity count | +9 entities / 120 pre = +7.5% | PASS |
| (d) Fleiss κ realized | ≥ 0.60 | 0.726 | PASS (substantial; -0.030 vs c73b 0.756) |
| (e) Per-chapter latency | ≤ 30s | ~30s (271s/9) | PASS (just at threshold) |

**Overall: FAIL on (a)** strict. Lift is real (+0.9pp 3-judge) but disappears when claude judge is removed (-0.15pp 2-judge) — proving the lift was claude-self-reinforcement, NOT a robust quality gain.

## Ship decision

**DO NOT ACTIVATE c73d-recov-plus-rel as compose default.** Current ship c73b-drop stays.

Rationale:
1. **Self-reinforcement confirmed**: c73d-recov-plus-rel gains +0.9pp on the 3-judge median but **regresses -0.15pp on the 2-judge mean (claude removed)**. The filter+recovery model (claude-4.7-opus) is the SAME model that produced the lift-only-on-claude-judge. Classic self-reinforcement signature.
2. **Latency cost real**: 30s/chapter vs c73b's 18.9s = +60% latency. Not justified by zero quality improvement on a clean measurement.
3. **Cascade-gap closure is real but not a measured F1 win**: 0% cascade-skip (vs c73b's 12.3%) is a downstream-storage property — it means the Neo4j writer silently drops fewer relations, but the F1 measurement already captured what mattered for the judge ensemble.

**What we DO ship:**
- ✅ SDK module `entity_recovery.py` (~340 lines, 13 unit tests passing)
- ✅ `EntityRecoveryConfig` + env loaders in worker-ai + knowledge-service orchestrator
- ✅ New Prometheus counter `knowledge_extraction_recovery_decisions_total{source, verdict}`
- ✅ Compose envs **defaulting to OFF** (override to enable opt-in)
- ✅ This compare doc documenting why we don't activate it
- ✅ Eval driver `run_c73d_recovery.py` for future re-validation

**Future re-validation conditions:** revisit cycle 73d when one of:
- A non-claude classifier model is available (e.g. cloud Anthropic claude-haiku-4-5 if a cloud BYOK lands) — eliminates the self-reinforcement bias
- A 4th non-claude judge is added to the ensemble — measures a 3-judge non-claude median directly
- An author-hints API ships in book-service (Tier 2 use case) — recovery gets more zero-LLM-cost lookups and the LLM-only ablation becomes less critical

Tracked as **D-PASS2-FILTER-CLOUD-CALIBRATION** (existing deferred, carryover from cycle 72) + **D-ENTITY-RECOVERY-NON-CLAUDE-CLASSIFIER** (NEW).

### Why ship the SDK at all if we're not activating it?

- The SDK is correct + tested. No reason to revert clean code.
- Future evaluation can re-use it without re-implementing.
- Opt-in via env means an experimental power user can flip the switch in their `.env` without code change.
- The cascade-gap analytics carry forward for any future writer-side improvement work (D-PASS2-WRITER-CASCADE-GAP-CLOSE has more options than just "Tier-3 LLM classifier").

## Methodology

Pipeline mirrors `extract_pass2` chain order:
1. Load c70a chapter dump as Pass A
2. Recovery: 3-tier (glossary→hints→LLM) — promotes recovered :Entity nodes, drops abstract-verdict relations
3. (Optional) precision filter
4. Dump filtered `actual.json`
5. Apply writer cascade simulation (relations whose subject/object name still isn't in entity set after recovery → cascade-drop)
6. Run 3-judge ensemble on realized dump

For c73d-recov-only: pipeline stops at step 4 with filter omitted.
For c73d-recov-plus-rel: filter = relation-only-drop (c73b config).
