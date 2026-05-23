# v5 Köppen Seasonal — Detailed Design Spec

> **Status:** ✅ **SHIPPED 2026-05-24** as Full Köppen scope. All 5 phases
> executed per §8. v5.0 baseline locked at mean 89.56 (+1.63 vs v4.5 87.93,
> a NEW PEAK across all v3-v5 batches). 7 of 11 renders improved ≥1pt;
> hemi_north +9.02 biggest single gain. 0 hard regressions ≥5pt after
> lat-band relaxation (initial v5.0 had hemi_south −6.66 from too-strict
> bands — fixed by relaxing Earth profile to allow Köppen variability per
> Beck 2018 maps).
>
> Companion to [`2026-05-23-climate-simulation-research.md`](2026-05-23-climate-simulation-research.md)
> §4.5 (seasonality) + §5.5 (phased roadmap).

---

## 1 — Context

### What's shipped (commit `0fb7f1ca` and earlier, 2026-05-24)

- 10 Whittaker biomes (Ice, Tundra, BorealForest, DeciduousForest,
  TemperateForest, Mediterranean, TemperateGrassland, HotDesert, Savanna,
  TropicalRainforest)
- 5-layer climate pipeline (Insolation, Circulation, **v3 OceanCurrent**,
  Continentality, Pixel ElevLapse) + **v4 Orographic** rain shadow
- ZoneClimate carries `temp_mean` + `precip_annual` (annual averages only)
- Eval framework v4.3 ecotone-aware (any-allowed / all-forbidden per pixel)

### What v5 adds

The current `whittaker_classify(temp, precip)` is a 2D step function on
annual means. **Real Earth biome distinction often hinges on seasonality**:

| Same (temp, precip), different biomes | Distinguished by |
|---|---|
| Oceanic Cfb (UK) vs Humid Continental Dfb (Toronto) | cold-month temp (UK mild, Toronto < −3°C) |
| Mediterranean Csa (LA) vs Humid Subtropical Cfa (Hong Kong) | precip seasonality (LA dry summer, HK wet summer) |
| Hot Desert BWh (Sahara) vs Cold Desert BWk (Gobi) | cold-month temp (Sahara mild, Gobi < 0°C) |
| Tropical Rainforest Af vs Monsoon Am vs Savanna Aw | dry season length + intensity |

v5 introduces **monthly extremes** (warmest/coldest month) and **precip
seasonality** as zone-level fields, then re-classifies into Köppen subtypes
that respect those distinctions.

---

## 2 — New ZoneClimate fields

```rust
pub struct ZoneClimate {
    pub temp_mean: f32,              // existing
    pub precip_annual: f32,          // existing
    pub temp_warm_month: f32,        // NEW v5 — warmest-month mean (°C)
    pub temp_cold_month: f32,        // NEW v5 — coldest-month mean (°C)
    pub precip_winter_frac: f32,     // NEW v5 — fraction of annual precip
                                     // falling in cold half-year [0, 1].
                                     // 0.5 = year-round even; ≪0.5 = dry
                                     // winter (monsoon); ≫0.5 = dry summer
                                     // (Mediterranean).
    pub biome: Biome,                // existing (now ~18-20 Köppen variants)
}
```

---

## 3 — New WorldClimateParams fields

