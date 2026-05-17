//! Stage 3 — climate.
//!
//! Per-cell `ClimateZone` from latitude × elevation × dryness, a
//! Köppen-Geiger-inspired deterministic classification (no RNG).
//!
//! Dryness comes from an **orographic moisture march** ([`moisture_field`]): a
//! prevailing wind carries moisture inland from the sea; over land it bleeds
//! away — a small overland leak plus a large orographic loss wherever the
//! terrain climbs — so the lee of a mountain range falls into a dry rain
//! shadow. The march subsumes continentality (deep inland = moisture spent).

use serde::{Deserialize, Serialize};

use crate::creative_seed::{HemisphereOrientation, PrevailingWind};

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
pub fn build(
    centers: &[(f32, f32)],
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
    hemisphere: HemisphereOrientation,
    prevailing_wind: PrevailingWind,
    climate_bias: Option<ClimateZone>,
) -> Vec<ClimateZone> {
    let moisture = moisture_field(centers, elevation, sea_level, neighbors, prevailing_wind);

    centers
        .iter()
        .enumerate()
        .map(|(i, &(_, y))| {
            let eff_lat = effective_latitude(y, hemisphere);
            let elev_norm = f32::from(elevation[i]) / 65535.0;
            // Dryness is the complement of the wind-carried moisture.
            let dryness = (1.0 - moisture[i]).clamp(0.0, 1.0);
            classify(eff_lat, elev_norm, dryness, climate_bias)
        })
        .collect()
}

/// Latitude in `[0,1]` — 0 = equator (hot), 1 = pole (cold).
fn effective_latitude(y: f32, hemi: HemisphereOrientation) -> f32 {
    match hemi {
        HemisphereOrientation::Northern => y,
        HemisphereOrientation::Southern => 1.0 - y,
        HemisphereOrientation::Equatorial => 2.0 * (y - 0.5).abs(),
    }
}

/// Classify one cell. Pure function — the determinism contract of stage 3.
/// `dryness` is `0` (saturated) .. `1` (parched).
pub fn classify(
    eff_lat: f32,
    elev_norm: f32,
    dryness: f32,
    bias: Option<ClimateZone>,
) -> ClimateZone {
    let (temp_d, dry_d) = bias.map_or((0.0, 0.0), bias_delta);
    let temp = (1.0 - eff_lat) - 0.35 * elev_norm + temp_d;
    let dry = (dryness + dry_d).clamp(0.0, 1.0);

    // Highland — altitude dominates, except at polar latitudes (a high cell
    // near the pole stays Polar so glaciated peaks remain reachable).
    if elev_norm > 0.62 && eff_lat < 0.75 {
        return ClimateZone::Highland;
    }

    let mut zone = if temp < 0.16 {
        ClimateZone::Polar
    } else if temp < 0.34 {
        ClimateZone::Boreal
    } else if temp < 0.58 {
        ClimateZone::Temperate
    } else if temp < 0.78 {
        if dry > 0.5 {
            ClimateZone::Mediterranean
        } else {
            ClimateZone::Subtropical
        }
    } else if dry > 0.55 {
        ClimateZone::Arid
    } else {
        ClimateZone::Tropical
    };

    // Dry continental interior → Arid even in the warm-temperate bands.
    if matches!(
        zone,
        ClimateZone::Temperate | ClimateZone::Mediterranean | ClimateZone::Subtropical
    ) && dry > 0.72
        && temp > 0.42
    {
        zone = ClimateZone::Arid;
    }
    zone
}

/// `(temp_delta, dry_delta)` nudging classification toward `z`.
fn bias_delta(z: ClimateZone) -> (f32, f32) {
    match z {
        ClimateZone::Polar => (-0.15, 0.0),
        ClimateZone::Boreal => (-0.10, 0.0),
        ClimateZone::Temperate => (0.0, -0.10),
        ClimateZone::Mediterranean => (0.05, 0.15),
        ClimateZone::Subtropical => (0.10, -0.10),
        ClimateZone::Tropical => (0.12, -0.15),
        ClimateZone::Arid => (0.05, 0.20),
        // Highland is purely elevation-driven; a bias toward it is a no-op.
        ClimateZone::Highland => (0.0, 0.0),
    }
}

/// Per-cell atmospheric moisture in `[0,1]` from a wind-driven march.
///
/// Air enters fully moist from the windward edge and recharges to `1.0` over
/// water; over land it bleeds away — a small overland leak (the continentality
/// gradient) plus a large orographic loss wherever the terrain climbs above
/// its upwind neighbours. The lee of a mountain range is therefore left with
/// little moisture: a dry rain shadow. Deterministic: a total-ordered downwind
/// sweep (`f32::total_cmp` on the wind projection, ties broken by cell index).
fn moisture_field(
    centers: &[(f32, f32)],
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
    wind: PrevailingWind,
) -> Vec<f32> {
    /// Moisture wrung out per unit of normalized climb (orographic rain) —
    /// high, so any real mountain range casts a strong rain shadow.
    const OROGRAPHIC: f32 = 4.5;
    /// Moisture lost per overland step — the continentality gradient.
    const LAND_LEAK: f32 = 0.025;

    let n = centers.len();
    let (wx, wy) = wind.vector();
    let proj = |i: usize| centers[i].0 * wx + centers[i].1 * wy;

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
        let loss = OROGRAPHIC * climb + LAND_LEAK;
        moisture[i] = (incoming - loss).max(0.0);
    }
    moisture
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn highland_needs_high_elevation_below_polar_latitude() {
        assert_eq!(classify(0.3, 0.7, 0.5, None), ClimateZone::Highland);
        // a high cell at a polar latitude stays Polar (→ Glacier-capable).
        assert_eq!(classify(0.95, 0.7, 0.5, None), ClimateZone::Polar);
    }

    #[test]
    fn equator_is_hot_pole_is_cold() {
        assert_eq!(classify(0.0, 0.0, 0.0, None), ClimateZone::Tropical);
        assert_eq!(classify(1.0, 0.0, 0.0, None), ClimateZone::Polar);
    }

    #[test]
    fn arid_bias_makes_borderline_cells_more_arid() {
        // Inputs on the Tropical/Arid border: unbiased → Tropical; an Arid
        // bias must push it to Arid (direction check, not just "differs").
        assert_eq!(classify(0.1, 0.1, 0.45, None), ClimateZone::Tropical);
        assert_eq!(
            classify(0.1, 0.1, 0.45, Some(ClimateZone::Arid)),
            ClimateZone::Arid
        );
    }

    #[test]
    fn all_eight_zones_are_reachable() {
        let mut seen = [false; 8];
        for lat in 0..=20 {
            for elev in 0..=20 {
                for dry in 0..=20 {
                    let z = classify(
                        lat as f32 / 20.0,
                        elev as f32 / 20.0,
                        dry as f32 / 20.0,
                        None,
                    );
                    seen[z.tag() as usize] = true;
                }
            }
        }
        assert!(
            seen.iter().all(|&s| s),
            "not all 8 ClimateZone variants reachable: {seen:?}"
        );
    }

    #[test]
    fn rain_shadow_follows_the_wind() {
        // Five cells in a row: [0] sea, [1]/[3]/[4] lowland, [2] a tall ridge.
        let centers = vec![(0.1, 0.5), (0.3, 0.5), (0.5, 0.5), (0.7, 0.5), (0.9, 0.5)];
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
