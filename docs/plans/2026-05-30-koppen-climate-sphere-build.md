# PLAN — Köppen climate on the sphere (BUILD)

> Size **L**. Spec: [`docs/specs/2026-05-30-koppen-climate-sphere.md`](../specs/2026-05-30-koppen-climate-sphere.md).
> Session 100, branch `world-gen-sdk-refactor`. Written 2026-05-30 after the
> DESIGN/REVIEW phase (spec review with PO sign-off on R1/R3 below).

## Goal

Replace `climate.rs`'s temperature-blind `dryness > 0.62` Arid gate with the
**validated** Köppen-Geiger classifier working in **real °C + mm/yr**, mapped onto
the existing 8 `ClimateZone`. Target: Megaplanet seed-7 Desert from 53 % → **30–40 %
of land**, with Tundra/Boreal at high latitude and Tropical/Forest at equator+mid-lat.

## Design decisions (from spec review, PO-confirmed)

- **R1 — keep `effective_latitude`.** Spec §2's `asin(p.z).abs()` is Equatorial
  shorthand; we compute `lat_dist` via `effective_latitude(lat, hemisphere)` to
  preserve the `hemisphere_orientation` knob (Northern world keeps one warm pole).
- **R2 — Mediterranean is climate-label-only in v1.** `winter_frac ≡ 0.5` ⇒
  `classify_koppen` never returns Mediterranean. biome.rs maps Mediterranean ==
  Temperate biomes, so **zero biome regression**. `classify_koppen` keeps
  `winter_frac` as a real param so the reachability test exercises all 8.
- **R3 — keep Highland override (conservative).** Gate `elev_above > GATE && t_warm
  ≥ 10` — parity with the old `elev_norm > 0.62` semantics; gate value is a
  calibration knob, verified in the histogram loop.
- **R4 — `moisture_field` unchanged.** Already pure `[0,1]` transport (post-`6767683a`);
  used as the horizontal attenuation multiplier on the circulation-mm base. The
  `rain_shadow_follows_the_wind` test is untouched.
- **R5 — `climate_bias` → physical-unit nudge.** New `bias_delta` returns
  `(temp_°C, precip_mm)`; applied before `classify_koppen`.

## Build steps (climate.rs)

1. Add `const`s: `T_EQ=28.0`, `T_POLE=-15.0`, `LAPSE_C=40.0` (calibrate),
   `AMP_EQ=2.0`, `AMP_LAT=28.0`, `AMP_CONT=0.8`, circulation anchors
   `2400/180/900/150`, Highland gate.
2. `fn circulation_precip_mm(lat_dist) -> f32` — port `circulation_curve` anchors.
3. `fn arid_precip_threshold(t_warm, t_cold, winter_frac) -> f32` — port verbatim.
4. `fn classify_koppen(t_warm, t_cold, precip, winter_frac, elev_above) -> ClimateZone`
   — port `koppen_classify` order (Highland → E → A → B → D → C), collapse 19→8.
5. `fn seasonal_amp(lat_dist, cont) -> f32` — port `seasonal_amplitude`.
6. Rewrite `build()`: per-cell `lat_dist = effective_latitude(...)`; `elev_above =
   ((elev-sea)/65535).max(0)`; `temp_mean = lerp(T_EQ,T_POLE,lat_dist) - LAPSE_C*elev_above`;
   `precip = circulation_precip_mm(lat_dist) * moisture[i]`; `cont = (1-moisture[i])`;
   `amp = seasonal_amp(...)`; `t_warm/t_cold = mean ± amp`; `winter_frac = 0.5`;
   apply `climate_bias` nudge; `classify_koppen(...)`.
7. Replace old `classify` + `bias_delta`; delete the `[0,1]`-space tree.

## Tests (climate.rs mod tests)

- `equator_is_hot_pole_is_cold` — rewrite for `classify_koppen` (Tropical at warm/wet
  equator, Polar at cold pole).
- `all_eight_zones_are_reachable` — sweep `(t_warm, t_cold, precip, winter_frac, elev)`;
  Mediterranean reached via high `winter_frac` (pure-fn reachability; v1 pipeline
  pins 0.5).
- `arid_threshold_is_temperature_dependent` (**NEW, headline**) — hot cell (t_warm=30,
  t_cold=10) precip 300 → Arid; cold cell (t_warm=12, t_cold=2) precip 300 → **not** Arid.
- `rain_shadow_follows_the_wind` — unchanged.
- `arid_bias_makes_borderline_cells_more_arid` — rewrite for °C/mm bias.
- `highland_needs_high_elevation_below_polar_latitude` — rewrite for new gate.

## VERIFY

`cargo test -p world-gen` green · `cargo clippy -p world-gen` clean · biome histogram
Desert 30–40 % land on Megaplanet seed 7 · Tundra/Boreal/Tropical visible · cross-check
seed 2 + Continent scale. No literal hash pin (determinism is run-vs-run).

## Out of scope (deferred)

Real `winter_frac` seasonality (Cs/Cw subtypes) → v2; 19-subtype palette → later;
continent-latitude placement for diversity → terrain track (lesson 1fbf8d34: if Desert
stays high post-Köppen, residual cause is seed-7 land at |lat|≈30° dry belt, not climate).
