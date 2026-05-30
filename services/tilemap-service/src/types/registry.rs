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

/// TMP-Q5 — per-book role color override. Each role independently
/// optional so authors can override only the colors they care about
/// (e.g., declare gold-themed Wilderness only; Hub/Forbidden/Sea
/// fall back to the frontend's `ZONE_ROLE_DEFAULTS`).
///
/// Wire shape: each declared field rides as a u32 (24-bit RGB; alpha
/// bits ignored at render). Each field omitted from TOML = `None` on
/// wire, skipped via `skip_serializing_if`. An all-`None` struct still
/// emits `{}` if wrapped in `Some(_)` on `RegistryRef.zone_role_colors`
/// — authors who want NO override should leave the outer `Option`
/// unset (default behavior).
///
/// V2 forward-compat: adding `AllyHome`/`RivalHome` later widens this
/// struct additively; pre-Q5 TOML continues to load (new fields
/// default to None).
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct ZoneRoleColors {
    /// Override color (24-bit RGB packed in u32) for `ZoneRole::Wilderness`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wilderness: Option<u32>,
    /// Override color for `ZoneRole::Hub`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hub: Option<u32>,
    /// Override color for `ZoneRole::Forbidden`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub forbidden: Option<u32>,
    /// Override color for `ZoneRole::Sea`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sea: Option<u32>,
}

impl ZoneRoleColors {
    /// Returns `true` iff EVERY field is `None`. Useful for callers
    /// that want to materially distinguish "no override declared"
    /// from "Some(empty struct)" — the wire treats the second as `{}`,
    /// not "no override" (LOW-1 from chunk-A self-review).
    pub fn is_empty(&self) -> bool {
        self.wilderness.is_none()
            && self.hub.is_none()
            && self.forbidden.is_none()
            && self.sea.is_none()
    }
}

/// Registry identifier + version, embedded in TilemapView responses so
/// frontends can detect mismatched registry assumptions.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RegistryRef {
    /// Registry identifier (e.g. `"lw"`, `"xianxia-demo"`).
    pub id: String,
    /// Semver-ish version. Bumped on schema-breaking changes.
    pub version: String,
    /// TMP-Q5 — per-book role color override. `None` (default) lets
    /// the frontend use `ZONE_ROLE_DEFAULTS` for every role.
    /// `Some(ZoneRoleColors)` overrides one or more roles; omitted
    /// fields still fall back to defaults at render time.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub zone_role_colors: Option<ZoneRoleColors>,
}

impl RegistryRef {
    pub fn new(id: impl Into<String>, version: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            version: version.into(),
            zone_role_colors: None,
        }
    }

    /// TMP-Q5 builder for tests + per-book registries that set
    /// role color overrides. Returns `Result` per
    /// `feedback_builder_validation_parity` (chunk-A TMP-Q4
    /// precedent) so future validation constraints (alpha-bit reserved,
    /// contrast-vs-foundation) can land without an API break, even
    /// though V1 validation is a no-op.
    ///
    /// **Semantic: REPLACE, not merge (LOW-4 from chunk-A /review-impl).**
    /// Calling this builder a second time discards any earlier
    /// override entirely:
    ///   `ref.with_zone_role_colors({wilderness: red})
    ///       .with_zone_role_colors({hub: blue})`
    /// produces `ZoneRoleColors { wilderness: None, hub: Some(blue), .. }`
    /// — Wilderness=red is dropped. If you want to merge sparse
    /// overrides across calls, build the merged struct yourself and
    /// call the builder once.
    pub fn with_zone_role_colors(
        mut self,
        colors: ZoneRoleColors,
    ) -> Result<Self, ZoneRoleColorsError> {
        // V1: u32 is intrinsically valid (TOML parses to native u32).
        // Future constraints land here. The Result-returning shape is
        // intentional even with no-op validation — see
        // feedback_builder_validation_parity.
        self.zone_role_colors = Some(colors);
        Ok(self)
    }
}

/// TMP-Q5 — surfaced when a builder caller passes a malformed
/// `ZoneRoleColors`. V1 has no constraint; the type exists so future
/// validation constraints land without an API break.
///
/// **`detail` field is currently unused (LOW-6 from chunk-A
/// /review-impl)** — reserved for chunk-C / future validation hooks
/// that surface a specific constraint violation (alpha-bit reserved,
/// contrast-vs-foundation, etc.). V1 never constructs an instance,
/// but the field stays so the future constructor signature lands
/// without an API break.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ZoneRoleColorsError {
    pub detail: String,
}

impl std::fmt::Display for ZoneRoleColorsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "invalid zone_role_colors: {}", self.detail)
    }
}

