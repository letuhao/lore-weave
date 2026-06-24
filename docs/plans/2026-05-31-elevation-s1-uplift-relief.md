# Plan — Elevation redesign **S1+S2 (merged)**: tectonic relief + a plate model that actually collides

> Stages 1+2 of the 6-stage arc ([`docs/specs/2026-05-31-elevation-redesign.md`](../specs/2026-05-31-elevation-redesign.md)).
> Size **XL**. Session 100 cont. PO chose to **merge S1+S2** after the S1 baseline
> measurement showed S1-alone is metric-neutral.

## ⚠ Premise correction (empirical, this session)

The spec's D1 ("mountains are noise; 0 % of Mountain cells near a convergent
boundary") is a **measurement artifact** — it counted only `Mountain`-biome
cells and ignored cold high belts labelled `Glacier`. Measured by **elevation**
(high-relief = `land_t ≥ 0.55`), the *existing* model already concentrates
relief on convergent belts: `conc≤1 ≈ 37 %`, `conc≤2 ≈ 69 %`, continental-arc
fill `≈ 44 %`. The S1 uplift-gating refactor (kept, `TECT_UPLIFT_LO=0.20`)
**matches** this baseline exactly — altitude-gating was already implicitly
uplift-coupled (`altitude = base + uplift`).

**The real, visible defect is upstream in the plate model (was scoped S2):**
convergence is **rare and weak**. Across the seed sweep the boundary census is
~75–80 % **Fault** (11–16/seed) vs 0–3 convergent/seed; **`FoldMountain` never
fires**; and **3 of 6 seeds are pancake-flat** (`max_land_t = 0.20`) because they
have no continental-convergent boundary. That is why "elevation depends on
collision" is invisible — collisions barely happen.

## S2 work (the real fix) — `crates/world-gen/src/plates.rs`

1. **Break fault dominance** — `boundary_kind_for_pair` calls *every* boundary
   with `tangential > |normal|` a `Fault`; with random motion that is most of
   them. Replace with a shear-ratio / angle gate (`Fault` only when shear
   *strongly* dominates, e.g. `tangential > FAULT_SHEAR_RATIO·|normal|`), so
   head-on motion classifies as convergent/divergent. → many more
   Subduction/Ridge/Rift/Fold boundaries; fewer flat worlds.
2. **Fold belts can fire** — once mixed-motion continental pairs are no longer
   mis-called Fault, adjacent continental-continental convergence yields
   `FoldMountain`. Verify it appears across the sweep (S2 metric: all 6 kinds
   present). If still absent, mildly bias continental-plate adjacency.
3. **Uplift reliability** — confirm a convergent boundary reliably lifts its
   continental side into the Mountain band (no `max_land_t 0.20` worlds *when a
   continental-convergent boundary exists*). Scale peaks only if measurement
   demands it.
4. **Determinism preserved** — classification change touches **no RNG draw**
   (seeds/motion/shuffle identical); only boundary *kinds* + uplift change.
   `content_hash` re-bases.

## Merged metric (real improvement, not the artifact)

- **All 6 `BoundaryKind`s present** across the seed sweep (incl. `FoldMountain`).
- **Fault share** drops from ~75–80 % to a sane minority (target ≲ 45 %).
- **No flat worlds with convergence**: every seed possessing a continental
  convergent boundary reaches the Mountain band (`max_land_t ≥ 0.55`); the count
  of pancake worlds drops.
- **Concentration preserved**: high-relief `conc≤2 ≥ 60 %`, continental-arc fill
  `≥ 40 %` (must not regress from baseline).
- Biome/climate proportion regression check; determinism; fresh `content_hash`.

---

## (Original S1 plan — relief amplified from the tectonic uplift field; kept)

> Fixes **D1** — relief now driven by the uplift field, not altitude. Foundation
> for S3 (isostasy) / S5 (coupled erosion). Metric-neutral vs baseline.

## 0 — Empirical baseline (this session, seed sweep {7,13,42,99,123,2024} × Continent+SuperContinent)

Measured with `tests/tectonic_relief.rs::s1_diagnostic_breakdown`:

| symptom | data | meaning |
|---|---|---|
| **No FoldMountain ever** | tag-1 absent in all 12 runs | D3 — continent–continent collision never fires (→ **S2**, not S1). |
| **Flat worlds** | seeds 13, 42: `max_land_t = 0.20` | No continental-convergent boundary ⇒ world is just the `CONT_BASE 0.10` platform. Consistent with "no collision ⇒ no relief"; making collisions common is **S2**. |
| **Arc fails to raise a range** | seed 99: Subduction present, `arc-land 18`, **`arc-mtn 0`** | The broad `ARC_PEAK` bulge + *independent* ridged-fBm ⇒ only sparse noise-crest cells clear the Mountain band; the belt is speckle, not a range. **This is D1.** |
| **Belt under-filled** | seeds 7/123: `arc-land ~150`, `arc-mtn ~23`, `arc-glac ~45` | Only ~16 % of the convergent-arc band is Mountain biome; `on-conv ≈ 0 %` — peaks placed by noise, not at the suture. |
| **Glacier steals Mountain** | cold arcs → `arc-glac` ≫ `arc-mtn` | A glaciated high range is still high relief; the metric must be **climate-independent**. |

