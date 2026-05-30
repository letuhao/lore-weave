//! Stage 3 — climate.
//!
//! Per-cell `ClimateZone` from a **real Köppen-Geiger classification** working
//! in physical units (°C + mm/yr), ported from the validated `flat_climate`
//! classifier. No RNG — a pure, deterministic function of geometry + terrain.
//!
//! The pipeline derives, per cell:
//! - a sea-level **temperature** from latitude (insolation), minus an elevation
//!   lapse, plus a seasonal amplitude → warm/cold-month extremes;
//! - an annual **precipitation** = a latitude circulation base (mm/yr, the four
//!   Earth bands ITCZ/subtropical/mid-lat/polar) × an orographic moisture
//!   transport factor `[0,1]` ([`moisture_field`]: a prevailing wind carries
//!   moisture inland and bleeds it over land + behind mountains → rain shadows);
//!
//! then classifies with the Köppen tree — crucially the **temperature-dependent
//! aridity threshold** `precip < 20·T_mean + offset`: a hot region needs far more
//! rain to escape desert than a cold one, so cold-dry interiors become
//! boreal/tundra (not desert) and only genuinely hot-dry belts read Arid. The 19
//! Köppen subtypes collapse onto the existing 8 [`ClimateZone`].

use serde::{Deserialize, Serialize};

use crate::creative_seed::{HemisphereOrientation, PrevailingWind};

// ── Calibrated parameters (ported from `flat_climate::WorldClimateParams`) ──

/// Sea-level temperature at the equator (°C).
const T_EQ: f32 = 28.0;
/// Sea-level temperature at the pole (°C).
const T_POLE: f32 = -15.0;
/// Elevation lapse (°C per unit of normalized height above sea level). A
/// full-height peak (`elev_above ≈ 0.6`) is ≈ 24 °C colder than its sea-level
/// latitude — matches Earth's ~6.5 °C/km over a ~3.7 km tall range. Calibration
/// knob for the desert/tundra balance.
const LAPSE_C: f32 = 40.0;

/// Annual precip at the ITCZ / equator (mm/yr).
const PRECIP_EQ: f32 = 2400.0;
/// Annual precip at the subtropical high / horse latitudes ~30° (mm/yr).
const PRECIP_SUBTROPIC: f32 = 180.0;
/// Annual precip at the mid-latitude westerlies ~55° (mm/yr).
const PRECIP_MIDLAT: f32 = 900.0;
/// Annual precip at the pole (mm/yr).
const PRECIP_POLAR: f32 = 150.0;

/// Seasonal amplitude at the equator (°C) — year-round-stable tropics.
const AMP_EQ: f32 = 2.0;
/// Extra seasonal amplitude per unit `lat_dist` (°C) — poles swing wide.
const AMP_LAT: f32 = 28.0;
/// Continentality amplification of the seasonal swing (interior > coast).
const AMP_CONT: f32 = 0.8;

/// Winter precip fraction in v1 — **fixed at 0.5** (year-round even). Real
/// hemisphere/margin seasonality (Mediterranean dry-summer Cs, monsoon
/// dry-winter Cw) is deferred to v2; with 0.5 everywhere the Mediterranean zone
/// is unreachable in the live pipeline, but biome.rs maps Mediterranean and
/// Temperate to identical biomes so there is no biome-level regression.
const WINTER_FRAC_V1: f32 = 0.5;

/// Highland override gate: a cell above this normalized height-above-sea, if
/// warm enough (`t_warm ≥ 10`), classifies Highland (→ Hill/Mountain in
/// biome.rs) rather than by precip. Cold high cells fall through to Polar so
/// glaciated peaks stay reachable. Calibration knob.
const HIGHLAND_ELEV: f32 = 0.30;

/// Closed climate-zone enum (GEO_001 §4.1, 8 variants).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ClimateZone {
    Polar,
    Boreal,
    Temperate,
    Mediterranean,
    Subtropical,
    Tropical,
    Arid,
    Highland,
}

impl ClimateZone {
    /// Rainfall multiplier feeding the hydrology stage.
    pub fn wetness(self) -> f32 {
        match self {
            ClimateZone::Tropical => 1.4,
            ClimateZone::Subtropical => 1.2,
            ClimateZone::Temperate => 1.0,
            ClimateZone::Boreal => 0.9,
            ClimateZone::Highland => 0.9,
            ClimateZone::Mediterranean => 0.8,
            ClimateZone::Polar => 0.5,
            ClimateZone::Arid => 0.3,
        }
    }

