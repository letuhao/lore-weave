# Köppen climate on the sphere — spec (candidate A, full classifier port)

> **Task size: L.** Port the **validated** `flat_climate.rs` Köppen-Geiger
> classifier to the production sphere `climate.rs`, replacing the ad-hoc
> `[0,1]`-dryness heuristic with the real, temperature-dependent aridity formula.
> Parent: [`FLAT_TO_3D_MIGRATION_PLAN.md`](../03_planning/LLM_MMO_RPG/FLAT_TO_3D_MIGRATION_PLAN.md)
> candidate A. Written 2026-05-30 after the climate audit + a circulation
> experiment (both summarised below); **not yet built**.

---

## 0 — Why (the audit that produced this spec)

A Megaplanet (seed 7) audit found the standing colour defect is **desert
monotony**, not "all-green":

| | original | after retune (`6767683a`) |
|---|---|---|
| Desert (land) | **63.3 %** | 52.7 % |
| Tundra | 0.1 % | 0.1 % |
| green (forest+jungle+plain+marsh) | ~17 % | ~24 % |

**Two findings drive this spec:**

1. **The desert over-production is a *classifier* defect.** The sphere's
   `climate::classify` flags Arid on a fixed `dryness > 0.62` gate — **temperature
   blind**. Earth's deserts follow the Köppen B-group rule: a region is arid iff
   `precip < 20·T_mean + offset` — a **hot** region needs ~470 mm/yr to escape
   desert, a **cold** region only ~70 mm/yr. The fixed gate turns cold-and-dry
   interiors (which should be steppe / boreal / tundra) into desert.

2. **A naive circulation-only patch made it worse / is placement-bound.** Adding
   latitude precip bands to the `[0,1]` proxy pushed Desert to 55–62 % because
   seed-7's land sits at median |lat| ≈ 30° (the horse-latitude dry belt) — which
   is *realistically* arid (cf. Australia). The circulation experiment was
   **reverted**; its lesson: circulation must feed the **real Köppen classifier
   in physical units**, not modulate a `[0,1]` proxy. Continent **latitude
   placement** is a separate (terrain) lever for biome diversity, out of scope
   here.

**Conclusion:** the correct fix is the full Köppen classifier (already proven in
`flat_climate.rs`), working in real °C + mm/yr, with the temperature-dependent
aridity threshold. That is what this spec builds.

---

## 1 — Integration decision: Option A (keep `ClimateZone`/`BiomeKind`)

`climate::build` is rewritten to derive physical units and classify with Köppen,
then **map the Köppen group → the existing `ClimateZone` (8)**. The `ClimateZone`
and `BiomeKind` enums, `biome.rs`, hydrology wetness, settlement, and all render
paths stay **unchanged** — only the *values* become Köppen-correct. This avoids a
new enum + a render rewrite while delivering the physically-correct distribution.
(A future richer-palette option could expose the 19 Köppen subtypes; not now.)

`climate.rs` must **not** depend on `flat_climate::Biome` (frozen track): port the
classification *logic* into `climate.rs` returning `ClimateZone` directly.

---

## 2 — Per-cell recipe (port of `flat_climate::compute_zone_climate`)

For each cell `i` (3D centre `p`, `elevation[i]: u16`, `sea_level: u16`):

```
lat_dist   = (asin(p.z).abs() / (π/2)).clamp(0,1)        // 0 = equator, 1 = pole
elev_above = ((elev - sea_level) as f32 / 65535).max(0)   // height above sea, ~[0,0.6]

temp_sea   = lerp(T_EQ, T_POLE, lat_dist)                 // insolation
temp_mean  = temp_sea - LAPSE_C * elev_above              // elevation lapse

precip_base = circulation_precip_mm(lat_dist)             // §3 — the mm curve
precip      = precip_base * moisture_transport[i]         // §4 — continentality × orographic

amp        = (AMP_EQ + AMP_LAT * lat_dist) * (1 + AMP_CONT * cont[i])   // seasonality
t_warm     = temp_mean + amp
t_cold     = temp_mean - amp
winter_frac = 0.5                                         // §6 — simplified for v1

zone = classify_koppen(t_warm, t_cold, precip, winter_frac, elev_above)   // §5
```

