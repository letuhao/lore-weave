# Cycle 73b — Pass2 precision filter, relation-only optimization

**Pass A source:** c70a saved fixture under [eval_runs/c70a/](./c70a/) (same as c72)
**Filter model:** `huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated` (UUID `019e5650-eca7-78c2-985d-465aa3bce1ce`)
**Hypothesis:** relations carried most of c72c-drop's +2.2pp F1 lift; relation-only filter saves ~65% latency
**Date:** 2026-05-30

## Ship gate (cycle 72 D10 + 2 cycle-73b-specific clauses)

| Clause | Threshold | Rationale |
|---|---|---|
| (a) median F1 lift vs c70a | ≥ +1.5pp | Same as c72 D10 — meaningful signal |
| (b) min F1 lift | ≥ -0.5pp | No judge regressed |
| (c) claude F1 lift | ≤ 2× median | Anti-self-reinforcement |
| (d) Fleiss κ | ≥ 0.60 | Reliability still substantial |
| **(e) NEW: F1 within 1pp of c72c-drop median (0.917)** | ≥ 0.907 | Relation-only must not regress meaningfully vs full filter |
| **(f) NEW: per-chapter latency** | ≤ 50% of c72c-drop (~21s avg) | Latency win is the cycle's main value-add |

## Variants

| Variant | Filter | `partial_policy` | `categories` | Wall-clock filter | s/chapter | Wall-clock ensemble |
|---|---|---|---|---|---|---|
| c70a (baseline) | none | — | — | — | — | already locked (session 69) |
| c72c (cycle-72 ship) | claude-4.7-opus | drop | entity+relation+event | 382s | 42.5s | ~16-20 min (locked) |
| **c73b-keep** | claude-4.7-opus | keep | **relation only** | 229.6s | **25.5s** | 19 min |
| **c73b-drop** | claude-4.7-opus | drop | **relation only** | 170.0s | **18.9s** | _TBD_ |

**Latency vs c72c-drop**: c73b-keep 60% (FAILS clause (f) by 4.5s); c73b-drop **44%** (clause (f) PASS).

## Per-chapter filter delta

### c73b-keep (relation-only, keep)

| Chapter | Pre rel | Post rel | Δ rel | Coverage | Duration |
|---|---:|---:|---:|---:|---:|
| alice_ch01 | 11 | 10 | -9% | 100% | 12.0s |
| alice_ch02 | 11 | 8 | -27% | 100% | 10.8s |
| journey_west_zh_ch01 | 11 | 10 | -9% | 100% | 15.2s |
| journey_west_zh_ch14 | 20 | 19 | -5% | 100% | 40.4s |
| little_women_ch01 | 18 | 14 | -22% | 100% | 51.3s |
| pride_prejudice_ch01 | 16 | 11 | -31% | 100% | 38.0s |
| sherlock_scandal_ch01 | 7 | 6 | -14% | 100% | 16.6s |
| son_tinh_thuy_tinh_vi | 12 | 11 | -8% | 100% | 21.9s |
| tam_cam_vi | 15 | 14 | -7% | 100% | 23.3s |

**Total**: relations 121 → 103 (-14.9% drop)

### c73b-drop (relation-only, drop)

| Chapter | Pre rel | Post rel | Δ rel | Coverage | Duration |
|---|---:|---:|---:|---:|---:|
| alice_ch01 | 11 | 8 | -27% | 100% | 12.0s |
| alice_ch02 | 11 | 6 | -45% | 100% | 10.8s |
| journey_west_zh_ch01 | 11 | 9 | -18% | 100% | 15.2s |
| journey_west_zh_ch14 | 20 | 11 | -45% | 100% | 40.4s |
| little_women_ch01 | 18 | 8 | -56% | 100% | 30.4s |
| pride_prejudice_ch01 | 16 | 6 | -62% | 100% | 22.5s |
| sherlock_scandal_ch01 | 7 | 3 | -57% | 100% | 8.7s |
| son_tinh_thuy_tinh_vi | 12 | 10 | -17% | 100% | 12.7s |
| tam_cam_vi | 15 | 12 | -20% | 100% | 17.3s |

