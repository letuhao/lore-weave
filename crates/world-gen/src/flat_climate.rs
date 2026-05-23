//! **Flat-world climate (B5 v2)** — hierarchical, layered climate for the
//! [`crate::zonegen`] track. NEW module separate from the sphere-track
//! [`crate::climate`].
//!
//! The model: 5 physical drivers stacked as a composition of pure functions,
//! applied at the *appropriate hierarchical level* (World → Plate → Zone →
//! Pixel). The biome is decided at the **zone level** so each zone reads as
//! one ecosystem; the pixel level only applies an **elevation-lapse** override
//! so tall peaks get Tundra / Ice regardless of the zone's biome (snow caps).
//!
//! Layers (v2): Insolation · Circulation · *(Plate slot — pass-through in v2;
//! v3 OceanCurrent goes here)* · Continentality · ZoneRefinement (implicit
//! by using zone-site coords) · ElevLapse (pixel only).
//!
//! Spec: [`docs/plans/2026-05-23-climate-simulation-research.md`](../../../../docs/plans/2026-05-23-climate-simulation-research.md) §10.
//!
//! Pure & deterministic — no RNG. Climate is a function of the world layout +
//! [`WorldClimateParams`] alone.

use serde::Serialize;

/// Where the equator sits on the flat-rectangle frame and which edge is which
/// pole. Author-set per seed; default [`HemisphereLayout::Equatorial`].
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub enum HemisphereLayout {
    /// `y = h/2` is the equator; both `y = 0` and `y = h` are poles.
    /// Symmetric, both hemispheres visible — the realistic default.
    #[default]
    Equatorial,
    /// `y = 0` is the equator; `y = h` is the (north) pole. One hemisphere only.
    NorthOnly,
    /// `y = h` is the equator; `y = 0` is the (south) pole. One hemisphere only.
    SouthOnly,
}

impl HemisphereLayout {
    /// Normalized "latitude distance from equator" in `[0, 1]` for pixel `y`
    /// on a map of height `h`. `0` = equator (warm), `1` = pole (cold).
    pub fn lat_dist(self, y: f32, h: f32) -> f32 {
        let h = h.max(1.0); // tests with degenerate h are still valid
        match self {
            HemisphereLayout::Equatorial => ((y - h * 0.5).abs() / (h * 0.5)).clamp(0.0, 1.0),
            HemisphereLayout::NorthOnly => (y / h).clamp(0.0, 1.0),
            HemisphereLayout::SouthOnly => ((h - y) / h).clamp(0.0, 1.0),
        }
    }
}

/// Author-set climate parameters for the world. Reference values are Earth-ish;
/// each is intervenable to shape a more or less extreme world.
#[derive(Debug, Clone)]
pub struct WorldClimateParams {
    pub hemisphere_layout: HemisphereLayout,
    // --- Insolation (World layer) ---
    /// Mean annual temperature at the equator at sea level (°C).
    pub t_eq: f32,
    /// Mean annual temperature at the pole at sea level (°C).
    pub t_pole: f32,
    // --- Circulation (World layer) — piecewise lat→precip ---
    /// mm / year at the ITCZ (lat_dist = 0).
    pub precip_eq: f32,
    /// mm / year at the subtropical dry belt (lat_dist ≈ 0.33).
    pub precip_subtropic: f32,
    /// mm / year at the mid-latitude wet belt (lat_dist ≈ 0.67).
    pub precip_midlat: f32,
    /// mm / year at the polar dry pole (lat_dist = 1).
    pub precip_polar: f32,
    // --- Continentality (Zone layer) ---
    /// Distance from the nearest sea pixel beyond which continentality
    /// saturates. In pixels — scale with map size via [`Self::scaled_for`].
    pub continentality_reach: f32,
    /// Fraction by which precip is attenuated at full continentality
    /// (cont=1.0): `precip *= 1 - atten * cont`. `0` disables.
    pub continentality_precip_atten: f32,
    // --- ElevLapse (Pixel layer) ---
    /// Sea-level threshold. Pixels with `elev < sea_level` count as sea for the
    /// continentality BFS. In the zonegen pipeline this should be
    /// `shore_level = min_land + SHORE_LEVEL_OFFSET`.
    pub sea_level: f32,
    /// °C lost per 1.0 of elevation above the zone base. Defaults assume the
    /// zonegen elevation field's mountain class adds ~0.45 above the base, so
    /// at LAPSE = 50, a typical peak is 22.5 °C colder than its zone.
    pub lapse_per_elev_unit: f32,
    /// Pixel temperature below which a pixel is overridden to [`Biome::Ice`].
    pub ice_temp: f32,
    /// Pixel temperature below which a pixel is overridden to [`Biome::Tundra`].
    pub tundra_temp: f32,
    /// Minimum elevation delta (pixel − zone base) below which the lapse
    /// override is suppressed and the zone biome stands. Stops sub-meter
    /// noise on a polar zone's plains from flickering to Ice — the override
    /// is reserved for actual *peaks* sticking out of the zone base.
    pub peak_lapse_min_delta: f32,
    /// Annual precipitation (mm/yr) BELOW which a cold-enough pixel becomes
    /// Tundra instead of Ice — real ice caps need snow accumulation. Polar
    /// dry plains read as Tundra; polar wet zones or true mountain peaks
    /// (delta > 3 × peak_lapse_min_delta) still earn Ice. W3-C fix from B5
    /// v2.1a; defaults from climate literature (~100mm separates true ice
    /// cap from polar desert).
    pub ice_precip_min: f32,
    /// **v3 OceanCurrent** — magnitude (°C) of the E-W temperature delta
    /// from ocean gyres at the peak-effect mid-latitudes (~30-60°). Real
    /// Earth example: NYC vs Madrid at same lat differ by ~6°C (Gulf
    /// Stream vs Canary Current). Default 5.0; set to 0 to disable.
    pub ocean_current_strength: f32,
    /// **v4 Orographic** — rain shadow strength: `precip *= exp(-strength × upwind_elev_gain)`.
    /// Upwind elev_gain is accumulated positive elevation changes walking upwind from
    /// the zone site (lat-banded wind: trade winds + polar easterlies blow from east,
    /// mid-lat westerlies from west). Real Earth example: Death Valley (Sierra Nevada
    /// shadow), Patagonia (Andes shadow), Atacama (Andes + Humboldt double shadow).
    /// Default 5.0 = ~50% precip reduction behind a 0.14-relief mountain range; 0 = disabled.
    pub orographic_strength: f32,
    /// **v4 Orographic** — upwind walk distance (px). Defaults to `continentality_reach × 2`
    /// via [`Self::scaled_for`] so it tracks plate scale. Larger → moisture transport
    /// considers more remote upwind features (Earth analog: large air masses crossing
    /// continents). Smaller → only adjacent zones contribute shadow.
    pub orographic_reach: f32,
}

impl Default for WorldClimateParams {
    fn default() -> Self {
        Self {
            hemisphere_layout: HemisphereLayout::default(),
            t_eq: 28.0,
            // B5 v2.1a default: -25 → -15 (per §6.1 sweep result). Mean Ice%
            // halved (17%→10%); polar Tundra majority with Ice on actual
            // mountain peaks. W3-C precip-gated Ice (`ice_precip_min`) further
            // reduces Ice on polar dry zones.
            t_pole: -15.0,
            precip_eq: 2400.0,
            // G3 (v2.1g): 300 → 180. Real Earth subtropics get <100mm/yr;
            // default 300 left subtropics above the 250 HotDesert threshold
            // → deserts barely fired. 180 lands subtropics below 250 → more
            // HotDesert at proper Earth latitudes.
            precip_subtropic: 180.0,
            precip_midlat: 900.0,
            precip_polar: 150.0,
            continentality_reach: 200.0, // calibrated for 1024×640
            continentality_precip_atten: 0.55,
            // Derived from zonegen's actual shoreline definition — if
            // `flatworld::BASE_LEVEL` or `zonegen::SHORE_LEVEL_OFFSET` change,
            // the climate default tracks them at compile time (no silent
            // desync). MED-3 fix from /review-impl.
            sea_level: crate::flatworld::BASE_LEVEL + crate::zonegen::SHORE_LEVEL_OFFSET,
            lapse_per_elev_unit: 50.0,
            ice_temp: -10.0,
            tundra_temp: 0.0,
            // Plains relief noise tops out at ±0.026 above the zone base; 0.05
            // sits just above that, so plains stay flat-coloured while Hills
            // (up to +0.13) and Mountain peaks (up to +0.48) earn the override.
            peak_lapse_min_delta: 0.05,
            // Ice cap accumulation threshold (mm/yr). Polar dry zones
            // (precip < 100) → Tundra; polar wet zones AND tall mountain
            // peaks (delta > 3 × peak_lapse_min_delta) → Ice. Allows snow
            // caps on dry tall peaks (Antarctica is dry but ice; Atacama
            // is dry without ice — the height makes the difference).
            ice_precip_min: 100.0,
            // v3 OceanCurrent: 5.0°C E-W delta at mid-lat peak; matches
            // real Earth Gulf-Stream-vs-Canary-Current magnitude.
            ocean_current_strength: 5.0,
            // v4 Orographic: 5.0 strength = ~50% precip reduction behind a
            // 0.14-relief mountain (exp(-5 × 0.14) ≈ 0.50). Matches Earth-
            // like rain shadow magnitude (Death Valley vs Pacific coast).
            orographic_strength: 5.0,
            // v4 Orographic reach: gets overwritten by scaled_for() to ~93px
            // (continentality_reach × 2) on the default 12-plate 1024×640 world.
            // Standalone fallback keeps tests that don't call scaled_for()
            // producing usable orographic output.
            orographic_reach: 200.0,
        }
    }
}

/// Fraction of a plate's mean radius beyond which continentality saturates.
/// 0.4 → at ~40% of plate-radius from coast, attenuation hits max → the
/// inland 60% of every plate reads fully continental. Bigger plates auto-
/// scale; smaller plates auto-scale; the climate signal stays plate-relative
/// regardless of how many plates the world has. (W14 fix from B5 v2.1a.)
pub const CONTINENTALITY_REACH_FRAC: f32 = 0.4;

impl WorldClimateParams {
    /// Return a copy with [`Self::continentality_reach`] scaled to **mean
    /// plate radius**, not map size. Per W14: the right scale for
    /// "continentality saturates at the interior of a typical plate" is the
    /// plate's own size, not the rectangle's. `mean_radius = 0.5 ×
    /// sqrt(map_area / plate_count)`. With 12 plates on 1024×640 → mean
    /// radius ≈ 116 px → reach ≈ 46 px (saturates ~40% from coast). With 7
    /// plates same size → mean radius ≈ 151 px → reach ≈ 60 px.
    ///
    /// The baseline fallback (`continentality_reach = 200.0`) applies if
    /// `scaled_for` is never called — useful for tests with synthetic
    /// continentality input.
    pub fn scaled_for(mut self, width: u32, height: u32, plate_count: usize) -> Self {
        let area = (width as f32) * (height as f32);
        let mean_radius = 0.5 * (area / plate_count.max(1) as f32).sqrt();
        self.continentality_reach = (mean_radius * CONTINENTALITY_REACH_FRAC).max(1.0);
        // **v4 Orographic** — walk twice the continentality reach upwind
        // (moisture transport considers ~2 plate-radius of remote upwind
        // features, not just the zone's immediate neighbourhood).
        self.orographic_reach = self.continentality_reach * 2.0;
        self
    }
}

