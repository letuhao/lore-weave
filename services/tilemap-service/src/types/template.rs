//! `TilemapTemplate` aggregate — author-declared template document.
//! Mirrors [TMP_001 §2 + §3.2](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md)
//! plus [TMP_004](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_004_template_authoring.md)
//! authoring detail. Phase 0a captures only the shape needed for the
//! `tilemap_view` reference fields; full author-editor schema lands in Phase 4+.

use serde::{Deserialize, Serialize};

use crate::types::biome::BiomeSelectionRules;
use crate::types::tile::TerrainKind;
use crate::types::treasure::TreasureTierSpec;
use crate::types::zone::{PassageKind, RoadOption, ZoneId, ZoneRole};
use crate::world_inherit::WorldZoneSnapshot;

/// Stable per-reality template identifier (e.g. `"wuxia_southern_song_v1"`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct TilemapTemplateId(pub String);

/// Author-declared zone specification. Phase 0a captures the structural minimum;
/// TMP_004 has the full schema (size, treasure tiers, mines, town hints, etc.).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ZoneSpec {
    pub zone_id: ZoneId,
    pub zone_role: ZoneRole,
    /// Relative size weight (TMP_002 §2.1). The zone placer scales a zone's
    /// force-directed soft-sphere radius by `sqrt(size)`. Author-tunable;
    /// defaults to a neutral mid weight so a template that omits it still
    /// places sanely (all zones equal-size).
    #[serde(default = "default_zone_size")]
    pub size: u32,
    /// Allowed terrain types in this zone (post-TerrainPainter).
    #[serde(default)]
    pub terrain_types: Vec<TerrainKind>,
    /// Author monster-strength tag (V1+30d freeform; closed enum at Phase 4+).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub monster_strength: Option<String>,
    /// Author connections (full graph at template level; runtime placement
    /// converts to `ZoneEdge` records on `tilemap_view`).
    #[serde(default)]
    pub connections: Vec<TemplateConnection>,
    /// Author treasure-tier spec (TMP_006 §2) — consumed by TreasurePlacer
    /// (Phase C). Empty = no treasure declared for this zone. Additive (TMP-A8).
    #[serde(default)]
    pub treasure_tiers: Vec<TreasureTierSpec>,
    /// Author biome-selection-rule override (TMP_005 §2.2) — consumed by
    /// ObstaclePlacer (Phase B). `None` ⇒ engine defaults. Additive (TMP-A8).
    #[serde(default)]
    pub biome_selection_rules: Option<BiomeSelectionRules>,
    /// Author treasure inheritance (TMP_006 §3.2 / TMP-TR-Q3 — Phase C D9).
    /// When `Some(z)`, this zone's *effective* treasure tiers are zone `z`'s
    /// literal `treasure_tiers` and its own `treasure_tiers` is ignored —
    /// resolution is one level, non-transitive (so an inheritance cycle is
    /// structurally impossible). A reference to a zone absent from the template
    /// yields no treasure (a deterministic author error, never a panic). `None`
    /// ⇒ this zone uses its own `treasure_tiers`. Additive (TMP-A8).
    #[serde(default)]
    pub inherit_treasure_from: Option<ZoneId>,
}

