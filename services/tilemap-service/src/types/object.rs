//! Tilemap objects: 7 V1+30d closed-enum kinds + placement record.
//! Mirrors TMP_001 §2 — most kinds are V2+ deferred per scope; V1+30d
//! activates Treasure / Town / Mine / Landmark / Monolith.

use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;

use crate::types::biome::BiomeObjectType;
use crate::types::primitive::ObjectPrimitive;
use crate::types::registry::{Direction, FootprintSize};
use crate::types::tile::TileCoord;

/// V1+30d 9-variant closed enum. Some variants are schema-reserved at V1+30d
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
    /// Ferry crossing — V1+30d simplified water route (TMP_007 §7): placed at a
    /// shore tile, click → instant transit. The V2 ship system is TVL_001.
    Ferry,
}

/// V2 fields deterministically derived from a V1 `TilemapObjectKind`
/// + optional `BiomeObjectType`. Mirrors entries in
/// `services/tilemap-service/registry/default.toml`; an integration
/// test (`v2_defaults_match_default_registry`) asserts agreement so
/// the two representations cannot silently drift.
///
/// Used during the V1→V2 migration (Batch 3.0c+3.1) so placer construction
/// sites can populate both legacy + V2 fields without plumbing a
/// registry reference through every call signature. Batch 3.1b replaces
/// these helpers with direct registry lookups.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct V2Defaults {
    pub tag: String,
    pub primitive: ObjectPrimitive,
    pub footprint: FootprintSize,
}

impl TilemapObjectKind {
    /// Returns the V2 tag + primitive + footprint mapping for this kind
    /// (and, for `Obstacle`, its biome object subtype). The mapping is
    /// the same as `registry/default.toml`.
    pub fn v2_defaults(self, biome_object_type: Option<BiomeObjectType>) -> V2Defaults {
        match self {
            Self::Treasure => V2Defaults {
                tag: "lw:treasure".into(),
                primitive: ObjectPrimitive::Pickup,
                footprint: FootprintSize::unit(),
            },
            Self::MonsterLair => V2Defaults {
                tag: "lw:monster_lair".into(),
                primitive: ObjectPrimitive::Spawner,
                footprint: FootprintSize::unit(),
            },
            Self::Town => V2Defaults {
                tag: "lw:town".into(),
                primitive: ObjectPrimitive::Habitable,
                footprint: FootprintSize::new(4, 4),
            },
            Self::Mine => V2Defaults {
                tag: "lw:mine".into(),
                primitive: ObjectPrimitive::Habitable,
                footprint: FootprintSize::new(2, 2),
            },
            Self::Landmark => V2Defaults {
                tag: "lw:landmark".into(),
                primitive: ObjectPrimitive::Decoration,
                footprint: FootprintSize::unit(),
            },
            Self::Monolith => V2Defaults {
                tag: "lw:monolith".into(),
                primitive: ObjectPrimitive::Trigger,
                footprint: FootprintSize::unit(),
            },
            Self::Decoration => V2Defaults {
                tag: "lw:decoration".into(),
                primitive: ObjectPrimitive::Decoration,
                footprint: FootprintSize::unit(),
            },
            Self::Ferry => V2Defaults {
                tag: "lw:ferry".into(),
                primitive: ObjectPrimitive::Vehicle,
                footprint: FootprintSize::unit(),
            },
            Self::Obstacle => {
                let subtype_suffix = biome_object_type
                    .map(|b| match b {
                        BiomeObjectType::Mountain => "mountain",
                        BiomeObjectType::Tree => "tree",
                        BiomeObjectType::Lake => "lake",
                        BiomeObjectType::Crater => "crater",
                        BiomeObjectType::Rock => "rock",
                        BiomeObjectType::Plant => "plant",
                        BiomeObjectType::Structure => "structure",
                        BiomeObjectType::Animal => "animal",
                        BiomeObjectType::Other => "other",
                    })
                    .unwrap_or("other");
                V2Defaults {
                    tag: format!("lw:obstacle.{}", subtype_suffix),
                    primitive: ObjectPrimitive::Blocker,
                    footprint: FootprintSize::unit(),
                }
            }
        }
    }
}