    /// Stable discriminant byte for the content hash.
    pub fn tag(self) -> u8 {
        match self {
            ClimateZone::Polar => 0,
            ClimateZone::Boreal => 1,
            ClimateZone::Temperate => 2,
            ClimateZone::Mediterranean => 3,
            ClimateZone::Subtropical => 4,
            ClimateZone::Tropical => 5,
            ClimateZone::Arid => 6,
            ClimateZone::Highland => 7,
        }
    }
}

/// Build the per-cell climate layer.
///
/// **Phase 3 Köppen (2026-05-30):** the ad-hoc `[0,1]`-dryness heuristic is
/// replaced by the real Köppen classifier in physical units. Each cell derives
/// °C + mm/yr from latitude × elevation × wind-carried moisture, then
/// [`classify_koppen`] maps the Köppen group onto a [`ClimateZone`]. `centers`
/// are 3D unit-sphere points; latitude is `asin(z)` and `lat_dist` honours the
/// `hemisphere` orientation via [`effective_latitude`].
pub fn build(
    centers: &[[f32; 3]],
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
    hemisphere: HemisphereOrientation,
    prevailing_wind: PrevailingWind,
    climate_bias: Option<ClimateZone>,
) -> Vec<ClimateZone> {
    let moisture = moisture_field(centers, elevation, sea_level, neighbors, prevailing_wind);
    // Climate bias is applied as a small physical-unit nudge (°C, mm/yr) before
    // classification, so `CreativeSeed.climate_bias` keeps steering the result.
    let (temp_bias, precip_bias) = climate_bias.map_or((0.0, 0.0), bias_delta);

    centers
        .iter()
        .enumerate()
        .map(|(i, &p)| {
            let lat = p[2].clamp(-1.0, 1.0).asin();
            let lat_dist = effective_latitude(lat, hemisphere); // [0,1], 0=equator
            let elev_above =
                ((f32::from(elevation[i]) - f32::from(sea_level)) / 65535.0).max(0.0);
            let m = moisture[i];
            let cont = (1.0 - m).clamp(0.0, 1.0); // interior = high continentality

            // Temperature: insolation − elevation lapse (+ bias).
            let temp_mean = lerp(T_EQ, T_POLE, lat_dist) - LAPSE_C * elev_above + temp_bias;
            // Precipitation: latitude circulation base (mm) × horizontal
            // moisture transport [0,1] (+ bias), clamped non-negative.
            let precip = (circulation_precip_mm(lat_dist) * m + precip_bias).max(0.0);

            // Seasonality → warm/cold-month extremes the Köppen tree reads.
            let amp = seasonal_amp(lat_dist, cont);
            let t_warm = temp_mean + amp;
            let t_cold = temp_mean - amp;

            classify_koppen(t_warm, t_cold, precip, WINTER_FRAC_V1, elev_above)
        })
        .collect()
}

/// "Effective latitude" in `[0,1]` — 0 = equator-warm, 1 = pole-cold —
/// derived from the cell's actual latitude (radians, `[-π/2, π/2]`).
///
/// - **Northern** orientation: the `+z` pole is cold; `lat = +π/2` → 1.
/// - **Southern** orientation: the `−z` pole is cold; `lat = −π/2` → 1.
/// - **Equatorial** orientation: both poles cold; `eff_lat = |lat|/(π/2)`.
fn effective_latitude(lat: f32, hemi: HemisphereOrientation) -> f32 {
    let norm = lat / std::f32::consts::FRAC_PI_2; // [-1, 1]
    match hemi {
        HemisphereOrientation::Northern => norm.clamp(-1.0, 1.0).max(0.0),
        HemisphereOrientation::Southern => (-norm).clamp(-1.0, 1.0).max(0.0),
        HemisphereOrientation::Equatorial => norm.abs(),
    }
}

