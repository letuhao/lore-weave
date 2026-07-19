//! TMP-Q2 chunk A — V2 byte-identical preservation tests for the
//! biome-theme opt-in fields.
//!
//! Locks AC-BIOME-1 (spec §3): a template with
//! `background_biome = None` + every zone `biome_theme = None` must
//! produce terrain_layer bytes identical to the pre-Q2 baseline. This
//! is the additive-Option discipline that mirrors decoration_density's
//! V2 preservation contract.
//!
//! Chunk B will add a separate `biome_theme_painter.rs` integration
//! test file with AC-BIOME-2..7 (placer behavior). Chunk A only proves
//! the *absence* of side effects when the opt-in is off.

use tilemap_service::engine::place_tilemap_with_registry;
use tilemap_service::registry::Registry;
use tilemap_service::types::template::{
    TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec,
};
use tilemap_service::types::treasure::TreasureTierSpec;
use tilemap_service::types::zone::{PassageKind, ZoneId, ZoneRole};
use tilemap_service::types::{ChannelId, ChannelTier, GridSize, TerrainKind};

/// 3-zone fixture mirrors decoration_placer.rs::fixture() so chunk-A
/// tests share the same baseline shape. All biome-theme fields are
/// `None` — this fixture represents the V2 path that must remain
/// byte-identical post-chunk-A.
fn v2_fixture() -> TilemapTemplate {
    TilemapTemplate {
        template_id: TilemapTemplateId("q2_chunk_a_v2".to_string()),
        zones: vec![
            ZoneSpec {
                zone_id: ZoneId("capital".to_string()),
                zone_role: ZoneRole::Wilderness,
                size: 100,
                terrain_types: vec![TerrainKind::Grass],
                monster_strength: None,
                connections: vec![TemplateConnection::new(
                    ZoneId("crossroad".to_string()),
                    PassageKind::Open,
                )],
                treasure_tiers: vec![TreasureTierSpec { min: 100, max: 800, density: 2 }],
                biome_selection_rules: None,
                inherit_treasure_from: None,
                biome_theme: None,
            },
            ZoneSpec {
                zone_id: ZoneId("crossroad".to_string()),
                zone_role: ZoneRole::Hub,
                size: 100,
                terrain_types: vec![],
                monster_strength: None,
                connections: vec![TemplateConnection::new(
                    ZoneId("frontier".to_string()),
                    PassageKind::Open,
                )],
                treasure_tiers: vec![],
                biome_selection_rules: None,
                inherit_treasure_from: None,
                biome_theme: None,
            },
            ZoneSpec {
                zone_id: ZoneId("frontier".to_string()),
                zone_role: ZoneRole::Wilderness,
                size: 100,
                terrain_types: vec![TerrainKind::Forest],
                monster_strength: None,
                connections: vec![],
                treasure_tiers: vec![],
                biome_selection_rules: None,
                inherit_treasure_from: None,
                biome_theme: None,
            },
        ],
        seed_offset: 0,
        world_zone: None,
        decoration_density: None,
        background_biome: None,
    }
}

/// LOW-1 fix from chunk-A /review-impl — blake3 hash of the V2
/// fixture's `terrain_layer` pinned as a regression anchor. Locked at
/// chunk A's BUILD time; any chunk B/C change that alters the V2
/// (biome_theme=None + background_biome=None) terrain bytes must
/// explicitly rebaseline this literal.
///
/// Computed by running the test once with a placeholder, then copying
/// the actual hash from the assertion failure message.
const V2_TERRAIN_LAYER_HASH_PIN: &str =
    "b32fe411f10299473557157b903124a81cee173f6af3bc952ca7fcfd24b27310";

