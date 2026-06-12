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
    /// TMP-Q3 chunk C — per-book cross-tile-blend shader hint.
    /// Kernel half-radius as a fraction of `uTilePx/2` in the
    /// frontend Stage-2 shader. Range `[0.0, 1.0]`, finite. When
    /// `None`, the frontend uses `STAGE2_BLEND_DEFAULTS.blendRadius`.
    /// Authors set this per-kind to tune how aggressively a terrain
    /// blurs at its edges (water=softer, mountain=sharper). Additive
    /// Option pattern preserves V2 byte-identical output when absent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub blend_radius: Option<f32>,
    /// TMP-Q3 chunk C — per-book cross-tile-blend shader hint.
    /// Mix factor at the tile EDGE in the frontend Stage-2 shader.
    /// Range `[0.0, 1.0]`, finite. When `None`, the frontend uses
    /// `STAGE2_BLEND_DEFAULTS.blendStrength`. Higher = more visible
    /// crossfade between this terrain and its neighbors.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub blend_strength: Option<f32>,
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
    /// TMP-Q1 chunk B — biome filter applied to every kind regardless
    /// of primitive (so author errors on Town/Mine entries fail at
    /// load-time, not silently). Each entry MUST be a
    /// `TerrainKind::tag()` value (snake_case: `"grass"`, `"forest"`,
    /// `"mountain"`, `"water"`, `"sand"`, `"snow"`, `"swamp"`, `"road"`,
    /// `"rough"`, `"subterranean"`). Empty list is allowed (the V2
    /// default; means "no biome restriction"). Duplicate keys in this
    /// list are rejected at registry load.
    ///
    /// V2 wire-discipline: `skip_serializing_if = "Vec::is_empty"`
    /// matches `world_zone` / `walkability_pattern` Option-skipping.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub biomes: Vec<String>,
    /// TMP-Q1 chunk B — relative weight for the DecorationPlacer's
    /// weighted random selection within a biome's pool. 1.0 is neutral;
    /// 1.5 makes the tag 50% more likely than a 1.0 neighbour; 0.3
    /// makes it rare. Ignored for non-decoration kinds. Registry-load
    /// validation rejects non-finite or non-positive values to keep
    /// chunk-C's weighted-sample call total-positive.
    ///
    /// `skip_serializing_if = "is_default_density_weight"` keeps the
    /// wire shape unchanged for V2 entries that don't set the field.
    #[serde(default = "default_density_weight",
            skip_serializing_if = "is_default_density_weight")]
    pub density_weight: f32,
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

fn default_density_weight() -> f32 {
    1.0
}

/// Tests whether a `density_weight` equals the default exactly (1.0).
/// Used by `#[serde(skip_serializing_if)]` so V2 entries that don't
/// declare the field stay omitted from a round-trip.
fn is_default_density_weight(weight: &f32) -> bool {
    *weight == 1.0
}

/// Registry identifier + version, embedded in TilemapView responses so
/// frontends can detect mismatched registry assumptions.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RegistryRef {
    /// Registry identifier (e.g. `"lw"`, `"xianxia-demo"`).
    pub id: String,
    /// Semver-ish version. Bumped on schema-breaking changes.
    pub version: String,
    /// TMP-Q4 — per-book value-band thresholds (ascending). 4 values
    /// = 5 bands (low / low-mid / mid / high / gilt). When `None`,
    /// the frontend falls back to `VALUE_BAND_DEFAULTS =
    /// [500, 2000, 5000, 12000]`. Validated at `Registry::from_file`:
    /// strictly ascending, no duplicates. Per-book registries OWN
    /// their value scale — a xianxia book with high-end qi-stones at
    /// 50k can override the defaults so its top tier maps to "gilt".
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub value_band_thresholds: Option<[u32; 4]>,
}

impl RegistryRef {
    pub fn new(id: impl Into<String>, version: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            version: version.into(),
            value_band_thresholds: None,
        }
    }

    /// TMP-Q4 builder for tests + per-book registries that set bands.
    ///
    /// **MED-2 from chunk-A /review-impl** — the builder validates the
    /// strict-ascending invariant up-front so production callers (and
    /// tests that bypass `Registry::from_file`) can't put invalid bands
    /// on the wire. Same check as `Registry::from_file` runs against the
    /// loaded TOML, so the two paths cannot diverge.
    pub fn with_value_band_thresholds(
        mut self,
        thresholds: [u32; 4],
    ) -> Result<Self, ValueBandThresholdsError> {
        for i in 0..3 {
            if thresholds[i] >= thresholds[i + 1] {
                return Err(ValueBandThresholdsError {
                    thresholds,
                    bad_index: i,
                });
            }
        }
        self.value_band_thresholds = Some(thresholds);
        Ok(self)
    }
}

/// TMP-Q4 MED-2 — surfaced when a builder caller passes a non-strictly-
/// ascending `value_band_thresholds` array.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValueBandThresholdsError {
    pub thresholds: [u32; 4],
    pub bad_index: usize,
}