/// Latitude circulation precip base (mm/yr) — piecewise-linear over the four
/// canonical Earth bands. Port of `flat_climate::circulation_curve`.
///
/// | `lat_dist` | band | mm/yr |
/// |---|---|---|
/// | 0.00 | ITCZ (equator) | 2400 |
/// | 0.33 | subtropical high (~30°) | 180 |
/// | 0.67 | mid-lat westerlies (~55°) | 900 |
/// | 1.00 | polar | 150 |
fn circulation_precip_mm(lat_dist: f32) -> f32 {
    let t = lat_dist.clamp(0.0, 1.0);
    let raw = if t <= 0.33 {
        lerp(PRECIP_EQ, PRECIP_SUBTROPIC, t / 0.33)
    } else if t <= 0.67 {
        lerp(PRECIP_SUBTROPIC, PRECIP_MIDLAT, (t - 0.33) / 0.34)
    } else {
        lerp(PRECIP_MIDLAT, PRECIP_POLAR, (t - 0.67) / 0.33)
    };
    raw.max(0.0)
}

/// Seasonal temperature amplitude (°C): half the warm/cold-month spread.
/// Port of `flat_climate::seasonal_amplitude` — small at the equator, large at
/// the poles, amplified in continental interiors.
fn seasonal_amp(lat_dist: f32, continentality: f32) -> f32 {
    let lat_amp = AMP_EQ + AMP_LAT * lat_dist.clamp(0.0, 1.0);
    lat_amp * (1.0 + continentality.clamp(0.0, 1.0) * AMP_CONT)
}

/// Köppen B-group aridity threshold (mm/yr): a zone is arid iff annual precip
/// is below this. Port of `flat_climate::arid_precip_threshold`.
///
/// `Pthr = 20·T_mean + offset`, the offset set by **when** the rain falls
/// (winter rain evaporates less → lower threshold needed):
/// - dry-summer / winter-heavy (`winter_frac > 0.70`): `−70`
/// - dry-winter / summer-heavy (`winter_frac < 0.30`): `+140`
/// - even: `+70`
///
/// This temperature dependence is the headline fix: it is what lets cold-dry
/// interiors classify D/E instead of falling into a fixed-gate desert.
fn arid_precip_threshold(t_warm: f32, t_cold: f32, winter_frac: f32) -> f32 {
    let t_mean = (t_warm + t_cold) * 0.5;
    let offset = if winter_frac > 0.70 {
        -70.0
    } else if winter_frac < 0.30 {
        140.0
    } else {
        70.0
    };
    (20.0 * t_mean + offset).max(0.0)
}

/// Classify one cell into a [`ClimateZone`] — pure function, the determinism
/// contract of stage 3. Ported from `flat_climate::koppen_classify`, collapsing
/// the 19 Köppen subtypes onto the 8 zones in canonical Köppen order
/// (Highland → E → A → B → D → C).
///
/// - `t_warm` / `t_cold`: warmest / coldest-month mean temperature (°C)
/// - `precip`: annual precipitation (mm/yr)
/// - `winter_frac`: fraction of precip in the cold half-year (v1 pins 0.5)
/// - `elev_above`: normalized height above sea level (for the Highland gate)
fn classify_koppen(
    t_warm: f32,
    t_cold: f32,
    precip: f32,
    winter_frac: f32,
    elev_above: f32,
) -> ClimateZone {
    // Highland — tall warm terrain (preserves biome.rs hill/mountain). Cold high
    // cells fall through to Polar so glaciated peaks stay reachable.
    if elev_above > HIGHLAND_ELEV && t_warm >= 10.0 {
        return ClimateZone::Highland;
    }
    // E — Polar: warmest month below 10 °C.
    if t_warm < 10.0 {
        return ClimateZone::Polar;
    }
    // A — Tropical: coldest month above 18 °C.
    if t_cold > 18.0 {
        return ClimateZone::Tropical;
    }
    // B — Arid: precip below the temperature-dependent threshold.
    if precip < arid_precip_threshold(t_warm, t_cold, winter_frac) {
        return ClimateZone::Arid;
    }
    // D — Boreal/continental: coldest month below −3 °C.
    if t_cold < -3.0 {
        return ClimateZone::Boreal;
    }
    // C — temperate group → Mediterranean / Subtropical / Temperate.
    if winter_frac > 0.65 {
        return ClimateZone::Mediterranean; // Cs (dry-summer) — v2-live (winter_frac=0.5 in v1)
    }
    if t_warm > 22.0 {
        return ClimateZone::Subtropical; // Cfa / Cwa
    }
    ClimateZone::Temperate // Cfb
}