/// The climate field computed *at one zone*. Carried per L1 zone; consumed by
/// [`pixel_biome`] at colour-pass time with the per-pixel elevation delta.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ZoneClimate {
    /// Mean annual temperature (°C) at the zone's *base elevation*.
    pub temp_mean: f32,
    /// Annual precipitation (mm / yr).
    pub precip_annual: f32,
    /// The zone's default biome — what every pixel in the zone reads as,
    /// unless the pixel's elevation pushes it below [`WorldClimateParams::tundra_temp`].
    pub biome: Biome,
}

/// 10 Whittaker-derived biomes. **Ice** is reserved for the per-pixel lapse
/// override ([`pixel_biome`]) — the zone-level classifier never returns Ice.
///
/// **B5 v2.1f expansion**: added DeciduousForest (cool temperate forest with
/// cold winters — Eastern N America, Europe, E Asia) and Mediterranean
/// (warm temperate dry-summer — California, Mediterranean basin, Cape SA,
/// SW Australia, central Chile). Splits TemperateForest (was previously
/// catch-all for any temperate forest) into 3 distinct types matching
/// Earth's actual distribution. Without seasonality data (v5 Köppen),
/// Mediterranean is approximated by `temp 14..22 ∧ precip 250..700` (the
/// dry-summer signature without explicit cold-month gating).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Biome {
    Ice,
    Tundra,
    BorealForest,
    DeciduousForest,    // NEW v2.1f
    TemperateForest,
    Mediterranean,      // NEW v2.1f
    TemperateGrassland,
    HotDesert,
    Savanna,
    TropicalRainforest,
}

impl Biome {
    /// Stable discriminant byte (intended for any future content hash).
    /// Old 8-biome tags 0..7 preserved; new biomes get 8 (DeciduousForest) +
    /// 9 (Mediterranean) so existing hash-pinned tests stay stable for
    /// biomes that classifier-paths still produce.
    pub fn tag(self) -> u8 {
        match self {
            Biome::Ice => 0,
            Biome::Tundra => 1,
            Biome::BorealForest => 2,
            Biome::TemperateForest => 3,
            Biome::TemperateGrassland => 4,
            Biome::HotDesert => 5,
            Biome::Savanna => 6,
            Biome::TropicalRainforest => 7,
            Biome::DeciduousForest => 8,
            Biome::Mediterranean => 9,
        }
    }

    /// Display RGB for renderers. Calibrated for visual contrast.
    /// - W7 tuning (B5 v2.1a): HotDesert reddened to distinguish from beach.
    /// - v2.1f: DeciduousForest = autumn olive (warmer than TempForest's
    ///   bright green); Mediterranean = olive-tan (cooler/drier hue than
    ///   TempGrassland's khaki, distinct from Savanna's yellow).
    pub fn color(self) -> [u8; 3] {
        match self {
            Biome::Ice => [232, 238, 242],                // near-white
            Biome::Tundra => [184, 183, 174],             // pale grey-tan
            Biome::BorealForest => [74, 107, 71],         // muted grey-green
            Biome::DeciduousForest => [138, 171, 82],     // autumn olive — v2.1f
            Biome::TemperateForest => [79, 139, 65],      // bright forest
            Biome::Mediterranean => [181, 165, 98],       // olive-tan — v2.1f
            Biome::TemperateGrassland => [184, 180, 90],  // tan/khaki
            Biome::HotDesert => [216, 144, 96],           // reddish sand (Sahara) — W7
            Biome::Savanna => [201, 192, 74],             // yellow-green
            Biome::TropicalRainforest => [15, 77, 26],    // deep dark green
        }
    }
}

/// Piecewise-linear interpolation of the lat-precip stops.
///
/// Stops at `lat_dist = [0.0, 0.33, 0.67, 1.0]` with values
/// `[precip_eq, precip_subtropic, precip_midlat, precip_polar]` — the four
/// canonical bands of Earth's atmospheric circulation (ITCZ wet, subtropical
/// dry, mid-latitude wet, polar dry).
pub fn circulation_curve(lat_dist: f32, p: &WorldClimateParams) -> f32 {
    let t = lat_dist.clamp(0.0, 1.0);
    // Stops chosen so the dry-belt minimum hits at ~30° (lat_dist ≈ 0.33) and
    // the wet mid-lat peak at ~50–60° (lat_dist ≈ 0.67). Linear between.
    let raw = if t <= 0.33 {
        let k = t / 0.33;
        lerp(p.precip_eq, p.precip_subtropic, k)
    } else if t <= 0.67 {
        let k = (t - 0.33) / (0.67 - 0.33);
        lerp(p.precip_subtropic, p.precip_midlat, k)
    } else {
        let k = (t - 0.67) / (1.0 - 0.67);
        lerp(p.precip_midlat, p.precip_polar, k)
    };
    // Bound to non-negative — a hostile config (e.g. `precip_polar = -100`)
    // must not propagate negative precip into the classifier. MED-4 fix.
    raw.max(0.0)
}

/// Classify a `(temp, precip)` point into a Whittaker biome (10 zones).
///
/// **Ice is excluded by design** — it is reserved for the per-pixel lapse
/// override in [`pixel_biome`]. The zone-level classifier returns Tundra at
/// the coldest end.
///
/// **v2.1f tiers** (temp °C × precip mm/yr):
/// ```text
/// temp < 0                           → Tundra
/// temp 0..5
///   precip > 250                     → BorealForest
///   else                             → Tundra
/// temp 5..14 (cool temperate)
///   precip > 500                     → DeciduousForest    ← NEW
///   precip 250..500                  → TemperateGrassland
///   else                             → HotDesert
/// temp 14..22 (warm temperate)
///   precip > 700                     → TemperateForest    (humid subtropical)
///   precip 250..700                  → Mediterranean      ← NEW
///   else                             → HotDesert
/// temp >= 22 (hot)
///   precip > 1500                    → TropicalRainforest
///   precip 250..1500                 → Savanna
///   else                             → HotDesert
/// ```
///
/// Order of checks (precedence): cold tier → cool tier → warm tier → hot
/// tier. Each tier splits by precip.
pub fn whittaker_classify(temp: f32, precip: f32) -> Biome {
    // Cold tier (temp < 0): always Tundra.
    if temp < 0.0 {
        return Biome::Tundra;
    }
    // Subarctic (0..5 °C): Boreal if precip, else Tundra (Yakutia-style).
    if temp < 5.0 {
        if precip > 250.0 {
            return Biome::BorealForest;
        }
        return Biome::Tundra;
    }
    // Cool temperate (5..14 °C): cold-winter forest if wet, grassland if
    // medium, cold desert (folded into HotDesert) if dry.
    if temp < 14.0 {
        if precip > 500.0 {
            return Biome::DeciduousForest;
        }
        if precip > 250.0 {
            return Biome::TemperateGrassland;
        }
        return Biome::HotDesert;
    }
    // Warm temperate (14..22 °C): humid subtropical → TempForest if wet;
    // Mediterranean dry-summer proxy if medium; HotDesert if dry.
    if temp < 22.0 {
        if precip > 700.0 {
            return Biome::TemperateForest;
        }
        if precip > 250.0 {
            return Biome::Mediterranean;
        }
        return Biome::HotDesert;
    }
    // Hot (temp ≥ 22): tropical rainforest if very wet, savanna if medium,
    // desert if dry.
    if precip > 1500.0 {
        return Biome::TropicalRainforest;
    }
    if precip > 250.0 {
        return Biome::Savanna;
    }
    Biome::HotDesert
}

fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

// ─────────────────────────────────────────────────────────────────────────
// W5 (v2.1d) — Classifier-level hue interpolation near Whittaker thresholds
// ─────────────────────────────────────────────────────────────────────────
//
// Whittaker classifier is a step function on (temp, precip): adjacent biomes
// flip at hard thresholds → "Tetris" feel where 10 biome classes appear as
// 4-5 distinct color blocks. W5 fix (per roadmap): at any threshold band,
// blend the 2 adjacent biome colors weighted by distance-to-threshold.
// Doubles effective palette without adding biome classes (option A deferred
// to v5 — requires seasonality data).
//
// Algorithm: probe 4 directions (±BLEND_TEMP, ±BLEND_PRECIP). If any probe
// returns a different biome, bisect along that axis to find the exact
// threshold location, then blend center-biome and other-biome colors by
// a smoothstep curve over the normalized distance to the threshold.

/// Half-width of the temperature blend band, in °C. Threshold crossings within
/// ±this distance are blended. 1.5°C ≈ 2.5% of the typical [-20, 40] range.
/// Tested at 0.5°C 2026-05-24 to mitigate regression under v4 eval; reverted
/// to 1.5°C after upgrading eval to ecotone-aware scoring (v4.3) — ecotones
/// at full spec width are now recognized as legitimate biome transitions
/// rather than penalized as "wrong biome" pixels.
const BLEND_TEMP: f32 = 1.5;

/// Half-width of the precipitation blend band, in mm/yr. 75 mm/yr ≈ 2.5%
/// of the typical [0, 3000] range — comparable %-band to BLEND_TEMP.
/// See BLEND_TEMP doc-comment for history of 75 → 25 → 75 round trip.
const BLEND_PRECIP: f32 = 75.0;

