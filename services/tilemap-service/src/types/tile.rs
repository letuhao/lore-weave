//! Per-tile types: `TerrainKind` (10 V1+30d closed enum), `TileState` (4 closed enum),
//! `TileCoord`. Mirrors [TMP_001 §2 + §5](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md).

use serde::{Deserialize, Serialize};

use crate::types::primitive::TerrainPrimitive;

/// Tile coordinate within a `tilemap_view`'s grid. `(x, y)` with origin at top-left.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TileCoord {
    pub x: u32,
    pub y: u32,
}

impl TileCoord {
    pub fn new(x: u32, y: u32) -> Self {
        Self { x, y }
    }

    /// Flat-array index for a given grid width: `y * width + x`.
    pub fn flat_index(self, grid_width: u32) -> usize {
        (self.y as usize) * (grid_width as usize) + (self.x as usize)
    }
}

/// V1+30d 10-variant closed enum per TMP_001 §2. Stored as `u8` index in the
/// flat terrain layer; explicit discriminants pin the wire format.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[repr(u8)]
pub enum TerrainKind {
    Grass = 1,
    Forest = 2,
    Mountain = 3,
    Water = 4,
    Sand = 5,
    Snow = 6,
    Swamp = 7,
    Road = 8,
    Rough = 9,
    Subterranean = 10,
}

impl TerrainKind {
    /// Stable lowercase tag — matches the `serde` `snake_case` wire name.
    /// Use this instead of `format!("{:?}", _)` so a future multi-word variant
    /// stays consistent with its serialized form.
    pub fn tag(self) -> &'static str {
        match self {
            Self::Grass => "grass",
            Self::Forest => "forest",
            Self::Mountain => "mountain",
            Self::Water => "water",
            Self::Sand => "sand",
            Self::Snow => "snow",
            Self::Swamp => "swamp",
            Self::Road => "road",
            Self::Rough => "rough",
            Self::Subterranean => "subterranean",
        }
    }

    /// TMP-Q2 chunk B — inverse of [`Self::tag`]. Resolves a snake_case
    /// `TerrainKind::tag()` value to its enum variant. Returns `None`
    /// for unknown strings — chunk-B [`crate::engine::modificators::biome_theme_painter`]
    /// relies on this AFTER registry-load validation (`is_valid_biome_key`)
    /// already gated the input, so an `Option::expect` at call site is
    /// safe.
    ///
    /// Closed-set match against the enum variants directly so adding a
    /// future variant fails this lookup AND `is_valid_biome_key` AND
    /// `tag()` in the same commit — no silent drift between the three.
    pub fn from_tag(tag: &str) -> Option<Self> {
        match tag {
            "grass" => Some(Self::Grass),
            "forest" => Some(Self::Forest),
            "mountain" => Some(Self::Mountain),
            "water" => Some(Self::Water),
            "sand" => Some(Self::Sand),
            "snow" => Some(Self::Snow),
            "swamp" => Some(Self::Swamp),
            "road" => Some(Self::Road),
            "rough" => Some(Self::Rough),
            "subterranean" => Some(Self::Subterranean),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests_terrain_kind_tag {
    use super::*;

    #[test]
    fn from_tag_round_trips_all_ten_variants() {
        for tk in [
            TerrainKind::Grass,
            TerrainKind::Forest,
            TerrainKind::Mountain,
            TerrainKind::Water,
            TerrainKind::Sand,
            TerrainKind::Snow,
            TerrainKind::Swamp,
            TerrainKind::Road,
            TerrainKind::Rough,
            TerrainKind::Subterranean,
        ] {
            assert_eq!(
                TerrainKind::from_tag(tk.tag()),
                Some(tk),
                "round-trip failed for {tk:?}"
            );
        }
    }

    #[test]
    fn from_tag_returns_none_for_unknown() {
        for unknown in ["atmosphere", "GRASS", "", " grass", "grass "] {
            assert_eq!(
                TerrainKind::from_tag(unknown),
                None,
                "from_tag({unknown:?}) should be None"
            );
        }
    }
}

/// V1+30d 4-variant tile state machine per TMP_001 §5 (standard procedural
/// level-gen pattern). Internal pipeline state — not exposed to player UI.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TileState {
    /// Passable + no object.
    Walkable,
    /// Passable + can fit an object.
    Open,
    /// Blocked — terrain or obstacle.
    Obstacle,
    /// Object placed; not walkable.
    Occupied,
}

impl TileState {
    /// Whether the tile permits actor traversal.
    pub fn is_passable(self) -> bool {
        matches!(self, TileState::Walkable | TileState::Open)
    }
}

/// V2 per-tile terrain cell. Combines engine-level `primitive` (closed
/// enum behavior) with open-tag `tag` (registry lookup for visuals +
/// lore). The tag namespacing convention is `lw:` for the default
/// registry; per-book registries use their own prefix.
///
/// Used in `TilemapView.terrain_vocabulary` — a dictionary indexed by
/// the u8 values in `TilemapView.terrain_layer`. The dict pattern keeps
/// `terrain_layer` compact (one byte per tile) while letting the cell
/// definitions live once per vocabulary.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TerrainCell {
    pub primitive: TerrainPrimitive,
    pub tag: String,
}