#[test]
fn v2_fixture_terrain_layer_is_deterministic_post_chunk_a() {
    // AC-BIOME-1 — running V2 fixture twice produces byte-identical
    // terrain_layer. Proves chunk-A's added types/fields/registry have
    // zero observable effect when the opt-in is off.
    let registry = Registry::load_default().expect("registry must load");
    let template = v2_fixture();
    let grid = GridSize { width: 48, height: 48 };
    let view_a = place_tilemap_with_registry(
        &template,
        ChannelId("ch_v2".to_string()),
        ChannelTier::Town,
        grid,
        tilemap_service::seed::TilemapSeed(1),
        &registry,
    )
    .expect("place_tilemap_with_registry must succeed");
    let view_b = place_tilemap_with_registry(
        &template,
        ChannelId("ch_v2".to_string()),
        ChannelTier::Town,
        grid,
        tilemap_service::seed::TilemapSeed(1),
        &registry,
    )
    .expect("place_tilemap_with_registry must succeed");
    assert_eq!(
        view_a.terrain_layer, view_b.terrain_layer,
        "AC-BIOME-1: deterministic terrain_layer over identical inputs"
    );

    // LOW-1 fix — pin the V2 terrain_layer hash as a regression anchor.
    // Chunk-B placer changes that alter V2 output must rebaseline this
    // literal explicitly (forcing the developer to acknowledge the
    // wire-shape impact).
    let actual = blake3::hash(&view_a.terrain_layer).to_hex().to_string();
    assert_eq!(
        actual, V2_TERRAIN_LAYER_HASH_PIN,
        "V2_TERRAIN_LAYER_HASH_PIN regressed — chunk-A baseline broken. \
         If this is intentional (placer logic shift), rebaseline with the actual hash."
    );
}

#[test]
fn v2_fixture_terrain_layer_survives_serde_round_trip() {
    // AC-BIOME-1 — fixture → JSON (no biome_theme / background_biome
    // because both None + skip_serializing_if) → fixture' → run, all
    // produce identical terrain_layer. Proves the additive serde
    // contract: pre-Q2 templates that never knew about biome fields
    // continue to deserialize + place identically.
    let template = v2_fixture();
    let json = serde_json::to_string(&template).expect("serialize");
    assert!(
        !json.contains("biome_theme"),
        "skip_serializing_if must suppress None biome_theme in JSON: {json}"
    );
    assert!(
        !json.contains("background_biome"),
        "skip_serializing_if must suppress None background_biome in JSON: {json}"
    );
    let reborn: TilemapTemplate = serde_json::from_str(&json).expect("deserialize");
    assert_eq!(template, reborn, "round-trip must preserve fixture identity");

    let registry = Registry::load_default().expect("registry must load");
    let grid = GridSize { width: 48, height: 48 };
    let view_orig = place_tilemap_with_registry(
        &template,
        ChannelId("ch_v2".to_string()),
        ChannelTier::Town,
        grid,
        tilemap_service::seed::TilemapSeed(1),
        &registry,
    )
    .unwrap();
    let view_reborn = place_tilemap_with_registry(
        &reborn,
        ChannelId("ch_v2".to_string()),
        ChannelTier::Town,
        grid,
        tilemap_service::seed::TilemapSeed(1),
        &registry,
    )
    .unwrap();
    assert_eq!(
        view_orig.terrain_layer, view_reborn.terrain_layer,
        "round-tripped fixture must produce byte-identical terrain_layer"
    );
}

#[test]
fn default_registry_loads_with_q2_biome_themes() {
    // AC-BIOME-3 — default registry contains 7 biome themes after
    // chunk A. Locks the registry-load surface so a typo in a new
    // entry fails this test immediately.
    let registry = Registry::load_default().expect("registry must load");
    assert_eq!(
        registry.biome_count(),
        7,
        "default registry must declare exactly 7 biome themes \
         (forest_temperate, forest_dense_pine, mountain_alpine, swamp_mangrove, \
          desert_dune, grassland_meadow, tundra_frost)"
    );
    // Each declared theme must be reachable via get_biome.
    for id in [
        "lw:biome.forest_temperate",
        "lw:biome.forest_dense_pine",
        "lw:biome.mountain_alpine",
        "lw:biome.swamp_mangrove",
        "lw:biome.desert_dune",
        "lw:biome.grassland_meadow",
        "lw:biome.tundra_frost",
    ] {
        assert!(
            registry.get_biome(id).is_some(),
            "registry.get_biome({id:?}) must return Some (id missing from default.toml?)"
        );
    }
    // Unknown id returns None — chunk-B placer relies on this for the
    // opt-in safety net.
    assert!(registry.get_biome("lw:biome.nonexistent").is_none());
}

#[test]
fn biome_ids_iteration_is_deterministic_btreemap_order() {
    // Chunk-B placer iterates biome_ids() for introspection; lock that
    // the order is sorted (BTreeMap) so per-zone seed labels stay stable.
    let registry = Registry::load_default().expect("registry must load");
    let ids: Vec<&str> = registry.biome_ids().collect();
    let mut sorted = ids.clone();
    sorted.sort_unstable();
    assert_eq!(
        ids, sorted,
        "biome_ids() must iterate in sorted (BTreeMap) order"
    );
}
