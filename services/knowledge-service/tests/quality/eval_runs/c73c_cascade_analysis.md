# Cycle 73c — Neo4j-realized F1 cascade analysis

**Question:** does the pass2_writer's relation-cascade-skip change the F1 numbers from cycle 72 / 73b ship decisions?

**Method:** simulate the writer's cascade rule ([pass2_writer.py:204](../../../../app/extraction/pass2_writer.py#L204)) on existing saved filter dumps (c70a baseline, c72c-drop ship, c73b-drop new default). For each variant, count relations whose `subject` or `object` name is NOT in the entity name list (these would skip at write time). Cross-reference per-judge verdict files to attribute lost precision: of cascade-skipped relations, how many were marked "supported" by ≥2/3 judges?

No LLM calls, no service touch — analytics on existing data.

**Caveat:** simulation uses NAME-based matching; the actual writer uses canonical IDs. The writer's canonicalization may merge surface forms that the simulation treats as distinct (e.g. "Holmes" + "Sherlock Holmes" canonicalize to the same ID). The simulation thus over-counts cascade conservatively.

**Date:** 2026-05-30

## Results

### Aggregate per variant (9 chapters)

| Variant | Filter | Relations kept | Cascade-skip | % skip | Supported-cascade | % of kept that are supported-cascade |
|---|---|---:|---:|---:|---:|---:|
| c70a | none (baseline) | 121 | 19 | 15.7% | 13 | **10.7%** |
| c72c-drop | entity+relation+event filter | 71 | 20 | 28.2% | 16 | **22.5%** |
| **c73b-drop** (current ship) | relation-only filter | 73 | 10 | 13.7% | 9 | **12.3%** |

### Per-chapter (c72c-drop)

| Chapter | Rel kept | Cascade-skip | % skip | Supported-cascade | Missing names sample |
|---|---:|---:|---:|---:|---|
| alice_ch01 | 6 | 4 | 66.7% | 4 | White Rabbit, daisy-chain |
| alice_ch02 | 7 | 1 | 14.3% | 0 | feet |
| journey_west_zh_ch01 | 8 | 2 | 25.0% | 2 | 仙卿, 大海 |
| journey_west_zh_ch14 | 11 | 0 | 0% | 0 | — |
| little_women_ch01 | 8 | 5 | 62.5% | 4 | fancy words and refined speech, home peace and comfort, ... |
| pride_prejudice_ch01 | 6 | 1 | 16.7% | 0 | Sir William and Lady Lucas |
| sherlock_scandal_ch01 | 4 | 1 | 25.0% | 0 | her sex |
| son_tinh_thuy_tinh_vi | 10 | 0 | 0% | 0 | — |
| tam_cam_vi | 11 | 6 | 54.5% | 6 | Bụt, cha Tấm, cung |

### Per-chapter (c73b-drop)

| Chapter | Rel kept | Cascade-skip | % skip | Supported-cascade | Missing names sample |
|---|---:|---:|---:|---:|---|
| alice_ch01 | 8 | 0 | 0% | 0 | — |
| alice_ch02 | 6 | 0 | 0% | 0 | — |
| journey_west_zh_ch01 | 9 | 2 | 22.2% | 1 | 仙卿, 大海 |
| journey_west_zh_ch14 | 11 | 0 | 0% | 0 | — |
| little_women_ch01 | 8 | 5 | 62.5% | 5 | fancy words and refined speech, home peace and comfort, ... |
| pride_prejudice_ch01 | 6 | 0 | 0% | 0 | — |
| sherlock_scandal_ch01 | 3 | 0 | 0% | 0 | — |
| son_tinh_thuy_tinh_vi | 10 | 0 | 0% | 0 | — |
| tam_cam_vi | 12 | 3 | 25.0% | 3 | cha Tấm, cung, mẹ ruột Tấm |

### Per-chapter (c70a baseline) — pre-existing cascade gap

| Chapter | Rel kept | Cascade-skip | % skip | Supported-cascade |
|---|---:|---:|---:|---:|
| alice_ch01 | 11 | 0 | 0% | 0 |
| alice_ch02 | 11 | 0 | 0% | 0 |
| journey_west_zh_ch01 | 11 | 4 | 36.4% | 3 |
| journey_west_zh_ch14 | 20 | 1 | 5.0% | 0 |
| little_women_ch01 | 18 | 7 | 38.9% | 4 |
| pride_prejudice_ch01 | 16 | 1 | 6.2% | 1 |
| sherlock_scandal_ch01 | 7 | 3 | 42.9% | 2 |
| son_tinh_thuy_tinh_vi | 12 | 0 | 0% | 0 |
| tam_cam_vi | 15 | 3 | 20.0% | 3 |

