# Cycle 72 — Pass2 precision filter validation results

**Spec:** [docs/specs/2026-05-29-pass2-precision-filter.md](../../../../../docs/specs/2026-05-29-pass2-precision-filter.md)
**Plan:** [docs/plans/2026-05-29-pass2-precision-filter.md](../../../../../docs/plans/2026-05-29-pass2-precision-filter.md)
**Filter model:** `huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated` (UUID `019e5650-eca7-78c2-985d-465aa3bce1ce`)
**Pass A source:** c70a saved fixture under [eval_runs/c70a/](./c70a/) (eliminates extraction nondeterminism per spec HIGH-1)
**Date:** 2026-05-30

## D10 acceptance gate (4-clause, symmetric)

Ship requires ALL four clauses true:

| Clause | Threshold | Rationale |
|---|---|---|
| (a) median F1 lift across 3 judges | ≥ +1.5pp | Real signal across the panel |
| (b) min F1 lift over 3 judges | ≥ -0.5pp | No judge regressed materially |
| (c) claude F1 lift | ≤ 2× median | Anti-self-reinforcement (filter model = judge C) |
| (d) Fleiss κ | ≥ 0.60 | Reliability still "substantial" (Landis-Koch) |

## Variants

| Variant | Pass A | Filter | `partial_policy` | Wall-clock filter | Wall-clock ensemble |
|---|---|---|---|---|---|
| c70a (baseline) | (own extraction) | none | — | — | already locked (session 69) |
| **c72b** | c70a saved | claude-4.7-opus | `keep` | 343.5s | _TBD — in progress_ |
| **c72c** | c70a saved | claude-4.7-opus | `drop` | 382.3s | _TBD — pending_ |

## Per-chapter filter delta — c72b (keep)

| Chapter | Pre (E/R/Ev) | Post (E/R/Ev) | Δ E | Δ R | Δ Ev | Coverage E/R/Ev |
|---|---|---|---:|---:|---:|---|
| alice_ch01 | 11/11/7 | 11/10/7 | +0 | -1 | +0 | 100/100/100% |
| alice_ch02 | 13/11/12 | 13/9/12 | +0 | -2 | +0 | 100/100/100% |
| journey_west_zh_ch01 | 16/11/4 | 16/10/4 | +0 | -1 | +0 | 100/100/100% |
| journey_west_zh_ch14 | 20/20/11 | 20/20/11 | +0 | +0 | +0 | 100/95/100% |
| little_women_ch01 | 18/18/38 | 18/15/38 | +0 | -3 | +0 | 100/100/100% |
| pride_prejudice_ch01 | 8/16/12 | 8/10/12 | +0 | -6 | +0 | 100/100/100% |
| sherlock_scandal_ch01 | 5/7/5 | 5/6/5 | +0 | -1 | +0 | 100/100/100% |
| son_tinh_thuy_tinh_vi | 16/12/10 | 16/11/10 | +0 | -1 | +0 | 100/100/100% |
| tam_cam_vi | 13/15/14 | 13/13/14 | +0 | -2 | +0 | 100/100/100% |

Aggregate (all 9 chapters):
- Entities: 120 → 120 (-0%) — keep policy keeps every entity (none judged outright unsupported)
- Relations: 121 → 104 (-14.0%)
- Events: 113 → 113 (0%) — every event passes
- Coverage: ≥95% on every category (one journey_west_zh_ch14 batch dropped 1 of 20 relation verdicts)

Detailed per-chapter decision counts in [c72b/c72_filter_run_summary.json](./c72b/c72_filter_run_summary.json).

## Per-chapter filter delta — c72c (drop)

| Chapter | Pre (E/R/Ev) | Post (E/R/Ev) | Δ E | Δ R | Δ Ev | Coverage E/R/Ev |
|---|---|---|---:|---:|---:|---|
| alice_ch01 | 11/11/7 | 9/6/7 | -2 | -5 | +0 | 100/100/100% |
| alice_ch02 | 13/11/12 | 12/7/9 | -1 | -4 | -3 | 100/100/75% |
| journey_west_zh_ch01 | 16/11/4 | 16/8/3 | +0 | -3 | -1 | 100/100/100% |
| journey_west_zh_ch14 | 20/20/11 | 20/11/10 | +0 | -9 | -1 | 100/95/100% |
| little_women_ch01 | 18/18/38 | 17/8/30 | -1 | -10 | -8 | 100/100/92% |
| pride_prejudice_ch01 | 8/16/12 | 7/6/10 | -1 | -10 | -2 | 100/100/100% |
| sherlock_scandal_ch01 | 5/7/5 | 5/4/3 | +0 | -3 | -2 | 100/100/100% |
| son_tinh_thuy_tinh_vi | 16/12/10 | 16/10/10 | +0 | -2 | +0 | 100/100/100% |
| tam_cam_vi | 13/15/14 | 11/11/14 | -2 | -4 | +0 | 100/100/100% |

Aggregate (all 9 chapters):
- Entities: 120 → 113 (-5.8%)
- Relations: 121 → 70 (-42.1%)
- Events: 113 → 96 (-15.0%)
- Coverage: 75-100% per chapter; ~94% average