```rust
pub struct WorldClimateParams {
    // ... existing 14 fields ...

    /// **v5 seasonality** — base seasonal temp amplitude (°C) at the equator
    /// where lat amplitude = 0. Real Earth equator amp ≈ 1-2°C.
    pub seasonal_amplitude_eq: f32,        // default 2.0

    /// **v5 seasonality** — extra amplitude per unit `lat_dist` (°C). At the
    /// pole, amp = eq + lat_factor. Real Earth amp ≈ 30°C at pole (Yakutsk
    /// −40 winter / +20 summer = 60°C swing ≈ 30°C amplitude).
    pub seasonal_amplitude_lat_factor: f32, // default 28.0

    /// **v5 seasonality** — amplification from continentality. Interior gets
    /// bigger temp swings than coast (UK +10/+15 vs Siberia −40/+20). Multi-
    /// plicative: `amp_final = amp_base × (1 + cont × this)`.
    pub seasonal_amplitude_cont_factor: f32, // default 0.8

    /// **v5 precip seasonality — Mediterranean dry-summer signature** at
    /// subtropical western continental margins (lat_dist ~0.25-0.40 + west
    /// coast). Default 0.20 (20% of precip falls in winter half — strong
    /// dry-summer pattern). Set to 0.5 to disable Mediterranean detection
    /// (returns all warm-temperate to Cfa).
    pub mediterranean_winter_frac: f32,     // default 0.20

    /// **v5 precip seasonality — Monsoon dry-winter signature** at tropical
    /// continental west margins (lat_dist ~0.10-0.30). Default 0.80 (80% of
    /// precip falls in summer = strong monsoon).
    pub monsoon_summer_frac: f32,           // default 0.80
}
```

### Seasonal amplitude formula

```rust
fn seasonal_amplitude(lat_dist: f32, continentality: f32, params: &WorldClimateParams) -> f32 {
    let lat_amp = params.seasonal_amplitude_eq
                + params.seasonal_amplitude_lat_factor * lat_dist;
    lat_amp * (1.0 + continentality * params.seasonal_amplitude_cont_factor)
}

// Then per zone:
let amp = seasonal_amplitude(lat_dist, cont, params);
let temp_warm_month = temp_mean + amp;
let temp_cold_month = temp_mean - amp;
```

### Precip seasonality formula

```rust
fn precip_winter_frac(
    lat_dist: f32,
    ew_position: f32,  // -1..+1 east/west of plate centroid
    hemisphere: HemisphereLayout,
    params: &WorldClimateParams,
) -> f32 {
    // Default: year-round even
    let mut frac = 0.5;

    // Mediterranean dry-summer pattern: subtropical western margin (lat 0.20-0.40),
    // west coast (ew_position < 0 for plates with NH=0 hemisphere). Real Earth:
    // California, Med basin, central Chile, SW Australia, Cape SA.
    if (0.20..0.40).contains(&lat_dist) && ew_position < -0.3 {
        frac = params.mediterranean_winter_frac;
    }

    // Monsoon summer pattern: tropical continental margin (lat 0.10-0.30),
    // east-side OR interior. Real Earth: India SW monsoon, SE Asia, W Africa.
    if (0.10..0.30).contains(&lat_dist) && ew_position > 0.0 {
        frac = 1.0 - params.monsoon_summer_frac;  // 0.20 if 80% summer = 20% winter
    }

    frac
}
```

---

## 4 — New Biome enum (Köppen-lite ~18 variants)

```rust
pub enum Biome {
    // POLAR (E)
    Ef,             // Ice cap (warmest < 0°C) — was Ice
    Et,             // Tundra (warmest 0-10°C) — was Tundra

    // CONTINENTAL (D) — cold winters (cold-month < -3°C), warm summers (warm > 10°C)
    Dfc,            // Subarctic (cold-month -40..-3, warm 10-22) — was BorealForest (mild)
    Dfd,            // Extreme subarctic (cold-month < -40) — was BorealForest (severe)
    Dfb,            // Warm humid continental (cold -3..-15, warm 14-22) — was TemperateForest split
    Dfa,            // Hot humid continental (cold -3..-15, warm >22) — was DeciduousForest split
    Dwa,            // Continental monsoon-influenced (dry winter)
    Bsk,            // Cold steppe (cold-month < 0, dry)
    Bwk,            // Cold desert (cold-month < 0, very dry) — Gobi, Atacama high alt

    // TEMPERATE (C) — mild winters (-3..18°C cold-month)
    Cfb,            // Oceanic (cold mild, warm 10-22) — was TemperateForest split
    Cfa,            // Humid subtropical (cold 0-18, warm >22, year-round wet) — was DeciduousForest
    Csa,            // Mediterranean hot summer (cold 5-18, warm >22, dry summer)
    Csb,            // Mediterranean warm summer (cold 5-18, warm 14-22, dry summer)
    Cwa,            // Subtropical monsoon (dry winter, wet summer)

    // ARID (B) — hot variants
    Bsh,            // Hot steppe (warm > 18, dry) — was TempGrassland (hot)
    Bwh,            // Hot desert (warm > 18, very dry) — Sahara, Arabian

    // TROPICAL (A) — all months > 18°C
    Af,             // Tropical rainforest (year-round wet, no dry month) — was TropicalRainforest
    Am,             // Tropical monsoon (dry season but compensated, > 100mm wet season)
    Aw,             // Tropical savanna (dry winter) — was Savanna
}
```

