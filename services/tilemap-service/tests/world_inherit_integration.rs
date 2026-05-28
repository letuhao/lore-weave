//! Integration test for world-inheritance: load mock world-gen JSON →
//! build tilemap template carrying that zone's snapshot → run
//! `place_tilemap` end-to-end → confirm no paradox + no panic.
//!
//! Closes **AC-WI-6** of the PLAN (docs/plans/2026-05-24-tilemap-world-inherit-module.md).
//! Lives in `tests/` so it goes through the published library surface
//! (`tilemap_service::*`) — proves the contract from outside the crate.

use std::path::PathBuf;

use tilemap_service::engine::biome_select::library_for_template;
use tilemap_service::engine::place_tilemap;
use tilemap_service::seed::TilemapSeed;
use tilemap_service::types::template::{TilemapTemplate, TilemapTemplateId, ZoneSpec};
use tilemap_service::types::zone::{ZoneId, ZoneRole};
use tilemap_service::types::{ChannelId, ChannelTier, GridSize, TerrainKind};
use tilemap_service::world_inherit::{
    BiomeBridge, MockFileWorldSource, RegionPath, WorldBiome, WorldSource, WorldZoneSnapshot,
};

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("world-mock")
        .join(name)
}

fn template_for_world_zone(
    template_id: &str,
    terrain: TerrainKind,
    snapshot: WorldZoneSnapshot,
) -> TilemapTemplate {
    TilemapTemplate {
        template_id: TilemapTemplateId(template_id.to_string()),
        zones: vec![ZoneSpec {
            zone_id: ZoneId("only".to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![terrain],
            monster_strength: None,
            connections: vec![],
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
        }],
        seed_offset: 0,
        world_zone: Some(snapshot),
    }
}

#[test]
fn ac_wi_6_hot_desert_zone_yields_only_sand_or_rough_compatible_library() {
    // Load the diverse-biomes fixture, extract zone [3, 1] (HotDesert per
    // README), embed it in a template, and confirm the bridge-filtered
    // library for that template contains only world-compatible biomes.
    let src = MockFileWorldSource::new(fixture("diverse-biomes.json"));
    let snap = src
        .load_zone(&RegionPath::new(vec![3, 1]))
        .expect("zone [3, 1] should exist and be HotDesert");
    assert_eq!(snap.climate.biome_name, WorldBiome::HotDesert);

    let template = template_for_world_zone("ac_wi_6_hot_desert", TerrainKind::Sand, snap);
    let filtered = library_for_template(&template);
    assert!(!filtered.is_empty());
    for bs in &filtered {
        let id = &bs.biome_id.0;
        assert!(
            id.starts_with("sand_") || id.starts_with("rough_"),
            "filtered library leaked {id} into a HotDesert template"
        );
    }
}

#[test]
fn ac_wi_6_ice_zone_yields_only_snow_compatible_library() {
    // Same end-to-end load+filter check for the climate opposite (Ice).
    let src = MockFileWorldSource::new(fixture("diverse-biomes.json"));
    let snap = src
        .load_zone(&RegionPath::new(vec![0, 0]))
        .expect("zone [0, 0] should exist and be Ice");
    assert_eq!(snap.climate.biome_name, WorldBiome::Ice);

    let template = template_for_world_zone("ac_wi_6_ice", TerrainKind::Snow, snap);
    let filtered = library_for_template(&template);
    assert!(!filtered.is_empty());
    for bs in &filtered {
        assert!(
            bs.biome_id.0.starts_with("snow_"),
            "Ice template leaked {} (expected snow_* only per shipped bridge)",
            bs.biome_id.0
        );
    }
}

#[test]
fn ac_wi_6_tropical_rainforest_admits_forest_and_swamp() {
    // Mid-rainfall extreme — verifies the bridge admits two terrain
    // families (forest_* + swamp_*) for one Whittaker biome.
    let src = MockFileWorldSource::new(fixture("diverse-biomes.json"));
    let snap = src
        .load_zone(&RegionPath::new(vec![4, 1]))
        .expect("zone [4, 1] should exist and be TropicalRainforest");
    assert_eq!(snap.climate.biome_name, WorldBiome::TropicalRainforest);

    let template = template_for_world_zone("ac_wi_6_tropical", TerrainKind::Forest, snap);
    let filtered = library_for_template(&template);
    assert!(!filtered.is_empty());
    let bridge = BiomeBridge::default_static();
    for bs in &filtered {
        bridge
            .validate_pick(WorldBiome::TropicalRainforest, &bs.biome_id.0)
            .expect("every filtered biome must satisfy the bridge");
    }
    // At least one forest_* AND at least one swamp_* / forest_lake — the
    // bridge admits both terrain families. forest_tree is the cheapest
    // check.
    assert!(filtered.iter().any(|bs| bs.biome_id.0.starts_with("forest_")));
}

#[test]
fn world_zone_some_actually_changes_pipeline_output() {
    // MED-2 regression (from /review-impl 2026-05-24): the four AC-WI-6
    // tests above prove the load path + filter math, but none prove the
    // public TilemapView actually differs between a world-inheriting run
    // and an unconstrained run. If a future refactor silently broke
    // `library_for_template` (e.g. always returned the full library),
    // every other test would still pass.
    //
    // Setup that maximises the visible delta:
    //   - World zone: Ice (allow-set = snow_*)
    //   - Author terrain: Sand  (incompatible with Ice's snow_* set)
    //   - With world_zone=None: picker has the full library; Sand zone
    //     gets sand_* biomes.
    //   - With world_zone=Some(Ice): picker has only snow_* in the pool;
    //     §9 Q3 fallback drives the count and `pool.len()` shifts → RNG
    //     state diverges → object_placements diverge.
    //
    // Same seed both runs — the only differing input is `world_zone`.
    let src = MockFileWorldSource::new(fixture("diverse-biomes.json"));
    let ice = src
        .load_zone(&RegionPath::new(vec![0, 0]))
        .expect("zone [0, 0] should exist and be Ice");
    assert_eq!(ice.climate.biome_name, WorldBiome::Ice);

    // Build twin templates with the SAME template_id so `derive_seed` (which
    // hashes template_id, not the whole template) yields the byte-identical
    // seed for both runs. The ONLY input that differs is `world_zone`.
    let template_id = tilemap_service::types::template::TilemapTemplateId(
        "world_zone_delta".to_string(),
    );

    let mut template_none =
        template_for_world_zone("placeholder", TerrainKind::Sand, ice.clone());
    template_none.world_zone = None;
    template_none.template_id = template_id.clone();

    let mut template_ice = template_for_world_zone("placeholder", TerrainKind::Sand, ice);
    template_ice.template_id = template_id;

    let view_none = place_tilemap(
        &template_none,
        ChannelId("ch_delta_test".to_string()),
        ChannelTier::Country,
        GridSize { width: 48, height: 48 },
        TilemapSeed(0xDE17A),
    )
    .expect("None-world_zone run must succeed");
    let view_ice = place_tilemap(
        &template_ice,
        ChannelId("ch_delta_test".to_string()),
        ChannelTier::Country,
        GridSize { width: 48, height: 48 },
        TilemapSeed(0xDE17A),
    )
    .expect("Ice-world_zone run must succeed");

    // Headline assertion: outputs MUST differ. If they don't, the bridge
    // wiring is a no-op and the entire BUILD is silently broken.
    assert_ne!(
        view_none, view_ice,
        "world_zone Some(Ice) must change TilemapView vs None at the same seed — \
         bridge wiring may be a no-op"
    );
}

#[test]
fn ac_wi_6_place_tilemap_runs_end_to_end_with_world_zone_inherited() {
    // The full pipeline accepts a template with world_zone Some(_) and
    // produces a TilemapView without panic. Doesn't assert specific
    // counts (placement is RNG-driven) — just proves the wire-through
    // is healthy.
    let src = MockFileWorldSource::new(fixture("minimal.json"));
    let snap = src
        .load_zone(&RegionPath::new(vec![2, 1]))
        .expect("zone [2, 1] should exist and be Savanna");
    assert_eq!(snap.climate.biome_name, WorldBiome::Savanna);

    let template = template_for_world_zone("ac_wi_6_savanna_e2e", TerrainKind::Grass, snap);
    let view = place_tilemap(
        &template,
        ChannelId("ch_world_inherit_test".to_string()),
        ChannelTier::Country,
        GridSize { width: 48, height: 48 },
        TilemapSeed(0xCAFE),
    )
    .expect("placement on a world-inheriting template must succeed");

    assert_eq!(view.zones.len(), 1);
    // Determinism still holds across world-inheriting runs (TMP-A4 lives).
    let view_b = place_tilemap(
        &template,
        ChannelId("ch_world_inherit_test".to_string()),
        ChannelTier::Country,
        GridSize { width: 48, height: 48 },
        TilemapSeed(0xCAFE),
    )
    .expect("second run must succeed");
    assert_eq!(view, view_b, "world-inheriting templates must still be replay-deterministic");
}
