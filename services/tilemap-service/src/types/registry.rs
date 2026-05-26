//! V2 data model — open tag-registry for per-book terrain + object kinds.
//!
//! Each book ships a registry file (TOML) describing its terrain + object
//! kinds. The engine reads `primitive` (closed enum behavior) and
//! `properties` (open property bag) at world-gen time. Adding a new
//! book = ship a new registry; no Rust code change required.
//!
//! See ADR `docs/specs/2026-05-26-data-model-v2-registry-footprint.md` §2.2.

use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;

use crate::types::primitive::{ObjectPrimitive, TerrainPrimitive};

/// Compass direction for asymmetric prop orientation (cottage door
/// facing road, ferry dock heading water, etc.). Default `S` for
/// sprites whose visual "front" is the bottom edge.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum Direction {
    #[serde(rename = "n")]
    N,
    #[serde(rename = "ne")]
    NE,
    #[serde(rename = "e")]
    E,
    #[serde(rename = "se")]
    SE,
    #[default]
    #[serde(rename = "s")]
    S,
    #[serde(rename = "sw")]
    SW,
    #[serde(rename = "w")]
    W,
    #[serde(rename = "nw")]
    NW,
}

/// Per-tile walkability within an object's footprint. Default per
/// primitive: `Blocker`/`Door` (closed) → `AllBlocked`; everything else
/// → `AllWalkable`. Override via `Mask` for kinds like Mine (anchor
/// tile walkable for entry, rest blocked).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WalkabilityPattern {
    /// All footprint tiles walkable.
    AllWalkable,
    /// All footprint tiles blocked.
    AllBlocked,
    /// Per-tile mask (length must equal footprint.width × footprint.height,
    /// row-major). `true` = walkable.
    Mask(Vec<bool>),
}

/// Grid size in tiles — borrowed from `tilemap::GridSize` shape but
/// declared here so the registry module doesn't depend on the wire
/// types module. Same JSON shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct FootprintSize {
    pub width: u32,
    pub height: u32,
}

impl FootprintSize {
    pub const fn unit() -> Self {
        Self { width: 1, height: 1 }
    }

    pub const fn new(width: u32, height: u32) -> Self {
        Self { width, height }
    }

    pub fn area(self) -> u32 {
        self.width * self.height
    }
}

/// Per-tag terrain definition. Loaded from registry TOML; engine reads
/// `primitive` for behavior and `properties` for configuration.
///
/// `id` convention: lowercase + dash; namespaced per book
/// (`lw:grass`, `xianxia:qi-meadow`, `noir:wet-asphalt`). Default
/// registry uses `lw:` prefix.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TerrainKindDef {
    /// Stable tag string referenced on the wire and in registry lookups.
    pub id: String,
    pub primitive: TerrainPrimitive,
    /// Display label ("Qi-rich Meadow"). UI shows this.
    pub label: String,
    /// Open property bag — engine ignores unknown keys; specific
    /// handlers (movement engine, growth tick, weather, etc.) read the
    /// keys they understand. See ADR §2.1.1 for conventions.
    #[serde(default = "default_properties")]
    pub properties: JsonValue,
}

/// Per-tag object definition. Loaded from registry TOML.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ObjectKindDef {
    pub id: String,
    pub primitive: ObjectPrimitive,
    pub label: String,
    /// Logical tile footprint at anchor. (1, 1) = single tile.
    /// Backend placer rejects overlap; frontend renders sprite at
    /// `footprint.width × TILE_PX` display size.
    #[serde(default = "default_unit_footprint")]
    pub footprint: FootprintSize,
    /// Per-tile walkability within the footprint. If `None`, defaults
    /// to AllWalkable / AllBlocked per `primitive.primitive_default_walkable()`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub walkability_pattern: Option<WalkabilityPattern>,
    /// Minimum Chebyshev distance to other placements of the same kind.
    /// 0 = no spacing rule. Engine enforces during placement.
    #[serde(default)]
    pub min_spacing: u32,
    /// Open property bag — see ADR §2.1.1.
    #[serde(default = "default_properties")]
    pub properties: JsonValue,
}

fn default_properties() -> JsonValue {
    JsonValue::Object(serde_json::Map::new())
}

fn default_unit_footprint() -> FootprintSize {
    FootprintSize::unit()
}

/// Registry identifier + version, embedded in TilemapView responses so
/// frontends can detect mismatched registry assumptions.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RegistryRef {
    /// Registry identifier (e.g. `"lw"`, `"xianxia-demo"`).
    pub id: String,
    /// Semver-ish version. Bumped on schema-breaking changes.
    pub version: String,
}

