# Plan — Elevation redesign **S3**: crustal-thickness isostasy + hypsometric lock

> Stage 3 of the arc ([`docs/specs/2026-05-31-elevation-redesign.md`](../specs/2026-05-31-elevation-redesign.md)).
> Fixes **D2** (isostasy is two constants) + **D6** (no bimodal calibration). Size **L**. Session 100 cont.

## 0 — Empirical baseline (this session, default Continent sweep)

`zz_tmp_hypsometry` (20-bin elevation histogram, sea ≈ bin 8):
- **Already bimodal**: ocean mode bin 0 (37 %, the deep-abyss `OCEAN_FULL` clamp), land mode bins 9–10 (22 %, the `CONT_BASE +0.10` platform just above sea), antimode dip bin 8 (1.4 %, shoreline).
- **High-land shoulder is a cliff**: bin 10 (10 %) → bin 11 (0.8 %). The continental crust is a flat platform with sparse sharp peaks — **no broad uplands/plateaus** (the D2 symptom: collisions don't thicken crust → no Tibet-style high plateau).

So D6 (bimodality) is essentially already met; S3's measurable contribution is **D2** — fill the plateau shoulder with crustal-thickening isostasy at continental collisions — while **keeping** the distribution bimodal and the biome/land guards in band.

## 1 — Design (`crates/world-gen/src/plates.rs`)

Replace the two-constant base (`CONT_BASE 0.10` / `OCEAN_BASE −0.55`) with a
**crust-thickness-driven isostatic base** (Airy: thicker crust floats higher,
research finding #2 — continental crust 10→80 km, >80 at Himalaya-Tibet):

- New `crust_thickness: Vec<f32>` on `Plates` (km; internal, like `base`/`uplift`
  — determinism is captured via `elevation`, so it is **not** added to
  `WorldMap`/`content_hash`, matching the existing `base`/`uplift` pattern).
- `crust_thickness[i] = OCEAN_CRUST_KM (7)` for oceanic cells; `CONT_CRUST_KM (35)
  + collision thickening` for continental. **Collision thickening** = a *broad*
  (wider-decay than the orogeny uplift) ramp from convergent-continental
  boundaries (`FoldMountain`, `Subduction` continental side), up to
  `COLLISION_THICKEN_KM (35)` → 70 km Tibet. Reuses the existing
  `boundary_field` `(kind, dist)` with a wider `PLATEAU_HOPS` decay.
- `isostasy_base(thickness, continental)`: continental → `CONT_BASE +
  CONT_ISO_SLOPE·(thickness − CONT_CRUST_KM)` (calibrated: 35 km → +0.10, 70 km →
  ~+0.40 broad plateau); oceanic → `OCEAN_BASE` (uniform — oceanic thickness
  varies by *age*, deferred to S4). This is the broad plateau that fills the
  shoulder; the existing `uplift`/`tect` relief still adds ridges on top (fold
  cores clamp to white — Himalayas *are* max).

**No change to the uplift/`tect` relief, ocean path, or quantize on the first
pass** — the thickening is localized to collision zones (interiors stay +0.10,
oceans stay −0.55), so the change is low-risk. Recalibrate `quantize_fixed_scale`
only if the histogram needs it.

## 2 — Metric / acceptance

- **Bimodal lock** (D6): histogram has an ocean mode below sea, a land mode at/
  above sea, and an antimode between them strictly lower than both — assert it so
  a future stage can't silently collapse it.
- **Plateau shoulder** (D2): the high-land/upland band (land_t ∈ ~[0.3, 0.7])
  rises from the ~2 % cliff to a populated shoulder (collision plateaus exist).
- **Determinism** (no literal hash pin); `crust_thickness` finite + sane range.
- **Regression guards stay green** — `terrain_proportions_stay_in_band`
  (Desert/land/Marsh) + `mountains_stay_a_land_minority` (≤40 %): calibrate the
  thickening so plateaus don't over-mountain.

## 3 — Steps

1. ✅ Baseline histogram probe.
2. `crust_thickness` + `isostasy_base` in `plates.rs`; replace the const base.
3. Probe histogram + guards; calibrate `COLLISION_THICKEN_KM`/`CONT_ISO_SLOPE`/
   `PLATEAU_HOPS` (and quantize if needed).
4. Add the bimodality + plateau-shoulder acceptance test; `crust_thickness` unit
   test in `plates.rs`.
5. VERIFY full suite + determinism + guards; `/review-impl`; POST-REVIEW.

## 4 — Risks

- **Over-mountaining** from broad plateaus → caught by `mountains_stay_a_land_minority`.
- **Double-count** (base plateau + `uplift FOLD_PEAK`) inflates fold cores → they
  clamp to white (acceptable; the plateau is the broad-base win). Dial back
  thickening if guards trip.
- **Determinism**: `crust_thickness` from index-ordered `boundary_field` reuse;
  `content_hash` re-bases.
- Frozen flat track untouched; downstream `u16`+`sea_level` contract intact.
