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

| Stage | Builds | Fixes | Size | Acceptance metric |
|---|---|---|---|---|
| **S1** 🎯 | **Relief amplified from the uplift field** — replace `land_relief`'s independent ridged-fBm with ridged detail **scaled by local tectonic uplift**, so mountains rise AT convergent/collision belts. | D1 | L | `% Mountain cells on/near a convergent boundary` rises from **0 %** to a high share (target ≥ 60 %); visible ranges trace the belts. |
| **S2** | **All boundary kinds fire** — bias plate motion/selection so continent–continent collision, ocean ridges, island arcs actually occur; verify per-kind uplift contributes. | D3 | M | All 6 `BoundaryKind`s present across a seed sweep; `FoldMountain` belts produce the highest peaks. |
| **S3** | **Crustal-thickness isostasy + hypsometric calibration** — base height from `crust_thickness` (collision thickening), replacing the two constants; calibrate the quantize so the histogram is bimodal and matches Earth bands. | D2, D6 | L | Elevation histogram is **bimodal**; continental & oceanic modes within tolerance of the ETOPO1 targets. |
| **S4** | **Age-based bathymetry** — assign `crust_age` (BFS from divergent ridges along spreading), set ocean depth = isostatic base + `√age` (GDH1), replacing the coast-distance curve. | D4 | L | Depth increases monotonically with age from ridges; ridge crests shallow, old abyss deep + flat. |
| **S5** | **Coupled uplift ⇄ erosion** — feed the tectonic uplift as the `U` source into the existing stream-power `erosion.rs` and iterate uplift+incision jointly toward steady state (Cordonnier). | D5 | XL | Equilibrium river profiles concave (`S ∝ A^(−0.5)` within tolerance); dendritic drainage on the tectonic relief, not on noise. |
| **S6** | **Render/export bathymetry fix** — `relief.rs` suppress fBm detail below sea; `export.rs` give the `.glb` real (exaggerated) ocean depth instead of a flat clamp; final hypsometry calibration pass. | D7 | M | In every render/glb, ocean surface is below the coast everywhere; bathymetry visible. |

**Dependency order:** S1 → S2 → S3 → S4 → S5 → S6 (each builds on the prior; S1
alone already fixes the headline defect). S2 can land with S1 if convenient.

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
