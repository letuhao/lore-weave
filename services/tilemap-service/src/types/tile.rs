//! Per-tile types: `TerrainKind` (10 V1+30d closed enum), `TileState` (4 closed enum),
//! `TileCoord`. Mirrors [TMP_001 §2 + §5](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md).

use serde::{Deserialize, Serialize};

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
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
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
