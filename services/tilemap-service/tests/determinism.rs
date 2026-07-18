//! Phase 1 placement-engine integration test — the TMP-A4 determinism axiom
//! (AC-4) plus AC-1 / AC-2 / AC-6 coverage of [`place_tilemap`].
//!
//! AC-4 is the load-bearing guarantee: same `(template, channel, tier, grid,
//! seed)` ⇒ byte-identical `TilemapView`. This test is **not** `#[ignore]`d —
//! it runs in CI on every build (AC-7).

use tilemap_service::engine::place_tilemap;
use tilemap_service::seed::TilemapSeed;
use tilemap_service::types::object::TilemapObjectKind;
use tilemap_service::types::template::{TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec};
use tilemap_service::types::tile_mask::TileMask;
use tilemap_service::types::treasure::TreasureTierSpec;
use tilemap_service::types::zone::{PassageKind, ZoneId, ZoneRole};
use tilemap_service::types::{ChannelId, ChannelTier, GridSize, TerrainKind, TilemapView};

/// Seed for the committed Phase-A golden baseline (AC-9) — reused by both the
/// regenerator and the byte-identity gate.
const GOLDEN_SEED: u64 = 0xA11CE;

fn zone(id: &str, role: ZoneRole, terrains: Vec<TerrainKind>, conns: &[(&str, PassageKind)]) -> ZoneSpec {
    ZoneSpec {
        zone_id: ZoneId(id.to_string()),
        zone_role: role,
        size: 100,
        terrain_types: terrains,
        monster_strength: None,
        connections: conns
            .iter()
            .map(|(to, kind)| TemplateConnection::new(ZoneId(to.to_string()), *kind))
            .collect(),
        treasure_tiers: vec![],
        biome_selection_rules: None,
        inherit_treasure_from: None,
        biome_theme: None,
    }
}

/// A 5-zone fixture covering every `ZoneRole`.
///
/// `inland_sea` carries no connection, so the golden does not exercise a
/// Pass-3 water route / `Ferry` — `place_zones`' seed-random geometry cannot
/// guarantee two zones non-bordering with the Sea between them, so a golden
/// ferry cannot be forced deterministically. Water routes are covered by the
/// `connections_placer` unit test `ac7` instead.
fn fixture() -> TilemapTemplate {
    let mut template = TilemapTemplate {
        template_id: TilemapTemplateId("phase1_determinism".to_string()),
        zones: vec![
            zone("capital", ZoneRole::Wilderness, vec![TerrainKind::Grass], &[("crossroad", PassageKind::Threshold)]),
            // crossroad — the Hub — connects out to `frontier` (an Open
            // passage) and into the Forbidden `rival` (a Portal: TMP_007 §2 — a
            // Forbidden zone is Portal-only-enterable, so the Phase-D golden
            // exercises the Pass-1 monolith pair + the Forbidden-zone fallback).
            zone("crossroad", ZoneRole::Hub, vec![], &[("frontier", PassageKind::Open), ("rival", PassageKind::Portal)]),
            // `frontier` is painted Mountain so ObstaclePlacer reliably emits
            // mountain obstacles — the Phase-E RiverPlacer's river sources.
            zone("frontier", ZoneRole::Wilderness, vec![TerrainKind::Mountain], &[("rival", PassageKind::Adversarial)]),
            zone("inland_sea", ZoneRole::Sea, vec![], &[]),
            zone("rival", ZoneRole::Forbidden, vec![], &[]),
        ],
        seed_offset: 0,
        world_zone: None,
        decoration_density: None,
        background_biome: None,
    };
    // Phase C — give the Wilderness zones a treasure tier so the rebaselined
    // golden exercises TreasurePlacer; `min ≥ 2000` ⇒ every pile is guarded, so
    // the golden carries both Treasure and MonsterLair records (spec D7 / AC-9).
    for z in &mut template.zones {
        if z.zone_role == ZoneRole::Wilderness {
            z.treasure_tiers = vec![TreasureTierSpec { min: 2000, max: 6000, density: 4 }];
        }
    }
    template
}

fn run(template: &TilemapTemplate, seed: u64) -> TilemapView {
    place_tilemap(
        template,
        ChannelId("ch_determinism".to_string()),
        ChannelTier::Country,
        GridSize { width: 64, height: 64 },
        TilemapSeed(seed),
    )
    .expect("placement on a well-formed 5-zone template must succeed")
}