Detailed per-chapter decision counts in [c72c/c72_filter_run_summary.json](./c72c/c72_filter_run_summary.json).

**Observation:** c72c (drop) is aggressive — drops ~42% of relations + ~6% of entities + ~15% of events. c72b (keep) is gentle — only drops outright-unsupported items (~14% of relations, zero entities or events). c72c precision/recall trade-off will depend heavily on whether the dropped "partial" items were true-positives or true-negatives.

## c70a baseline (locked from session-69 ensemble)

| Judge | Macro Precision | Macro Recall | Macro F1 |
|---|---:|---:|---:|
| gemma | 0.785 | 0.921 | 0.848 |
| qwen-30b | 0.914 | 1.000 | 0.955 |
| claude-4.7-opus | 0.868 | 0.924 | 0.895 |
| **Median across 3 judges** | — | — | **0.895** |
| Fleiss κ | — | — | **0.671** (substantial) |

(Recomputed from the saved per-judge verdicts in [c70a/](./c70a/). Differs slightly from the SESSION_HANDOFF report which reported macro P + macro R separately.)

## Ensemble results — c72b (keep policy)

Run wall-clock: ~19 min (LM Studio JIT model swap × 3 judges, 9 chapters).

| Judge | Macro P | Macro R | Macro F1 | Δ vs c70a F1 |
|---|---:|---:|---:|---:|
| gemma | 0.810 | 0.901 | 0.853 | +0.5pp |
| qwen-30b | 0.939 | 1.000 | 0.969 | +1.4pp |
| claude-4.7-opus | 0.905 | 0.913 | 0.909 | +1.4pp |
| **Median** | — | — | **0.909** | **+1.4pp** |
| Fleiss κ | — | — | **0.690** | +0.019 (still substantial) |

Per-judge bias from ensemble report:
- gemma: strictness 0.81 (gap 0.04), lang_bias 0.15 (at flag threshold), rp_bias -0.14
- qwen-30b: strictness 0.92 (gap 0.07), lang_bias 0.09, rp_bias -0.11
- claude-4.7-opus: strictness 0.85 (gap 0.00 — median), lang_bias 0.10, rp_bias -0.07

## Ensemble results — c72c (drop policy)

Run wall-clock: ~16 min (slightly faster than c72b — fewer items judged after the aggressive filter).

| Judge | Macro P | Macro R | Macro F1 | Δ vs c70a F1 |
|---|---:|---:|---:|---:|
| gemma | 0.907 | 0.876 | 0.891 | **+4.3pp** |
| qwen-30b | 0.953 | 0.993 | 0.973 | +1.8pp |
| claude-4.7-opus | 0.972 | 0.868 | 0.917 | +2.2pp |
| **Median** | — | — | **0.917** | **+2.2pp** |
| Fleiss κ | — | — | **0.776** | **+0.105** (substantial → strong) |

Per-judge bias from ensemble report:
- gemma: strictness 0.88 (gap 0.05), lang_bias **0.06 (improved from 0.15 in c70a)**, rp_bias -0.00
- qwen-30b: strictness 0.94 (gap 0.01 — median), lang_bias 0.04, rp_bias -0.08
- claude-4.7-opus: strictness 0.93 (gap 0.00 — median), lang_bias 0.02, rp_bias +0.10

**Key observation:** gemma's language_bias dropped from 0.15 (at flag threshold) in c70a to 0.06 in c72c. The drop policy removed enough multilingual ambiguity that gemma judges English-vs-CJK/VN much more evenly. This is a real qualitative win — closes the prior "English judges accept CJK extractions more readily" concern from cycle 69.

## D10 4-clause gate evaluation

_Filled after both ensembles complete._

### c72b

| Clause | Computed | Threshold | PASS / FAIL |
|---|---:|---:|---|
| (a) median F1 lift | +1.4pp | ≥ +1.5pp | **FAIL (by 0.1pp)** |
| (b) min F1 lift (gemma) | +0.5pp | ≥ -0.5pp | PASS |
| (c) claude F1 lift bound | 1.4pp ≤ 2×1.4pp = 2.8pp | ≤ 2× median | PASS |
| (d) Fleiss κ | 0.690 | ≥ 0.60 | PASS (improved from 0.671) |
| **Overall** | 3-of-4 | strict 4-of-4 | **borderline FAIL on (a)** |

**Interpretation:** lift is real, directionally correct, and consistent across all 3 judges (no self-reinforcement). Fleiss κ even improved, suggesting cleaner ground truth post-filter. The +1.4pp median misses the +1.5pp threshold by 0.1pp — within measurement noise per spec D10 (the threshold was set for a *meaningful* signal).

### c72c