**Biome.color() palette suggestion** (RGB, calibrated for visual distinctness +
real-Earth analogs):

| Variant | RGB | Real analog |
|---|---|---|
| Ef | `[245, 248, 250]` | Bright white-ice |
| Et | `[184, 183, 174]` | Pale grey-tan |
| Dfd | `[58, 86, 60]` | Very dark grey-green (Yakutsk) |
| Dfc | `[74, 107, 71]` | Dark grey-green (Siberia) |
| Dfb | `[100, 138, 88]` | Warm dark green (Canada prairies) |
| Dfa | `[125, 158, 96]` | Slightly olive green (Central US) |
| Dwa | `[148, 175, 110]` | Yellow-green (NE China) |
| Bsk | `[174, 165, 105]` | Tan-olive (Kazakh steppe) |
| Bwk | `[195, 165, 132]` | Pale grey-brown (Gobi) |
| Cfb | `[79, 139, 65]` | Bright forest green (UK, NW Europe) |
| Cfa | `[138, 171, 82]` | Autumn olive (SE USA, Yangzi) |
| Csa | `[181, 165, 98]` | Olive-tan (Mediterranean basin) |
| Csb | `[165, 175, 115]` | Cool olive (coastal California) |
| Cwa | `[155, 180, 95]` | Bright yellow-green (S China) |
| Bsh | `[201, 192, 74]` | Yellow-tan (Sahel) |
| Bwh | `[216, 144, 96]` | Reddish sand (Sahara) |
| Af | `[15, 77, 26]` | Deep dark green (Amazon, Congo) |
| Am | `[35, 100, 35]` | Slightly lighter deep green (Mumbai, SE Asia) |
| Aw | `[201, 192, 74]` | Yellow-green savanna |

Palette mapping preserves visual continuity: Whittaker biomes that split keep
canonical color for the "anchor" subtype (Af = TropicalRainforest old, Bwh =
HotDesert old, etc.) so existing rendered baselines partially carry over.

---

## 5 — Köppen classifier