#[test]
fn ac4_same_seed_yields_byte_identical_tilemap() {
    let template = fixture();
    let a = run(&template, 0xA11CE);
    let b = run(&template, 0xA11CE);

    assert_eq!(a, b, "same seed must produce an equal TilemapView");
    let ja = serde_json::to_string(&a).unwrap();
    let jb = serde_json::to_string(&b).unwrap();
    assert_eq!(ja, jb, "same seed must serialize byte-identically (TMP-A4)");
    // Phase C — the fixture's Wilderness zones carry a min≥2000 treasure tier,
    // so the pipeline places Treasure piles + their MonsterLair guards on top
    // of the Phase-B obstacle objects (AC-8: object_placements non-empty and
    // carrying the new Phase-C record kinds).
    assert!(!a.object_placements.is_empty(), "the pipeline must place objects");
    assert!(
        a.object_placements.iter().any(|p| p.kind == TilemapObjectKind::Treasure),
        "Phase C must place Treasure piles",
    );
    assert!(
        a.object_placements.iter().any(|p| p.kind == TilemapObjectKind::MonsterLair),
        "a min≥2000 treasure tier must place MonsterLair guards",
    );
    // Phase D — the crossroad→rival Portal places a Monolith pair (one per
    // zone) carrying a shared pair_id (AC-1); a no-op detector for the
    // rebaselined Phase-D golden.
    assert_eq!(
        a.object_placements.iter().filter(|p| p.kind == TilemapObjectKind::Monolith).count(),
        2,
        "the Portal connection must place a Monolith pair (Phase D)",
    );
    // Phase E — the fixture's connections record `road_nodes`, so RoadPlacer
    // builds a road network; `frontier` is Mountain terrain, so ObstaclePlacer
    // emits mountain obstacles and RiverPlacer flows rivers to `inland_sea`. A
    // present river also proves AC-2 — RiverPlacer ran *after* ObstaclePlacer
    // (otherwise there would be no mountain tags to source from).
    assert!(!a.road_segments.is_empty(), "Phase E RoadPlacer must place roads (AC-1)");
    assert!(!a.river_segments.is_empty(), "Phase E RiverPlacer must place rivers (AC-2)");
}

#[test]
fn ac2_river_barrier_fords_far_less_after_the_reorder() {
    // DEFERRED #026 — before the ObstacleSourcePlacer→River→ObstacleFillPlacer
    // reorder, the river ran into a post-erosion zone fragmented into narrow
    // channels, so the conservative `would_seal_a_gap` gate forded *most*
    // river tiles (the golden was ~76 % crossings, ford-dominated). Now the
    // river carves a wide-open zone (markers placed pre-erosion), so
    // connectivity-forced fords are rare. Gate: aggregate ford ratio < 0.25.
    use tilemap_service::types::tilemap::CrossingKind;
    let view = run(&fixture(), GOLDEN_SEED);
    let total_tiles: usize = view.river_segments.iter().map(|s| s.tiles.len()).sum();
    let total_fords: usize = view
        .river_segments
        .iter()
        .flat_map(|s| &s.crossings)
        .filter(|c| c.kind == CrossingKind::Ford)
        .count();
    assert!(total_tiles > 0, "the fixture must place a river to test barrier strength");
    let ford_ratio = total_fords as f64 / total_tiles as f64;
    assert!(
        ford_ratio < 0.25,
        "river ford ratio {ford_ratio:.3} ({total_fords} fords / {total_tiles} tiles) — \
         the reorder should keep connectivity-forced fords rare",
    );
}

#[test]
fn ace_phase_e_roads_are_painted_and_rivers_stay_connected() {
    // Phase E end-to-end — every road waypoint is painted `Road`, and every
    // river crossing tile stays passable terrain-wise (a carved tile is the
    // only impassable river tile). Connectivity is gated in the modificator;
    // here we confirm the realised view is internally consistent.
    let view = run(&fixture(), GOLDEN_SEED);
    let width = view.grid_size.width;
    for seg in &view.road_segments {
        for &t in &seg.waypoints {
            assert_eq!(
                view.terrain_layer[t.flat_index(width)],
                TerrainKind::Road as u8,
                "road waypoint {t:?} not painted Road",
            );
        }
    }
    for seg in &view.river_segments {
        // Every crossing is one of the segment's tiles.
        for crossing in &seg.crossings {
            assert!(
                seg.tiles.contains(&crossing.at),
                "crossing {:?} is not on its river",
                crossing.at,
            );
        }
    }
}

#[test]
fn ac4_different_seed_yields_a_different_layout() {
    let template = fixture();
    let a = run(&template, 1);
    let b = run(&template, 2);

    // Not just the `seed` scalar — the actual placement must differ.
    assert!(
        a.zones != b.zones || a.terrain_layer != b.terrain_layer,
        "a different seed must change the layout, not only the seed field",
    );
}