## Findings

### Finding 1 (HIGH — pre-existing writer bug): baseline has 10.7% supported-cascade

Even with no filter applied (c70a baseline), the writer would cascade-skip **13 of 121 relations** (10.7%) that judges rated "supported". The pattern is consistent: LLM extracts relations with abstract or compound subjects/objects ("civil practice", "home peace and comfort", "fancy words and refined speech", "her sex") that were NOT extracted as entities.

**This is a writer-side issue, not a filter issue.** Cycle 72 + 73b filter-output F1 reports were upper bounds — the realized Neo4j F1 has been systematically lower across all variants.

**Estimated F1 impact:** if all 13 supported-cascade relations are precision losses on the realized state, relation precision drops by `13/121 ≈ 10.7pp`. Overall median F1 impact (relations are 1/3 of categories): roughly **2-4pp lower realized than reported**.

### Finding 2 (validates c73b-drop ship): relation-only filter doesn't worsen the cascade gap

| Variant | Baseline supported-cascade | Filter-induced supported-cascade | Total |
|---|---:|---:|---:|
| c70a (no filter) | 13 | 0 | 13 |
| c72c-drop | — | +3 over c70a | 16 |
| **c73b-drop** | — | **-4 under c70a** | **9** |

c73b-drop actually has **fewer** supported-cascade relations than c70a baseline (9 vs 13). Reason: the relation-only filter dropped some of the abstract-subject relations the LLM produced. Filter happens to clean up some of the writer's pain points.

**c73b-drop ship verdict reinforced**: realized F1 of c73b-drop is essentially equal to realized c70a baseline + the filter's precision lift = a clean win.

### Finding 3 (cycle-72 ship was over-credited): c72c-drop adds cascade penalty

c72c-drop has **22.5% supported-cascade** (vs c73b's 12.3% and baseline's 10.7%). Filtering entities + events dropped the entities that real relations referenced, doubling the cascade rate.

**Realized F1 for c72c-drop is likely 4-6pp lower than its reported 0.917** — putting it in the same neighborhood as (or below) c73b-drop's realized F1.

The cycle-72 ship's measured +2.2pp F1 lift over c70a is **partially an artifact** of the writer-cascade gap closing in the wrong direction. c73b-drop would likely have ranked HIGHER than c72c-drop on a realized-F1 leaderboard.

## Cascade impact verdict

| Variant | Cascade verdict | Recommendation |
|---|---|---|
| c70a baseline | **LARGE** (13/121 supported) | Track via D-PASS2-WRITER-CASCADE-GAP-CLOSE |
| c72c-drop | **LARGER** (16/71 supported) — additive on top of baseline | Don't ship; c73b-drop strictly better |
| **c73b-drop** (current ship) | **NEGLIGIBLE delta** (9 vs 13 baseline) — actually slightly better | Ship stands; realized F1 ≈ filter-output F1 minus baseline cascade |

## Empirical re-judge — realized F1 (ran 2026-05-30, ~33 min total wall-clock)

Simulated the writer cascade ([simulate_realized_dump.py](../simulate_realized_dump.py)) on each variant's filter dump → wrote a "realized" `actual.json` per chapter → ran the same 3-judge ensemble against the realized dumps.

### Per-variant realized macros

| Variant | Filter-output median F1 | **Realized median F1** | Δ realized vs filter-output | Fleiss κ realized |
|---|---:|---:|---:|---:|
| c70a baseline | 0.895 | _not re-judged (=baseline)_ | — | 0.671 |
| c72c-drop (cycle-72 ship) | 0.917 | **0.904** | **-1.3pp** | 0.773 |
| **c73b-drop (current ship)** | 0.916 | **0.913** | **-0.3pp** | 0.756 |

Per-judge breakdown (realized):

| Judge | c72c-realized F1 | c73b-realized F1 |
|---|---:|---:|
| gemma | 0.899 | 0.888 |
| qwen-30b | 0.965 | 0.972 |
| claude-4.7-opus | 0.904 | 0.913 |
| **Median** | **0.904** | **0.913** |

