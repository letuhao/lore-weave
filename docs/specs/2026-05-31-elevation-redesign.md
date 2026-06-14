# Spec — physically-grounded elevation redesign (arc)

> **Task size: XL arc (6 staged sub-ships).** Redesign the sphere terrain
> elevation so it is driven by **plate tectonics + isostasy + erosion** per real
> geology, instead of procedural noise weakly coupled to tectonics. Session 100
> cont. Research basis: [`docs/research/2026-05-31-geological-elevation.md`](../research/2026-05-31-geological-elevation.md)
> (Cortial 2019 *Procedural Tectonic Planets*; Cordonnier 2016; Stein & Stein 1992
> GDH1; Whipple & Tucker 1999; NOAA ETOPO1 hypsometry).

---

## 0 — The defect (empirically verified, seed-7 megaplanet)

The current `terrain.rs` Tectonic pipeline is `plate base (const) + boundary
orogeny uplift (broad) + **ridged-fBm relief (the VISIBLE mountains, gated by an
altitude+noise "ruggedness" field, INDEPENDENT of tectonics)** + post-process
erosion + fixed-scale quantize`. Measured consequences:

- **D1 🔴 mountains are noise, not tectonics** — 0 % of `Mountain` cells lie on/near
  a convergent boundary. The peaks come from `land_relief`'s ridged-fBm, decoupled
  from the uplift field.
- **D2** isostasy is two constants (`CONT_BASE +0.10` / `OCEAN_BASE −0.55`), not
  crust-thickness-driven → no crustal thickening at collisions → no high fold mtns.
- **D3** boundary kinds under-fire — seed-7 produced only Fault/Subduction/Rift; no
  `FoldMountain` (continent–continent), `Ridge` (ocean divergent), or `IslandArc`.
- **D4** bathymetry is coast-distance-driven (`ocean_depth(coast_dist)`), not
  oceanic-crust-age — no shallow ridges, no proper abyssal age structure.
- **D5** erosion (real stream-power, `K·A^m·S^n`, already in `erosion.rs`) runs as a
  **post-process on the noise**, not **coupled** with uplift toward equilibrium.
- **D6** no calibration to Earth's **bimodal hypsometric curve** (the realism target).
- **D7** render/export artifacts: `relief.rs` fBm `detail` bumps the flat ocean floor
  and the `.glb` clamps ocean to a flat sphere → the "ocean rises above land" visual;
  no real bathymetry in the export. (Raw model is correct: ocean < sea < land.)

## 1 — The correct pipeline (from research)

Real elevation = a **sequence**, not a sum-of-noise:

1. **Isostatic 2-mode base** — per-cell base height from crust *type + thickness*
   (continental 10→80 km floats high; oceanic ~7 km sits low). Source of the
   **bimodal** distribution. `h_iso ∝ (ρ_mantle − ρ_crust)/ρ_mantle · thickness − c`.
2. **Tectonic uplift field** — a volumetric uplift map from boundary *type*:
   convergent ocean–continent → arc (+) + trench (−); ocean–ocean → island arc (+) +
   trench (−); continent–continent → broad crustal-thickening uplift (+, no trench);
   divergent → ridge (+, ocean) / rift (−, continent); transform → minor fault relief.
3. **Oceanic bathymetry by crust age** — depth grows as `√age` from the spreading
   ridge and flattens for old crust (GDH1: `d = 2600 + 365·√t` m, `t` in Myr; flatten
   ≳ 80 Myr). Ridges shallow, abyssal plains deep.
