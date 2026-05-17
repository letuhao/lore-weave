//! `CreativeSeed` — the creative-direction input to the generator.
//!
//! Phase 1 carries only the geometry-relevant fields (scale, archetype,
//! coastline). Later phases extend this with climate / political / culture
//! direction. `CreativeSeed` is *not* the RNG seed — `generate(seed, &cs)`
//! takes the `u64` seed separately.

use serde::{Deserialize, Serialize};

/// Creative direction for a generated world (Phase 1 fields).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct CreativeSeed {
    pub world_scale: WorldScale,
    pub world_archetype: WorldArchetype,
    pub coastline_profile: CoastlineProfile,
}

impl Default for CreativeSeed {
    fn default() -> Self {
        CreativeSeed {
            world_scale: WorldScale::Continent,
            world_archetype: WorldArchetype::HighFantasy,
            coastline_profile: CoastlineProfile::Coastal,
        }
    }
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