**Conclusion.** The spec's shorthand ("0 % of Mountain cells near convergent") is imprecise: with the altitude-gated ruggedness, mountains already only *form* near boundaries (near-conv share is ~100 % when any exist). The true D1 defect is that **convergent uplift produces a broad smooth bulge whose peaks are decided by independent noise**, so belts are under-filled / speckled / sometimes empty, and peaks never sit on the suture.

## 1 — Metric (refined, climate-independent)

A **high-relief cell** = land cell with `land_t = (elev−sea)/(65535−sea) ≥ 0.55` (the Mountain elevation band biome already uses; counts Mountain **and** Glacier and any high cell).

Convergent boundary kinds: `FoldMountain`, `Subduction`, `IslandArc`. Continental-arc kinds (raise *land*): `FoldMountain`, `Subduction`.

- **M1 — belt fill** (headline): aggregated over seeds that have a continental-arc boundary, `high_relief_arc / arc_land ≥ 0.60`, where `arc_land` = land cells ≤1 hop from a `Subduction`/`FoldMountain` boundary. *Collisions raise a continuous range, not speckle.* (Baseline ≈ 0.11–0.44.)
- **M2 — on-suture concentration** (guard): of all high-relief cells, `≥ 0.70` lie within ≤2 hops of any convergent boundary. *Peaks belong to belts, not noise.*
- **Determinism**: byte-identical re-run (existing `tests/determinism.rs` + a fresh `content_hash` per run — no literal pin).
- **Biome/climate regression**: dump the biome histogram before/after; no catastrophic skew (Mountain/Hill/Plain shares stay sane). Highland-gate proportions stay sane.

## 2 — Implementation (`crates/world-gen/src/terrain.rs`, Tectonic branch)

Replace the **altitude-gated ruggedness** relief with **convergent-uplift-gated relief**:

1. Per land cell, `uplift_pos = plates.uplift[i].max(0.0)` — the convergent orogeny signal (folds + arcs are `+`; rifts/trenches are `−` ⇒ excluded).
2. `tect = smoothstep(TECT_LO, TECT_HI, uplift_pos)` — relief amplitude that is **0 in plate interiors** and ramps to 1 across a convergent belt. (Tunable; start `TECT_LO≈0.06`, `TECT_HI≈0.45` so even modest arc uplift fills the band.)
3. Keep a **small** organic interior ruggedness `interior` (the existing low-freq fBm uplands term, re-derived **without** the altitude smoothstep so it no longer rings every coast), capped so it alone never reaches the Mountain band (`≤ ~0.30`).
4. `amp = tect.max(interior)`; `relief = land_relief(p, amp, tect, seed)` where the **ridged ranges are scaled by `tect`** (belts) and the gentle hills by `amp`. The ridged term gets enough weight that `macro + tect·ridges` clears `land_t 0.55` continuously across the belt and **peaks at the uplift maximum** (the suture), decaying out with the uplift.
5. Feed `amp` (not the old `rugged`) to `erosion::apply` as the incision gate (mountains carve, plains stay flat).

`ruggedness()` is replaced by `relief_amp()` (uplift-driven); `land_relief()` signature gains the `tect` term. No change to `quantize_fixed_scale`, sea level, ocean path (that's S3/S4/S6). Constants are calibrated empirically against M1/M2 + the biome histogram.

**Out of scope for S1** (tracked): FoldMountain firing / flat no-collision worlds (**S2**); crustal-thickness isostasy + hypsometric calibration (**S3**); bathymetry (**S4**); coupled erosion (**S5**); render/export ocean (**S6**). Glacier-vs-Mountain naming at cold belts is *correct* and left as-is.

## 3 — Steps

1. ✅ Baseline diagnostic harness (`tests/tectonic_relief.rs`).
2. Implement the uplift-driven relief in `terrain.rs`; keep determinism discipline.
3. Convert `mountains_trace_convergent_belts` into the M1+M2 acceptance test.
4. Calibrate constants vs M1≥0.60 / M2≥0.70 + biome histogram (iterate).
5. VERIFY: full `cargo test -p world-gen`; biome-proportion before/after; determinism.
6. REVIEW (2-stage) + `/review-impl` + POST-REVIEW (human).

## 4 — Risks

- **Over-filling** → too many mountains / desert-style monotony of peaks. Guard: M2 + biome histogram (Mountain share must stay a minority).
- **Erosion coupling**: amp now gates erosion; ensure plains (amp≈0) still don't incise and belts still carve valleys.
- **Determinism**: all new fields index-ordered, same noise salts; `content_hash` re-bases (no literal pin). Frozen flat track untouched.
