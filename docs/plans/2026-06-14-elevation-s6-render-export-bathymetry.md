# Plan — elevation S6: render/export bathymetry (arc finale)

> Final stage S6 of the elevation-redesign arc
> (`docs/specs/2026-05-31-elevation-redesign.md`). Size **M**. Fixes **D7** (the
> "ocean rises above land" visual): the `.glb` clamped the ocean to a flat sea
> sphere, and `relief.rs` let fBm detail bump sub-sea pixels. **Render/export
> only — NOT `content_hash`** (the model bathymetry is already correct after S4).

## The two defects

1. **`export.rs` glb** — every water vertex is displaced to `relief.sea` (a flat
   sphere); ocean has zero bathymetry and shallow-water detail could poke a
   coastal vertex *above* sea → "ocean rises above land."
2. **`relief.rs` detail** — the open-ocean detail gate is
   `smoothstep(-0.15, 0.02, land_t)`, which is **≈0.97 at sea level** (`land_t=0`).
   So fBm detail is nearly full into shallow water, bumping the ocean floor and
   muddying the `water_color` depth ramp.

(The model is correct: after S4 the per-cell `elevation` has real age-driven
ocean depth — `water_color` already ramps by depth. S6 makes the *render/export*
show it cleanly.)

## Changes

### `relief.rs` — suppress sub-sea detail
Retune the detail gate to `smoothstep(0.0, DETAIL_SEA_RAMP, land_t)` so detail is
**0 at/below sea** and ramps in just above the waterline. Open ocean + shallow
water get no fBm bumps → the `water_color` depth ramp and the heightmap read the
clean S4 bathymetry; the fractal coastline still forms on the land side (where
`land_t > 0`).

### `export.rs` — real ocean depth in the `.glb`
Water vertices displace to their **actual** (exaggerated) depth below sea instead
of the flat `relief.sea`:
```
h = if water { e.min(sea) }   // ocean floor — bathymetry below sea
    else     { e.max(sea) }   // land — above sea
r = BASE_RADIUS + h · exaggeration
```
Ocean sinks below the sea radius by its real depth (ridges shallow, abyss deep),
land rises above — the planet reads with visible bathymetry, coastline at sea.

## Tests / pins

- Re-pin the **8 render hashes** (`render.rs::render_output_is_byte_identical_baseline`)
  — the relief detail change shifts every PNG. **Content pins unchanged** (S6 is
  render/export only) — verify `default_profile_is_byte_identical_baseline` stays green.
- **Rewrite** `export.rs::ocean_is_clamped_to_sea_radius_and_land_rises` →
  `ocean_sinks_below_sea_and_land_rises`: assert some ocean vertices are *below*
  the sea radius, land rises above, and ocean radii span a range (bathymetry
  visible, not flat).
- **New `relief.rs` test:** a water pixel's `elev` equals its detail-free base
  (sub-sea detail is fully suppressed), and `field_has_both_land_and_water` /
  determinism still hold.

## Out of scope
Model/`content_hash` changes (done in S1–S5); a final hypsometry *re-calibration*
is unnecessary — the S3 bimodal lock + S4 spread + S5 proportions already hold.
This closes the elevation-redesign arc (S1–S6).