#[test]
fn ac1_every_zone_is_fully_placed() {
    let view = run(&fixture(), 0xB0B);
    assert_eq!(view.zones.len(), 5);
    for z in &view.zones {
        assert!(!z.assigned_tiles.is_empty(), "zone {} owns no tiles", z.zone_id.0);
        assert!(
            z.assigned_tiles.get(z.center_position),
            "zone {} centre is outside its mask",
            z.zone_id.0,
        );
        // free_paths is empty only for Forbidden zones.
        if z.zone_role == ZoneRole::Forbidden {
            assert!(z.free_paths.is_empty(), "Forbidden zone has free paths");
        } else {
            assert!(!z.free_paths.is_empty(), "zone {} has no free path", z.zone_id.0);
        }
    }
    // Terrain layer fully painted — no tile left at the unpainted sentinel 0.
    assert_eq!(view.terrain_layer.len(), view.grid_size.tile_count());
    assert!(view.terrain_layer.iter().all(|&t| t != 0), "a tile was left unpainted");
}

#[test]
fn ac2_zones_are_a_disjoint_partition_of_the_grid() {
    let view = run(&fixture(), 0xC0FFEE);
    let grid = view.grid_size;
    let mut union = TileMask::new(grid.width, grid.height);
    for z in &view.zones {
        union.union_with(&z.assigned_tiles);
    }
    assert_eq!(union.count_ones(), grid.tile_count(), "tiles left unassigned");
    for i in 0..view.zones.len() {
        for j in (i + 1)..view.zones.len() {
            assert!(
                !view.zones[i].assigned_tiles.intersects(&view.zones[j].assigned_tiles),
                "zones {} and {} overlap",
                view.zones[i].zone_id.0,
                view.zones[j].zone_id.0,
            );
        }
    }
}

#[test]
fn ac6_sea_zone_is_painted_water() {
    let view = run(&fixture(), 0xD15EA5E);
    let sea = view
        .zones
        .iter()
        .find(|z| z.zone_role == ZoneRole::Sea)
        .expect("fixture has a Sea zone");
    assert_eq!(sea.terrain_type, TerrainKind::Water);
    for tile in sea.assigned_tiles.iter_set() {
        let idx = tile.flat_index(view.grid_size.width);
        assert_eq!(
            view.terrain_layer[idx],
            TerrainKind::Water as u8,
            "Sea tile {tile:?} not painted Water",
        );
    }
}

/// Regenerate the committed golden baseline — the **deliberate rebaseline**
/// tool. `#[ignore]`d; run with `cargo test regenerate_golden_baseline --
/// --ignored` when a phase legitimately changes `place_tilemap` output (Phase B
/// did — ObstaclePlacer; Phase C did — TreasurePlacer). The committed
/// `tests/golden/tilemap_baseline.json` is a frozen reference: it gates later
/// phases against *unintended* output drift.
#[test]
#[ignore = "regenerator — run explicitly to rebaseline the golden snapshot"]
fn regenerate_golden_baseline() {
    let json = serde_json::to_string_pretty(&run(&fixture(), GOLDEN_SEED)).unwrap();
    std::fs::create_dir_all("tests/golden").expect("create tests/golden");
    std::fs::write("tests/golden/tilemap_baseline.json", json).expect("write golden");
}

/// AC-9 — `place_tilemap` reproduces the committed golden snapshot
/// (`tests/golden/tilemap_baseline.json`, frozen at the reviewed Phase-C engine)
/// byte-identically. Within the rebaselining phase this is trivially green; its
/// value is cross-phase — a later phase that changes zone, terrain, obstacle,
/// or treasure/guard output without a deliberate `regenerate_golden_baseline`
/// rebaseline trips this gate.
#[test]
fn golden_baseline_byte_identical() {
    // `include_str!` reads the WORKING-TREE bytes. On Windows (core.autocrlf=true) a copy
    // checked out before .gitattributes pinned `eol=lf` still sits there as CRLF, while
    // serde_json always emits LF — so every one of the 8408 lines "differs" and the message
    // below accuses the engine of drifting when nothing drifted at all (verified: `diff
    // --strip-trailing-cr` → 0 lines). The fixture's line endings are not engine output, so
    // normalise them; any REAL drift in the JSON still fails this byte-for-byte.
    let golden = include_str!("golden/tilemap_baseline.json").replace("\r\n", "\n");
    let fresh = serde_json::to_string_pretty(&run(&fixture(), GOLDEN_SEED)).unwrap();
    assert_eq!(
        golden, fresh,
        "place_tilemap output drifted from the committed golden baseline (AC-9). \
         (If EVERY line differs, suspect a stale CRLF checkout of the golden, not the engine: \
         `git rm --cached -r . && git reset --hard` renormalises the working tree.)",
    );
}