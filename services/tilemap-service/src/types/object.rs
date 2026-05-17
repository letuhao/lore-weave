//! Tilemap objects: 7 V1+30d closed-enum kinds + placement record.
//! Mirrors TMP_001 §2 — most kinds are V2+ deferred per scope; V1+30d
//! activates Treasure / Town / Mine / Landmark / Monolith.

use serde::{Deserialize, Serialize};

use crate::types::tile::TileCoord;

/// V1+30d 7-variant closed enum. Some variants are schema-reserved at V1+30d
/// (V2+ activation tracked via TMP-D* deferrals in TMP_001 §16).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TilemapObjectKind {
    /// Treasure pile (TreasureTierSpec post-placement).
    Treasure,
    /// Monster lair — V2+ activation (TMP_006).
    MonsterLair,
    /// Town marker — clicking drills into the cell's CSC_001 16×16 interior.
    Town,
    /// V2 mine — integrates with RES_001 cell-production (TMP-D10 reservation).
    Mine,
    /// Landmark — wilderness cell marker; click drills into CSC_001.
    Landmark,
    /// Teleport pair endpoint (paired via `PassageKind::Portal`).
    Monolith,
    /// V2+ cosmetic / decoration.
    Decoration,
}

/// A placed object's full record on the tilemap. Inner detail (canonical refs,
/// per-kind payload) lands at Phase 1+ when the object placer modificator runs.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TilemapObjectPlacement {
    pub kind: TilemapObjectKind,
    pub anchor: TileCoord,
    /// Optional canonical reference into MAP_001 / CSC_001 / PF_001 for drill-down.
    /// Phase 0a: opaque string; Phase 2 will swap to typed `CanonicalRef`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub canon_ref: Option<String>,
}
