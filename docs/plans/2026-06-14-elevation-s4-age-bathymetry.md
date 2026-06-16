# Plan — elevation S4: age-based oceanic bathymetry

> Stage S4 of the elevation-redesign arc
> (`docs/specs/2026-05-31-elevation-redesign.md`). Size **L**. Fixes **D4**
> (bathymetry was coast-distance-driven, not oceanic-crust-age) and the
> deep-abyss clamp that spikes the ocean mode.

## Premise (empirically verified on HEAD, seed sweep [7,13,42,99,123,2024] Continent)

The coast-distance depth curve (`ocean_depth(coast_dist)`) saturates at
`ocean_abyss_hops = 7`: every open-ocean cell ≥ 7 hops from any coast clamps to
`ocean_abyss`. Measured: **51.2 % of all ocean cells fall in the single deepest
elevation bin** (bin 0 of 20). The ocean has no depth structure — it is a flat
abyss with a thin coastal shelf. (Spec estimated ~37 %; the real number is worse.)

## The fix (from research §3 / GDH1 plate-cooling)

Oceanic lithosphere deepens with **age**: `d = 2600 + 365·√t` m (Stein & Stein
1992 GDH1), flattening for old crust (≳ 80 Myr). New crust is born shallow at
**divergent mid-ocean ridges** and sinks as it spreads away. Replace the
coast-distance curve with an **age-driven √age curve**: ridges shallow, abyss
deep, depth spread across the range instead of clamped.

## Design (locked)

### 1. `crust_age` — new per-cell field on `Plates` (`plates.rs`)

`crust_age: Vec<u32>` — BFS hops from the nearest **divergent ocean ridge**
along oceanic crust. `0` = a ridge cell.

- **Sources:** oceanic-plate cells adjacent to a `BoundaryKind::Ridge` pair
  (divergent oceanic — where new crust forms). `Rift` is continental divergent
  (a rift valley, not new ocean floor) → not a source.
- **Domain:** BFS traverses **oceanic-plate cells only** (`PlateKind::Oceanic`).
  Continental cells keep `u32::MAX` (irrelevant — land doesn't use bathymetry).
- **Unreachable oceanic cells** (an oceanic plate with no ridge boundary) stay
  `u32::MAX` → treated as maximally old → deep + flat (correct: old abyssal plain).
- **Determinism:** ascending-id seed sweep, sorted neighbour lists, first-writer-
  wins min-distance — the same discipline as `boundary_field`/`coast_distance`.

Stored on the `Plates` build struct, **not** `WorldMap` — consistent with S3's
`crust_thickness` (also Plates-only). It flows into `content_hash` via the
resulting `elevation` values. (Spec §2 floated WorldMap; S3 already chose Plates
for the sibling field, so we match it — no serde / `compute_hash` churn.)

### 2. Age → depth curve (`terrain.rs`)

Replace `ocean_depth(coast_dist, …)` with `ocean_depth_by_age(age, coast_dist, …)`:

```
age_depth = ocean_ridge + (ocean_abyss - ocean_ridge) · √(min(age/ocean_age_flatten, 1))
shelf_ramp = smoothstep(0, ocean_shelf_hops, coast_dist)
depth = ocean_shelf + (age_depth - ocean_shelf) · shelf_ramp  + ripple
```

- At a **ridge** (age 0) offshore: `age_depth = ocean_ridge` (shallow ridge crest).
- **Old crust** (age ≥ flatten, or unreachable `u32::MAX`): `age_depth = ocean_abyss`.
- **Coastal shelf preserved:** within `ocean_shelf_hops` of land, depth ramps from
  the shallow `ocean_shelf` to the age-driven open-ocean depth. The shelf is a
  real geological feature (submerged margin) and coastal shallows feed
  biome/settlement/`is_coast`; dropping it would regress those. The age-depth
  metric is asserted on **open-ocean** cells (coast_dist ≥ shelf_hops).
- `u32::MAX` age is safe in f32: `MAX/flatten` → huge → `min(1)` → `1` → abyss.

The arc-welding gate (`ocean_arc_gate_*` on coast_dist) is unchanged.

### 3. `ReliefParams` (`params.rs`)

- **Remove** `ocean_abyss_hops` (the dead coast-dist scale).
- **Add** `ocean_ridge` (ridge-crest depth, default **−0.26** ≈ GDH1 2600 m vs
  abyss 5800 m), `ocean_shelf_hops` (shelf ramp width, default **3.0**),
  `ocean_age_flatten` (√age saturation in hops, default **25.0**).
- `resolved()`: `ocean_ridge.clamp(-3,0)`, `ocean_shelf_hops.clamp(0.5,50)`,
  `ocean_age_flatten.clamp(0.5,200)`. `ocean_abyss` still scaled by the
  `ocean_depth` knob (deeper-abyss path unchanged).
- The example config / README reference only the `ocean_depth` knob, not the
  removed field → no doc breakage.

### 4. Pins to re-capture (S4 deliberately changes default ocean elevation)

- `tests/parameterization.rs::default_profile_is_byte_identical_baseline` (3 hashes).
- `src/render.rs::render_output_is_byte_identical_baseline` (8 hashes — relief/biome
  /political/etc. all derive from the changed elevation).
- **Unaffected:** `profile_mode_is_byte_identical_baseline` — Profile mode uses
  `height_at`+`apply_falloff`, never the tectonic ocean path. (Verify it stays green.)

### 5. Tests (acceptance)

- `plates.rs` unit: `crust_age_zero_at_ridges_and_grows` — ridge cells age 0,
  ages finite, oceanic cells reachable from a ridge get a finite age, determinism.
- `terrain.rs` unit: `ocean_depth_by_age_deepens_with_age` — monotone deeper with
  age, ridge (age 0) strictly shallower than old crust, clamped/finite; plus a
  **real-terrain correlation** test (build a pocket tectonic terrain; mean ocean
  elevation strictly decreases across age quartiles for open-ocean cells).
- `tests/age_bathymetry.rs` integration: the **bin-0 spike drops materially**
  (target < 40 % of ocean, from 51 %), ocean depths span ≥ 4 bins, and
  `elevation_histogram_is_bimodal` still holds (re-check in tectonic_relief).
- Downstream proportion guard: `tectonic_relief.rs` `terrain_proportions_stay_in_band`
  + `mountains_stay_a_land_minority` stay green (biome/climate recalibration check).

## Out of scope (later stages)

S5 coupled uplift⇄erosion; S6 render/export bathymetry (the `.glb` flat-ocean
clamp + sub-sea fBm suppression). S4 changes the model only.