impl std::fmt::Display for ValueBandThresholdsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "value_band_thresholds must be strictly ascending; got {:?} (index {} >= {})",
            self.thresholds, self.bad_index, self.bad_index + 1
        )
    }
}

impl std::error::Error for ValueBandThresholdsError {}

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
            blend_radius: None,
            blend_strength: None,
        };
        let s = serde_json::to_string(&def).unwrap();
        let back: TerrainKindDef = serde_json::from_str(&s).unwrap();
        assert_eq!(def, back);
    }

    // TMP-Q3 chunk C — round-trip + skip-serializing tests for the
    // optional per-kind shader hints.
    #[test]
    fn terrain_kind_def_deserializes_without_blend_fields() {
        // Pre-Q3 wire shape: no blend_radius / blend_strength → both
        // default to None.
        let toml_text = r#"
id = "lw:grass"
primitive = "land"
label = "Grass"
"#;
        let def: TerrainKindDef = toml::from_str(toml_text).unwrap();
        assert!(def.blend_radius.is_none(),
            "missing blend_radius must serde-default to None");
        assert!(def.blend_strength.is_none(),
            "missing blend_strength must serde-default to None");
    }

    #[test]
    fn terrain_kind_def_round_trips_with_blend_hints() {
        let def = TerrainKindDef {
            id: "lw:water".to_string(),
            primitive: TerrainPrimitive::Water,
            label: "Water".to_string(),
            properties: json!({}),
            blend_radius: Some(0.95),
            blend_strength: Some(0.45),
        };
        let s = serde_json::to_string(&def).unwrap();
        assert!(s.contains("blend_radius"),
            "Some(_) blend_radius must be serialized: {s}");
        assert!(s.contains("0.95"));
        let back: TerrainKindDef = serde_json::from_str(&s).unwrap();
        assert_eq!(def, back);
    }

    #[test]
    fn terrain_kind_def_skip_serializing_when_blend_none() {
        // Wire-shape invariant: None values must be ABSENT from JSON.
        // Locks the V2 byte-identical contract — pre-Q3 consumers
        // continue to see the same wire shape against default templates.
        let def = TerrainKindDef {
            id: "lw:grass".to_string(),
            primitive: TerrainPrimitive::Land,
            label: "Grass".to_string(),
            properties: json!({}),
            blend_radius: None,
            blend_strength: None,
        };
        let s = serde_json::to_string(&def).unwrap();
        assert!(!s.contains("blend_radius"),
            "None blend_radius must NOT appear in JSON (skip_serializing_if discipline): {s}");
        assert!(!s.contains("blend_strength"),
            "None blend_strength must NOT appear in JSON: {s}");
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

    #[test]
    fn registry_ref_round_trips_with_value_band_thresholds() {
        // TMP-Q4 AC-VBT-7 — a per-book registry that declares custom
        // value-band thresholds round-trips through JSON.
        let r = RegistryRef::new("xianxia", "1.0.0")
            .with_value_band_thresholds([1_000, 5_000, 15_000, 50_000])
            .expect("ascending thresholds must build");
        let s = serde_json::to_string(&r).unwrap();
        assert!(s.contains("\"value_band_thresholds\":[1000,5000,15000,50000]"),
            "thresholds must appear on wire: {s}");
        let back: RegistryRef = serde_json::from_str(&s).unwrap();
        assert_eq!(back.value_band_thresholds, Some([1_000, 5_000, 15_000, 50_000]));
    }

    #[test]
    fn registry_ref_builder_rejects_non_ascending_thresholds() {
        // TMP-Q4 MED-2 — the builder is just as strict as
        // `Registry::from_file`. Invalid arrays return Err instead of
        // silently shipping bad bands to the frontend.
        for (label, bad) in [
            ("equal pair", [500, 500, 5_000, 12_000]),
            ("descending mid", [500, 2_000, 1_500, 12_000]),
            ("descending tail", [500, 2_000, 5_000, 4_000]),
        ] {
            let err = RegistryRef::new("bad", "1.0.0")
                .with_value_band_thresholds(bad)
                .expect_err(&format!("[{label}] {bad:?} must reject"));
            assert!(
                err.to_string().contains("ascending"),
                "[{label}] error message must mention 'ascending'; got {err}",
            );
        }
    }

    #[test]
    fn registry_ref_skip_serializes_thresholds_when_none() {
        // TMP-Q4 AC-VBT-1 — a registry without thresholds preserves V2
        // byte-identical wire (no spurious `"value_band_thresholds":null`).
        let r = RegistryRef::new("lw", "1.0.0");
        let s = serde_json::to_string(&r).unwrap();
        assert!(!s.contains("value_band_thresholds"),
            "None must be skipped: {s}");
    }

    #[test]
    fn registry_ref_deserializes_pre_q4_fixture_without_thresholds() {
        // TMP-Q4 LOW-2 — pre-Q4 wire JSON without `value_band_thresholds`
        // round-trips via `#[serde(default)]` to None.
        let json = r#"{"id":"lw","version":"1.0.0"}"#;
        let r: RegistryRef = serde_json::from_str(json).unwrap();
        assert_eq!(r.value_band_thresholds, None);
    }
}