```rust
/// **v5 Köppen-lite classifier**: returns Köppen subtype from monthly extremes
/// + annual precip + precip seasonality.
///
/// Implements the canonical Köppen decision tree (Köppen-Geiger, Beck 2018
/// update). Order: Polar → Tropical → Arid → Continental → Temperate.
pub fn koppen_classify(
    t_warm: f32,  // warmest-month mean (°C)
    t_cold: f32,  // coldest-month mean (°C)
    precip: f32,  // annual mm/yr
    winter_frac: f32,  // 0..1 fraction in cold half
) -> Biome {
    // 1. POLAR (warmest < 10°C)
    if t_warm < 0.0 { return Biome::Ef; }
    if t_warm < 10.0 { return Biome::Et; }

    // 2. TROPICAL (coldest > 18°C — all months above 18)
    if t_cold > 18.0 {
        if precip > 2000.0 {
            // dry month threshold via winter_frac × precip_annual / 6
            if winter_frac > 0.20 { return Biome::Af; }  // year-round wet
            return Biome::Am;                              // monsoon
        }
        return Biome::Aw;  // savanna (dry winter — most tropical)
    }

    // 3. ARID (evaporation > precip). Köppen aridity threshold depends on
    // temperature + precip seasonality. Simplified: precip < threshold.
    let arid_threshold = arid_precip_threshold(t_warm, t_cold, winter_frac);
    if precip < arid_threshold {
        let hot = t_cold > 0.0;  // hot if cold-month > 0°C
        let very_dry = precip < arid_threshold * 0.5;
        match (hot, very_dry) {
            (true, true) => Biome::Bwh,
            (true, false) => Biome::Bsh,
            (false, true) => Biome::Bwk,
            (false, false) => Biome::Bsk,
        }
    } else {
        // 4. CONTINENTAL (cold-month < -3°C, warm > 10°C)
        if t_cold < -3.0 {
            // Dry winter check: Dwa if winter_frac < 0.3 + summer is wet
            if winter_frac < 0.3 && t_warm > 22.0 { return Biome::Dwa; }
            // Severe subarctic
            if t_cold < -40.0 { return Biome::Dfd; }
            if t_warm < 14.0 { return Biome::Dfc; }
            if t_warm > 22.0 { return Biome::Dfa; }
            Biome::Dfb
        } else {
            // 5. TEMPERATE (mild winters)
            // Dry summer (Mediterranean) check
            if winter_frac > 0.65 {
                if t_warm > 22.0 { return Biome::Csa; }
                return Biome::Csb;
            }
            // Dry winter monsoon-influenced
            if winter_frac < 0.30 && t_warm > 22.0 { return Biome::Cwa; }
            // Year-round wet
            if t_warm > 22.0 { return Biome::Cfa; }
            Biome::Cfb
        }
    }
}

/// Köppen aridity precip threshold (mm/yr). Higher temp = more evaporation =
/// higher threshold for "arid" classification. Beck 2018 formula:
/// 20 × T_mean + 280 (or 140 if winter_frac > 0.7, or 0 if winter_frac < 0.3).
fn arid_precip_threshold(t_warm: f32, t_cold: f32, winter_frac: f32) -> f32 {
    let t_mean = (t_warm + t_cold) * 0.5;
    let seasonal_offset = if winter_frac > 0.7 { 140.0 }
                          else if winter_frac < 0.3 { 0.0 }
                          else { 280.0 };
    20.0 * t_mean + seasonal_offset
}
```

### Decision tree for classifier-level hue interpolation (v5 W5 update)

The existing `whittaker_classify_blended_color` (v2.1d) probes ±1.5°C / ±75mm.
For Köppen, **add 2 more axes**: ±t_cold and ±winter_frac. Probe budget grows
from 4 to 8 directions. Bisect-and-blend logic stays the same.

Alternative simpler approach: blend only at the temp threshold (warmest-month
or coldest-month) since precip-seasonality boundaries are sharp ecotones in
real Earth (Mediterranean→TempForest at the precip-seasonal-pattern edge =
narrow strip, not a gradient).

---

## 6 — Eval framework updates

### `climate_eval.py` BIOME_COLORS

Replace 10-entry dict with 18-entry dict matching new palette. NEAR_THRESHOLD
of 55 RGB should still work (palette spread > 55 in RGB space — verify on
implementation).

### PROFILE_LAT_BANDS

Each scenario (earth, snowball, hothouse, desert) needs full rework. New
biomes per band require fresh allowed/forbidden classification. Sample for
earth:

```python
LAT_BANDS_EARTH_V5 = [
    (0.00, 0.20,  # tropics 0-15°
     {Af, Am, Aw, Bwh, Bsh},
     {Ef, Et, Dfd, Dfc, Dfb, Cfb, Csb}),
    (0.20, 0.40,  # subtropics 15-30°
     {Bwh, Bsh, Aw, Cfa, Csa, Cwa, Bsk},
     {Ef, Et, Dfd, Dfc, Af}),
    (0.40, 0.60,  # mid-lat 30-50°
     {Cfb, Cfa, Csa, Csb, Cwa, Dfa, Dfb, Bsk, Bwk, Bsh, Bwh},
     {Ef, Et, Dfd, Af, Am, Aw}),
    (0.60, 0.80,  # sub-arctic 50-70°
     {Dfc, Dfb, Dfa, Dwa, Bsk, Bwk, Cfb, Et},
     {Af, Am, Aw, Bwh, Bsh, Cfa, Csa, Cwa}),
    (0.80, 1.00,  # polar 70-90°
     {Et, Ef, Dfd, Dfc},
     {Af, Am, Aw, Bwh, Bsh, Cfa, Csa, Cwa, Csb, Cfb, Dfa, Dfb, Dwa, Bsh, Bsk}),
]
```

### profile distributions

The TOML `[profiles.X.distribution]` tables were dropped in v4 framework
(replaced by law-based gradient metrics). v5 doesn't reintroduce them. Earth
distribution profile becomes informational only (not scored against).

### Hash pin

Biome render output will shift significantly (10→18 colors, different boundary
geometry). Rebase the hash pin in `zonegen.rs::biome_render_pins_a_content_hash`
on first ship.

---

## 7 — Sidecar export updates

```rust
#[derive(Serialize)]
pub struct ZoneClimateExport {
    pub plate_id: usize,
    pub zone_id: usize,
    pub site: [f32; 2],
    pub lat_dist: f32,
    pub temp_mean: f32,
    pub precip_annual: f32,
    pub temp_warm_month: f32,      // NEW v5
    pub temp_cold_month: f32,      // NEW v5
    pub precip_winter_frac: f32,   // NEW v5
    pub biome: &'static str,       // now Köppen code: "Cfb", "Dfa", "Af", etc.
    pub koppen_group: &'static str, // NEW v5 — "A", "B", "C", "D", "E"
    pub base_elevation: f32,
}
```

Tilemap consumer contract update: `--climate-out` JSON gains 4 new fields.
Existing consumers parsing only existing fields keep working (additive change).

---

## 8 — Implementation order (recommended for future session)

**Phase 1 — Seasonality data (~2h):**
1. Add 5 new fields to `WorldClimateParams` + scaled_for defaults
2. Compute amplitude + monthly extremes in `compute_zone_climate`
3. Compute precip_winter_frac per zone
4. Extend `ZoneClimate` struct + `ZoneClimateExport`
5. Tests: amplitude formula, winter_frac per region

**Phase 2 — Köppen classifier (~2h):**
6. Implement `koppen_classify(t_warm, t_cold, precip, winter_frac) -> Biome`
7. Implement `arid_precip_threshold`
8. Tests: every Köppen subtype has at least one input that classifies to it;
   canonical Earth-city test cases (UK→Cfb, Yakutsk→Dfd, Sahara→Bwh, etc.)

**Phase 3 — Biome enum migration (~1.5h):**
9. Replace 10-variant Biome with 18-variant Köppen enum
10. Update `Biome::color()` + `Biome::tag()` + `Biome::name()`
11. Update `pixel_biome` + `pixel_color` to call koppen_classify
12. Hash pin rebase + biome render tests update

**Phase 4 — Eval framework update (~1h):**
13. `climate_eval.py` BIOME_COLORS + 4 PROFILE_LAT_BANDS tables
14. Run eval to verify framework handles new biome set
15. Lock v5.0 baseline

**Phase 5 — Visual review + docs (~1h):**
16. Render compare set Whittaker (v4.5) vs Köppen (v5.0)
17. Update roadmap doc with v5 SHIPPED section
18. Update tilemap consumer contract doc with new sidecar fields

**Total: ~7-8h** focused work. Realistic 1-2 sessions depending on stride.

---

## 9 — Risks and mitigations