4. **Coupled uplift ⇄ erosion** — relief is **amplified from the uplift field** (peaks
   where uplift is high) then carved by stream-power fluvial incision + hillslope
   diffusion toward an **uplift/erosion steady state** (`dh/dt = U − K·A^m·S^n`;
   equilibrium `S ∝ A^(−m/n)`, Flint's law, `m/n ≈ 0.5`).

Finally quantize, **calibrated** so the elevation histogram matches the bimodal
hypsometric target (continental mode ~+0.1 km above sea, oceanic mode ~−4.3 km).

## 2 — Data-model additions (`world_map.rs`, feed `content_hash`)

- `crust_age: Vec<u32>` — oceanic-crust age proxy per cell (hops from nearest
  divergent ridge along spreading; 0 = ridge). Drives bathymetry (S4).
- `crust_thickness: Vec<f32>` — per-cell crustal thickness (continental base +
  collision thickening near convergent continental boundaries). Drives isostasy (S3).
- Keep/repurpose `plates.uplift` as the unified tectonic uplift field (S1/S2).

`content_hash` re-bases each stage (terrain change). No literal hash pinned.

## 3 — Staged plan (each stage is independently shippable, with a metric)

> **⚠ Premise correction (S1+S2 BUILD, session 100).** The D1 premise ("mountains
> are noise; 0 % near convergent") was a **measurement artifact** — it counted
> only `Mountain`-biome cells and ignored cold high belts labelled `Glacier`.
> Measured by **elevation** (high-relief = `land_t ≥ 0.55`) the pre-existing model
> *already* concentrated relief on convergent belts (`conc≤2 ≈ 69 %`, arc-fill
> `≈ 44 %`): its altitude-gated ruggedness was implicitly uplift-coupled
> (`altitude = base + uplift`). So **S1 alone is metric-neutral**. The real,
> visible defect was upstream in the plate model (was scoped S2): convergence was
> **rare and weak** (~78 % of boundaries mis-classified `Fault`; `FoldMountain`
> never fired; 50 % of seeds pancake-flat). **PO merged S1+S2** — both shipped
> together (commit, session 100). See
> `docs/plans/2026-05-31-elevation-s1-uplift-relief.md`.

| Stage | Builds | Fixes | Size | Acceptance metric |
|---|---|---|---|---|
| **S1 ✅** | **Relief amplified from the uplift field** — `land_relief` ridged detail **scaled by local tectonic uplift** (`TECT_*` in `terrain.rs`), mountains rise AT the belts. *(Metric-neutral refactor — see premise correction; foundation for S3/S5.)* | D1 | L | high-relief `conc≤2 ≥ 60 %` (achieved 70 %), continental-arc fill `≥ 40 %` (45 %); no regression vs baseline. |
| **S2 ✅** | **The plate model collides** — `FAULT_SHEAR_RATIO` (`plates.rs`) stops ~78 % of boundaries being mis-called `Fault`; the normal-component sign then decides convergent/divergent, so continent–continent `FoldMountain`, ocean ridges, island arcs all occur. | D3 | M | All 6 `BoundaryKind`s present across a 60-seed sweep (`FoldMountain` 29/60); Fault share 78 %→38 %; pancake-flat worlds 50 %→3 %. |
| **S3 ✅** | **Crustal-thickness isostasy** — the base is now `crust_thickness`-driven (Airy: oceanic 7 km → `OCEAN_BASE`, continental 35 km → `CONT_BASE`, collision thickening to 70 km → broad isostatic shoulder), replacing the two constants. Bimodality verified + locked. | D2, D6 | L | Histogram **bimodal** (ocean mode < sea < land mode, antimode dip between — locked by `elevation_histogram_is_bimodal`). Collision highland belt broadens from ~2→~4 hops: high-relief `conc≤4` **99 %** (vs the old `conc≤2`), arc-fill 58 %; mountains 10 % of land. **Note:** the dramatic Tibet-plateau *magnitude* is left modest (a deeper uplift⇄isostasy reconciliation would over-broaden the Mountain band / fight the relief tuning) — the thickness-driven *mechanism* is the D2 win, magnitude tunable later. |
| **S4 ✅** | **Age-based bathymetry** — `Plates::crust_age` (BFS from divergent `Ridge` boundaries over oceanic crust; `0` = ridge, `u32::MAX` = continental / no-ridge). Ocean depth is now `ocean_ridge + (ocean_abyss−ocean_ridge)·√(min(age/ocean_age_flatten,1))` blended with a preserved coastal shelf, replacing the coast-distance curve. (`crust_age` lives on `Plates`, not `WorldMap`, matching S3's `crust_thickness`; feeds `content_hash` via elevation.) | D4 | L | **Achieved:** mean open-ocean depth strictly deepens across crust-age quartiles; ridge crests shallow, sentinel-age → abyss. The deep-abyss spike that piled **51 %** of ocean cells into the single deepest bin dropped to **~20 %**, ocean depth now spans 8 bins (broad abyssal mode). Bimodality (S3) + land/Desert/Marsh proportion guards still hold. `tests/age_bathymetry.rs` + plates/terrain unit tests. |
| **S5 ✅** | **Coupled uplift ⇄ erosion** — `erosion::couple` iterates `dh/dt = U − K·A^m·S^n + D·∇²h` (detachment-limited): each step forces land up by the tectonic uplift field then runs one stream-power incision + hillslope-diffusion pass. The land surface is now `base + uplift skeleton + plains whisper` carved to a fluvial steady state — the ridged-fBm "noise mountains" (`land_relief`) are **retired**, so relief emerges from physics, not noise. (PO chose the full rewrite over augment.) | D5 | XL | **Achieved:** slope–area concavity θ **0.81 → 0.59** (toward the 0.5 steady state; new guard `river_profiles_are_concave_at_steady_state`, band [0.40,0.72]). Belt concentration *improved* (high-relief `conc≤4` 100 %, arc-fill 58 %→79 % — relief is the uplift, carved). Land/Desert/Marsh proportions + bimodality (S3) + mountains-minority all hold. Defaults worked first try (no tuning). |
| **S6 ✅** | **Render/export bathymetry fix** — `relief.rs` detail gate retuned to `smoothstep(0, 0.04, land_t)` so fBm detail is **0 at/below sea** (was ≈0.97 at sea → it bumped the ocean floor); `export.rs` `.glb` ocean floor displaces to its **real exaggerated depth** (`h = water ? e.min(sea) : e.max(sea)`) instead of a flat sea clamp, with pole rows given a uniform radius. **Render/export only — `content_hash` unchanged** (model bathymetry was already correct after S4). | D7 | M | **Achieved:** glb ocean sinks below the sea radius (ridges shallow, abyss deep, depth range > 0.01), land rises above, coastline at sea (`ocean_sinks_below_sea_and_land_rises`); sub-sea detail suppressed (`sub_sea_detail_is_suppressed`); the `water_color`/heightmap depth ramp reads clean S4 bathymetry. 8 render pins re-captured; content pins unchanged. |

**Dependency order:** ~~S1~~ → ~~S2~~ (✅ together) → ~~S3~~ (✅) → ~~S4~~ (✅) → ~~S5~~ (✅) → ~~S6~~ (✅).
**🏔 ELEVATION-REDESIGN ARC COMPLETE (S1–S6, 2026-06-14).** Elevation is now driven
by plate tectonics + crustal-thickness isostasy + age-based bathymetry + coupled
uplift⇄erosion, rendered/exported with real bathymetry — matching the bimodal
hypsometric target, all D1–D7 closed.
**Deferred cleanup:** `D-S5-DEAD-RELIEF-PARAMS` — remove the 7 now-inert
`ReliefParams` ridged-relief fields (`tect_belt_lift`, `tect_range_weight`,
`tect_uplift_lo/hi`, `interior_rugged_cap`, `rugged_freq`, `tec_hill_weight`).

## 4 — Cross-cutting rules

- **Determinism preserved** — all new fields from index-ordered BFS/flood-fills +
  ascending-id tie-breaks (the `plates.rs`/`feature.rs` discipline). `content_hash`
  re-bases per stage; no literal hash pin (run-vs-run).
- **Frozen flat track untouched** — `flat_climate.rs`/`flatworld.rs`/`zonegen.rs`/
  `civ_adapter.rs` unchanged throughout.
- **Downstream contract** — `biome.rs`/climate/hydrology read `elevation: u16` +
  `sea_level`; keep those types. Only the *values* become geologically correct.
- **Downstream recalibration (biome + climate) — REQUIRED per stage.** The refactor
  changes the elevation *distribution* (more bimodal; mountains concentrated at
  tectonic belts), so the elevation-band thresholds tuned for the old noise
  distribution will skew biome/climate proportions if left as-is:
  - `biome.rs` land tiers `land_t ≥ 0.22` (Hill) / `≥ 0.55` (Mountain) — recalibrate
    so Mountain/Hill/Plain shares stay sensible against the new distribution.
  - `climate.rs` Highland gate `elev_above > 0.30` (+ the `LAPSE_C` lapse) —
    recalibrate so Highland/Glacier proportions and mountain coldness stay sane.
  - **Net effect is an improvement** — Mountain/Highland will then sit on the
    tectonic belts (geologically correct) and the lapse will cool *real* mountains.
  - **Per-stage VERIFY adds a biome/climate-proportion regression check** (dump the
    biome histogram before/after; no catastrophic skew). A final **biome/Highland
    threshold recalibration** lands in S3 (when the hypsometric distribution settles)
    and is re-checked in S6.
- **Per-stage workflow** — each stage runs the full 12-phase (its own plan file +
  VERIFY metric + `/review-impl` + POST-REVIEW). Calibration is empirical
  (histogram + the metric), no literal hash pinned.

## 5 — Out of scope (this arc)

True time-stepped plate simulation (plates stay static per generation — phenomenological,
per Cortial); mantle convection; sediment stratigraphy; glacial/aeolian erosion;
sea-level eustasy. The export's in-app 3D viewer (separate track).
