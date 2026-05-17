//! Tilemap objects: 7 V1+30d closed-enum kinds + placement record.
//! Mirrors TMP_001 §2 — most kinds are V2+ deferred per scope; V1+30d
//! activates Treasure / Town / Mine / Landmark / Monolith.

use serde::{Deserialize, Serialize};

use crate::types::biome::BiomeObjectType;
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
    /// Biome obstacle — mountain, tree, rock, lake, etc. (TMP_005 §4). Blocking.
    Obstacle,
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
    /// For `kind == Obstacle` — which biome object type this is (TMP_005 §4.5
    /// river source/sink discovery). `None` for non-obstacle placements.
    /// Additive (TMP-A8).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub biome_object_type: Option<BiomeObjectType>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::tile::TileCoord;

    #[test]
    fn placement_deserializes_without_biome_object_type() {
        // AC-8 — a pre-Phase-B placement JSON still loads; biome_object_type
        // defaults to None.
        let json = r#"{"kind":"treasure","anchor":{"x":3,"y":4}}"#;
        let p: TilemapObjectPlacement = serde_json::from_str(json).unwrap();
        assert!(p.biome_object_type.is_none());
        assert_eq!(p.kind, TilemapObjectKind::Treasure);
    }

    #[test]
    fn obstacle_placement_round_trips_with_biome_object_type() {
        // AC-8 — an obstacle placement carries its BiomeObjectType.
        let p = TilemapObjectPlacement {
            kind: TilemapObjectKind::Obstacle,
            anchor: TileCoord::new(7, 9),
            canon_ref: None,
            biome_object_type: Some(BiomeObjectType::Mountain),
        };
        let back: TilemapObjectPlacement =
            serde_json::from_str(&serde_json::to_string(&p).unwrap()).unwrap();
        assert_eq!(p, back);
        assert_eq!(back.biome_object_type, Some(BiomeObjectType::Mountain));
    }
}