| Risk | Mitigation |
|---|---|
| Köppen palette colors too close → ecotone-aware eval can't disambiguate | RGB pairwise distance check ≥55 NEAR_THRESHOLD during palette finalization |
| Aridity threshold formula picks wrong tier (e.g. mid-lat misclassified as tropical) | Pin canonical city test cases in unit tests; calibrate with Earth reference |
| Lat-band tables get too permissive (everything allowed everywhere) → sanity score becomes meaningless | Cross-check allowed sets against Beck 2018 Köppen world map |
| Winter_frac formula too crude (only E-W position, no monsoon source) | Acceptable simplification for v5; v6 can add explicit monsoon source modeling |
| Existing rendered baselines invalidated | Lock new v5.0 baseline; archive v4.5 as historical reference |
| W6/W9/W2/Orographic interactions with new biome set | Re-run all compare sets after Phase 4; spot-check no regression on v4-known-good renders |
| Sidecar JSON breaking change | Additive only; existing fields unchanged |

---

## 10 — Open questions for the implementer

1. **Earth-calibration source**: which dataset to validate against? Suggest:
   Beck et al. 2018 "Present and future Köppen-Geiger climate classification
   maps at 1-km resolution" — has 30+ class definitions with thresholds.
2. **Highland (H) class**: Köppen sometimes adds H for high-altitude. Skip
   for v5? Or use elev-lapse + reclassify pixels above threshold? Probably
   the existing pixel_color lapse override handles this case for Ice/Tundra;
   no need for explicit H.
3. **18 vs 25 biomes**: this design picks 18 for manageability. Going to 25
   adds Cfc (subpolar oceanic), Csc, Aw splits, etc. Probably not worth the
   palette spread effort unless requested.
4. **Precip seasonality formula**: current proposal uses E-W position + lat
   to predict Mediterranean / Monsoon patterns. Real Earth has more sources
   (orographic + ocean current effects). Defer refinement to v6.

---

## 11 — Acceptance criteria for v5 ship

Per workflow gate phase QC, v5 ships if:
- All ~10 new koppen_classify unit tests pass
- All ~3 new seasonality formula tests pass
- All 198+ existing tests still pass (no regression in non-classifier logic)
- Eval framework parses v5 sidecar without error
- Eval mean composite within ±3 pt of v4.5 baseline (87.93); biggest single
  regression ≤ 5pt (per existing thresholds)
- Visual compare set shows Köppen subtypes appearing as distinct colors
  (e.g. Cfb green coastal vs Dfb dark-green continental, Csa olive coastal
  vs Cfa autumn-olive coastal)
- Tilemap consumer contract doc updated with new sidecar fields
- Roadmap doc updated with v5 SHIPPED section

---

## 12 — Estimated effort

- **Optimistic:** 5h focused work (experienced contributor familiar with codebase)
- **Realistic:** 7-8h (one long session or two ~4h sessions)
- **Pessimistic:** 12h (eval framework rework takes longer; palette tuning iterates)

Lower-effort scope variants (if 7h is too much):
- **v5-lite**: implement seasonality data + Köppen classifier; defer
  full biome split (just split TemperateForest → Cfb/Dfb as PoC). M task ~4h.
- **v5-data-only**: implement seasonality fields + sidecar export; keep
  Whittaker classification; tilemap consumers get seasonality data even if
  renderer doesn't use it. XS task ~1h.

---

## 13 — References

- Köppen, W. (1936). *Das geographische System der Klimate.*
- Beck, H. E. et al. (2018). *Present and future Köppen-Geiger climate
  classification maps at 1-km resolution.* (Nature Scientific Data)
- Climate research doc: [`2026-05-23-climate-simulation-research.md`](2026-05-23-climate-simulation-research.md)
  §3.1 Köppen-Geiger, §4.5 Seasonality, §5.5 phased roadmap (v5 row)
- v2/v3/v4 weakness analysis: [`2026-05-23-b5-v2-weakness-analysis.md`](2026-05-23-b5-v2-weakness-analysis.md)
  (current shipped state)
- v4.5 baseline: [`eval/baselines/v4.5.json`](../../eval/baselines/v4.5.json)
  (mean composite 87.93 — the to-beat number for v5 ship)