/// V2 terrain default — every V1 `TerrainKind` variant resolves to a
/// canonical `TerrainCell` under the `lw:` namespace. Mirrors entries
/// in `services/tilemap-service/registry/default.toml`; a drift-
/// prevention test asserts the helper output matches the default
/// registry.
impl TerrainKind {
    /// V2 default cell (primitive + tag) for this V1 terrain kind.
    pub fn v2_cell(self) -> TerrainCell {
        let (primitive, tag) = match self {
            Self::Grass => (TerrainPrimitive::Land, "lw:grass"),
            Self::Forest => (TerrainPrimitive::Land, "lw:forest"),
            Self::Mountain => (TerrainPrimitive::Land, "lw:mountain"),
            Self::Water => (TerrainPrimitive::Water, "lw:water"),
            Self::Sand => (TerrainPrimitive::Land, "lw:sand"),
            Self::Snow => (TerrainPrimitive::Land, "lw:snow"),
            Self::Swamp => (TerrainPrimitive::Land, "lw:swamp"),
            Self::Road => (TerrainPrimitive::Path, "lw:road"),
            Self::Rough => (TerrainPrimitive::Land, "lw:rough"),
            Self::Subterranean => (TerrainPrimitive::Land, "lw:subterranean"),
        };
        TerrainCell { primitive, tag: tag.to_string() }
    }
}

/// Build the default `terrain_vocabulary` for V1 wire-shape backward
/// compat. Indexed by the u8 values used in `TilemapView.terrain_layer`:
/// `vocab[0]` is a Void sentinel (matches "unset" tile); `vocab[1..=10]`
/// maps to the V1 `TerrainKind` enum order.
///
/// Length 11 (index 0 + 10 V1 variants). When the engine + registry
/// migration completes (Batch 3.1), this helper will be replaced by
/// `Registry::build_default_terrain_vocabulary()`.
pub fn default_terrain_vocabulary() -> Vec<TerrainCell> {
    vec![
        TerrainCell { primitive: TerrainPrimitive::Void, tag: "lw:void".to_string() },
        TerrainKind::Grass.v2_cell(),        // index 1
        TerrainKind::Forest.v2_cell(),       // index 2
        TerrainKind::Mountain.v2_cell(),     // index 3
        TerrainKind::Water.v2_cell(),        // index 4
        TerrainKind::Sand.v2_cell(),         // index 5
        TerrainKind::Snow.v2_cell(),         // index 6
        TerrainKind::Swamp.v2_cell(),        // index 7
        TerrainKind::Road.v2_cell(),         // index 8
        TerrainKind::Rough.v2_cell(),        // index 9
        TerrainKind::Subterranean.v2_cell(), // index 10
    ]
}

#[cfg(test)]
mod terrain_v2_tests {
    use super::*;

    #[test]
    fn v2_cell_round_trips_for_every_kind() {
        for k in [
            TerrainKind::Grass,
            TerrainKind::Forest,
            TerrainKind::Mountain,
            TerrainKind::Water,
            TerrainKind::Sand,
            TerrainKind::Snow,
            TerrainKind::Swamp,
            TerrainKind::Road,
            TerrainKind::Rough,
            TerrainKind::Subterranean,
        ] {
            let cell = k.v2_cell();
            assert_eq!(cell.tag, format!("lw:{}", k.tag()), "tag drift for {k:?}");
            let json = serde_json::to_string(&cell).unwrap();
            let back: TerrainCell = serde_json::from_str(&json).unwrap();
            assert_eq!(cell, back);
        }
    }

    #[test]
    fn default_vocabulary_is_11_entries_with_void_at_zero() {
        let vocab = default_terrain_vocabulary();
        assert_eq!(vocab.len(), 11, "11 entries: void sentinel + 10 V1 kinds");
        assert_eq!(vocab[0].primitive, TerrainPrimitive::Void);
        assert_eq!(vocab[0].tag, "lw:void");
        // Spot-check a few indexed positions
        assert_eq!(vocab[1].tag, "lw:grass");
        assert_eq!(vocab[4].tag, "lw:water");
        assert_eq!(vocab[4].primitive, TerrainPrimitive::Water);
        assert_eq!(vocab[8].tag, "lw:road");
        assert_eq!(vocab[8].primitive, TerrainPrimitive::Path);
        assert_eq!(vocab[10].tag, "lw:subterranean");
    }

    #[test]
    fn vocabulary_index_matches_terrainkind_u8_repr() {
        // The `#[repr(u8)]` discriminants on TerrainKind are 1-based.
        // Indexing vocab[kind as u8] must return the matching cell.
        let vocab = default_terrain_vocabulary();
        assert_eq!(vocab[TerrainKind::Grass as usize].tag, "lw:grass");
        assert_eq!(vocab[TerrainKind::Water as usize].tag, "lw:water");
        assert_eq!(vocab[TerrainKind::Subterranean as usize].tag, "lw:subterranean");
    }
}