**Total**: relations 121 → 73 (-39.7% drop, near-identical to c72c-drop's -42.1%)

## Baselines (locked, for comparison)

| Reference | Median F1 | Fleiss κ | Notes |
|---|---:|---:|---|
| c70a (no filter) | 0.895 | 0.671 | cycle-69 ensemble baseline |
| c72b (keep, all 3 cat) | 0.909 | 0.690 | cycle-72 runner-up; D10(a) borderline FAIL |
| c72c (drop, all 3 cat) | **0.917** | **0.776** | cycle-72 ship; D10 4/4 PASS |

## Ensemble results — c73b-keep (relation-only, keep)

| Judge | Macro P | Macro R | Macro F1 | Δ vs c70a | Δ vs c72c-drop |
|---|---:|---:|---:|---:|---:|
| gemma | 0.814 | 0.901 | 0.855 | +0.7pp | -3.6pp |
| qwen-30b | 0.931 | 1.000 | 0.964 | +0.9pp | -0.9pp |
| claude-4.7-opus | 0.904 | 0.909 | 0.907 | +1.2pp | -1.0pp |
| **Median** | — | — | **0.907** | **+1.2pp** | **-1.0pp** |
| Fleiss κ | — | — | **0.688** | +0.017 | -0.088 |

## Ensemble results — c73b-drop (relation-only, drop)

| Judge | Macro P | Macro R | Macro F1 | Δ vs c70a | Δ vs c72c-drop |
|---|---:|---:|---:|---:|---:|
| gemma | 0.874 | 0.901 | 0.887 | +3.9pp | -0.4pp |
| qwen-30b | 0.943 | 1.000 | 0.971 | +1.6pp | -0.2pp |
| claude-4.7-opus | 0.939 | 0.894 | 0.916 | +2.1pp | -0.1pp |
| **Median** | — | — | **0.916** | **+2.1pp** | **-0.1pp** |
| Fleiss κ | — | — | **0.754** | +0.083 | -0.022 |

## D10 + (e)+(f) gate evaluation

### c73b-keep (relation-only, keep) — FAIL

| Clause | Computed | Threshold | PASS / FAIL |
|---|---:|---:|---|
| (a) median F1 lift vs c70a | +1.2pp | ≥ +1.5pp | **FAIL by 0.3pp** |
| (b) min F1 lift | +0.7pp (gemma) | ≥ -0.5pp | PASS |
| (c) claude F1 lift bound | 1.2pp ≤ 2×1.2pp | ≤ 2× median | PASS |
| (d) Fleiss κ | 0.688 | ≥ 0.60 | PASS |
| (e) F1 within 1pp of c72c-drop (0.917) | 0.907 (gap 1.0pp, borderline) | ≥ 0.907 | PASS (exact) |
| (f) Per-chapter latency ≤ 21s (50% of c72c-drop) | 25.5s | ≤ 21s | **FAIL by 4.5s** |
| **Overall** | 4/6 PASS | strict 6/6 | **FAIL** — drops 2 clauses |

### c73b-drop (relation-only, drop) — **PASS 6/6 — SHIP**

| Clause | Computed | Threshold | PASS / FAIL |
|---|---:|---:|---|
| (a) median F1 lift vs c70a | +2.1pp | ≥ +1.5pp | **PASS** |
| (b) min F1 lift (qwen-30b) | +1.6pp | ≥ -0.5pp | **PASS** |
| (c) claude F1 lift bound | 2.1pp ≤ 4.2pp | ≤ 2× median | **PASS** |
| (d) Fleiss κ | 0.754 | ≥ 0.60 | **PASS** |
| (e) F1 within 1pp of c72c-drop (0.917) | 0.916 (gap 0.1pp) | ≥ 0.907 | **PASS** with margin |
| (f) Per-chapter latency ≤ 21s | **18.9s** | ≤ 21s | **PASS** with margin |
| **Overall** | **6/6 PASS** | strict 6/6 | **PASS — ship-eligible** |

**Anti-self-reinforcement check:** gemma (+3.9pp) lifted MORE than claude (+2.1pp). The filter model is claude-family but it's not the high-lift judge. Same structurally-healthy pattern as c72c-drop.

## Ship decision

**Ship c73b-drop as the new default precision filter config.**

| Variant | Median F1 | Δ vs c70a | Per-chapter latency | D10 verdict |
|---|---:|---:|---:|---|
| c70a (no filter) | 0.895 | — | — | — |
| c72c-drop (cycle 72 ship) | 0.917 | +2.2pp | 42.5s | PASS 4/4 D10 |
| c73b-keep (relation-only) | 0.907 | +1.2pp | 25.5s | FAIL (a)+(f) |
| **c73b-drop (relation-only)** | **0.916** | **+2.1pp** | **18.9s** | **PASS 6/6** ← ship |

Rationale:
1. **F1 within noise of c72c-drop** — 0.916 vs 0.917 = -0.1pp = within Fleiss κ measurement noise.
2. **55% latency reduction** — 18.9s/chapter vs 42.5s/chapter. This is the cycle's main value-add.
3. **κ regression -0.022 is acceptable** — c73b-drop κ=0.754 still "substantial" (>0.60); c72c-drop κ=0.776 advantage doesn't justify the ~2× latency.
4. **Hypothesis confirmed**: relations carried virtually all of c72c-drop's F1 lift. Filtering entities and events added measurable but small κ improvement (+0.022) at +24s/chapter cost — bad latency-vs-quality trade.

### Per-category yield attribution (from this cycle's data)

| Filter scope | Median F1 | Latency | F1/sec efficiency |
|---|---:|---:|---:|
| relation only | 0.916 | 18.9s | 0.0485 |
| relation+entity+event | 0.917 | 42.5s | 0.0216 |

Relation-only is **~2.2× more efficient** per second of latency, with negligible F1 loss.

### Activation config update

```bash
# infra/docker-compose.yml — knowledge-service + worker-ai
# OLD (cycle-72 default):
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY=drop
WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY=drop
# (categories implicitly all-3 = entity,relation,event)

# NEW (cycle-73b default):
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY=drop
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_CATEGORIES=relation   # NEW
WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY=drop
WORKER_AI_PRECISION_FILTER_CATEGORIES=relation              # NEW
```

Requires SDK + service code change: extend `_load_precision_filter_config` in BOTH `services/worker-ai/app/runner.py` AND `services/knowledge-service/app/extraction/pass2_orchestrator.py` to read `KNOWLEDGE_EXTRACTION_PRECISION_FILTER_CATEGORIES` (knowledge-service) and `WORKER_AI_PRECISION_FILTER_CATEGORIES` (worker-ai). Parse comma-separated; default to all 3 for backward-compat.

## Measurement validity (carryover from cycle 72)

Same caveat applies: this reports FILTER-OUTPUT F1, not Neo4j-realized F1. **D-PASS2-FILTER-NEO4J-REALIZED-F1** remains deferred.

## Latency cost (revised)

- c72c-drop: 382s for 9 chapters = 42.5s/chapter
- c73b-drop: 170s for 9 chapters = **18.9s/chapter (-55%)**
- Production wall-clock impact: for a 100-chapter book, filter overhead drops from ~70 min → ~32 min. Significant.

## Deferred items (carryover + new)

- **D-PASS2-FILTER-NEO4J-REALIZED-F1** (carryover) — F1 post writer-cascade
- **D-PASS2-FILTER-FACTS-SUPPORT** (carryover) — filter facts
- **D-PASS2-FILTER-CLOUD-CALIBRATION** (carryover) — cloud Claude calibration
- **D-PASS2-FILTER-RUNTIME-FLAG** (carryover) — per-request header override
- **D-PASS2-FILTER-CACHE** (carryover) — verdict caching
- **D-PASS2-FILTER-PER-USER-UI** (carryover) — UI surface
- **D-PASS2-FILTER-CATEGORIES-AB-TUNE** (NEW) — re-validate relation-only ship after first month of production data; consider per-language or per-genre `categories` override

## D10 + (e)+(f) gate evaluation

_TBD_

## Ship decision

_TBD_
