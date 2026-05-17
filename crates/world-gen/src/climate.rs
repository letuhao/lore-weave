//! Stage 3 — climate.
//!
//! Per-cell `ClimateZone` from latitude × elevation × ocean-distance, a
//! Köppen-Geiger-inspired deterministic classification (no RNG).

use std::collections::VecDeque;

use serde::{Deserialize, Serialize};

use crate::creative_seed::HemisphereOrientation;

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
    climate_bias: Option<ClimateZone>,
) -> Vec<ClimateZone> {
    let ocean_dist = ocean_distance(elevation, sea_level, neighbors);
    // Normalizer: ~half the grid side — a cell this many cells from water
    // counts as a fully continental interior.
    let norm = ((centers.len() as f32).sqrt() / 2.0).max(1.0);

    centers
        .iter()
        .enumerate()
        .map(|(i, &(_, y))| {
            let eff_lat = effective_latitude(y, hemisphere);
            let elev_norm = f32::from(elevation[i]) / 65535.0;
            let dist_norm = if ocean_dist[i] == u32::MAX {
                1.0
            } else {
                (ocean_dist[i] as f32 / norm).min(1.0)
            };
            classify(eff_lat, elev_norm, dist_norm, climate_bias)
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
pub fn classify(
    eff_lat: f32,
    elev_norm: f32,
    dist_norm: f32,
    bias: Option<ClimateZone>,
) -> ClimateZone {
    let (temp_d, dry_d) = bias.map_or((0.0, 0.0), bias_delta);
    let temp = (1.0 - eff_lat) - 0.35 * elev_norm + temp_d;
    let dry = (dist_norm + dry_d).clamp(0.0, 1.0);

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

/// Graph distance (in cells) from each cell to the nearest water cell.
/// Multi-source BFS — deterministic (sources swept in index order, BFS over
/// the stored sorted `neighbors`).
fn ocean_distance(elevation: &[u16], sea_level: u16, neighbors: &[Vec<u32>]) -> Vec<u32> {
    let n = elevation.len();
    let mut dist = vec![u32::MAX; n];
    let mut queue: VecDeque<usize> = VecDeque::new();
    for (i, &e) in elevation.iter().enumerate() {
        if e < sea_level {
            dist[i] = 0;
            queue.push_back(i);
        }
    }
    while let Some(c) = queue.pop_front() {
        let d = dist[c] + 1;
        for &nb in &neighbors[c] {
            let nb = nb as usize;
            if d < dist[nb] {
                dist[nb] = d;
                queue.push_back(nb);
            }
        }
    }
    dist
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
}