impl RegistryRef {
    pub fn new(id: impl Into<String>, version: impl Into<String>) -> Self {
        Self { id: id.into(), version: version.into() }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn direction_serde_snake_case() {
        assert_eq!(serde_json::to_string(&Direction::S).unwrap(), "\"s\"");
        assert_eq!(serde_json::to_string(&Direction::NE).unwrap(), "\"ne\"");
        let back: Direction = serde_json::from_str("\"nw\"").unwrap();
        assert_eq!(back, Direction::NW);
    }

    #[test]
    fn direction_default_is_south() {
        assert_eq!(Direction::default(), Direction::S);
    }

    #[test]
    fn walkability_pattern_serde() {
        let all_walk = WalkabilityPattern::AllWalkable;
        let s = serde_json::to_string(&all_walk).unwrap();
        assert_eq!(s, "\"all_walkable\"");
        let mask = WalkabilityPattern::Mask(vec![true, false, true, false]);
        let mask_s = serde_json::to_string(&mask).unwrap();
        let back: WalkabilityPattern = serde_json::from_str(&mask_s).unwrap();
        assert_eq!(back, mask);
    }

    #[test]
    fn footprint_size_unit_is_1x1() {
        let u = FootprintSize::unit();
        assert_eq!(u.width, 1);
        assert_eq!(u.height, 1);
        assert_eq!(u.area(), 1);
    }

    #[test]
    fn footprint_size_area_multiplies() {
        assert_eq!(FootprintSize::new(4, 4).area(), 16);
        assert_eq!(FootprintSize::new(2, 3).area(), 6);
        assert_eq!(FootprintSize::new(1, 1).area(), 1);
    }

    #[test]
    fn terrain_kind_def_round_trip_toml() {
        let toml_text = r#"
id = "lw:grass"
primitive = "land"
label = "Grass"

[properties]
movement_speed = 1.0
biome_affinity = "grassland_temperate"
"#;
        let def: TerrainKindDef = toml::from_str(toml_text).unwrap();
        assert_eq!(def.id, "lw:grass");
        assert_eq!(def.primitive, TerrainPrimitive::Land);
        assert_eq!(def.label, "Grass");
        assert_eq!(def.properties["movement_speed"], json!(1.0));
        assert_eq!(def.properties["biome_affinity"], json!("grassland_temperate"));
    }

    #[test]
    fn object_kind_def_round_trip_toml_with_footprint() {
        let toml_text = r#"
id = "lw:town"
primitive = "habitable"
label = "Town"
min_spacing = 8
footprint = { width = 4, height = 4 }

[properties]
drill_down_target = "csc_interior"
"#;
        let def: ObjectKindDef = toml::from_str(toml_text).unwrap();
        assert_eq!(def.id, "lw:town");
        assert_eq!(def.primitive, ObjectPrimitive::Habitable);
        assert_eq!(def.footprint, FootprintSize::new(4, 4));
        assert_eq!(def.min_spacing, 8);
        assert!(def.walkability_pattern.is_none(), "defaults to primitive's walkability");
    }

    #[test]
    fn object_kind_def_default_footprint_is_unit() {
        let toml_text = r#"
id = "lw:tree"
primitive = "blocker"
label = "Tree"
"#;
        let def: ObjectKindDef = toml::from_str(toml_text).unwrap();
        assert_eq!(def.footprint, FootprintSize::unit());
        assert_eq!(def.min_spacing, 0);
    }

    #[test]
    fn object_kind_def_walkability_mask_round_trip() {
        // A mine: footprint 2×2, anchor tile (0,0) walkable, rest blocked.
        let toml_text = r#"
id = "lw:mine"
primitive = "habitable"
label = "Mine"
footprint = { width = 2, height = 2 }
walkability_pattern = { mask = [true, false, false, false] }
"#;
        let def: ObjectKindDef = toml::from_str(toml_text).unwrap();
        match def.walkability_pattern {
            Some(WalkabilityPattern::Mask(m)) => assert_eq!(m, vec![true, false, false, false]),
            other => panic!("expected Mask, got {other:?}"),
        }
    }

    #[test]
    fn registry_ref_round_trip() {
        let r = RegistryRef::new("lw", "1.0.0");
        let json = serde_json::to_string(&r).unwrap();
        let back: RegistryRef = serde_json::from_str(&json).unwrap();
        assert_eq!(r, back);
        assert_eq!(r.id, "lw");
        assert_eq!(r.version, "1.0.0");
    }

    #[test]
    fn json_round_trip_terrain_kind_def() {
        // Confirm JSON shape is wire-friendly for embedding in TilemapView
        // (registry doesn't need to ship as TOML over wire; it ships as JSON).
        let def = TerrainKindDef {
            id: "lw:water".to_string(),
            primitive: TerrainPrimitive::Water,
            label: "Water".to_string(),
            properties: json!({ "depth": "shallow" }),
        };
        let s = serde_json::to_string(&def).unwrap();
        let back: TerrainKindDef = serde_json::from_str(&s).unwrap();
        assert_eq!(def, back);
    }

    #[test]
    fn empty_properties_defaults_to_empty_object() {
        let toml_text = r#"
id = "lw:wall"
primitive = "wall"
label = "Wall"
"#;
        let def: TerrainKindDef = toml::from_str(toml_text).unwrap();
        assert_eq!(def.properties, json!({}));
    }
}