/// `(temp_delta_°C, precip_delta_mm)` nudging classification toward `z`. The
/// nudge is applied to `temp_mean` (shifts both monthly extremes) and to annual
/// precip before [`classify_koppen`]. Magnitudes are Earth-plausible: enough to
/// flip a borderline cell, small enough not to override clear climates.
fn bias_delta(z: ClimateZone) -> (f32, f32) {
    match z {
        ClimateZone::Polar => (-10.0, 0.0),
        ClimateZone::Boreal => (-7.0, 0.0),
        ClimateZone::Temperate => (0.0, 150.0),
        // v1 has no reachable Mediterranean zone (winter_frac ≡ 0.5), so nudge
        // toward the nearest reachable *mild* climate (warm-temperate) rather
        // than drying — a drying nudge would risk tipping a borderline cell into
        // Arid, the opposite of the mild-Mediterranean intent. True Cs → v2.
        ClimateZone::Mediterranean => (2.0, 0.0),
        ClimateZone::Subtropical => (6.0, 80.0),
        ClimateZone::Tropical => (8.0, 250.0),
        ClimateZone::Arid => (0.0, -200.0),
        // Highland is purely elevation-driven; a bias toward it is a no-op.
        ClimateZone::Highland => (0.0, 0.0),
    }
}