where `cont[i] = (1 - moisture_transport[i]).clamp(0,1)` (interior = high
continentality).

---

## 3 — Circulation precip curve (mm/yr)

Port `flat_climate::circulation_curve`: piecewise-linear over `lat_dist` with the
calibrated anchors (mm/yr):

| lat_dist | band | mm/yr |
|---|---|---|
| 0.0 | ITCZ (equator) | **2400** (`precip_eq`) |
| 0.33 | subtropical high (~30°) | **180** (`precip_subtropic`) |
| 0.67 | mid-lat westerlies (~55°) | **900** (`precip_midlat`) |
| 1.0 | polar (pole) | **150** (`precip_polar`) |

```rust
fn circulation_precip_mm(lat_dist: f32) -> f32 {
    let t = lat_dist.clamp(0.0, 1.0);
    if t <= 0.33 { lerp(2400.0, 180.0, t / 0.33) }
    else if t <= 0.67 { lerp(180.0, 900.0, (t - 0.33) / 0.34) }
    else { lerp(900.0, 150.0, (t - 0.67) / 0.33) }.max(0.0)
}
```

---

## 4 — Moisture transport `[0,1]` (continentality × orographic)

**Revert `moisture_field` to a pure transport factor** (the post-retune state,
sea source `1.0`, no circulation inside it): the existing wind march that starts
moist at the coast and depletes by `OROGRAPHIC*climb + land_leak` per step, with
the **resolution-scaled `land_leak`** from the committed retune (`6767683a`).
Output `[0,1]` = 1 at the windward coast, →0 deep inland / in a rain shadow. The
Köppen path multiplies the mm circulation base by this factor, so:
- coast at a wet latitude → full circulation mm (humid);
- interior / lee → attenuated mm (continental / rain-shadow dry).

Circulation is the **latitude base (mm)**; transport is the **horizontal
attenuation `[0,1]`** — the two are now cleanly separated (the bug in the
reverted experiment was folding circulation *into* the `[0,1]` transport).

---

## 5 — `classify_koppen` → `ClimateZone` (the core fix)

Inline the Köppen-Geiger tree (port of `flat_climate::koppen_classify` +
`arid_precip_threshold`), collapsing 19 subtypes to the 8 `ClimateZone`:

```rust
fn arid_precip_threshold(t_warm: f32, t_cold: f32, winter_frac: f32) -> f32 {
    let t_mean = (t_warm + t_cold) * 0.5;
    let offset = if winter_frac > 0.70 { -70.0 }       // dry-summer (Med)
                 else if winter_frac < 0.30 { 140.0 }  // dry-winter (monsoon)
                 else { 70.0 };                        // even
    (20.0 * t_mean + offset).max(0.0)
}

fn classify_koppen(t_warm, t_cold, precip, winter_frac, elev_above) -> ClimateZone {
    // Highland override kept for tall terrain (preserves biome.rs hill/mountain).
    if elev_above > 0.30 && t_warm >= 10.0 { return Highland; }  // calibrate the gate
    if t_warm < 10.0  { return Polar; }                          // E
    if t_cold > 18.0  { return Tropical; }                       // A
    if precip < arid_precip_threshold(t_warm, t_cold, winter_frac) { return Arid; } // B
    if t_cold < -3.0  { return Boreal; }                         // D
    // C group → Mediterranean / Subtropical / Temperate
    if winter_frac > 0.65 { return Mediterranean; }              // Cs
    if t_warm > 22.0 { return Subtropical; }                     // Cfa / Cwa
    Temperate                                                    // Cfb
}
```

The **B test is the whole point**: `precip < 20·T_mean + offset` is temperature-
dependent, so cold-dry → D/E (not desert), hot-dry → B (desert at the right
latitudes). This is what breaks the 50 % desert floor the heuristic couldn't.

---

## 6 — Parameters (port the calibrated `flat_climate` defaults)

```
T_EQ      = 28.0    T_POLE    = -15.0          // °C, insolation
LAPSE_C   = ~40     (calibrate: a full-height peak ≈ 25 °C colder)
AMP_EQ    = 2.0     AMP_LAT   = 28.0   AMP_CONT = 0.8    // seasonality
winter_frac = 0.5   (v1 simplification — even precip everywhere)
```