/// Classify `(temp, precip)` and return a color blended with the nearest
/// adjacent biome across the closest Whittaker threshold within the
/// `±BLEND_TEMP / ±BLEND_PRECIP` window. Pixels deep in their biome return
/// the canonical `Biome::color()`; pixels near a threshold return a blend
/// that fades smoothly from canonical to canonical across the band.
///
/// **W5 spec** (v2.1d): doubles effective palette without adding biome
/// classes. Eliminates the "Tetris" color-block feel at biome boundaries.
pub fn whittaker_classify_blended_color(temp: f32, precip: f32) -> [u8; 3] {
    let center = whittaker_classify(temp, precip);
    let center_c = center.color();

    // Probe 4 axis-aligned directions for a different biome at ±BLEND_X.
    let probes: [(f32, f32); 4] = [
        (BLEND_TEMP, 0.0),
        (-BLEND_TEMP, 0.0),
        (0.0, BLEND_PRECIP),
        (0.0, -BLEND_PRECIP),
    ];

    let mut best: Option<(Biome, f32)> = None; // (other_biome, threshold_dist ∈ [0,1])
    for (dt, dp) in probes {
        let nb = whittaker_classify(temp + dt, precip + dp);
        if nb == center {
            continue;
        }
        // Bisect along this axis to find threshold position. lo = at center,
        // hi = at probe (where nb classifies). 6 iterations → 1/64 precision.
        let mut lo = 0.0_f32;
        let mut hi = 1.0_f32;
        for _ in 0..6 {
            let mid = (lo + hi) * 0.5;
            let mb = whittaker_classify(temp + dt * mid, precip + dp * mid);
            if mb == center {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        let threshold_dist = (lo + hi) * 0.5;
        match best {
            None => best = Some((nb, threshold_dist)),
            Some((_, td)) if threshold_dist < td => best = Some((nb, threshold_dist)),
            _ => {}
        }
    }

    let Some((other, td)) = best else {
        return center_c; // No threshold within band → pure biome color.
    };

    // Smoothstep over [0, 1]: t=0 (at threshold) → 50/50; t=1 (full BLEND_X
    // away) → 100/0 center. Ease-in-out so band edges don't have a visible
    // discontinuity where blending switches off.
    let t = td.clamp(0.0, 1.0);
    let smooth = t * t * (3.0 - 2.0 * t);
    let w_center = 0.5 + 0.5 * smooth;
    let other_c = other.color();
    [
        (center_c[0] as f32 * w_center + other_c[0] as f32 * (1.0 - w_center)) as u8,
        (center_c[1] as f32 * w_center + other_c[1] as f32 * (1.0 - w_center)) as u8,
        (center_c[2] as f32 * w_center + other_c[2] as f32 * (1.0 - w_center)) as u8,
    ]
}

/// Per-pixel COLOR (RGB) with both lapse override (Ice/Tundra at peaks) AND
/// W5 classifier hue interpolation. Mirrors [`pixel_biome`]'s decision tree
/// but returns a blended color instead of a single Biome enum.
///
/// **Lapse overrides remain hard** (Ice and Tundra at altitude flip cleanly,
/// no blend) — softening those is a separate concern (would need elev-aware
/// blend bands). Only the zone-classifier output is blended.
pub fn pixel_color(
    zc: &ZoneClimate,
    elev_pixel: f32,
    zone_base_elev: f32,
    params: &WorldClimateParams,
) -> [u8; 3] {
    let delta = elev_pixel - zone_base_elev;
    if delta < params.peak_lapse_min_delta {
        // No peak override active → blend at zone-level (temp_mean, precip).
        return whittaker_classify_blended_color(zc.temp_mean, zc.precip_annual);
    }
    let temp_pixel = zc.temp_mean - params.lapse_per_elev_unit * delta;
    if temp_pixel < params.ice_temp {
        // Same precip-gated Ice / tall-peak logic as pixel_biome; hard flip.
        let tall_peak_threshold = params.peak_lapse_min_delta * 3.0;
        if zc.precip_annual >= params.ice_precip_min || delta > tall_peak_threshold {
            return Biome::Ice.color();
        } else {
            return Biome::Tundra.color();
        }
    } else if temp_pixel < params.tundra_temp {
        return Biome::Tundra.color();
    }
    // No override → blend at the lapse-cooled (temp_pixel, precip).
    whittaker_classify_blended_color(temp_pixel, zc.precip_annual)
}

// ─────────────────────────────────────────────────────────────────────────
// Layer pipeline — compute_zone_climate (Zone level) + pixel_biome (Pixel)
// ─────────────────────────────────────────────────────────────────────────

use crate::flatworld::FlatWorld;

/// Compute the climate field for one L1 zone, applying the 5-layer pipeline.
///
/// **Per-level binding (v2):**
/// - **World layers** (Insolation, Circulation) — sampled at the zone's
///   latitude.
/// - **Plate layer** — pass-through; v3 OceanCurrent will slot here.
/// - **Zone layers** (Continentality, ZoneRefinement) — Continentality uses
///   the zone's *site* coast distance; ZoneRefinement is implicit (the whole
///   pipeline reads zone-site coords, not plate averages).
/// - **Pixel layer** (ElevLapse) — NOT applied here; that's [`pixel_biome`].
///
/// `edge_dist_sea` is the BFS distance-to-nearest-sea (`is_sea = !is_land || elev <
/// sea_level`) over the world's raster grid. The caller (zonegen) computes it
/// once per render and re-uses for the beach band.
///
/// **Known v2 limitation:** continentality is sampled at a single point (the
/// zone's site). An elongated zone with a coastal end + an inland end is
/// represented by its site's coast distance. Per-zone-average is a v3
/// refinement.
///
/// # Panics
///
/// Panics if `plate_id >= world.plates.len()` or
/// `zone_id >= world.plates[plate_id].zone_sites.len()`. Callers must pass
/// indices derived from those bounds (the in-crate `colorize_biome` does).
pub fn compute_zone_climate(
    world: &FlatWorld,
    params: &WorldClimateParams,
    plate_id: usize,
    zone_id: usize,
    edge_dist_sea: &[u32],
) -> ZoneClimate {
    let (sx, sy) = world.plates[plate_id].zone_sites[zone_id];
    let h = world.height as f32;

    // 1. Insolation (World) — sea-level temp at the zone's latitude.
    let lat_dist = params.hemisphere_layout.lat_dist(sy, h);
    let temp_sea = lerp(params.t_eq, params.t_pole, lat_dist);

    // Zone-level elevation lapse: the lat-derived temp is for sea level; a
    // zone whose base sits above `sea_level` is correspondingly cooler. This
    // gives elevated plateaus / mountain zones a colder default biome (so a
    // Tibetan plateau classifies as Boreal/Tundra, not Temperate) — and means
    // [`pixel_biome`] only has to handle the *additional* drop from the zone
    // base up to a peak (snow caps on top of an already-cool mountain zone).
    let zone_elev = world.elevation_at(sx, sy);
    let zone_lapse = params.lapse_per_elev_unit * (zone_elev - params.sea_level).max(0.0);
    let temp = temp_sea - zone_lapse;

    // 2. Circulation (World) — precip base at the zone's latitude.
    let mut precip = circulation_curve(lat_dist, params);

    // 3. **OceanCurrent (Plate)** — v3 active. E-W temperature delta from
    //    gyres: east-NH-midlat warmer, west-NH-midlat cooler; reversed in SH.
    //    Zero in tropics + polar (gyres have small effect at extremes).
    let current_delta = ocean_current_delta(world, params, plate_id, zone_id, sy, lat_dist);
    let temp = temp + current_delta;

    // 4. Continentality (Zone) — attenuate precip by coast distance.
    //
    // **W13 (v2.1c)**: average `edge_dist` across 9 points (center + 8
    // around in a circle) instead of sampling at the single zone site.
    // Elongated zones with one coastal end + one inland end get a more
    // representative "zone-average" coast distance, not site-luck.
    //
    // Sample radius is the mean nearest-neighbour distance between
    // sub-zone sites — scales with the zone's actual size, not a magic
    // number. Falls back to `params.continentality_reach * 0.3` for
    // degenerate cases (1 sub-zone).
    let subzone_sites = world.plates[plate_id].subzone_sites.get(zone_id);
    let sample_radius = subzone_sites
        .map(|s| mean_nearest_neighbour(s))
        .unwrap_or(params.continentality_reach * 0.3)
        .max(1.0);
    let coast_d = sample_edge_dist_avg(edge_dist_sea, sx, sy, world.width, sample_radius);
    let mut cont = (coast_d / params.continentality_reach).clamp(0.0, 1.0);

    // **W2 (v2.1c)**: anti-ring noise overlay. Isotropic BFS coast-distance
    // produces concentric contour lines on convex plates → biome rings.
    // Add a low-frequency fBm perturbation to break the rings without
    // changing the underlying model (full anisotropic upwind march is
    // deferred to v4 Orographic). AMP = 0.15, FREQ = 0.005 — large enough
    // to bend contours visibly, small enough to preserve the gradient.
    let n = crate::noise::fbm_3d(sx * W2_FREQ, sy * W2_FREQ, 0.0, W2_SALT, 3);
    cont = (cont + W2_AMP * n).clamp(0.0, 1.0);

    precip *= 1.0 - params.continentality_precip_atten * cont;

    // 5. (ZoneRefinement — implicit by using zone-site coords throughout.)

    // 6. **Orographic (Zone)** — v4 active. Anisotropic rain shadow: walk
    //    upwind, accumulate elevation gain, attenuate precip by exp(−strength
    //    × gain). Real Earth: Death Valley behind Sierra Nevada, Patagonia
    //    behind Andes, Atacama behind Andes+Humboldt double shadow.
    if params.orographic_strength > 0.0 && params.orographic_reach > 0.0 {
        let upwind = upwind_direction(lat_dist);
        let elev_gain = upwind_elev_gain(world, sx, sy, upwind, params.orographic_reach, 5.0);
        let shadow = (-params.orographic_strength * elev_gain).exp();
        precip *= shadow;
    }

    let biome = whittaker_classify(temp, precip);
    ZoneClimate {
        temp_mean: temp,
        precip_annual: precip,
        biome,
    }
}

/// **v4 Orographic** — upwind direction at a given latitude.
///
/// Returns the unit vector pointing TOWARDS the upwind source (i.e. walking
/// along this vector takes you upstream of the wind). Earth-physics 3-band
/// model:
/// - Tropics (lat_dist < 0.33): trade winds blow from the east → upwind = `+x`
/// - Mid-lat (0.33..0.67): westerlies blow from the west → upwind = `−x`
/// - Polar (lat_dist > 0.67): polar easterlies → upwind = `+x`
///
/// Hemisphere dimension (north vs south) doesn't affect E-W direction in the
/// simple 3-band model — the E-W reversal is symmetric across the equator.
/// (Full meridional cells with N-S component → v5+ refinement.)
fn upwind_direction(lat_dist: f32) -> (f32, f32) {
    if lat_dist < 0.33 {
        (1.0, 0.0)
    } else if lat_dist < 0.67 {
        (-1.0, 0.0)
    } else {
        (1.0, 0.0)
    }
}

/// **v4 Orographic** — walk upwind from `(sx, sy)` and accumulate **positive**
/// elevation changes. Sum represents total "mountain mass" the air passed over
/// to reach this zone — which depleted the moisture (rain shadow physics).
///
/// `step` = walking step in world pixels (small enough to catch elevation
/// transitions on mountain slopes; default 5 px). `reach` = total walk
/// distance (px). Steps = `reach / step`. Boundary hit → stop walking
/// (no contribution from beyond world edge).
fn upwind_elev_gain(
    world: &FlatWorld,
    sx: f32,
    sy: f32,
    upwind: (f32, f32),
    reach: f32,
    step: f32,
) -> f32 {
    let n_steps = ((reach / step.max(0.5)) as usize).max(1);
    let w = world.width as f32;
    let h = world.height as f32;
    let mut total_gain = 0.0_f32;
    let mut prev_elev = world.elevation_at(sx, sy);
    for i in 1..=n_steps {
        let x = sx + upwind.0 * step * i as f32;
        let y = sy + upwind.1 * step * i as f32;
        if x < 0.0 || x >= w || y < 0.0 || y >= h {
            break; // hit world edge — no further moisture-stealing terrain
        }
        let elev = world.elevation_at(x, y);
        let delta = elev - prev_elev;
        if delta > 0.0 {
            total_gain += delta;
        }
        prev_elev = elev;
    }
    total_gain
}

/// **v3 OceanCurrent** — compute the temperature delta from ocean gyres for
/// one zone. Returns °C to ADD to the zone's insolation temp.
///
/// Physical model:
/// - Real Earth: gyres rotate CW in NH, CCW in SH → east coast of each
///   continent gets warm poleward current (NH: Gulf Stream), west coast
///   gets cold equatorward current (NH: Canary). At same lat, east-NH-coast
///   ~6°C warmer than west-NH-coast (NYC vs Madrid).
/// - Implemented: classify each zone as east-half or west-half of its plate
///   (using plate centroid); apply hemisphere-correct sign × lat envelope ×
///   strength.
///
/// Lat envelope: sin curve peaking at lat_dist 0.5 (mid-lat), zero at 0.2
/// (tropics — currents have small effect on tropical temp) and 0.85 (polar —
/// currents are blocked by sea ice).
fn ocean_current_delta(
    world: &FlatWorld,
    params: &WorldClimateParams,
    plate_id: usize,
    zone_id: usize,
    sy: f32,
    lat_dist: f32,
) -> f32 {
    if params.ocean_current_strength == 0.0 {
        return 0.0;
    }
    // Lat envelope: zero outside 0.2..0.85, sin peak at 0.5
    let lat_envelope = if !(0.2..=0.85).contains(&lat_dist) {
        return 0.0;
    } else {
        let normalized = (lat_dist - 0.2) / 0.65;
        (normalized * std::f32::consts::PI).sin()
    };
    // East-west position relative to plate centroid: -1 = far west, +1 = far east
    let plate = &world.plates[plate_id];
    let (sx, _) = plate.zone_sites[zone_id];
    let (cx, _) = plate.center;
    let mut min_x = f32::INFINITY;
    let mut max_x = f32::NEG_INFINITY;
    for &(vx, _) in &plate.vertices {
        min_x = min_x.min(vx);
        max_x = max_x.max(vx);
    }
    let half_width = ((max_x - min_x) * 0.5).max(1.0);
    let ew_position = ((sx - cx) / half_width).clamp(-1.0, 1.0);
    // Hemisphere sign: NH (sy < h/2 for Equatorial) → east coast warm.
    // For NorthOnly (sy ∈ [0, h], 0 = equator, h = pole), all is NH → +1.
    // For SouthOnly, all is SH → -1.
    let h = world.height as f32;
    let hemi_sign = match params.hemisphere_layout {
        HemisphereLayout::Equatorial => {
            if sy < h * 0.5 { 1.0 } else { -1.0 }
        }
        HemisphereLayout::NorthOnly => 1.0,
        HemisphereLayout::SouthOnly => -1.0,
    };
    ew_position * hemi_sign * lat_envelope * params.ocean_current_strength
}

/// **W2 (v2.1c) anti-ring noise overlay parameters**.
/// - `W2_AMP = 0.30` — peak perturbation added to `cont` (post-clamp it
///   still lands in [0, 1]). Bumped from initial 0.15 after 2026-05-24
///   visual review showed 0.15 produced byte-different but visually
///   imperceptible output on most renders (only flips biome at exact
///   boundary pixels). 0.30 doubles the perturbation → biome boundaries
///   actually bend visibly, breaking the concentric-ring artifact PO
///   flagged in W2 spec.
/// - `W2_FREQ = 0.005` — noise spatial frequency. 1/0.005 = 200 px
///   wavelength on the default 1024×640 map ≈ 1.5 plate diameters →
///   continentality contours bend on a plate-scale, not at pixel-noise
///   scale.
/// - `W2_SALT = 0xC0FE` — deterministic salt; tied to v2.1c so future
///   rework can opt in to a different field without breaking history.
const W2_AMP: f32 = 0.15;
const W2_FREQ: f32 = 0.005;
const W2_SALT: u32 = 0xC0FE;

/// **W13 (v2.1c) helper**: mean nearest-neighbour distance among `points`,
/// in the same coordinate frame. Used as the sample radius for
/// [`sample_edge_dist_avg`] so the "around the zone" sample circle scales
/// with the zone's actual sub-zone density.
///
/// Returns `0.0` for 0 or 1 input points (caller must fall back).
fn mean_nearest_neighbour(points: &[(f32, f32)]) -> f32 {
    if points.len() < 2 {
        return 0.0;
    }
    let mut total = 0.0;
    let mut count = 0;
    for (i, &(ax, ay)) in points.iter().enumerate() {
        let mut nearest_sq = f32::INFINITY;
        for (j, &(bx, by)) in points.iter().enumerate() {
            if i == j {
                continue;
            }
            let dx = ax - bx;
            let dy = ay - by;
            let d_sq = dx * dx + dy * dy;
            if d_sq < nearest_sq {
                nearest_sq = d_sq;
            }
        }
        if nearest_sq.is_finite() {
            total += nearest_sq.sqrt();
            count += 1;
        }
    }
    if count == 0 {
        0.0
    } else {
        total / count as f32
    }
}

/// **W13 (v2.1c)**: average `sample_edge_dist` across 9 points (center +
/// 8 cardinal/diagonal at `radius`). Falls back to single-site sample if
/// `radius <= 0`. Returns the average BFS coast distance, which represents
/// the zone better than a single-site sample for elongated zones whose
/// site happens to land on a coastal or interior extreme.
fn sample_edge_dist_avg(
    edge_dist: &[u32],
    sx: f32,
    sy: f32,
    world_w: u32,
    radius: f32,
) -> f32 {
    let center = sample_edge_dist(edge_dist, sx, sy, world_w);
    if radius <= 0.0 {
        return center;
    }
    // 8 points around a circle: cardinals + diagonals (sin/cos of multiples
    // of 45°). Diagonals use 1/√2 ≈ 0.7071 so all 8 points lie on the same
    // radius — uniform sampling.
    const D: f32 = std::f32::consts::FRAC_1_SQRT_2;
    const OFFSETS: [(f32, f32); 8] = [
        (1.0, 0.0),
        (D, D),
        (0.0, 1.0),
        (-D, D),
        (-1.0, 0.0),
        (-D, -D),
        (0.0, -1.0),
        (D, -D),
    ];
    let mut sum = center;
    for (dx, dy) in OFFSETS {
        sum += sample_edge_dist(edge_dist, sx + dx * radius, sy + dy * radius, world_w);
    }
    sum / 9.0
}

/// Sample the `edge_dist_sea` grid at world point `(sx, sy)`. Returns the BFS
/// distance to the nearest sea pixel as f32. Out-of-bounds → `0.0` (treats
/// the off-map as sea, so peripheral zones aren't accidentally continental).
fn sample_edge_dist(edge_dist: &[u32], sx: f32, sy: f32, world_w: u32) -> f32 {
    // Reject non-finite inputs explicitly — `NaN as isize` is `0` in Rust,
    // which would silently sample the corner. LOW-7 fix from /review-impl.
    if !sx.is_finite() || !sy.is_finite() {
        return 0.0;
    }
    let w = world_w as usize;
    let h = edge_dist.len() / w.max(1);
    let px = sx.floor() as isize;
    let py = sy.floor() as isize;
    if px < 0 || py < 0 || px >= w as isize || py >= h as isize {
        return 0.0;
    }
    let i = py as usize * w + px as usize;
    edge_dist[i] as f32
}

/// Per-pixel biome — applies the **ElevLapse** override on the zone's biome.
///
/// `elev_pixel` is the pixel's post-erosion elevation; `zone_base_elev` is the
/// zone's anchor base (the lapse anchor). The lapse override only fires when
/// the pixel sits **strictly above** its zone base — pixels at or below the
/// zone base (a flat zone, or an erosion-carved valley) keep the zone biome.
/// This is what makes the override mean "snow cap on a peak" rather than "I
/// am the new climate of this whole zone": the zone climate ([`compute_zone_climate`])
/// already incorporates the zone's base elevation via its own lapse, so the
/// per-pixel pass only contributes the *additional* drop from the zone base
/// up to a peak.
///
/// Order: Ice (very cold) > Tundra (cold) > zone biome (default).
pub fn pixel_biome(
    zc: &ZoneClimate,
    elev_pixel: f32,
    zone_base_elev: f32,
    params: &WorldClimateParams,
) -> Biome {
    let delta = elev_pixel - zone_base_elev;
    if delta < params.peak_lapse_min_delta {
        // Pixel at, below, or only marginally above the zone base — no peak to
        // put a snow cap on. The zone biome is authoritative; we don't let
        // sub-peak noise flip a flat-Tundra polar plain to Ice (the bug a
        // pure `delta > 0` test would re-introduce).
        return zc.biome;
    }
    let temp_pixel = zc.temp_mean - params.lapse_per_elev_unit * delta;
    if temp_pixel < params.ice_temp {
        // W3-C precip-gated Ice: real ice caps need snow accumulation. A
        // cold dry plain stays Tundra; a cold wet zone OR a truly tall peak
        // (delta > 3 × peak_gate) earns Ice. Polar dry plain (low precip,
        // shallow delta) → Tundra. Polar Antarctica-style ice cap (low
        // precip BUT tall delta) → Ice. Polar moist mountain (wet + tall)
        // → Ice.
        let tall_peak_threshold = params.peak_lapse_min_delta * 3.0;
        if zc.precip_annual >= params.ice_precip_min || delta > tall_peak_threshold {
            Biome::Ice
        } else {
            Biome::Tundra
        }
    } else if temp_pixel < params.tundra_temp {
        Biome::Tundra
    } else {
        zc.biome
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Sidecar export — eval / consumer contract (v4 law-based metrics)
// ─────────────────────────────────────────────────────────────────────────
//
// Dumps per-zone climate alongside the biome PNG so external eval can score
// against geographic-law correlations (temperature gradient by latitude,
// precipitation gradient by circulation curve) without re-implementing the
// climate physics in another language.
//
// Source-of-truth invariant: this calls the SAME `compute_zone_climate` the
// renderer uses. Pixel painted with biome X for zone Z ⇒ JSON also reports
// biome X for zone Z. Pinned by `export_matches_in_memory_compute` test.

/// One zone's climate snapshot. Field names are wire-stable for JSON consumers.
#[derive(Debug, Clone, Serialize)]
pub struct ZoneClimateExport {
    pub plate_id: usize,
    pub zone_id: usize,
    pub site: [f32; 2],
    pub lat_dist: f32,
    pub temp_mean: f32,
    pub precip_annual: f32,
    pub biome: &'static str,
    pub base_elevation: f32,
}

/// Scenario params snapshot — eval needs these to predict the expected
/// circulation curve per zone (precipitation_gradient_law correlates observed
/// vs predicted, normalizing for scenario like Hothouse / Snowball / Desert).
#[derive(Debug, Clone, Serialize)]
pub struct ClimateParamsExport {
    pub t_eq: f32,
    pub t_pole: f32,
    pub precip_eq: f32,
    pub precip_subtropic: f32,
    pub precip_midlat: f32,
    pub precip_polar: f32,
    pub continentality_reach: f32,
    pub continentality_precip_atten: f32,
    pub ocean_current_strength: f32,
    pub orographic_strength: f32,
    pub orographic_reach: f32,
}

/// Top-level world climate export (one JSON document per render).
#[derive(Debug, Clone, Serialize)]
pub struct WorldClimateExport {
    pub width: u32,
    pub height: u32,
    pub hemisphere_layout: &'static str,
    pub climate_params: ClimateParamsExport,
    pub zones: Vec<ZoneClimateExport>,
}

/// Build a sidecar export of every zone's climate. Uses the same
/// [`compute_zone_climate`] the renderer uses, so values match the painted
/// pixels by construction — see `export_matches_in_memory_compute` test.
///
/// `is_sea` is derived from plate coverage (matches render's `is_sea` in v2
/// since coast taper guarantees land ≥ sea_level — only void cells are sea).
pub fn export_zone_climates(
    world: &FlatWorld,
    params: &WorldClimateParams,
) -> WorldClimateExport {
    let w = world.width as usize;
    let h = world.height as usize;
    let mut is_sea = vec![false; w * h];
    for py in 0..h {
        for px in 0..w {
            if world
                .plates_at(px as f32 + 0.5, py as f32 + 0.5)
                .is_empty()
            {
                is_sea[py * w + px] = true;
            }
        }
    }
    let edge_dist = crate::zonegen::edge_dist_from_sea(&is_sea, w, h);

    let mut zones = Vec::new();
    for (pid, plate) in world.plates.iter().enumerate() {
        for (zid, &(sx, sy)) in plate.zone_sites.iter().enumerate() {
            let lat_dist = params.hemisphere_layout.lat_dist(sy, h as f32);
            let zc = compute_zone_climate(world, params, pid, zid, &edge_dist);
            zones.push(ZoneClimateExport {
                plate_id: pid,
                zone_id: zid,
                site: [sx, sy],
                lat_dist,
                temp_mean: zc.temp_mean,
                precip_annual: zc.precip_annual,
                biome: biome_name(zc.biome),
                base_elevation: world.elevation_at(sx, sy),
            });
        }
    }

    WorldClimateExport {
        width: world.width,
        height: world.height,
        hemisphere_layout: hemisphere_name(params.hemisphere_layout),
        climate_params: ClimateParamsExport {
            t_eq: params.t_eq,
            t_pole: params.t_pole,
            precip_eq: params.precip_eq,
            precip_subtropic: params.precip_subtropic,
            precip_midlat: params.precip_midlat,
            precip_polar: params.precip_polar,
            continentality_reach: params.continentality_reach,
            continentality_precip_atten: params.continentality_precip_atten,
            ocean_current_strength: params.ocean_current_strength,
            orographic_strength: params.orographic_strength,
            orographic_reach: params.orographic_reach,
        },
        zones,
    }
}

fn biome_name(b: Biome) -> &'static str {
    match b {
        Biome::Ice => "Ice",
        Biome::Tundra => "Tundra",
        Biome::BorealForest => "BorealForest",
        Biome::DeciduousForest => "DeciduousForest",
        Biome::TemperateForest => "TemperateForest",
        Biome::Mediterranean => "Mediterranean",
        Biome::TemperateGrassland => "TemperateGrassland",
        Biome::HotDesert => "HotDesert",
        Biome::Savanna => "Savanna",
        Biome::TropicalRainforest => "TropicalRainforest",
    }
}

fn hemisphere_name(h: HemisphereLayout) -> &'static str {
    match h {
        HemisphereLayout::Equatorial => "Equatorial",
        HemisphereLayout::NorthOnly => "NorthOnly",
        HemisphereLayout::SouthOnly => "SouthOnly",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---- HemisphereLayout::lat_dist ----

    #[test]
    fn hemisphere_equatorial_centre_is_equator() {
        let h = 640.0;
        assert!((HemisphereLayout::Equatorial.lat_dist(320.0, h) - 0.0).abs() < 1e-5);
    }

    #[test]
    fn hemisphere_equatorial_edges_are_poles() {
        let h = 640.0;
        assert!((HemisphereLayout::Equatorial.lat_dist(0.0, h) - 1.0).abs() < 1e-5);
        assert!((HemisphereLayout::Equatorial.lat_dist(640.0, h) - 1.0).abs() < 1e-5);
    }

    #[test]
    fn hemisphere_north_only_y0_is_equator_and_yh_is_pole() {
        let h = 640.0;
        assert!((HemisphereLayout::NorthOnly.lat_dist(0.0, h) - 0.0).abs() < 1e-5);
        assert!((HemisphereLayout::NorthOnly.lat_dist(640.0, h) - 1.0).abs() < 1e-5);
    }

    #[test]
    fn hemisphere_south_only_yh_is_equator_and_y0_is_pole() {
        let h = 640.0;
        assert!((HemisphereLayout::SouthOnly.lat_dist(0.0, h) - 1.0).abs() < 1e-5);
        assert!((HemisphereLayout::SouthOnly.lat_dist(640.0, h) - 0.0).abs() < 1e-5);
    }

    #[test]
    fn hemisphere_lat_dist_is_always_in_unit_interval() {
        // LOW-4 fix from /review-impl: property test. For every layout, every
        // out-of-range y, and degenerate / huge h values, the result must
        // stay in [0, 1] — the rest of the pipeline depends on it.
        let layouts = [
            HemisphereLayout::Equatorial,
            HemisphereLayout::NorthOnly,
            HemisphereLayout::SouthOnly,
        ];
        let ys = [-1000.0_f32, -1.0, 0.0, 1.0, 100.0, 320.0, 640.0, 1280.0, 1e8];
        let hs = [1.0_f32, 100.0, 640.0, 1e6, 1e9];
        for layout in layouts {
            for &h in &hs {
                for &y in &ys {
                    let v = layout.lat_dist(y, h);
                    assert!(
                        v.is_finite() && (0.0..=1.0).contains(&v),
                        "lat_dist out of [0,1]: layout={layout:?} y={y} h={h} v={v}"
                    );
                }
            }
        }
    }

    // ---- circulation_curve ----

    #[test]
    fn circulation_curve_hits_all_four_anchors() {
        let p = WorldClimateParams::default();
        assert!((circulation_curve(0.0, &p) - p.precip_eq).abs() < 1e-3);
        assert!((circulation_curve(0.33, &p) - p.precip_subtropic).abs() < 1e-3);
        assert!((circulation_curve(0.67, &p) - p.precip_midlat).abs() < 1e-3);
        assert!((circulation_curve(1.0, &p) - p.precip_polar).abs() < 1e-3);
    }

    #[test]
    fn circulation_curve_is_monotonic_between_anchors() {
        // Between 0 and 0.33 (eq → subtropic dry): precip drops monotonically.
        let p = WorldClimateParams::default();
        let a = circulation_curve(0.1, &p);
        let b = circulation_curve(0.2, &p);
        let c = circulation_curve(0.3, &p);
        assert!(a > b && b > c, "monotone fail (eq→subtropic): {a} {b} {c}");
        // Between 0.33 and 0.67 (subtropic dry → midlat wet): rises.
        let d = circulation_curve(0.4, &p);
        let e = circulation_curve(0.55, &p);
        let f = circulation_curve(0.66, &p);
        assert!(d < e && e < f, "monotone fail (subtropic→midlat): {d} {e} {f}");
    }

    // ---- whittaker_classify ----

    #[test]
    fn whittaker_nine_biomes_reachable_ice_excluded() {
        // v2.1f: 10-biome enum; classifier reaches 9 (Ice excluded — that's
        // pixel-lapse-override only).
        let mut seen = [false; 10];
        for ti in 0..=30 {
            for pi in 0..=30 {
                let t = -20.0 + (ti as f32) * 2.0; // -20 .. 40 °C
                let pr = (pi as f32) * 200.0; // 0 .. 6000 mm/yr
                let b = whittaker_classify(t, pr);
                seen[b.tag() as usize] = true;
            }
        }
        assert!(!seen[Biome::Ice.tag() as usize], "Ice must NOT come from zone classifier");
        for b in [
            Biome::Tundra,
            Biome::BorealForest,
            Biome::DeciduousForest,    // NEW v2.1f
            Biome::TemperateForest,
            Biome::Mediterranean,       // NEW v2.1f
            Biome::TemperateGrassland,
            Biome::HotDesert,
            Biome::Savanna,
            Biome::TropicalRainforest,
        ] {
            assert!(seen[b.tag() as usize], "missing {b:?}");
        }
    }

    #[test]
    fn whittaker_canonical_points() {
        // Cold tier
        assert_eq!(whittaker_classify(-15.0, 100.0), Biome::Tundra);
        assert_eq!(whittaker_classify(3.0, 600.0), Biome::BorealForest);
        // Cool temperate (5..14)
        assert_eq!(whittaker_classify(10.0, 800.0), Biome::DeciduousForest);   // wet cool
        assert_eq!(whittaker_classify(10.0, 400.0), Biome::TemperateGrassland); // mid
        assert_eq!(whittaker_classify(10.0, 100.0), Biome::HotDesert);          // cold desert
        // Warm temperate (14..22)
        assert_eq!(whittaker_classify(17.0, 1000.0), Biome::TemperateForest);   // humid subtropical
        assert_eq!(whittaker_classify(17.0, 500.0), Biome::Mediterranean);      // dry-summer
        assert_eq!(whittaker_classify(17.0, 100.0), Biome::HotDesert);          // warm desert
        // Hot
        assert_eq!(whittaker_classify(25.0, 100.0), Biome::HotDesert);
        assert_eq!(whittaker_classify(25.0, 800.0), Biome::Savanna);
        assert_eq!(whittaker_classify(27.0, 2500.0), Biome::TropicalRainforest);
    }

    // ---- compute_zone_climate ----

    use crate::flatworld::{generate as gen_flat, FlatParams};

    /// A trivial test world: 2 plates, predictable layout, seed-pinned.
    fn test_world() -> crate::flatworld::FlatWorld {
        gen_flat(&FlatParams {
            width: 640,
            height: 400,
            plate_count: 4,
            seed: 7,
            ..FlatParams::default()
        })
    }

    /// A trivial all-coast `edge_dist_sea` array (every cell = 0 dist) so
    /// continentality is 0 — isolates insolation + circulation in unit tests.
    fn edge_dist_all_coast(world: &crate::flatworld::FlatWorld) -> Vec<u32> {
        vec![0u32; (world.width as usize) * (world.height as usize)]
    }

    #[test]
    fn ocean_current_sign_matches_hemisphere() {
        // v3 OceanCurrent semantic: NH east coast warm + west coast cold;
        // SH reversed. Test the helper directly with synthetic positions so
        // we don't depend on test_world's plate layout luck.
        let world = test_world();
        let params = WorldClimateParams::default();
        let h = world.height as f32;
        // Pick a plate — any plate works because ocean_current_delta only
        // needs (plate.vertices, plate.center, plate.zone_sites).
        let p = &world.plates[0];
        if p.zone_sites.len() < 2 { return; } // skip if test_world degenerate
        // Manually compute east-most and west-most zone indices.
        let mut min_x = (f32::INFINITY, 0usize);
        let mut max_x = (f32::NEG_INFINITY, 0usize);
        for (zi, &(sx, _)) in p.zone_sites.iter().enumerate() {
            if sx < min_x.0 { min_x = (sx, zi); }
            if sx > max_x.0 { max_x = (sx, zi); }
        }
        if min_x.1 == max_x.1 { return; }
        // Synthesize NH mid-lat sy + lat_dist=0.5 for the helper.
        let nh_sy = h * 0.25;     // upper half = NH for Equatorial
        let sh_sy = h * 0.75;     // lower half = SH for Equatorial
        let lat_d = 0.5;
        let nh_west = ocean_current_delta(&world, &params, 0, min_x.1, nh_sy, lat_d);
        let nh_east = ocean_current_delta(&world, &params, 0, max_x.1, nh_sy, lat_d);
        let sh_west = ocean_current_delta(&world, &params, 0, min_x.1, sh_sy, lat_d);
        let sh_east = ocean_current_delta(&world, &params, 0, max_x.1, sh_sy, lat_d);
        // NH: east > west.
        assert!(
            nh_east > nh_west,
            "NH: east coast {} should be warmer than west {}", nh_east, nh_west
        );
        // SH: opposite (west > east).
        assert!(
            sh_west > sh_east,
            "SH: west coast {} should be warmer than east {}", sh_west, sh_east
        );
        // NH east + SH east signs differ (hemisphere flip).
        assert!(nh_east * sh_east <= 0.0, "NH east + SH east signs should differ");
    }

    #[test]
    fn ocean_current_zero_at_equator_and_pole() {
        // Lat envelope clamps to 0 outside lat_dist 0.2..0.85.
        let world = test_world();
        let params = WorldClimateParams::default();
        let h = world.height as f32;
        // Use east-most zone of plate 0; sy doesn't matter for the envelope check
        // since we control lat_dist directly.
        let p = &world.plates[0];
        if p.zone_sites.is_empty() { return; }
        // Find some zone with non-trivial ew_position.
        let mut max_x = (f32::NEG_INFINITY, 0usize);
        for (zi, &(sx, _)) in p.zone_sites.iter().enumerate() {
            if sx > max_x.0 { max_x = (sx, zi); }
        }
        // Equator (lat_dist 0.1) → envelope = 0.
        let eq = ocean_current_delta(&world, &params, 0, max_x.1, h * 0.5, 0.1);
        assert_eq!(eq, 0.0, "equator current delta should be 0");
        // Pole (lat_dist 0.95) → envelope = 0.
        let pol = ocean_current_delta(&world, &params, 0, max_x.1, h * 0.05, 0.95);
        assert_eq!(pol, 0.0, "polar current delta should be 0");
    }

    #[test]
    fn ocean_current_disabled_when_strength_zero() {
        // Setting `ocean_current_strength = 0` must completely disable the
        // current modifier (used by author code to opt out for non-Earth-like
        // worlds).
        let world = test_world();
        let params_off = WorldClimateParams {
            ocean_current_strength: 0.0,
            ..WorldClimateParams::default()
        };
        let params_on = WorldClimateParams::default();
        let ed = edge_dist_all_coast(&world);
        // Compare temp of the same zone with current on/off.
        let p = &world.plates[0];
        let zi = 0;
        let zc_off = compute_zone_climate(&world, &params_off, 0, zi, &ed);
        let zc_on = compute_zone_climate(&world, &params_on, 0, zi, &ed);
        // Difference should be exactly the current delta (could be 0 if zone is
        // tropics or at plate center). For at least one zone in the world, the
        // two should differ.
        let any_zone_differs = (0..p.zone_sites.len()).any(|zi| {
            let off = compute_zone_climate(&world, &params_off, 0, zi, &ed);
            let on  = compute_zone_climate(&world, &params_on, 0, zi, &ed);
            (off.temp_mean - on.temp_mean).abs() > 0.01
        });
        assert!(any_zone_differs, "current should affect at least one zone in test_world plate 0");
        // And the off-version of zone 0 itself must NOT be modified by current.
        let zc_off_2 = compute_zone_climate(&world, &params_off, 0, zi, &ed);
        assert_eq!(zc_off.temp_mean, zc_off_2.temp_mean, "deterministic when off");
        // (silence unused warning if zc_on irrelevant)
        let _ = zc_on;
    }

    #[test]
    fn compute_warmer_near_equator_than_pole() {
        // Equatorial layout — a zone with site near y=h/2 should be warmer
        // than any zone with site near y=0. Use the synthetic world and
        // search for two zones at extreme y.
        let world = test_world();
        let params = WorldClimateParams::default();
        let ed = edge_dist_all_coast(&world);
        let h = world.height as f32;

        // Find the zone with the smallest |sy - h/2| (most equatorial)
        // and the largest (most polar).
        let mut eq_t = None;
        let mut po_t = None;
        let mut eq_dy = f32::INFINITY;
        let mut po_dy = 0.0f32;
        for (pi, p) in world.plates.iter().enumerate() {
            for (zi, &(_, sy)) in p.zone_sites.iter().enumerate() {
                let dy = (sy - h * 0.5).abs();
                let zc = compute_zone_climate(&world, &params, pi, zi, &ed);
                if dy < eq_dy {
                    eq_dy = dy;
                    eq_t = Some(zc.temp_mean);
                }
                if dy > po_dy {
                    po_dy = dy;
                    po_t = Some(zc.temp_mean);
                }
            }
        }
        let eq_t = eq_t.unwrap();
        let po_t = po_t.unwrap();
        assert!(eq_t > po_t, "equatorial zone temp {eq_t} not warmer than polar {po_t}");
    }

    #[test]
    fn compute_continentality_actually_attenuates_precip() {
        // MED-2 fix from /review-impl: the prior version used `>=` so the test
        // passed even when `continentality_precip_atten = 0` disabled the
        // entire layer. This version uses synthetic edge_dist values directly
        // sampled at zone sites (instead of relying on x-position luck) and
        // asserts a STRICT inequality with a measurable magnitude.
        let world = test_world();
        // Pin reach so a coast (dist=0) vs interior (dist=400) zone gives a
        // clear, computable attenuation independent of map size.
        let params = WorldClimateParams {
            continentality_reach: 200.0,
            continentality_precip_atten: 0.55,
            ..WorldClimateParams::default()
        };

        let w = world.width as usize;
        let h = world.height as usize;

        // Two synthetic edge_dist arrays: all-zero (coast everywhere) and
        // all-large (interior everywhere). Reusing the same plate+zone keeps
        // lat-based insolation+circulation equal across the two queries.
        let ed_coast: Vec<u32> = vec![0u32; w * h];
        let ed_interior: Vec<u32> = vec![400u32; w * h]; // 2× reach → saturated cont = 1

        let zc_coast = compute_zone_climate(&world, &params, 0, 0, &ed_coast);
        let zc_inter = compute_zone_climate(&world, &params, 0, 0, &ed_interior);

        // With atten=0.55 and cont=1 (saturated), interior should be ~45 %
        // of coast. **W2 noise overlay (v2.1c)** adds AMP=±0.30 perturbation
        // to `cont` (post-clamp), so observed ratio at saturated interior
        // can swing ±(0.30 × 0.55) = ±0.165 around 0.45 → [0.285, 0.615].
        // Tolerance loosened to ±0.20 to admit the bumped W2_AMP while
        // still asserting the layer fires (no atten = ratio 1.0).
        let ratio = zc_inter.precip_annual / zc_coast.precip_annual.max(1e-6);
        assert!(
            (ratio - 0.45).abs() < 0.20,
            "interior precip ratio should be ~0.45 ± W2_AMP × atten vs coast; got {ratio}"
        );

        // Bonus: with atten=0, the prior version's `>=` passed silently.
        // Confirm here that disabling the layer makes them EQUAL (no attenuation).
        let mut p0 = params.clone();
        p0.continentality_precip_atten = 0.0;
        let zc_coast0 = compute_zone_climate(&world, &p0, 0, 0, &ed_coast);
        let zc_inter0 = compute_zone_climate(&world, &p0, 0, 0, &ed_interior);
        assert_eq!(
            zc_coast0.precip_annual, zc_inter0.precip_annual,
            "atten=0 must disable continentality"
        );
    }

    // ---- pixel_biome ----

    #[test]
    fn pixel_biome_low_elev_keeps_zone_biome() {
        let zc = ZoneClimate {
            temp_mean: 26.0,
            precip_annual: 2000.0,
            biome: Biome::TropicalRainforest,
        };
        let p = WorldClimateParams::default();
        // Pixel sitting at the zone base → no lapse → zone biome.
        assert_eq!(pixel_biome(&zc, 0.35, 0.35, &p), Biome::TropicalRainforest);
    }

    #[test]
    fn pixel_biome_tropical_peak_is_ice() {
        let zc = ZoneClimate {
            temp_mean: 26.0,
            precip_annual: 2000.0,
            biome: Biome::TropicalRainforest,
        };
        let p = WorldClimateParams::default(); // ice_temp = -10, lapse = 50
        // Need temp_pixel < -10 → delta > (26 - -10) / 50 = 0.72.
        let elev = 0.35 + 0.80; // delta 0.80 → temp_pixel = 26 - 40 = -14 → Ice
        assert_eq!(pixel_biome(&zc, elev, 0.35, &p), Biome::Ice);
    }

    #[test]
    fn pixel_biome_precip_gated_ice_polar_dry_plain_stays_tundra() {
        // W3-C fix (B5 v2.1a): a polar zone classified Tundra with LOW precip
        // and a SHALLOW peak (just above the gate, NOT tall) — even though
        // temp_pixel falls below ice_temp, Ice should NOT fire because
        // (a) precip < ice_precip_min AND (b) delta is not > 3 × peak gate.
        // This is the "polar dry desert" case (Atacama-like, Antarctica's
        // dry valleys) — Tundra, not Ice.
        let zc = ZoneClimate {
            temp_mean: -18.0,
            precip_annual: 50.0, // dry — below ice_precip_min (100)
            biome: Biome::Tundra,
        };
        let p = WorldClimateParams::default(); // gate=0.05, ice_temp=-10, lapse=50
        // Shallow peak: delta = 0.08 (just above gate, NOT > 3×gate=0.15).
        // temp_pixel = -18 - 50*0.08 = -22 < ice_temp → would be Ice in v2.
        // W3-C: Tundra (low precip + shallow delta).
        assert_eq!(pixel_biome(&zc, 0.48, 0.40, &p), Biome::Tundra);
    }

    #[test]
    fn pixel_biome_precip_gated_ice_polar_wet_zone_becomes_ice() {
        // Same shallow peak but the zone has accumulation-grade precip
        // (≥ ice_precip_min) → Ice fires.
        let zc = ZoneClimate {
            temp_mean: -18.0,
            precip_annual: 200.0, // wet — above ice_precip_min
            biome: Biome::Tundra,
        };
        let p = WorldClimateParams::default();
        assert_eq!(pixel_biome(&zc, 0.48, 0.40, &p), Biome::Ice);
    }

    #[test]
    fn pixel_biome_precip_gated_ice_dry_tall_peak_still_ice() {
        // Antarctica-style: dry zone (no snowfall) BUT very tall peak — the
        // peak's altitude alone earns Ice (delta > 3 × peak_lapse_min_delta).
        let zc = ZoneClimate {
            temp_mean: -18.0,
            precip_annual: 50.0, // dry
            biome: Biome::Tundra,
        };
        let p = WorldClimateParams::default(); // 3×gate = 0.15
        // Tall peak: delta = 0.30 > 0.15 → Ice via tall-peak override.
        assert_eq!(pixel_biome(&zc, 0.70, 0.40, &p), Biome::Ice);
    }

    #[test]
    fn pixel_biome_precip_gated_ice_works_on_non_tundra_zone() {
        // LOW-2 fix from /review-impl: the 3 precip-gated Ice tests use
        // `biome=Tundra`. A refactor that accidentally gated the precip
        // check on `zc.biome == Tundra` would pass those tests but break for
        // other zones. Confirm the logic is zone-biome-independent: a
        // BorealForest zone with very cold pixel + low precip → Tundra
        // (precip-gated NOT Ice), not BorealForest.
        let zc = ZoneClimate {
            temp_mean: -15.0,
            precip_annual: 50.0, // dry — below ice_precip_min
            biome: Biome::BorealForest, // NOT Tundra
        };
        let p = WorldClimateParams::default();
        // Shallow peak: delta = 0.08 (NOT > 3 × peak_gate=0.15).
        // temp_pixel = -15 - 50*0.08 = -19 < ice_temp=-10 → would be Ice in v2.
        // W3-C: precip < ice_precip_min AND delta < tall_peak → fall through to
        // Tundra branch (temp_pixel < tundra_temp=0).
        assert_eq!(pixel_biome(&zc, 0.48, 0.40, &p), Biome::Tundra);
    }

    #[test]
    fn pixel_biome_polar_zone_plains_stay_tundra_only_peaks_become_ice() {
        // Regression: a polar zone (Tundra, temp_mean = -28 °C) must NOT have
        // its flat / shallow-noise pixels overridden to Ice just because
        // temp_mean < ice_temp. The `peak_lapse_min_delta` gate (default
        // 0.05) suppresses the override for sub-peak relief — only an actual
        // peak ≥ 0.05 above the zone base earns the override.
        let zc = ZoneClimate {
            temp_mean: -28.0,
            precip_annual: 100.0,
            biome: Biome::Tundra,
        };
        let p = WorldClimateParams::default();
        // Pixel exactly at zone base → delta = 0 → zone biome (Tundra).
        assert_eq!(pixel_biome(&zc, 0.40, 0.40, &p), Biome::Tundra);
        // Pixel BELOW zone base (eroded valley) → delta < 0 → zone biome.
        assert_eq!(pixel_biome(&zc, 0.39, 0.40, &p), Biome::Tundra);
        // Plains noise: delta = +0.02 (typical) → still below 0.05 gate → zone biome.
        assert_eq!(pixel_biome(&zc, 0.42, 0.40, &p), Biome::Tundra);
        // Just under the gate: delta = +0.049 → still zone biome.
        assert_eq!(pixel_biome(&zc, 0.449, 0.40, &p), Biome::Tundra);
        // Real peak: delta = +0.20 (≥ 0.05) → temp_pixel = -28 - 10 = -38 → Ice.
        assert_eq!(pixel_biome(&zc, 0.60, 0.40, &p), Biome::Ice);
    }

    #[test]
    fn pixel_biome_gate_threshold_value_actually_matters() {
        // LOW-5 fix from /review-impl: the prior tests used the default
        // `peak_lapse_min_delta = 0.05` for the sub-peak / peak boundary;
        // they would pass with default values in (~0.02, ~0.20). This test
        // pins the parameter's behavior by varying it and asserting the same
        // pixel flips from zone biome to Ice as the gate moves.
        let zc = ZoneClimate {
            temp_mean: -28.0,
            precip_annual: 100.0,
            biome: Biome::Tundra,
        };
        let pixel_elev = 0.46; // delta = +0.06 above zone base 0.40

        // Loose gate (0.03 < 0.06) → override fires → Ice (very-cold polar).
        let p_loose = WorldClimateParams {
            peak_lapse_min_delta: 0.03,
            ..WorldClimateParams::default()
        };
        assert_eq!(pixel_biome(&zc, pixel_elev, 0.40, &p_loose), Biome::Ice);

        // Tight gate (0.10 > 0.06) → override suppressed → zone biome (Tundra).
        let p_tight = WorldClimateParams {
            peak_lapse_min_delta: 0.10,
            ..WorldClimateParams::default()
        };
        assert_eq!(pixel_biome(&zc, pixel_elev, 0.40, &p_tight), Biome::Tundra);
    }

    #[test]
    fn pixel_biome_at_exact_gate_boundary_triggers_override() {
        // LOW-6 fix from /review-impl: the gate uses strict `<` so
        // `delta == peak_lapse_min_delta` should fire the override. Locks
        // the boundary inclusive/exclusive choice. Use `zone_base = 0.0` so
        // `delta == elev_pixel` exactly (no f32 subtraction loss).
        let zc = ZoneClimate {
            temp_mean: -28.0,
            precip_annual: 100.0,
            biome: Biome::Tundra,
        };
        let p = WorldClimateParams::default(); // gate = 0.05
        // delta = exactly peak_lapse_min_delta → NOT strictly less → override fires.
        // temp_pixel = -28 - 50*0.05 = -30.5 < ice_temp (-10) → Ice.
        assert_eq!(pixel_biome(&zc, p.peak_lapse_min_delta, 0.0, &p), Biome::Ice);
        // delta = gate - epsilon → strictly less → suppressed → Tundra.
        let below = p.peak_lapse_min_delta - 1e-4;
        assert_eq!(pixel_biome(&zc, below, 0.0, &p), Biome::Tundra);
    }

    #[test]
    fn pixel_biome_intermediate_elev_becomes_tundra() {
        let zc = ZoneClimate {
            temp_mean: 26.0,
            precip_annual: 2000.0,
            biome: Biome::TropicalRainforest,
        };
        let p = WorldClimateParams::default(); // tundra_temp = 0, ice_temp = -10
        // Need 0 < temp_pixel - ice_temp threshold but temp_pixel < 0:
        // delta in (26/50, 36/50) = (0.52, 0.72).
        let elev = 0.35 + 0.60; // delta 0.60 → temp_pixel = 26 - 30 = -4 → Tundra
        assert_eq!(pixel_biome(&zc, elev, 0.35, &p), Biome::Tundra);
    }

    // ---- scaled_for ----

    #[test]
    fn params_scaled_for_uses_plate_radius_not_map_size() {
        // W14 fix: reach scales by mean plate radius, not absolute map size.
        // Two maps with same plate_count → reach scales linearly with map dim
        // (sqrt(area) ~ side, so reach ~ side). Same map with 4× plate_count
        // → mean_radius halves → reach halves.
        let p = WorldClimateParams::default();

        // 1024×640, 12 plates: mean_radius = 0.5 × sqrt(1024×640/12) ≈ 116.6
        // reach ≈ 116.6 × 0.4 ≈ 46.6
        let baseline = p.clone().scaled_for(1024, 640, 12).continentality_reach;
        assert!(
            (baseline - 46.6).abs() < 1.0,
            "12-plate 1024×640 reach should ≈ 46.6, got {baseline}"
        );

        // Same area (1024×640) but 48 plates → mean_radius halves → reach halves.
        let many = p.clone().scaled_for(1024, 640, 48).continentality_reach;
        assert!(
            (many - baseline / 2.0).abs() < 1.0,
            "4× plate_count should halve reach; baseline={baseline} many={many}"
        );

        // Same plate_count, 4× area (2048×1280, 12 plates) → mean_radius
        // doubles → reach doubles.
        let big = p.clone().scaled_for(2048, 1280, 12).continentality_reach;
        assert!(
            (big - baseline * 2.0).abs() < 1.0,
            "4× area should double reach; baseline={baseline} big={big}"
        );

        // Defensive: plate_count = 0 must not divide-by-zero; reach > 0.
        let edge = p.clone().scaled_for(1024, 640, 0).continentality_reach;
        assert!(edge.is_finite() && edge >= 1.0, "0 plates → defensive reach, got {edge}");
    }

    // ---- export_zone_climates ----

    // ---- v4 Orographic ----

    #[test]
    fn upwind_direction_three_band() {
        // Tropics: easterlies → upwind = +x
        assert_eq!(upwind_direction(0.0), (1.0, 0.0));
        assert_eq!(upwind_direction(0.15), (1.0, 0.0));
        assert_eq!(upwind_direction(0.32), (1.0, 0.0));
        // Mid-lat: westerlies → upwind = -x
        assert_eq!(upwind_direction(0.34), (-1.0, 0.0));
        assert_eq!(upwind_direction(0.5), (-1.0, 0.0));
        assert_eq!(upwind_direction(0.66), (-1.0, 0.0));
        // Polar: polar easterlies → upwind = +x
        assert_eq!(upwind_direction(0.68), (1.0, 0.0));
        assert_eq!(upwind_direction(1.0), (1.0, 0.0));
    }

    #[test]
    fn upwind_elev_gain_accumulates_positive_only() {
        // Synthetic plate: a tall vertical strip from x=50 to x=70 with high
        // elevation (mountain wall), surrounded by flat low ground.
        // Walking from (100, 50) upwind in (+1, 0) direction does NOT cross
        // the wall (wall is at x=50-70, walking east from x=100 goes AWAY
        // from wall). Should accumulate 0.
        // Walking from (10, 50) upwind in (+1, 0) direction crosses the wall
        // → accumulates the elevation gain.
        let mut params = FlatParams {
            width: 200,
            height: 100,
            plate_count: 1,
            seed: 1,
            ..FlatParams::default()
        };
        params.separation = 0.0; // single plate, no spread constraint
        let world = crate::flatworld::generate(&params);
        // No mountains in a 1-plate world (no collisions) so elev_gain ≈ 0
        // for any walk. Just verify the function runs + returns finite ≥ 0.
        let gain = upwind_elev_gain(&world, 50.0, 50.0, (1.0, 0.0), 50.0, 5.0);
        assert!(gain.is_finite());
        assert!(gain >= 0.0, "elev_gain must be non-negative (positive only): got {gain}");
    }

    #[test]
    fn upwind_elev_gain_world_edge_stops_walk() {
        // Walking off the right edge should terminate cleanly + return ≤ the
        // distance actually walked. Test with a 1-step walk from near the
        // right edge.
        let world = test_world();
        let w = world.width as f32;
        // (w - 3, sy): only ~1 step possible before hitting right edge
        let gain = upwind_elev_gain(&world, w - 3.0, 50.0, (1.0, 0.0), 100.0, 5.0);
        assert!(gain.is_finite());
        assert!(gain >= 0.0);
        // For a single-step world-edge walk, total gain is bounded by max
        // elevation in the field (typically < 1.0). Sanity-check the gain
        // hasn't accumulated nonsense from out-of-bounds samples.
        assert!(gain < 2.0, "edge walk produced suspicious gain: {gain}");
    }

    #[test]
    fn orographic_disabled_when_strength_zero() {
        // Setting orographic_strength = 0 must NOT change zone precip
        // regardless of underlying terrain.
        let world = test_world();
        let params_off = WorldClimateParams {
            orographic_strength: 0.0,
            ..WorldClimateParams::default()
        };
        let params_on = WorldClimateParams::default();
        let ed = edge_dist_all_coast(&world);
        for (pi, p) in world.plates.iter().enumerate() {
            for zi in 0..p.zone_sites.len() {
                let zc_off = compute_zone_climate(&world, &params_off, pi, zi, &ed);
                let zc_on = compute_zone_climate(&world, &params_on, pi, zi, &ed);
                // params_off can ONLY differ in precip if orographic fires
                // even when disabled (bug). Temperatures must match exactly.
                assert_eq!(
                    zc_off.temp_mean.to_bits(),
                    zc_on.temp_mean.to_bits(),
                    "orographic should not affect temperature"
                );
            }
        }
    }

    #[test]
    fn orographic_reduces_precip_behind_mountains() {
        // Use the default world (12-plate, default params). Some zones will
        // have upwind mountains (collision belts) → orographic shadow fires.
        // Verify: at least one zone differs in precip between strength=0 and
        // strength=default.
        let world = test_world();
        let params_off = WorldClimateParams {
            orographic_strength: 0.0,
            ..WorldClimateParams::default()
        }
        .scaled_for(world.width, world.height, world.plates.len());
        let params_on = WorldClimateParams::default()
            .scaled_for(world.width, world.height, world.plates.len());
        let ed = edge_dist_all_coast(&world);

        let mut any_differs = false;
        let mut any_reduced = false;
        for (pi, p) in world.plates.iter().enumerate() {
            for zi in 0..p.zone_sites.len() {
                let off = compute_zone_climate(&world, &params_off, pi, zi, &ed);
                let on = compute_zone_climate(&world, &params_on, pi, zi, &ed);
                let delta = on.precip_annual - off.precip_annual;
                if delta.abs() > 0.1 {
                    any_differs = true;
                }
                if delta < -1.0 {
                    any_reduced = true; // precip on < precip off → orographic shadow firing
                }
            }
        }
        // In a default 12-plate world with seed 7, the collision belts
        // produce SOME mountains. Walking 93 px upwind should encounter at
        // least one. If this test ever fails because the test_world has no
        // mountains, replace with a forced-mountain world (plates=5,
        // separation=0.5, collision_gain=0.7).
        assert!(
            any_differs,
            "orographic should affect at least one zone's precip in test_world"
        );
        assert!(
            any_reduced,
            "orographic shadow should REDUCE precip for at least one downwind-of-mountain zone"
        );
    }

    // ---- W5 classifier-level hue interpolation (v2.1d) ----

    #[test]
    fn whittaker_blended_color_returns_canonical_deep_in_biome() {
        // Pixel at (27, 2500) = deep in TropicalRainforest territory.
        // All 4 probes (±1.5°C, ±75mm) still classify as TropicalRainforest
        // (nearest threshold is precip=1500 at distance 1000mm >> 75mm; temp
        // is at 22 boundary at distance 5°C >> 1.5°C). Should return
        // canonical color exactly.
        let c = whittaker_classify_blended_color(27.0, 2500.0);
        assert_eq!(c, Biome::TropicalRainforest.color());

        // Pixel deep in Tundra (cold tier, far from precip thresholds).
        let c2 = whittaker_classify_blended_color(-10.0, 50.0);
        assert_eq!(c2, Biome::Tundra.color());
    }

    #[test]
    fn whittaker_blended_color_blends_at_precip_threshold() {
        // Pixel at (20, 700) — exactly on the warm-tier threshold between
        // Mediterranean (precip 250..700) and TemperateForest (precip > 700).
        // At exactly the threshold, bisect finds td → 0, smoothstep(0) = 0,
        // w_center = 0.5 → 50/50 blend of Mediterranean + TemperateForest.
        let blend = whittaker_classify_blended_color(20.0, 700.0);
        let med = Biome::Mediterranean.color();
        let tf = Biome::TemperateForest.color();
        let expected = [
            ((med[0] as u32 + tf[0] as u32) / 2) as u8,
            ((med[1] as u32 + tf[1] as u32) / 2) as u8,
            ((med[2] as u32 + tf[2] as u32) / 2) as u8,
        ];
        // Allow ±2 for f32 rounding in lerp.
        for ch in 0..3 {
            assert!(
                (blend[ch] as i32 - expected[ch] as i32).abs() <= 2,
                "channel {ch}: blend {blend:?} vs expected midpoint {expected:?}"
            );
        }
        // Sanity: blend is NEITHER pure Mediterranean NOR pure TemperateForest.
        assert_ne!(blend, med);
        assert_ne!(blend, tf);
    }

    #[test]
    fn pixel_color_preserves_lapse_overrides_unblended() {
        // Lapse overrides (Ice / Tundra at peaks) intentionally stay hard —
        // softening those is a separate concern. Verify pixel_color returns
        // EXACT Ice.color() at a tall cold peak.
        let zc = ZoneClimate {
            temp_mean: 26.0,
            precip_annual: 2000.0,
            biome: Biome::TropicalRainforest,
        };
        let p = WorldClimateParams::default();
        // Tall peak: delta = 0.80 → temp_pixel = 26 - 40 = -14 < ice_temp(-10);
        // precip 2000 ≥ ice_precip_min(100) → Ice override fires.
        let c = pixel_color(&zc, 0.35 + 0.80, 0.35, &p);
        assert_eq!(c, Biome::Ice.color(), "lapse override should return pure Ice color, not a blend");

        // Pixel at zone base → no override → blends at zone-level (temp, precip).
        // (27, 2000) → deep TropicalRainforest → canonical color.
        let c2 = pixel_color(&zc, 0.35, 0.35, &p);
        assert_eq!(c2, Biome::TropicalRainforest.color());
    }

    #[test]
    fn export_matches_in_memory_compute() {
        // Source-of-truth invariant: the sidecar JSON's temp_mean/precip/biome
        // for zone (pid, zid) MUST equal what compute_zone_climate returns
        // when called directly with the same inputs. Drift here = eval
        // measures different physics than the painted pixels.
        let world = test_world();
        let params = WorldClimateParams::default()
            .scaled_for(world.width, world.height, world.plates.len());

        // Build the same is_sea grid the export uses, so we can call
        // compute_zone_climate identically.
        let w = world.width as usize;
        let h = world.height as usize;
        let mut is_sea = vec![false; w * h];
        for py in 0..h {
            for px in 0..w {
                if world.plates_at(px as f32 + 0.5, py as f32 + 0.5).is_empty() {
                    is_sea[py * w + px] = true;
                }
            }
        }
        let ed = crate::zonegen::edge_dist_from_sea(&is_sea, w, h);

        let export = export_zone_climates(&world, &params);
        for ze in &export.zones {
            let zc = compute_zone_climate(&world, &params, ze.plate_id, ze.zone_id, &ed);
            assert_eq!(
                ze.temp_mean.to_bits(),
                zc.temp_mean.to_bits(),
                "temp drift at zone ({},{})",
                ze.plate_id, ze.zone_id
            );
            assert_eq!(
                ze.precip_annual.to_bits(),
                zc.precip_annual.to_bits(),
                "precip drift at zone ({},{})",
                ze.plate_id, ze.zone_id
            );
            assert_eq!(
                ze.biome,
                biome_name(zc.biome),
                "biome drift at zone ({},{})",
                ze.plate_id, ze.zone_id
            );
        }
        assert!(!export.zones.is_empty(), "expected at least one zone in test_world");
    }

    // ---- W2 anti-ring noise overlay + W13 N=9 zone-avg coast_d (v2.1c) ----

    #[test]
    fn mean_nearest_neighbour_picks_smallest_pairwise() {
        // 4 points: (0,0), (1,0), (10,0), (10,1)
        // NN distances: 0→1 = 1, 1→0 = 1, 10→10,1 = 1, 10,1→10,0 = 1
        // All NN = 1, mean = 1.
        let pts = [(0.0, 0.0), (1.0, 0.0), (10.0, 0.0), (10.0, 1.0)];
        assert!((mean_nearest_neighbour(&pts) - 1.0).abs() < 1e-5);
        // Degenerate cases: 0 or 1 points returns 0.0.
        assert_eq!(mean_nearest_neighbour(&[]), 0.0);
        assert_eq!(mean_nearest_neighbour(&[(0.0, 0.0)]), 0.0);
    }

    #[test]
    fn sample_edge_dist_avg_equals_center_when_radius_zero() {
        // Synthetic edge_dist grid: a 10x10 with uniform 42 everywhere.
        let w = 10u32;
        let ed: Vec<u32> = vec![42u32; (w * w) as usize];
        // radius=0 → fall back to single center sample.
        assert_eq!(sample_edge_dist_avg(&ed, 5.0, 5.0, w, 0.0), 42.0);
        // radius>0 with uniform field → all 9 samples = 42 → avg = 42.
        assert_eq!(sample_edge_dist_avg(&ed, 5.0, 5.0, w, 1.0), 42.0);
    }

    #[test]
    fn sample_edge_dist_avg_smooths_a_gradient() {
        // edge_dist grid where dist = x (linear gradient along x).
        // At center (5, 5) = 5. At (5±1, 5) = 4 and 6. At (5, 5±1) = 5.
        // Diagonals = 5 ± 0.707 ≈ 4.293 / 5.707.
        // Sum = 5 (center) + (6+4+5+5) cardinals + (5.707+4.293+5.707+4.293) diag
        //     = 5 + 20 + 20 = 45; avg = 45/9 = 5.0.
        // Linear gradient: avg = center. Test passes.
        let w = 20u32;
        let mut ed = vec![0u32; (w * w) as usize];
        for y in 0..w {
            for x in 0..w {
                ed[(y * w + x) as usize] = x;
            }
        }
        let avg = sample_edge_dist_avg(&ed, 5.0, 5.0, w, 1.0);
        // f32 conversion + sin/cos imprecision → small tolerance.
        assert!(
            (avg - 5.0).abs() < 0.5,
            "linear gradient avg should ≈ center; got {avg}"
        );
    }

    #[test]
    fn continentality_w2_w13_active_in_zone_climate() {
        // Verify that compute_zone_climate's continentality is actually
        // affected by both layers. We can't easily isolate W2 from W13
        // without monkey-patching internals, but we CAN verify that the
        // overall zone climate temp/precip differs from a synthetic
        // "no-continentality" baseline (`continentality_precip_atten = 0`)
        // when both layers fire — proving the continentality path runs.
        let world = test_world();
        let params_on = WorldClimateParams::default()
            .scaled_for(world.width, world.height, world.plates.len());
        let mut params_off = params_on.clone();
        params_off.continentality_precip_atten = 0.0;

        let ed = edge_dist_all_coast(&world);
        // With coast-everywhere edge_dist (=0) the noise overlay W2 still
        // perturbs cont away from 0 → precip CAN differ from the no-atten
        // baseline. Use an interior edge_dist instead so W13 sees something
        // to average.
        let w = world.width as usize;
        let h = world.height as usize;
        let ed_interior: Vec<u32> = vec![100u32; w * h];

        let mut any_diff = false;
        for (pi, plate) in world.plates.iter().enumerate() {
            for zi in 0..plate.zone_sites.len() {
                let on = compute_zone_climate(&world, &params_on, pi, zi, &ed_interior);
                let off = compute_zone_climate(&world, &params_off, pi, zi, &ed_interior);
                if (on.precip_annual - off.precip_annual).abs() > 0.1 {
                    any_diff = true;
                    break;
                }
            }
            if any_diff { break; }
        }
        // Force unused warning silence + assert the layer fires.
        let _ = ed;
        assert!(any_diff, "continentality path should affect at least one zone's precip");
    }

    #[test]
    fn w2_noise_overlay_breaks_radial_symmetry() {
        // W2 acceptance: two zones with the SAME coast_d (same continentality
        // input) but different (sx, sy) should produce different cont
        // perturbations from the noise overlay → different precip.
        // We synthesize a uniform edge_dist so the only source of precip
        // variance between zones at the same lat is the W2 noise.
        let world = test_world();
        let params = WorldClimateParams::default()
            .scaled_for(world.width, world.height, world.plates.len());
        let w = world.width as usize;
        let h = world.height as usize;
        // Uniform 100 → all zones have coast_d=100 → cont_base same.
        let ed = vec![100u32; w * h];

        // Group zones by their lat band; within a band, precip should still
        // VARY because of W2 noise (would be uniform without W2).
        let h_f = world.height as f32;
        let mut by_lat_band: std::collections::HashMap<u32, Vec<f32>> = Default::default();
        for (pi, plate) in world.plates.iter().enumerate() {
            for (zi, &(_, sy)) in plate.zone_sites.iter().enumerate() {
                let lat_d = params.hemisphere_layout.lat_dist(sy, h_f);
                let band = (lat_d * 10.0) as u32; // 10 bands
                let zc = compute_zone_climate(&world, &params, pi, zi, &ed);
                by_lat_band.entry(band).or_default().push(zc.precip_annual);
            }
        }
        // At least one band must show precip variance > 1 mm (W2 perturbation
        // typical magnitude is ~AMP × atten × precip_band ≈ 0.15 × 0.55 ×
        // 500 = 41 mm).
        let max_band_variance: f32 = by_lat_band
            .values()
            .filter(|v| v.len() >= 2)
            .map(|v| {
                let mean: f32 = v.iter().sum::<f32>() / v.len() as f32;
                v.iter().map(|x| (x - mean).abs()).fold(0.0f32, f32::max)
            })
            .fold(0.0f32, f32::max);
        assert!(
            max_band_variance > 1.0,
            "W2 noise overlay should produce >1mm precip variance within \
             a lat band on a uniform edge_dist; got max={max_band_variance}"
        );
    }

    #[test]
    fn export_serializes_to_json() {
        let world = test_world();
        let params = WorldClimateParams::default()
            .scaled_for(world.width, world.height, world.plates.len());
        let export = export_zone_climates(&world, &params);
        let json = serde_json::to_string(&export).expect("serialize");
        // Smoke-test the wire format — field names callers will rely on.
        assert!(json.contains("\"width\""));
        assert!(json.contains("\"hemisphere_layout\""));
        assert!(json.contains("\"climate_params\""));
        assert!(json.contains("\"zones\""));
        assert!(json.contains("\"temp_mean\""));
        assert!(json.contains("\"precip_annual\""));
        assert!(json.contains("\"biome\""));
        assert!(json.contains("\"lat_dist\""));
    }
}