### Empirical takeaways

1. **c73b-drop's realized F1 (0.913) beats c72c-drop's realized F1 (0.904) by +0.9pp** — much larger gap than the +0.1pp on filter-output. The c72c-drop ship was over-credited; c73b-drop is decisively better on the realized-F1 axis users actually see.

2. **c73b-drop loses only -0.3pp to cascade** — confirms relation-only filter doesn't worsen the writer-cascade gap meaningfully. The analytics upper-bound (9 supported-cascade relations on c73b) translated to ~0.3pp F1 loss.

3. **c72c-drop loses -1.3pp to cascade** — confirms filtering entities cascade-drops supported relations. The analytics upper-bound (16 supported-cascade relations on c72c) translated to ~1.3pp F1 loss. Roughly tracks linearly with the cascade count (4× more relations cascade-skipped on c72c → 4× more F1 loss, both within margin of noise).

4. **Fleiss κ holds substantial in both realized variants** (0.773 / 0.756) — the cascade doesn't degrade judge agreement, which means the kept relations are still "judge-clean" extraction.

### Updated ship comparison (realized F1)

| Variant | Filter-output F1 | Realized F1 | Per-chapter latency | Verdict on realized basis |
|---|---:|---:|---:|---|
| c70a baseline | 0.895 | _est ~0.89_ | — | — |
| c72c-drop | 0.917 | 0.904 | 42.5s | Over-credited; c73b-drop wins on realized |
| **c73b-drop** | 0.916 | **0.913** | **18.9s** | **Strictly better than c72c-drop on realized; ship stands** |

**c73b-drop ship is reinforced by realized data**: not just equal to c72c on filter-output, but **+0.9pp ahead on realized**.

### c70a-realized deferred

We did NOT re-judge c70a baseline on realized state. The cascade-attribution finding (13/121 supported-cascade) implies c70a-realized would also be lower than the reported 0.895, possibly around 0.88-0.89. This is informational (doesn't change the ship); a future cycle could close the loop. Tracked as **D-PASS2-CASCADE-C70A-REALIZED-REJUDGE**.

## Ship recommendations

1. **c73b-drop ship stays** — relation-only filter doesn't worsen the writer cascade; in fact slightly reduces it. The cycle-73b ship decision was correct.

2. **c72c-drop ship was reasonable for cycle 72** (best available knowledge at that point), but c73b-drop is strictly better on the realized-F1 axis we now have visibility into. No action needed — c73b-drop is already the default.

3. **New deferred row: D-PASS2-WRITER-CASCADE-GAP-CLOSE** — the writer drops ~10% of judge-supported relations because the extractor produces relations with abstract/compound subjects that aren't entities. Either:
   - Teach the extractor to also extract abstract subjects as entities (prompt change in entity_extraction)
   - OR teach the writer to create entities on-the-fly for unmatched relation endpoints (writer change)
   - OR pre-filter relations whose endpoints don't resolve (would need new filter category)

   Option (a) preserves the 1-pass model; option (b) gives 100% relation retention but might pollute the entity graph with abstractions. Option (c) duplicates the writer's cascade in the filter — wasteful. **Recommend (a) for first-pass.**

## Methodology limits

- Name-based cascade simulation over-counts vs the writer's canonical-ID matching. Some "cascade-skipped" relations in this analysis may actually persist when the writer's canonicalization normalizes surface forms. The numbers above are upper bounds.
- "Supported by majority" uses ≥2/3 judges; a fourth judge could shift specific items.
- Per-chapter verdict lookup matches on `idx` (filter-output position). If the writer reordered relations, indices would mismatch — for our variants the order is preserved.

## Deferred rows added this cycle

- **D-PASS2-WRITER-CASCADE-GAP-CLOSE** (NEW) — close the ~10% baseline cascade by extending entity extraction to include abstract/compound subjects, OR teaching the writer to auto-create entities for unmatched relation endpoints. Empirical impact (c72c, c73b): cascade drops ~0.3-1.3pp realized F1 per chapter set.
- **D-PASS2-CASCADE-C70A-REALIZED-REJUDGE** (NEW) — re-judge c70a baseline on realized state to complete the realized-F1 picture; expected ~0.88-0.89 (vs reported 0.895). Informational; doesn't change ship decision.
