//! Types mirroring the `lore-weave-game/world-gen` consumer contract (§11.2
//! base + §11.5 climate + polygon levers). Tilemap-service parses these
//! from a `WorldSource` (file fixture today, HTTP later) and uses them as
//! input constraints on biome selection and zone placement.
//!
//! See spec: docs/specs/2026-05-24-tilemap-world-inheritance-contract.md

use serde::{Deserialize, Serialize};
use std::fmt;

use super::error::WorldInheritError;

/// File-path-style address of a region in the world-gen tree.
///
/// - `RegionPath(vec![])` is the world root.
/// - `RegionPath(vec![3])` is plate 3.
/// - `RegionPath(vec![3, 2])` is zone 2 of plate 3.
/// - `RegionPath(vec![3, 2, 5])` is sub-zone 5 of that zone.
///
/// Display format: `/3/2/5` (folder-style).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct RegionPath(pub Vec<u32>);

impl RegionPath {
    pub fn new(parts: Vec<u32>) -> Self {
        Self(parts)
    }

    pub fn depth(&self) -> usize {
        self.0.len()
    }

    pub fn is_root(&self) -> bool {
        self.0.is_empty()
    }

    pub fn as_slice(&self) -> &[u32] {
        &self.0
    }
}

impl fmt::Display for RegionPath {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.0.is_empty() {
            return write!(f, "/");
        }
        for part in &self.0 {
            write!(f, "/{part}")?;
        }
        Ok(())
    }
}

/// One of ten Whittaker biomes from upstream `world-gen`. Tags 0..=9 match
/// `Biome::tag()` in the upstream crate; tags 0..=7 are pinned across
/// upstream versions, tags 8..=9 (DeciduousForest, Mediterranean) added in
/// v2.1f.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorldBiome {
    /// tag 0
    Ice,
    /// tag 1
    Tundra,
    /// tag 2
    BorealForest,
    /// tag 3
    TemperateForest,
    /// tag 4
    TemperateGrassland,
    /// tag 5
    HotDesert,
    /// tag 6
    Savanna,
    /// tag 7
    TropicalRainforest,
    /// tag 8 — added v2.1f, may shift if upstream re-tags
    DeciduousForest,
    /// tag 9 — added v2.1f, may shift if upstream re-tags
    Mediterranean,
}

impl WorldBiome {
    /// Upstream tag byte. Stable wire format for 0..=7; 8..=9 may shift if
    /// upstream re-tags — prefer matching by `biome_name` when possible.
    pub fn tag(self) -> u8 {
        match self {
            Self::Ice => 0,
            Self::Tundra => 1,
            Self::BorealForest => 2,
            Self::TemperateForest => 3,
            Self::TemperateGrassland => 4,
            Self::HotDesert => 5,
            Self::Savanna => 6,
            Self::TropicalRainforest => 7,
            Self::DeciduousForest => 8,
            Self::Mediterranean => 9,
        }
    }

    /// Parse from upstream tag byte. Returns `UnknownBiomeTag` for values
    /// outside 0..=9.
    pub fn from_tag(tag: u8) -> Result<Self, WorldInheritError> {
        Ok(match tag {
            0 => Self::Ice,
            1 => Self::Tundra,
            2 => Self::BorealForest,
            3 => Self::TemperateForest,
            4 => Self::TemperateGrassland,
            5 => Self::HotDesert,
            6 => Self::Savanna,
            7 => Self::TropicalRainforest,
            8 => Self::DeciduousForest,
            9 => Self::Mediterranean,
            n => return Err(WorldInheritError::UnknownBiomeTag(n)),
        })
    }

    /// All ten variants in tag order; useful for tests + bridge table
    /// completeness checks.
    pub fn all() -> [Self; 10] {
        [
            Self::Ice,
            Self::Tundra,
            Self::BorealForest,
            Self::TemperateForest,
            Self::TemperateGrassland,
            Self::HotDesert,
            Self::Savanna,
            Self::TropicalRainforest,
            Self::DeciduousForest,
            Self::Mediterranean,
        ]
    }
}

/// Per-zone climate facts from upstream world-gen. Currently a §11.5 lever —
/// upstream JSON export does not include it yet; our mock fixtures
/// pre-emptively ship it because tilemap-service cannot apply biome
/// constraints without it.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ZoneClimate {
    /// Mean annual temperature, °C.
    pub temp_mean: f32,
    /// Total annual precipitation, mm/year.
    pub precip_annual: f32,
    /// Upstream biome tag (canonical wire byte; redundant with `biome_name`
    /// but kept for explicit cross-check).
    pub biome_tag: u8,
    /// Typed biome variant; the field tilemap actually uses for bridge
    /// lookups.
    pub biome_name: WorldBiome,
}

/// Wire-shaped read of one world-gen zone. Parsed from JSON (mock now,
/// HTTP later). Frozen at template-construction time so tilemap replay
/// determinism remains stable.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WorldZoneSnapshot {
    pub path: RegionPath,
    pub site: [f32; 2],
    pub base_elevation: f32,
    pub boundary: Vec<[f32; 2]>,
    pub climate: ZoneClimate,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn world_biome_from_tag_round_trips_all_ten() {
        for variant in WorldBiome::all() {
            let tag = variant.tag();
            let parsed = WorldBiome::from_tag(tag).expect("valid tag round-trips");
            assert_eq!(parsed, variant, "tag {tag} round-trip mismatch");
        }
    }

    #[test]
    fn world_biome_from_tag_rejects_out_of_range() {
        let err = WorldBiome::from_tag(10).expect_err("tag 10 is out of range");
        match err {
            WorldInheritError::UnknownBiomeTag(n) => assert_eq!(n, 10),
            other => panic!("expected UnknownBiomeTag(10), got {other:?}"),
        }
    }

    #[test]
    fn region_path_display_formats_as_folder_path() {
        let p = RegionPath::new(vec![2, 1, 5]);
        assert_eq!(format!("{p}"), "/2/1/5");

        let root = RegionPath::new(vec![]);
        assert_eq!(format!("{root}"), "/");
        assert!(root.is_root());

        let plate = RegionPath::new(vec![3]);
        assert_eq!(format!("{plate}"), "/3");
        assert_eq!(plate.depth(), 1);
    }

    #[test]
    fn region_path_serde_round_trip() {
        let p = RegionPath::new(vec![0, 1, 0]);
        let j = serde_json::to_string(&p).expect("serialize");
        assert_eq!(j, "[0,1,0]");
        let back: RegionPath = serde_json::from_str(&j).expect("deserialize");
        assert_eq!(back, p);
    }
}
