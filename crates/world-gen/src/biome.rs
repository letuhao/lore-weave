//! Stage 4c — biome derivation.
//!
//! `derive_biome` is a **total** deterministic function of
//! `(climate, elevation, river_flux, water flags)` — the GEO_001 §4.2 matrix.

use serde::{Deserialize, Serialize};

use crate::climate::ClimateZone;
use crate::params::BiomeParams;

/// Closed biome enum (GEO_001 §4.2, 14 variants).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BiomeKind {
    Ocean,
    Lake,
    River,
    Coast,
    Beach,
    Plain,
    Forest,
    Jungle,
    Marsh,
    Mountain,
    Hill,
    Desert,
    Tundra,
    Glacier,
}

impl BiomeKind {
    /// Stable discriminant byte for the content hash.
    pub fn tag(self) -> u8 {
        match self {
            BiomeKind::Ocean => 0,
            BiomeKind::Lake => 1,
            BiomeKind::River => 2,
            BiomeKind::Coast => 3,
            BiomeKind::Beach => 4,
            BiomeKind::Plain => 5,
            BiomeKind::Forest => 6,
            BiomeKind::Jungle => 7,
            BiomeKind::Marsh => 8,
            BiomeKind::Mountain => 9,
            BiomeKind::Hill => 10,
            BiomeKind::Desert => 11,
            BiomeKind::Tundra => 12,
            BiomeKind::Glacier => 13,
        }
    }

    /// Whether this biome is a water cell.
    pub fn is_water(self) -> bool {
        matches!(self, BiomeKind::Ocean | BiomeKind::Lake)
    }

    /// Integer movement cost to enter a cell of this biome (stages 5, 7).
    /// `None` = impassable (open water).
    pub fn terrain_cost(self) -> Option<u32> {
        match self {
            BiomeKind::Ocean | BiomeKind::Lake => None,
            BiomeKind::Plain | BiomeKind::Coast | BiomeKind::Beach => Some(1),
            BiomeKind::Forest | BiomeKind::River => Some(2),
            BiomeKind::Hill | BiomeKind::Desert | BiomeKind::Tundra => Some(3),
            BiomeKind::Jungle | BiomeKind::Marsh => Some(4),
            BiomeKind::Mountain => Some(8),
            BiomeKind::Glacier => Some(20),
        }
    }

    /// Integer culture-spread cost (stage 8). `None` = hard barrier.
    ///
    /// Glacier is a *land* biome here (`is_water() == false`), so culture must
    /// be able to reach Glacier land cells — it is a high finite cost, not the
    /// `None` hard barrier GEO_002 §5.2 used (where glacier was modelled as
    /// water). Open water alone is the hard barrier.
    pub fn culture_barrier(self) -> Option<u32> {
        match self {
            BiomeKind::Ocean | BiomeKind::Lake => None,
            BiomeKind::Plain
            | BiomeKind::Forest
            | BiomeKind::Coast
            | BiomeKind::Beach
            | BiomeKind::River => Some(1),
            BiomeKind::Hill | BiomeKind::Marsh | BiomeKind::Jungle | BiomeKind::Tundra => Some(2),
            BiomeKind::Desert | BiomeKind::Mountain => Some(3),
            BiomeKind::Glacier => Some(8),
        }
    }

    /// Base habitability for the stage-6 burg score (`0.0` = uninhabitable).
    pub fn population_potential(self) -> f32 {
        match self {
            BiomeKind::Plain => 1.0,
            BiomeKind::Coast | BiomeKind::River => 0.9,
            BiomeKind::Forest => 0.7,
            BiomeKind::Hill => 0.6,
            BiomeKind::Beach => 0.5,
            BiomeKind::Jungle => 0.4,
            BiomeKind::Marsh => 0.3,
            BiomeKind::Tundra | BiomeKind::Desert => 0.2,
            BiomeKind::Mountain => 0.15,
            BiomeKind::Ocean | BiomeKind::Lake | BiomeKind::Glacier => 0.0,
        }
    }
}

/// Build the per-cell biome layer using the **default** elevation tiers. Thin
/// wrapper over [`build_with`] for callers that don't tune them (tests).
pub fn build(
    elevation: &[u16],
    sea_level: u16,
    climate: &[ClimateZone],
    river_flux: &[f32],
    river_threshold: f32,
    is_in_ocean: &[bool],
    is_coast: &[bool],
) -> Vec<BiomeKind> {
    build_with(
        elevation, sea_level, climate, river_flux, river_threshold, is_in_ocean, is_coast,
        &BiomeParams::default(),
    )
}

/// Build the per-cell biome layer with caller-tuned [`BiomeParams`] elevation
/// tiers (parameterization P7). Default params ⇒ byte-identical to the prior
/// literals.
#[allow(clippy::too_many_arguments)]
pub fn build_with(
    elevation: &[u16],
    sea_level: u16,
    climate: &[ClimateZone],
    river_flux: &[f32],
    river_threshold: f32,
    is_in_ocean: &[bool],
    is_coast: &[bool],
    bp: &BiomeParams,
) -> Vec<BiomeKind> {
    (0..elevation.len())
        .map(|i| {
            derive_biome(
                climate[i],
                elevation[i],
                sea_level,
                river_flux[i],
                river_threshold,
                is_in_ocean[i],
                is_coast[i],
                bp,
            )
        })
        .collect()
}

