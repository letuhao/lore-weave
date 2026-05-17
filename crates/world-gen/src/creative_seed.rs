//! `CreativeSeed` — the creative-direction input to the generator.
//!
//! Phase 1 carries only the geometry-relevant fields (scale, archetype,
//! coastline). Later phases extend this with climate / political / culture
//! direction. `CreativeSeed` is *not* the RNG seed — `generate(seed, &cs)`
//! takes the `u64` seed separately.

use serde::{Deserialize, Serialize};

use crate::climate::ClimateZone;

/// Creative direction for a generated world.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct CreativeSeed {
    pub world_scale: WorldScale,
    pub world_archetype: WorldArchetype,
    pub coastline_profile: CoastlineProfile,
    /// Which way the continent faces the poles — drives latitude → climate.
    pub hemisphere_orientation: HemisphereOrientation,
    /// Optional nudge toward a climate zone (`None` = unbiased).
    pub climate_bias: Option<ClimateZone>,
    /// How densely settlements are placed (Phase 3).
    pub settlement_density: SettlementDensity,
    /// Number of culture regions (Phase 3); clamped to `1..=16` at use.
    pub culture_count: u8,
}

impl Default for CreativeSeed {
    fn default() -> Self {
        CreativeSeed {
            world_scale: WorldScale::Continent,
            world_archetype: WorldArchetype::HighFantasy,
            coastline_profile: CoastlineProfile::Coastal,
            hemisphere_orientation: HemisphereOrientation::Northern,
            climate_bias: None,
            settlement_density: SettlementDensity::Medium,
            culture_count: 5,
        }
    }
}

/// Settlement placement density (Phase 3).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SettlementDensity {
    Sparse,
    Medium,
    Dense,
}

impl SettlementDensity {
    /// Land cells per settlement (target-count divisor).
    pub fn cells_per_settlement(self) -> usize {
        match self {
            SettlementDensity::Sparse => 800,
            SettlementDensity::Medium => 400,
            SettlementDensity::Dense => 200,
        }
    }

    /// Poisson-disk minimum separation (normalized distance).
    pub fn min_separation(self) -> f32 {
        match self {
            SettlementDensity::Sparse => 0.08,
            SettlementDensity::Medium => 0.05,
            SettlementDensity::Dense => 0.03,
        }
    }
}

/// Continent orientation relative to the poles (latitude convention).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum HemisphereOrientation {
    /// Map top (`y → 1`) is the pole.
    Northern,
    /// Map bottom (`y → 0`) is the pole.
    Southern,
    /// Equator across the middle (`y = 0.5`); both edges are polar.
    Equatorial,
}

/// World size — sets the deterministic mesh dimensions (GEO_001 §6).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WorldScale {
    Pocket,
    Region,
    Continent,
    SuperContinent,
    Megaplanet,
}

impl WorldScale {
    /// Grid side `g` ≈ round(√target) for the GEO_001 §6 cell-count target.
    /// The mesh is a perimeter ring + a `(g-2)×(g-2)` jittered interior.
    pub fn grid_side(self) -> usize {
        match self {
            WorldScale::Pocket => 32,
            WorldScale::Region => 45,
            WorldScale::Continent => 91,
            WorldScale::SuperContinent => 111,
            WorldScale::Megaplanet => 128,
        }
    }

    /// Exact, deterministic total cell count = `(g-2)² + 4·(g-1)`.
    /// → 1024 / 2025 / 8281 / 12321 / 16384, all within `[1024, 16384]`.
    pub fn cell_count(self) -> usize {
        let g = self.grid_side();
        (g - 2) * (g - 2) + 4 * (g - 1)
    }

    /// Stable discriminant byte for the content hash.
    pub fn tag(self) -> u8 {
        match self {
            WorldScale::Pocket => 0,
            WorldScale::Region => 1,
            WorldScale::Continent => 2,
            WorldScale::SuperContinent => 3,
            WorldScale::Megaplanet => 4,
        }
    }
}

/// World genre — stored for later phases; Phase 1 does not branch on it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WorldArchetype {
    Wuxia,
    HighFantasy,
    LowFantasy,
    Cyberpunk,
    SteamPunk,
    Postapocalyptic,
    ScienceFiction,
    Historical,
    Mythological,
    Romance,
    Mystery,
    Custom,
}

/// Coastline shape — drives the heightmap radial falloff + sea-level target.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CoastlineProfile {
    Island,
    Peninsula,
    Coastal,
    Inland,
    Archipelago,
}

impl CoastlineProfile {
    /// Target land fraction — drives the percentile sea-level pick.
    pub fn land_fraction(self) -> f32 {
        match self {
            CoastlineProfile::Island => 0.38,
            CoastlineProfile::Peninsula => 0.46,
            CoastlineProfile::Coastal => 0.55,
            CoastlineProfile::Inland => 0.70,
            CoastlineProfile::Archipelago => 0.32,
        }
    }

    /// Archipelago worlds are intentionally fragmented (scattered islands).
    pub fn is_archipelago(self) -> bool {
        matches!(self, CoastlineProfile::Archipelago)
    }

    /// Amplitude of the continental base dome (terrain stage). A broad dome
    /// gives a *connected* land backbone — needed for `Inland`, whose 0.70
    /// land target a blob-only heightmap cannot form coherently. Other
    /// profiles do not need it (their land target is reachable from blobs +
    /// radial falloff alone) → 0.0, no terrain change.
    pub fn base_amplitude(self) -> f32 {
        match self {
            CoastlineProfile::Inland => 0.75,
            _ => 0.0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cell_counts_match_design_table() {
        assert_eq!(WorldScale::Pocket.cell_count(), 1024);
        assert_eq!(WorldScale::Region.cell_count(), 2025);
        assert_eq!(WorldScale::Continent.cell_count(), 8281);
        assert_eq!(WorldScale::SuperContinent.cell_count(), 12321);
        assert_eq!(WorldScale::Megaplanet.cell_count(), 16384);
    }

    #[test]
    fn cell_counts_within_bounds() {
        for s in [
            WorldScale::Pocket,
            WorldScale::Region,
            WorldScale::Continent,
            WorldScale::SuperContinent,
            WorldScale::Megaplanet,
        ] {
            assert!((1024..=16384).contains(&s.cell_count()));
        }
    }
}