/// Default `ZoneSpec.size` — a neutral mid weight (all zones equal when the
/// author does not differentiate).
fn default_zone_size() -> u32 {
    100
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TemplateConnection {
    pub to_zone: ZoneId,
    pub kind: PassageKind,
    /// Monster-guard strength for this connection (TMP_007 §1). Default 0 — a
    /// connection with 0 strength gets an unguarded passage. Additive (TMP-A8).
    #[serde(default)]
    pub guard_strength: u32,
    /// Whether the connection materializes a road (TMP_007 §2.2). Default
    /// `RoadOption::True`. Additive (TMP-A8).
    #[serde(default)]
    pub road: RoadOption,
}

impl TemplateConnection {
    /// A connection with the default guard strength (0) and road option
    /// (`True`) — the common author case before per-edge tuning.
    pub fn new(to_zone: ZoneId, kind: PassageKind) -> Self {
        Self { to_zone, kind, guard_strength: 0, road: RoadOption::default() }
    }
}

/// V2/Reality aggregate. Phase 0a is structural minimum.
///
/// **Note on `Eq`:** dropped from the derive when `world_zone` was added, because
/// `WorldZoneSnapshot` embeds `f32` fields (temp/precip/elevation/site/boundary)
/// which only impl `PartialEq`. No call site uses `TilemapTemplate` as a HashMap
/// key or with an `Eq` bound — only `assert_eq!` (PartialEq is enough). If
/// strict equality ever matters, hash the serialized form.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TilemapTemplate {
    pub template_id: TilemapTemplateId,
    pub zones: Vec<ZoneSpec>,
    /// Author seed offset — combined with channel_id into the final blake3 seed
    /// (per TMP-A4). Default 0; non-zero forces a different deterministic seed
    /// for the same template applied to the same channel.
    #[serde(default)]
    pub seed_offset: u64,
    /// Optional upstream world zone snapshot — present when this template opts
    /// in to world-inheritance constraints (spec
    /// `docs/specs/2026-05-24-tilemap-world-inheritance-contract.md`). `None`
    /// preserves the pre-Chunk-3 standalone path (existing 332-test baseline).
    /// Additive — fields default to None and skip-serializing when absent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub world_zone: Option<WorldZoneSnapshot>,
    /// Optional V3 quality-push opt-in for the decoration-density pass
    /// (spec `docs/specs/2026-05-28-decoration-placer-density-pass.md`).
    /// `None` (the implicit serde default) keeps every V2 golden test
    /// byte-identical; `DecorationPlacer` early-returns. `Some(_)`
    /// activates the chunk-C density logic. Additive Option pattern
    /// matches `world_zone` discipline above.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decoration_density: Option<crate::types::decoration::DecorationDensity>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn template_connection_deserializes_without_the_new_fields() {
        // TMP-A8 — a pre-extension connection JSON (no guard_strength / road)
        // still loads, with the additive defaults applied.
        let json = r#"{"to_zone":"sea_north","kind":"threshold"}"#;
        let c: TemplateConnection = serde_json::from_str(json).unwrap();
        assert_eq!(c.guard_strength, 0);
        assert_eq!(c.road, RoadOption::True);
        assert_eq!(c.to_zone, ZoneId("sea_north".to_string()));
    }

    #[test]
    fn template_connection_round_trips_with_the_new_fields() {
        // TMP-A8 — explicit non-default values survive a JSON round-trip.
        let c = TemplateConnection {
            to_zone: ZoneId("z2".to_string()),
            kind: PassageKind::Portal,
            guard_strength: 4200,
            road: RoadOption::False,
        };
        let back: TemplateConnection =
            serde_json::from_str(&serde_json::to_string(&c).unwrap()).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn zone_spec_deserializes_without_treasure_tiers() {
        // TMP-A8 — a pre-extension ZoneSpec JSON still loads; treasure_tiers
        // defaults to empty and the older defaults still apply.
        let json = r#"{"zone_id":"capital","zone_role":"wilderness"}"#;
        let z: ZoneSpec = serde_json::from_str(json).unwrap();
        assert!(z.treasure_tiers.is_empty());
        assert_eq!(z.size, 100, "size still falls back to default_zone_size");
        assert!(z.connections.is_empty());
    }

    #[test]
    fn tilemap_template_deserializes_without_decoration_density() {
        // TMP-Q1 chunk A — MED-1 fix from /review-impl. A pre-chunk-A
        // template JSON (no decoration_density field) still loads with
        // decoration_density = None — the load-bearing invariant for V2
        // wire-format byte-identical preservation. Mirrors the
        // template_connection_deserializes_without_the_new_fields +
        // zone_spec_deserializes_without_treasure_tiers patterns.
        let json = r#"{"template_id":"t","zones":[],"seed_offset":0}"#;
        let t: TilemapTemplate = serde_json::from_str(json).unwrap();
        assert!(t.decoration_density.is_none(),
            "missing field must serde-default to None, not Some(_) or error");
        assert!(t.world_zone.is_none(), "world_zone unchanged");
        assert_eq!(t.seed_offset, 0);
    }

    #[test]
    fn tilemap_template_round_trips_with_decoration_density_some() {
        // TMP-Q1 chunk A — LOW-2 fix from /review-impl. A TilemapTemplate
        // with decoration_density: Some(TOWN) survives a JSON round-trip
        // and is Eq to the original. Mirrors zone_spec_round_trips_with_*
        // round-trip discipline.
        use crate::types::decoration::DecorationDensity;
        let t = TilemapTemplate {
            template_id: TilemapTemplateId("rt".to_string()),
            zones: vec![],
            seed_offset: 7,
            world_zone: None,
            decoration_density: Some(DecorationDensity::TOWN),
        };
        let json = serde_json::to_string(&t).unwrap();
        assert!(json.contains("decoration_density"),
            "Some(_) must be serialized (only None is skipped)");
        let back: TilemapTemplate = serde_json::from_str(&json).unwrap();
        assert_eq!(t, back);
    }

    #[test]
    fn tilemap_template_with_decoration_density_none_omits_field_from_json() {
        // TMP-Q1 chunk A — wire-format invariant: skip_serializing_if =
        // "Option::is_none" means None fields are absent from JSON. This
        // is what keeps V2 HTTP API consumers byte-identical against
        // default templates.
        let t = TilemapTemplate {
            template_id: TilemapTemplateId("rt".to_string()),
            zones: vec![],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
        };
        let json = serde_json::to_string(&t).unwrap();
        assert!(!json.contains("decoration_density"),
            "None must NOT appear in JSON (skip_serializing_if discipline)");
        assert!(!json.contains("world_zone"),
            "world_zone None also skipped (pattern consistency check)");
    }

    #[test]
    fn zone_spec_round_trips_with_treasure_tiers() {
        // TMP-A8 — declared tiers survive a round-trip.
        let z = ZoneSpec {
            zone_id: ZoneId("vault".to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 250,
            terrain_types: vec![],
            monster_strength: None,
            connections: vec![TemplateConnection::new(ZoneId("a".to_string()), PassageKind::Open)],
            treasure_tiers: vec![
                TreasureTierSpec { min: 100, max: 800, density: 4 },
                TreasureTierSpec { min: 8000, max: 12000, density: 3 },
            ],
            biome_selection_rules: None,
            inherit_treasure_from: None,
        };
        let back: ZoneSpec = serde_json::from_str(&serde_json::to_string(&z).unwrap()).unwrap();
        assert_eq!(z, back);
    }

    #[test]
    fn zone_spec_deserializes_without_biome_selection_rules() {
        // TMP-A8 — a pre-Phase-B ZoneSpec JSON still loads; biome_selection_rules
        // defaults to None.
        let json = r#"{"zone_id":"capital","zone_role":"wilderness"}"#;
        let z: ZoneSpec = serde_json::from_str(json).unwrap();
        assert!(z.biome_selection_rules.is_none());
    }

    #[test]
    fn zone_spec_round_trips_with_biome_selection_rules() {
        // TMP-A8 — a ZoneSpec carrying an author biome-selection override (D8)
        // survives a JSON round-trip, including one rule with `xor_with: Some`
        // and one with `xor_with: None` (the field's skip_serializing_if).
        use crate::types::biome::{BiomeObjectType, BiomePriority, BiomeSelectionRule};
        let z = ZoneSpec {
            zone_id: ZoneId("vault".to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 120,
            terrain_types: vec![TerrainKind::Grass],
            monster_strength: None,
            connections: vec![],
            treasure_tiers: vec![],
            biome_selection_rules: Some(BiomeSelectionRules {
                use_engine_default: false,
                rules: vec![
                    BiomeSelectionRule {
                        object_type: BiomeObjectType::Lake,
                        count_min: 0,
                        count_max: 1,
                        xor_with: Some(BiomeObjectType::Crater),
                        priority: BiomePriority::First,
                    },
                    BiomeSelectionRule {
                        object_type: BiomeObjectType::Tree,
                        count_min: 1,
                        count_max: 2,
                        xor_with: None,
                        priority: BiomePriority::Normal,
                    },
                ],
            }),
            inherit_treasure_from: None,
        };
        let back: ZoneSpec = serde_json::from_str(&serde_json::to_string(&z).unwrap()).unwrap();
        assert_eq!(z, back);
    }

    #[test]
    fn zone_spec_deserializes_without_inherit_treasure_from() {
        // AC-11 — a pre-Phase-C ZoneSpec JSON still loads; inherit_treasure_from
        // defaults to None.
        let json = r#"{"zone_id":"capital","zone_role":"wilderness"}"#;
        let z: ZoneSpec = serde_json::from_str(json).unwrap();
        assert!(z.inherit_treasure_from.is_none());
    }

    #[test]
    fn ac_wi_5_template_without_world_zone_deserializes_and_field_is_none() {
        // World-inheritance opt-in is additive: existing template JSON that
        // predates `world_zone` still loads, and the field defaults to None.
        let json = r#"{
            "template_id": "phase1_determinism",
            "zones": [
                {"zone_id": "capital", "zone_role": "wilderness"}
            ]
        }"#;
        let t: TilemapTemplate = serde_json::from_str(json).unwrap();
        assert!(t.world_zone.is_none(), "pre-extension template must default to None");
        assert_eq!(t.zones.len(), 1);
    }

    #[test]
    fn ac_wi_5_template_with_world_zone_round_trips() {
        // A template carrying a populated WorldZoneSnapshot survives a JSON
        // round-trip including nested climate + boundary polygon.
        use crate::world_inherit::{RegionPath, WorldBiome, WorldZoneSnapshot, ZoneClimate};
        let t = TilemapTemplate {
            template_id: TilemapTemplateId("inherit_demo".to_string()),
            zones: vec![],
            seed_offset: 0,
            world_zone: Some(WorldZoneSnapshot {
                path: RegionPath::new(vec![3, 1]),
                site: [735.0, 450.0],
                base_elevation: 0.37,
                boundary: vec![
                    [510.0, 400.0],
                    [960.0, 400.0],
                    [960.0, 500.0],
                    [510.0, 500.0],
                ],
                climate: ZoneClimate {
                    temp_mean: 28.6,
                    precip_annual: 75.0,
                    biome_tag: 5,
                    biome_name: WorldBiome::HotDesert,
                },
            }),
            decoration_density: None,
        };
        let s = serde_json::to_string(&t).unwrap();
        let back: TilemapTemplate = serde_json::from_str(&s).unwrap();
        assert_eq!(back.world_zone, t.world_zone);
        // Belt-and-braces: the serialized form must include the field name.
        assert!(s.contains("world_zone"), "world_zone must appear in JSON: {s}");
        assert!(s.contains("hot_desert"), "snake_case biome name must serialize");
    }

    #[test]
    fn template_with_world_zone_none_does_not_emit_null_field() {
        // The skip_serializing_if = Option::is_none attribute keeps the
        // additive field invisible when absent, so existing fixtures are
        // byte-identical post-Chunk-3.
        let t = TilemapTemplate {
            template_id: TilemapTemplateId("p".to_string()),
            zones: vec![],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
        };
        let s = serde_json::to_string(&t).unwrap();
        assert!(!s.contains("world_zone"), "absent world_zone must not appear in JSON: {s}");
        assert!(!s.contains("null"), "absent world_zone must not serialize as null: {s}");
    }

    #[test]
    fn zone_spec_round_trips_with_inherit_treasure_from() {
        // AC-11 — a ZoneSpec that inherits another zone's treasure tiers (D9)
        // survives a JSON round-trip.
        let z = ZoneSpec {
            zone_id: ZoneId("vault".to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: vec![],
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: Some(ZoneId("treasury".to_string())),
        };
        let back: ZoneSpec = serde_json::from_str(&serde_json::to_string(&z).unwrap()).unwrap();
        assert_eq!(z, back);
        assert_eq!(back.inherit_treasure_from, Some(ZoneId("treasury".to_string())));
    }
}