/// A placed object's full record on the tilemap.
///
/// V2 data-model migration (in flight): the legacy `kind` +
/// `biome_object_type` fields stay populated for backward compatibility
/// while the V2 `primitive` + `tag` + `footprint` + `orientation` +
/// `properties` fields land alongside. Both representations are
/// serialised; a later commit removes the legacy fields once every
/// consumer migrates. Per ADR
/// `docs/specs/2026-05-26-data-model-v2-registry-footprint.md`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TilemapObjectPlacement {
    /// **Legacy V1 closed-enum kind.** Kept additive until consumers
    /// migrate to `tag` + `primitive`. Always populated by the placer.
    pub kind: TilemapObjectKind,
    pub anchor: TileCoord,
    /// Optional canonical reference into MAP_001 / CSC_001 / PF_001 for drill-down.
    /// Phase 0a: opaque string; Phase 2 will swap to typed `CanonicalRef`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub canon_ref: Option<String>,
    /// **Legacy V1 obstacle subtype.** Kept additive until consumers
    /// migrate to `tag`.
    /// For `kind == Obstacle` — which biome object type this is (TMP_005 §4.5
    /// river source/sink discovery). `None` for non-obstacle placements.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub biome_object_type: Option<BiomeObjectType>,
    /// Kind-specific magnitude carried from generation. Survives both V1
    /// and V2 — semantic now `properties["value"]` but field kept for
    /// loot/economy/combat to recover without re-derivation.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub value: Option<u32>,

    // ── V2 fields (additive; populated by placer alongside V1 fields) ──
    /// V2 engine primitive. Derived from registry lookup of `tag`.
    /// Skipped on wire only when absent (legacy fixtures pre-V2).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub primitive: Option<ObjectPrimitive>,
    /// V2 registry tag (e.g. `lw:treasure`, `lw:obstacle.mountain`).
    /// Subsumes `kind` + `biome_object_type` once migration completes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tag: Option<String>,
    /// V2 footprint at anchor. (1, 1) for legacy single-tile kinds;
    /// (4, 4) for towns once registry-driven placement lands.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub footprint: Option<FootprintSize>,
    /// V2 prop orientation (asymmetric sprite facing). Default `S`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub orientation: Option<Direction>,
    /// V2 open property bag for per-instance overrides + per-kind data
    /// not covered by the registry's defaults. Empty by default.
    #[serde(default, skip_serializing_if = "JsonValue::is_null")]
    pub properties: JsonValue,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::tile::TileCoord;

    #[test]
    fn placement_deserializes_without_biome_object_type() {
        // TMP-A8 — a pre-Phase-B placement JSON still loads; biome_object_type
        // defaults to None.
        let json = r#"{"kind":"treasure","anchor":{"x":3,"y":4}}"#;
        let p: TilemapObjectPlacement = serde_json::from_str(json).unwrap();
        assert!(p.biome_object_type.is_none());
        assert_eq!(p.kind, TilemapObjectKind::Treasure);
    }

    #[test]
    fn obstacle_placement_round_trips_with_biome_object_type() {
        // TMP-A8 — an obstacle placement carries its BiomeObjectType.
        let v2 = TilemapObjectKind::Obstacle.v2_defaults(Some(BiomeObjectType::Mountain));
        let p = TilemapObjectPlacement {
            kind: TilemapObjectKind::Obstacle,
            anchor: TileCoord::new(7, 9),
            canon_ref: None,
            biome_object_type: Some(BiomeObjectType::Mountain),
            value: None,
            primitive: Some(v2.primitive),
            tag: Some(v2.tag),
            footprint: Some(v2.footprint),
            orientation: None,
            properties: JsonValue::Null,
        };
        let back: TilemapObjectPlacement =
            serde_json::from_str(&serde_json::to_string(&p).unwrap()).unwrap();
        assert_eq!(p, back);
        assert_eq!(back.biome_object_type, Some(BiomeObjectType::Mountain));
    }

    #[test]
    fn placement_without_value_omits_the_field_and_still_deserializes() {
        // AC-11 — `value` is additive (TMP-A8): pre-Phase-C JSON with no
        // `value` key loads (value defaults to None), and a None-value
        // placement serializes without the key — so the golden stays
        // byte-identical for the Phase-B obstacle records.
        let json = r#"{"kind":"obstacle","anchor":{"x":3,"y":4}}"#;
        let p: TilemapObjectPlacement = serde_json::from_str(json).unwrap();
        assert!(p.value.is_none());
        let s = serde_json::to_string(&p).unwrap();
        assert!(!s.contains("value"), "a None value must be skipped: {s}");
    }

    #[test]
    fn treasure_placement_round_trips_with_value() {
        // AC-11 — a Treasure placement carries its composed pile value (D10).
        let v2 = TilemapObjectKind::Treasure.v2_defaults(None);
        let p = TilemapObjectPlacement {
            kind: TilemapObjectKind::Treasure,
            anchor: TileCoord::new(5, 6),
            canon_ref: None,
            biome_object_type: None,
            value: Some(4200),
            primitive: Some(v2.primitive),
            tag: Some(v2.tag),
            footprint: Some(v2.footprint),
            orientation: None,
            properties: JsonValue::Null,
        };
        let back: TilemapObjectPlacement =
            serde_json::from_str(&serde_json::to_string(&p).unwrap()).unwrap();
        assert_eq!(p, back);
        assert_eq!(back.value, Some(4200));
    }

    #[test]
    fn ferry_placement_round_trips() {
        // AC-12 — a Ferry placement (TMP_007 §7 water route) serialises as the
        // snake_case tag "ferry" and survives a JSON round-trip.
        let v2 = TilemapObjectKind::Ferry.v2_defaults(None);
        let p = TilemapObjectPlacement {
            kind: TilemapObjectKind::Ferry,
            anchor: TileCoord::new(4, 8),
            canon_ref: None,
            biome_object_type: None,
            value: None,
            primitive: Some(v2.primitive),
            tag: Some(v2.tag),
            footprint: Some(v2.footprint),
            orientation: None,
            properties: JsonValue::Null,
        };
        let json = serde_json::to_string(&p).unwrap();
        assert!(json.contains("\"ferry\""), "Ferry must serialise as \"ferry\": {json}");
        let back: TilemapObjectPlacement = serde_json::from_str(&json).unwrap();
        assert_eq!(p, back);
        assert_eq!(back.kind, TilemapObjectKind::Ferry);
    }
}