/// Derive one cell's biome — total deterministic function (GEO_001 §4.2).
///
/// Total by construction: "is this a water cell?" is computed here from
/// `elevation < sea_level`, so the `elevation - sea_level` land-tier
/// subtraction below is only ever reached when `elevation >= sea_level` —
/// no caller can pass an inconsistent flag.
#[allow(clippy::too_many_arguments)]
pub fn derive_biome(
    climate: ClimateZone,
    elevation: u16,
    sea_level: u16,
    river_flux: f32,
    river_threshold: f32,
    is_in_ocean: bool,
    is_coast: bool,
    bp: &BiomeParams,
) -> BiomeKind {
    if elevation < sea_level {
        return if is_in_ocean {
            BiomeKind::Ocean
        } else {
            BiomeKind::Lake
        };
    }
    if river_flux > river_threshold {
        return BiomeKind::River;
    }
    // Elevation tier within the land range [sea_level, 65535].
    let land_t = f32::from(elevation - sea_level) / f32::from((65535 - sea_level).max(1));
    if is_coast {
        return if land_t < bp.beach_t {
            BiomeKind::Beach
        } else {
            BiomeKind::Coast
        };
    }
    let high = land_t >= bp.high_t;
    let mid = land_t >= bp.mid_t;
    // Wet but not a river — feeds Marsh in warm-humid lowlands.
    let wet_low = land_t < bp.mid_t && river_flux > bp.wet_low_flux_frac * river_threshold;

    match climate {
        ClimateZone::Highland => hill_or_mountain(high),
        ClimateZone::Polar => {
            if high {
                BiomeKind::Glacier
            } else {
                BiomeKind::Tundra
            }
        }
        ClimateZone::Boreal => {
            if high {
                BiomeKind::Mountain
            } else if mid {
                BiomeKind::Hill
            } else {
                BiomeKind::Forest
            }
        }
        ClimateZone::Temperate | ClimateZone::Mediterranean => {
            if high {
                BiomeKind::Mountain
            } else if mid {
                BiomeKind::Hill
            } else {
                BiomeKind::Plain
            }
        }
        ClimateZone::Subtropical => {
            if high {
                BiomeKind::Mountain
            } else if mid {
                BiomeKind::Hill
            } else if wet_low {
                BiomeKind::Marsh
            } else {
                BiomeKind::Forest
            }
        }
        ClimateZone::Tropical => {
            if high {
                BiomeKind::Mountain
            } else if mid {
                BiomeKind::Hill
            } else if wet_low {
                BiomeKind::Marsh
            } else {
                BiomeKind::Jungle
            }
        }
        ClimateZone::Arid => {
            if high {
                BiomeKind::Mountain
            } else if mid {
                BiomeKind::Hill
            } else {
                BiomeKind::Desert
            }
        }
    }
}

fn hill_or_mountain(high: bool) -> BiomeKind {
    if high {
        BiomeKind::Mountain
    } else {
        BiomeKind::Hill
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Inputs hand-picked to surface a given biome.
    fn b(
        climate: ClimateZone,
        land_t: f32,
        flux: f32,
        threshold: f32,
        is_water: bool,
        ocean: bool,
        coast: bool,
    ) -> BiomeKind {
        let sea = 20_000u16;
        let elevation = if is_water {
            sea - 1
        } else {
            sea + (land_t * f32::from(65535 - sea)) as u16
        };
        derive_biome(climate, elevation, sea, flux, threshold, ocean, coast, &BiomeParams::default())
    }

    #[test]
    fn all_fourteen_biomes_are_reachable() {
        use ClimateZone as C;
        let cases = [
            BiomeKind::Ocean,   // water + ocean
            BiomeKind::Lake,    // water + !ocean
            BiomeKind::River,   // flux > threshold
            BiomeKind::Coast,   // coast, land_t >= 0.06
            BiomeKind::Beach,   // coast, land_t < 0.06
            BiomeKind::Plain,   // Temperate low
            BiomeKind::Forest,  // Boreal low
            BiomeKind::Jungle,  // Tropical low dry
            BiomeKind::Marsh,   // Tropical low wet
            BiomeKind::Mountain,// any high
            BiomeKind::Hill,    // any mid
            BiomeKind::Desert,  // Arid low
            BiomeKind::Tundra,  // Polar low
            BiomeKind::Glacier, // Polar high
        ];
        let got = [
            b(C::Temperate, 0.0, 0.0, 100.0, true, true, false),
            b(C::Temperate, 0.0, 0.0, 100.0, true, false, false),
            b(C::Temperate, 0.3, 200.0, 100.0, false, false, false),
            b(C::Temperate, 0.3, 0.0, 100.0, false, false, true),
            b(C::Temperate, 0.0, 0.0, 100.0, false, false, true),
            b(C::Temperate, 0.1, 0.0, 100.0, false, false, false),
            b(C::Boreal, 0.1, 0.0, 100.0, false, false, false),
            b(C::Tropical, 0.1, 0.0, 100.0, false, false, false),
            b(C::Tropical, 0.1, 60.0, 100.0, false, false, false),
            b(C::Temperate, 0.8, 0.0, 100.0, false, false, false),
            b(C::Temperate, 0.4, 0.0, 100.0, false, false, false),
            b(C::Arid, 0.1, 0.0, 100.0, false, false, false),
            b(C::Polar, 0.1, 0.0, 100.0, false, false, false),
            b(C::Polar, 0.8, 0.0, 100.0, false, false, false),
        ];
        assert_eq!(got, cases, "biome matrix does not surface all 14 variants");
    }

    #[test]
    fn water_cells_never_get_a_land_biome() {
        for ocean in [true, false] {
            let biome = b(ClimateZone::Tropical, 0.0, 999.0, 1.0, true, ocean, false);
            assert!(biome.is_water(), "water cell got land biome {biome:?}");
        }
    }

    #[test]
    fn land_cells_never_get_a_water_biome() {
        let biome = b(ClimateZone::Tropical, 0.5, 0.0, 100.0, false, false, false);
        assert!(!biome.is_water(), "land cell got water biome {biome:?}");
    }
}