| Clause | Computed | Threshold | PASS / FAIL |
|---|---:|---:|---|
| (a) median F1 lift | +2.2pp | ≥ +1.5pp | **PASS** |
| (b) min F1 lift (qwen-30b) | +1.8pp | ≥ -0.5pp | **PASS** |
| (c) claude F1 lift bound | 2.2pp ≤ 2×2.2pp = 4.4pp | ≤ 2× median | **PASS** |
| (d) Fleiss κ | 0.776 | ≥ 0.60 | **PASS** (improved from 0.671) |
| **Overall** | 4-of-4 | strict 4-of-4 | **PASS — ship-eligible** |

**Anti-self-reinforcement note:** gemma (+4.3pp) lifted MORE than claude (+2.2pp). The filter model is claude-family but its lift is in line with the median, not the outlier. The outlier is gemma — which is suspicious of the OPPOSITE pattern (cross-judge consensus that the filter helped). This is structurally healthy: claude-4.7-opus didn't disproportionately approve of its own filtering.

## Measurement validity caveat (per spec round-1 MED-3 fold)

These results report **filter-output F1** (what `apply_precision_filter` returns), not Neo4j-realized F1 (what `pass2_writer` actually persists). The writer enforces relation referential integrity at [services/knowledge-service/app/extraction/pass2_writer.py:204](../../../../app/extraction/pass2_writer.py#L204) — relations whose subject/object entity isn't merged get auto-skipped, so when the filter drops an entity, downstream relations involving it cascade-skip at write time.

Event participants do NOT cascade (they're free-text strings, no FK), so a filter-dropped entity may leave orphan event-participant strings in Neo4j.

Deferred for follow-up cycle: **D-PASS2-FILTER-NEO4J-REALIZED-F1**.

## Ship decision

| Variant | D10 verdict | Median F1 | Median F1 Δ | κ Δ | Recommended action |
|---|---|---:|---:|---:|---|
| c72b (keep) | borderline FAIL on (a) | 0.909 | +1.4pp | +0.019 | runner-up; consider if c72c had failed |
| **c72c (drop)** | **PASS (4/4)** | **0.917** | **+2.2pp** | **+0.105** | **SHIP — recommended default** |

### Ship c72c

**Decision: ship c72c with `partial_policy="drop"` as the default precision filter config.**

Rationale:
1. **Strict D10 PASS** — all 4 clauses cleared with margin.
2. **κ improvement of +0.105** — judges agree dramatically more after the drop filter (0.671 → 0.776). The filter removed real noise that was driving judge disagreement.
3. **gemma language_bias dropped 0.15 → 0.06** — closes the EN-vs-CJK/VN judge-bias concern from cycle 69's eval framework overhaul.
4. **Anti-self-reinforcement signature absent** — claude lift (+2.2pp) matches median, gemma is the high outlier (+4.3pp). The filter judge model isn't getting an artificial boost.
5. **c72b is the runner-up** — if c72c had failed, c72b's +1.4pp median lift is still positive on all 3 judges and would have been a defensible ship under pragmatic interpretation. But c72c is decisively better.

### Activation config

For production worker-ai:
```bash
WORKER_AI_PRECISION_FILTER_MODEL_REF=019e5650-eca7-78c2-985d-465aa3bce1ce
WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY=drop
WORKER_AI_PRECISION_FILTER_MODEL_SOURCE=user_model
```

For production knowledge-service orchestrator (chat-turn + chapter paths):
```bash
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF=019e5650-eca7-78c2-985d-465aa3bce1ce
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY=drop
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_SOURCE=user_model
```

Both envs default unset; the cycle ships with filter OFF in containers. Activation is a separate ops step (caller decides per-service whether the +30-90s/chapter latency is worth the F1 lift).

### Per-category yield insight (informational, follow-up cycle)

c72c relations contributed most of the F1 lift (-42% volume but +2-4pp F1). Entities contributed marginally (-6% volume, ~+1pp F1). Events contributed -15% volume + ~+1pp F1.

A future cycle could try `categories=("relation",)` to validate whether relation-only filtering captures most of the c72c lift at lower latency (one filter call per chapter instead of three). Deferred as **D-PASS2-FILTER-RELATION-ONLY-OPTIMIZATION**.

## Latency cost

- c72b filter run: 343.5s for 9 chapters = ~38s/chapter avg
- c72c filter run: 382.3s for 9 chapters = ~42s/chapter avg (slightly slower under drop policy — more "partial" verdicts to handle)
- Production worker-ai latency impact: filter is **off by default** per env unset; activation doubles wall-clock per chapter (~30-90s added). Acceptable trade-off only if F1 lift justifies it.

## Operator deferred items (added this cycle)

- **D-PASS2-FILTER-NEO4J-REALIZED-F1** — re-measure F1 after the pass2_writer cascade
- **D-PASS2-FILTER-FACTS-SUPPORT** — extend filter to facts (per spec D2)
- **D-PASS2-FILTER-CLOUD-CALIBRATION** — cloud Claude calibration (per spec non-goal)
- **D-PASS2-FILTER-RUNTIME-FLAG** — per-request header override (per spec non-goal)
- **D-PASS2-FILTER-CACHE** — verdict caching (per spec non-goal)
- **D-PASS2-FILTER-PER-USER-UI** — UI toggle (per spec non-goal)