**Deferred to a v2 (not v1):** real `winter_frac` from hemisphere + E/W margin
(Mediterranean dry-summer west coasts, monsoon dry-winter east). v1 uses 0.5
everywhere → no Cs/Cw subtypes, but the A/B/D/E split (the desert fix) is intact.

---

## 7 — Calibration plan (the empirical loop)

Driving metric: **Desert ≈ 30–40 % of land** on Megaplanet seed 7 (Earth land is
~33 % arid/semi-arid), with **Tundra/Boreal visible at high latitude** and
**Tropical/Forest at the equator + mid-lat**. Loop:

1. Generate `--scale megaplanet --seed 7 --png`, dump the biome histogram
   (the python one-liner used in the audit).
2. If Desert still > 45 %: lower `LAPSE_C` (warmer interiors need more rain ⇒
   more desert — careful) or raise `precip_subtropic` slightly, or check
   `moisture_transport` isn't over-drying (the retune already tuned `land_leak`).
3. If Tundra ~0: confirm high-lat land exists; lower the Polar `t_warm < 10`
   nothing — Tundra comes from `biome.rs` Polar-low. Check Polar zone share.
4. Cross-check a second seed + a Continent-scale world (smaller continents ⇒
   should be *less* desert).

Pin nothing to a literal hash (determinism is run-vs-run).

---

## 8 — Files + tests

**Touch:** `climate.rs` (rewrite `build` + replace `classify`/`effective_latitude`
+ add `circulation_precip_mm` / `arid_precip_threshold` / `classify_koppen` /
`seasonal_amp`; revert `moisture_field` to transport-only). `lib.rs` call is
unchanged (same `build` signature) **unless** `climate_bias` handling changes —
see below. `content_hash` re-bases.

**`climate_bias`:** the old `classify` took an optional `ClimateZone` bias. In the
Köppen path, apply it as a small `temp`/`precip` nudge before `classify_koppen`
(e.g. an Arid bias subtracts ~150 mm precip; a Tropical bias adds temp), so the
`CreativeSeed.climate_bias` field + its author schema keep working. Keep the
feature; do not drop the param.

**Tests to rewrite (`climate.rs` mod tests):**
- `equator_is_hot_pole_is_cold` → assert `classify_koppen` gives Tropical at the
  equator (warm, wet), Polar at the pole (cold).
- `all_eight_zones_are_reachable` → sweep `(t_warm, t_cold, precip, winter_frac,
  elev)` and assert every `ClimateZone` is produced (Mediterranean needs
  `winter_frac > 0.65` — only reachable once §6-v2 lands; for v1, either keep a
  test hook that passes a high winter_frac, or accept Mediterranean is v2).
- `arid_threshold_is_temperature_dependent` (NEW) → assert a hot cell with
  precip 300 mm is Arid while a cold cell with the same 300 mm is **not**
  (the headline property).
- `rain_shadow_follows_the_wind` → unchanged (`moisture_field` reverts to the
  transport-only form it already had).
- determinism + `compute_hash_covers_every_field` → unaffected (climate is a
  `Vec<ClimateZone>`, already hashed).

**VERIFY:** lib green; biome histogram Desert 30–40 %; Tundra/Boreal/Tropical
visible; clippy-clean; `/review-impl`.

---

## 9 — R6 note (the migration-plan trap)

R6 = "don't copy flat's 2D continentality; use great-circle on the sphere." This
spec honours it: continentality here is the **sphere wind march** (great-circle
graph hops over `neighbors`), already resolution-scaled (`6767683a`) — it is
**not** flat's 2D pixel-grid `edge_dist`. Only the *circulation curve* and the
*Köppen classifier logic* (both latitude/unit functions, geometry-agnostic) are
lifted from `flat_climate`; the spatial moisture transport stays sphere-native.

---

## 10 — Out of scope

Ocean-current E-W temp delta (`flat` has it; minor); real `winter_frac`
seasonality (Cs/Cw subtypes) → v2; 19-subtype richer biome palette → later;
continent-latitude placement for biome diversity → terrain track.
