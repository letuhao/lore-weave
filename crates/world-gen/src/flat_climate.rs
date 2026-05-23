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
            precip_subtropic: 300.0,
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

/// 8 Whittaker biomes. **Ice** is reserved for the per-pixel lapse override
/// ([`pixel_biome`]) — the zone-level classifier never returns Ice.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Biome {
    Ice,
    Tundra,
    BorealForest,
    TemperateForest,
    TemperateGrassland,
    HotDesert,
    Savanna,
    TropicalRainforest,
}

impl Biome {
    /// Stable discriminant byte (intended for any future content hash).
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
        }
    }

    /// Display RGB for renderers. Calibrated for visual contrast — the two
    /// "dark green" biomes (tropical / boreal) are deliberately spread on the
    /// hue axis to read distinctly. **W7 tuning (B5 v2.1a)**: HotDesert
    /// reddened to distinguish from beach sand; previously `#D8B070` was
    /// visually ambiguous with WET_SAND `#C4B284`.
    pub fn color(self) -> [u8; 3] {
        match self {
            Biome::Ice => [232, 238, 242],                // near-white
            Biome::Tundra => [184, 183, 174],             // pale grey-tan
            Biome::BorealForest => [74, 107, 71],         // muted grey-green
            Biome::TemperateForest => [79, 139, 65],      // bright forest
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

/// Classify a `(temp, precip)` point into a Whittaker biome (8 zones).
///
/// **Ice is excluded by design** — it is reserved for the per-pixel lapse
/// override in [`pixel_biome`]. The zone-level classifier returns Tundra at
/// the coldest end.
///
/// Order of checks (precedence): cold tier → dry tier → hot tier → default
/// temperate.
pub fn whittaker_classify(temp: f32, precip: f32) -> Biome {
    // Cold tier — temp dominates regardless of precip.
    if temp < 0.0 {
        return Biome::Tundra;
    }
    if temp < 7.0 {
        // 0..7 °C — subarctic. Borealforest if any precip, else still Tundra
        // (very cold + very dry — Yakutia steppe-tundra reads as Tundra here).
        if precip > 250.0 {
            return Biome::BorealForest;
        }
        return Biome::Tundra;
    }
    // Warm tier — split by precip.
    // Hot (> 22 °C): TropicalRainforest > 1500, Savanna 250..1500, HotDesert < 250.
    if temp >= 22.0 {
        if precip < 250.0 {
            return Biome::HotDesert;
        }
        if precip > 1500.0 {
            return Biome::TropicalRainforest;
        }
        return Biome::Savanna;
    }
    // Mid (7..22 °C): HotDesert if very dry, Grassland if mid, Forest if wet.
    if precip < 250.0 {
        return Biome::HotDesert;
    }
    if precip < 600.0 {
        return Biome::TemperateGrassland;
    }
    Biome::TemperateForest
}

fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
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

    // 3. (Plate layer reserved — v3 OceanCurrent slots here.)

    // 4. Continentality (Zone) — attenuate precip by coast distance.
    let coast_d = sample_edge_dist(edge_dist_sea, sx, sy, world.width);
    let cont = (coast_d / params.continentality_reach).clamp(0.0, 1.0);
    precip *= 1.0 - params.continentality_precip_atten * cont;

    // 5. (ZoneRefinement — implicit by using zone-site coords throughout.)

    let biome = whittaker_classify(temp, precip);
    ZoneClimate {
        temp_mean: temp,
        precip_annual: precip,
        biome,
    }
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
    fn whittaker_seven_biomes_reachable_ice_excluded() {
        let mut seen = [false; 8];
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
            Biome::TemperateForest,
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
        assert_eq!(whittaker_classify(-15.0, 100.0), Biome::Tundra);
        assert_eq!(whittaker_classify(3.0, 600.0), Biome::BorealForest);
        assert_eq!(whittaker_classify(15.0, 1000.0), Biome::TemperateForest);
        assert_eq!(whittaker_classify(15.0, 400.0), Biome::TemperateGrassland);
        assert_eq!(whittaker_classify(15.0, 100.0), Biome::HotDesert);
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

        // With atten=0.55 and cont=1 (saturated), interior should be 45 % of
        // coast. Strict ratio assertion proves the multiplier actually fired.
        let ratio = zc_inter.precip_annual / zc_coast.precip_annual.max(1e-6);
        assert!(
            (ratio - 0.45).abs() < 0.001,
            "interior precip ratio should be ~0.45 vs coast; got {ratio}"
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
}