/// Linear interpolation `a + (b - a) * t`.
fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// Per-cell atmospheric moisture in `[0,1]` from a wind-driven march.
///
/// Air enters fully moist from the windward edge and recharges to `1.0` over
/// water; over land it bleeds away — a small overland leak (the continentality
/// gradient) plus a large orographic loss wherever the terrain climbs above
/// its upwind neighbours. The lee of a mountain range is therefore left with
/// little moisture: a dry rain shadow. Deterministic: a total-ordered downwind
/// sweep (`f32::total_cmp` on the wind projection, ties broken by cell index).
///
/// Output is a pure horizontal-transport factor `[0,1]`: the Köppen path
/// multiplies the latitude circulation base (mm) by it, so a wet-latitude coast
/// keeps its full circulation precip while a deep interior or lee dries out.
fn moisture_field(
    centers: &[[f32; 3]],
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
    wind: PrevailingWind,
) -> Vec<f32> {
    /// Moisture wrung out per unit of normalized climb (orographic rain) —
    /// high, so any real mountain range casts a strong rain shadow. This term
    /// is already resolution-invariant: climb telescopes to the total elevation
    /// gain over a range regardless of how many cells span it.
    const OROGRAPHIC: f32 = 4.5;
    /// Continentality leak per overland step — moisture lost as the air crosses
    /// each cell. **Resolution-scaled** (see `land_leak` below): a per-step
    /// constant would dry the interior of a large mesh (Megaplanet+) into
    /// wall-to-wall desert purely because it has more, shorter steps per
    /// geographic unit. Scaling by `sqrt(REF / n)` keeps the *total* drying over
    /// a fixed great-circle distance invariant across `WorldScale`. Lowered from
    /// the prior `0.025` after the 2026-05-30 climate audit (63 %→ target ~⅓
    /// desert on land).
    const LAND_LEAK_BASE: f32 = 0.018;
    /// Reference cell count (~`WorldScale::Continent`) at which the leak scale
    /// is `1.0`; clamped to `[0.1, 3.0]` so degenerate tiny meshes (unit tests)
    /// and Gigaplanet stay sane.
    const LEAK_REF_CELLS: f32 = 8192.0;

    let n = centers.len();
    let leak_scale = (LEAK_REF_CELLS / n as f32).sqrt().clamp(0.1, 3.0);
    let land_leak = LAND_LEAK_BASE * leak_scale;
    // **Sphere wind march (Stage B):** the per-cell `(lon, −lat)` projection
    // gives an `(u, v)`-shaped tuple suited to the existing 1-direction
    // global wind sort. Antimeridian wrap is an accepted Phase-1 artefact
    // (full Hadley/Ferrel cell modelling is Phase 3 Köppen).
    let (wx, wy) = wind.vector();
    let proj = |i: usize| {
        let p = centers[i];
        let lon = p[1].atan2(p[0]);
        let lat = p[2].clamp(-1.0, 1.0).asin();
        lon * wx + (-lat) * wy
    };

    // Downwind processing order — every upwind cell is handled first.
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by(|&a, &b| proj(a).total_cmp(&proj(b)).then(a.cmp(&b)));

    let mut moisture = vec![0.0f32; n];
    for &i in &order {
        if elevation[i] < sea_level {
            moisture[i] = 1.0; // the sea recharges the passing air
            continue;
        }
        let proj_i = proj(i);
        let mut sum_moist = 0.0f32;
        let mut sum_elev = 0.0f32;
        let mut count = 0u32;
        for &nb in &neighbors[i] {
            let nb = nb as usize;
            if proj(nb) < proj_i {
                sum_moist += moisture[nb];
                sum_elev += f32::from(elevation[nb]);
                count += 1;
            }
        }
        // A windward-edge land cell has no upwind neighbour — air arrives
        // from the off-map ocean, fully moist.
        let incoming = if count > 0 { sum_moist / count as f32 } else { 1.0 };
        let up_elev = if count > 0 {
            sum_elev / count as f32
        } else {
            // Windward-edge cell: the air crossed the off-map ocean, so it
            // was at sea level — a coastal mountain still self-shadows.
            f32::from(sea_level)
        };
        let climb = ((f32::from(elevation[i]) - up_elev) / 65535.0).max(0.0);
        let loss = OROGRAPHIC * climb + land_leak;
        moisture[i] = (incoming - loss).max(0.0);
    }
    moisture
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn highland_needs_high_elevation_and_warmth() {
        // High + warm → Highland (→ Hill/Mountain downstream).
        assert_eq!(
            classify_koppen(20.0, 5.0, 600.0, 0.5, 0.5),
            ClimateZone::Highland
        );
        // High but cold (warmest month < 10 °C) → Polar, so glaciated peaks
        // stay reachable in biome.rs.
        assert_eq!(
            classify_koppen(5.0, -20.0, 200.0, 0.5, 0.5),
            ClimateZone::Polar
        );
    }

    #[test]
    fn equator_is_hot_pole_is_cold() {
        // Equator: warm + wet → Tropical (coldest month > 18 °C).
        assert_eq!(
            classify_koppen(30.0, 26.0, 2400.0, 0.5, 0.0),
            ClimateZone::Tropical
        );
        // Pole: warmest month well below 10 °C → Polar.
        assert_eq!(
            classify_koppen(-5.0, -40.0, 150.0, 0.5, 0.0),
            ClimateZone::Polar
        );
    }

    #[test]
    fn arid_threshold_is_temperature_dependent() {
        // **Headline property.** Same 300 mm/yr precip, different temperatures →
        // opposite aridity verdicts. The hot cell (t_mean=20 → threshold 470)
        // is Arid; the cold cell (t_mean=7 → threshold 210) is not — the fixed
        // `dryness>0.62` heuristic could never make this distinction.
        assert_eq!(
            classify_koppen(30.0, 10.0, 300.0, 0.5, 0.0),
            ClimateZone::Arid,
            "hot-dry cell must be Arid"
        );
        assert_ne!(
            classify_koppen(12.0, 2.0, 300.0, 0.5, 0.0),
            ClimateZone::Arid,
            "cold cell with the same precip must NOT be Arid"
        );
    }

    #[test]
    fn all_eight_zones_are_reachable() {
        let mut seen = [false; 8];
        for &tw in &[-5.0_f32, 5.0, 12.0, 15.0, 18.0, 25.0, 30.0, 35.0] {
            for &tc in &[-40.0_f32, -20.0, -10.0, -4.0, 0.0, 5.0, 12.0, 20.0] {
                if tc > tw {
                    continue;
                }
                for &pr in &[10.0_f32, 100.0, 300.0, 800.0, 1500.0, 2400.0] {
                    // winter_frac sweep includes >0.65 so Mediterranean (Cs) is
                    // reachable as a pure-function property; the v1 pipeline pins
                    // 0.5 (Mediterranean == Temperate biome, no regression).
                    for &wf in &[0.2_f32, 0.5, 0.8] {
                        for &elev in &[0.0_f32, 0.5] {
                            let z = classify_koppen(tw, tc, pr, wf, elev);
                            seen[z.tag() as usize] = true;
                        }
                    }
                }
            }
        }
        assert!(
            seen.iter().all(|&s| s),
            "not all 8 ClimateZone variants reachable: {seen:?}"
        );
    }

    #[test]
    fn arid_bias_makes_borderline_cells_more_arid() {
        // A humid-warm cell that classifies Subtropical unbiased...
        let (tw, tc, pr) = (30.0_f32, 12.0_f32, 520.0_f32);
        assert_eq!(
            classify_koppen(tw, tc, pr, 0.5, 0.0),
            ClimateZone::Subtropical
        );
        // ...with an Arid bias (precip −200 mm) flips to Arid (direction check).
        let (td, pd) = bias_delta(ClimateZone::Arid);
        assert_eq!(
            classify_koppen(tw + td, tc + td, (pr + pd).max(0.0), 0.5, 0.0),
            ClimateZone::Arid
        );
    }

    #[test]
    fn build_derives_a_latitude_climate_gradient() {
        // **Distribution guard** — the unit tests above exercise
        // `classify_koppen` with hand-picked inputs; this one exercises the
        // `build()` *derivation* (geometry → °C + mm/yr → zone) so an inverted
        // lat→temp wiring or an all-one-zone collapse can't pass silently. The
        // assertions are directional properties (not a pinned distribution), so
        // legitimate param retunes don't break them (spec §7: no literal pin).
        //
        // A meridian of land cells from the equator (z≈0) toward the pole
        // (z≈0.95). North wind ⇒ moisture marches equator→pole, so interiors
        // dry out with latitude — a realistic continentality gradient.
        let n = 12;
        let centers: Vec<[f32; 3]> = (0..n)
            .map(|i| {
                let z = i as f32 / n as f32 * 0.95; // sin(lat): 0 → ~0.95
                let x = (1.0 - z * z).sqrt(); // lon = 0 meridian
                [x, 0.0, z]
            })
            .collect();
        let sea = 10_000u16;
        let elevation = vec![20_000u16; n]; // all land, low + uniform elevation
        let neighbors: Vec<Vec<u32>> = (0..n)
            .map(|i| {
                let mut v = Vec::new();
                if i > 0 {
                    v.push((i - 1) as u32);
                }
                if i + 1 < n {
                    v.push((i + 1) as u32);
                }
                v
            })
            .collect();

        let zones = build(
            &centers,
            &elevation,
            sea,
            &neighbors,
            HemisphereOrientation::Equatorial,
            PrevailingWind::North,
            None,
        );

        // Equator end: hot + very wet (2400 mm base) → Tropical.
        assert_eq!(zones[0], ClimateZone::Tropical, "equator must be Tropical");
        // Pole end: warmest-month cold enough to leave the A/B groups → a cold
        // continental/polar class.
        assert!(
            matches!(zones[n - 1], ClimateZone::Boreal | ClimateZone::Polar),
            "pole end must be a cold zone, got {:?}",
            zones[n - 1]
        );
        // The gradient must produce real variety — a regression that collapsed
        // every cell to one zone (the failure this guards) would trip here.
        let mut seen = [false; 8];
        for z in &zones {
            seen[z.tag() as usize] = true;
        }
        let distinct = seen.iter().filter(|&&s| s).count();
        assert!(distinct >= 3, "expected ≥3 distinct zones, got {distinct}: {zones:?}");
    }

    #[test]
    fn rain_shadow_follows_the_wind() {
        // Five cells along the equator, ascending longitude: [0] sea,
        // [1]/[3]/[4] lowland, [2] a tall ridge. Cells are 3D unit-sphere
        // points at lat=0; lon from −0.6 to +0.6 rad (Phase 1 Stage B —
        // sphere-native).
        let centers: Vec<[f32; 3]> = [-0.6_f32, -0.3, 0.0, 0.3, 0.6]
            .iter()
            .map(|&lon| [lon.cos(), lon.sin(), 0.0])
            .collect();
        let sea = 10_000u16;
        let elevation = vec![5_000u16, 15_000, 60_000, 15_000, 15_000];
        let neighbors = vec![vec![1u32], vec![0, 2], vec![1, 3], vec![2, 4], vec![3]];

        // West wind blows the air east → the lee (cell 3, east of the ridge)
        // is left dry; the windward side (cell 1) keeps its moisture.
        let west = moisture_field(&centers, &elevation, sea, &neighbors, PrevailingWind::West);
        assert!(west[1] > west[3], "W wind: windward {} <= lee {}", west[1], west[3]);
        assert!(west[3] < 0.1, "W wind: rain shadow not dry, got {}", west[3]);

        // East wind flows the other way → the rain shadow flips to cell 1.
        let east = moisture_field(&centers, &elevation, sea, &neighbors, PrevailingWind::East);
        assert!(east[3] > east[1], "E wind: windward {} <= lee {}", east[3], east[1]);
        assert!(east[1] < 0.1, "E wind: rain shadow did not flip, got {}", east[1]);
    }
}