impl std::error::Error for ZoneRoleColorsError {}

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
    fn zone_role_colors_default_is_all_none() {
        // TMP-Q5 AC-ZRV-2 — Default impl gives all-None struct so
        // partial declarations only need to set the fields they care
        // about (sparse overrides).
        let c = ZoneRoleColors::default();
        assert!(c.wilderness.is_none());
        assert!(c.hub.is_none());
        assert!(c.forbidden.is_none());
        assert!(c.sea.is_none());
        assert!(c.is_empty());
    }

    #[test]
    fn zone_role_colors_is_empty_helper() {
        // is_empty distinguishes "all-None inner" from "any field set".
        let empty = ZoneRoleColors::default();
        assert!(empty.is_empty());
        let with_one = ZoneRoleColors { wilderness: Some(0x4ade80), ..Default::default() };
        assert!(!with_one.is_empty());
    }

    #[test]
    fn zone_role_colors_round_trips_with_all_fields() {
        // TMP-Q5 AC-ZRV-1 — full override round-trips through JSON.
        let c = ZoneRoleColors {
            wilderness: Some(0x4ade80),
            hub: Some(0x818cf8),
            forbidden: Some(0xf87171),
            sea: Some(0x60a5fa),
        };
        let s = serde_json::to_string(&c).unwrap();
        // All 4 fields appear on wire (decimal repr of the hex values).
        assert!(s.contains("\"wilderness\":4906624"), "wire: {s}");
        assert!(s.contains("\"hub\":8490232"), "wire: {s}");
        assert!(s.contains("\"forbidden\":16281969"), "wire: {s}");
        assert!(s.contains("\"sea\":6333946"), "wire: {s}");
        let back: ZoneRoleColors = serde_json::from_str(&s).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn zone_role_colors_round_trips_sparse() {
        // TMP-Q5 AC-ZRV-2 — only one role declared; the others stay
        // off-wire so per-book authors can override only what they
        // care about.
        let c = ZoneRoleColors {
            wilderness: Some(0xffff00),
            ..Default::default()
        };
        let s = serde_json::to_string(&c).unwrap();
        assert!(s.contains("wilderness"), "wire: {s}");
        assert!(!s.contains("hub"), "hub must be skipped: {s}");
        assert!(!s.contains("forbidden"), "forbidden must be skipped: {s}");
        assert!(!s.contains("sea"), "sea must be skipped: {s}");
        let back: ZoneRoleColors = serde_json::from_str(&s).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn registry_ref_round_trips_with_zone_role_colors() {
        // TMP-Q5 AC-ZRV-1 — RegistryRef carries the override through
        // a JSON round-trip.
        let r = RegistryRef::new("xianxia", "1.0.0")
            .with_zone_role_colors(ZoneRoleColors {
                wilderness: Some(0xfacc15),
                ..Default::default()
            })
            .expect("V1 builder must accept all u32 values");
        let s = serde_json::to_string(&r).unwrap();
        assert!(s.contains("zone_role_colors"), "wire: {s}");
        assert!(s.contains("wilderness"), "wire: {s}");
        let back: RegistryRef = serde_json::from_str(&s).unwrap();
        assert_eq!(back.zone_role_colors, r.zone_role_colors);
    }

    #[test]
    fn registry_ref_skip_serializes_when_zone_role_colors_none() {
        // TMP-Q5 AC-ZRV-1 — V2 byte-identical preservation: a registry
        // that doesn't declare an override produces no key on wire.
        let r = RegistryRef::new("lw", "1.0.0");
        assert!(r.zone_role_colors.is_none());
        let s = serde_json::to_string(&r).unwrap();
        assert!(
            !s.contains("zone_role_colors"),
            "None outer must be skipped from wire: {s}",
        );
    }

    #[test]
    fn registry_ref_deserializes_pre_q5_fixture_without_zone_role_colors() {
        // TMP-Q5 backward compat: pre-Q5 wire JSON (no zone_role_colors
        // key) round-trips via `#[serde(default)]` to None.
        let json = r#"{"id":"lw","version":"1.0.0"}"#;
        let r: RegistryRef = serde_json::from_str(json).unwrap();
        assert_eq!(r.zone_role_colors, None);
    }

    #[test]
    fn registry_ref_builder_with_zone_role_colors_succeeds() {
        // TMP-Q5 AC-ZRV-3 — builder parity (feedback_builder_validation_parity):
        // Result-returning even with V1 no-op validation so future
        // constraints land without an API break.
        let result = RegistryRef::new("lw", "1.0.0")
            .with_zone_role_colors(ZoneRoleColors::default());
        assert!(result.is_ok(), "V1 builder must accept default (all-None) override");
        let r = result.unwrap();
        assert!(r.zone_role_colors.is_some()); // wrapped Some(empty)
        assert!(r.zone_role_colors.as_ref().unwrap().is_empty());
    }

    #[test]
    fn registry_ref_builder_replaces_not_merges_on_second_call() {
        // TMP-Q5 LOW-4 from chunk-A /review-impl — the builder REPLACES
        // the entire override on each call. Sparse overrides are NOT
        // merged across calls. A future user who chains the builder
        // expecting merge semantics would silently lose the first
        // call's fields. This test pins the replace semantic so a
        // future API change to merge would fail loudly.
        let result = RegistryRef::new("lw", "1.0.0")
            .with_zone_role_colors(ZoneRoleColors {
                wilderness: Some(0xff0000),
                ..Default::default()
            })
            .expect("first call succeeds")
            .with_zone_role_colors(ZoneRoleColors {
                hub: Some(0x0000ff),
                ..Default::default()
            })
            .expect("second call succeeds");
        let colors = result.zone_role_colors.as_ref().expect("Some");
        assert_eq!(colors.hub, Some(0x0000ff), "second call's hub override stays");
        assert_eq!(
            colors.wilderness, None,
            "REPLACE semantic: first call's wilderness override is DROPPED \
             by the second call (not merged)",
        );
    }

    #[test]
    fn registry_ref_with_some_empty_zone_role_colors_emits_curly_braces() {
        // TMP-Q5 LOW-1 from chunk-A self-review — the outer
        // `skip_serializing_if = Option::is_none` only skips when the
        // outer Option is None. Wrapping an empty inner struct in Some
        // emits the literal `"zone_role_colors":{}` on wire (the empty
        // fields are skipped via their own skip_serializing_if; the
        // wrapper is not). Authors who want "no override" should leave
        // the outer Option as None. This test pins the documented quirk
        // so future cleanup (custom skip predicate) is intentional.
        let r = RegistryRef::new("lw", "1.0.0")
            .with_zone_role_colors(ZoneRoleColors::default())
            .unwrap();
        let s = serde_json::to_string(&r).unwrap();
        assert!(s.contains("\"zone_role_colors\":{}"), "expected {{}}: {s}");
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
