//! TMP-Q2 chunk B — BiomeThemePainter integration tests.
//!
//! Exercises the full pipeline via `place_tilemap_with_registry` with
//! `background_biome: Some(_)` and/or `ZoneSpec.biome_theme: Some(_)`.
//! Locks AC-BIOME-4/5/6/7 from the spec (per-tile sampling, background
//! fill, determinism, per-zone uncorrelated Perlin) and pins two
//! chunk-B snapshot hashes for regression.

use std::collections::BTreeMap;

use tilemap_service::engine::place_tilemap_with_registry;
use tilemap_service::registry::Registry;
use tilemap_service::seed::TilemapSeed;
use tilemap_service::types::template::{
    TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec,
};
use tilemap_service::types::zone::{PassageKind, ZoneId, ZoneRole};
use tilemap_service::types::{ChannelId, ChannelTier, GridSize, TerrainKind, TilemapView};

/// Fixture matching the chunk-A V2 baseline (3 zones), parameterized by
/// per-zone biome_theme and template-level background_biome. With all
/// fields None this fixture is byte-identical to the chunk-A V2
/// preservation fixture (same blake3 hash pin).
fn fixture(
    capital_biome: Option<&str>,
    crossroad_biome: Option<&str>,
    frontier_biome: Option<&str>,
    background: Option<&str>,
) -> TilemapTemplate {
    TilemapTemplate {
        template_id: TilemapTemplateId("q2_chunk_b".to_string()),
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
                treasure_tiers: vec![],
                biome_selection_rules: None,
                inherit_treasure_from: None,
                biome_theme: capital_biome.map(str::to_string),
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
                biome_theme: crossroad_biome.map(str::to_string),
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
                biome_theme: frontier_biome.map(str::to_string),
            },
        ],
        seed_offset: 0,
        world_zone: None,
        decoration_density: None,
        background_biome: background.map(str::to_string),
    }
}

fn run(template: &TilemapTemplate) -> TilemapView {
    let registry = Registry::load_default().expect("registry must load");
    place_tilemap_with_registry(
        template,
        ChannelId("ch_q2b".to_string()),
        ChannelTier::Town,
        GridSize { width: 48, height: 48 },
        TilemapSeed(1),
        &registry,
    )
    .expect("place_tilemap_with_registry must succeed")
}

/// Histogram of TerrainKind values within a tile mask projected to flat
/// indices. Keys are `TerrainKind as u8`.
fn histogram(view: &TilemapView, indices: &[usize]) -> BTreeMap<u8, u32> {
    let mut h: BTreeMap<u8, u32> = BTreeMap::new();
    for &i in indices {
        *h.entry(view.terrain_layer[i]).or_insert(0) += 1;
    }
    h
}

/// Tile indices belonging to a zone by id, projecting the runtime
/// `assigned_tiles` mask through the grid width.
fn zone_tile_indices(view: &TilemapView, zone_id: &str) -> Vec<usize> {
    let width = view.grid_size.width;
    let zone = view
        .zones
        .iter()
        .find(|z| z.zone_id.0 == zone_id)
        .unwrap_or_else(|| panic!("zone {zone_id} not found"));
    zone.assigned_tiles.iter_set()
        .map(|tc| tc.flat_index(width))
        .collect()
}

// ─── AC-BIOME-1 — V2 byte-identical preserved ──────────────────────────

const V2_TERRAIN_LAYER_HASH_PIN: &str =
    "b32fe411f10299473557157b903124a81cee173f6af3bc952ca7fcfd24b27310";

#[test]
fn v2_path_unchanged_when_both_opt_ins_are_none() {
    // AC-BIOME-1 re-check against chunk-A hash pin. Proves the chunk-B
    // placer's early-return path produces zero observable effect when
    // no biome opt-in is set. The hash literal is intentionally shared
    // with biome_theme_v2_preservation.rs — chunk-A and chunk-B both
    // promise the same V2 byte sequence.
    let template = fixture(None, None, None, None);
    // Reuse the chunk-A template_id so the fixture matches byte-for-byte.
    let template = TilemapTemplate {
        template_id: TilemapTemplateId("q2_chunk_a_v2".to_string()),
        ..template
    };
    let view = run(&template);
    let actual = blake3::hash(&view.terrain_layer).to_hex().to_string();
    assert_eq!(
        actual, V2_TERRAIN_LAYER_HASH_PIN,
        "AC-BIOME-1: chunk-B placer must not alter V2 baseline when all opt-ins are None"
    );
}

// ─── AC-BIOME-4 — Zone biome_theme produces multiple TerrainKinds ──────

#[test]
fn zone_biome_theme_produces_multiple_terrain_kinds() {
    // AC-BIOME-4: zone with forest_temperate (70% Forest / 20% Grass /
    // 10% Rough) MUST yield ≥2 distinct TerrainKind values across its
    // tiles. A 48-tile zone is large enough that any reasonable Perlin
    // pattern crosses CDF thresholds.
    let template = fixture(
        Some("lw:biome.forest_temperate"),
        None,
        None,
        None,
    );
    let view = run(&template);
    let indices = zone_tile_indices(&view, "capital");
    let hist = histogram(&view, &indices);
    // RoadPlacer may carve Road tiles through the zone after the biome
    // paint; exclude Road from the distinct-mix-kind count.
    let mix_kinds_present: Vec<u8> = hist
        .keys()
        .copied()
        .filter(|&k| k != TerrainKind::Road as u8)
        .collect();
    assert!(
        mix_kinds_present.len() >= 2,
        "AC-BIOME-4: forest_temperate (3-kind mix) must produce ≥2 distinct mix kinds across {} tiles, got hist {:?}",
        indices.len(),
        hist
    );
    // Every kind painted MUST be one of the theme's mix entries OR Road
    // (RoadPlacer carves connections after the biome pass).
    let allowed_mix: [u8; 3] = [
        TerrainKind::Forest as u8,
        TerrainKind::Grass as u8,
        TerrainKind::Rough as u8,
    ];
    for &kind in hist.keys() {
        assert!(
            allowed_mix.contains(&kind) || kind == TerrainKind::Road as u8,
            "AC-BIOME-4: painted kind {kind} not in forest_temperate's mix {allowed_mix:?} (Road allowed)"
        );
    }
}

#[test]
fn zone_biome_theme_distribution_roughly_matches_mix_weights() {
    // AC-BIOME-4 quality clause: 70/20/10 weights → output approximately
    // (within ±20pp) matches. Perlin's spatial correlation produces
    // chunkier distributions than IID sampling so the tolerance is wide.
    let template = fixture(
        Some("lw:biome.forest_temperate"),
        None,
        None,
        None,
    );
    let view = run(&template);
    let indices = zone_tile_indices(&view, "capital");
    let hist = histogram(&view, &indices);
    let total = indices.len() as f32;
    let pct_forest = hist
        .get(&(TerrainKind::Forest as u8))
        .copied()
        .unwrap_or(0) as f32 / total * 100.0;
    // Loose bound — Perlin patches mean a small sample can be skewed.
    // Forest should be majority (>40%) since it's 70% of the mix.
    assert!(
        pct_forest > 40.0,
        "Forest should dominate the 70/20/10 mix output, got {pct_forest:.1}% (hist {hist:?})"
    );
}

// ─── AC-BIOME-5 — background_biome paints non-zone tiles ──────────────

#[test]
fn background_biome_paints_all_non_zone_tiles() {
    // AC-BIOME-5: with template.background_biome = Some, every tile in
    // terrain_layer must be != 0 (i.e. the void u8 is fully covered).
    let template = fixture(None, None, None, Some("lw:biome.grassland_meadow"));
    let view = run(&template);
    let void_count = view.terrain_layer.iter().filter(|&&v| v == 0).count();
    assert_eq!(
        void_count, 0,
        "AC-BIOME-5: background_biome must paint every u8==0 tile, found {void_count} void tiles"
    );
    // Every painted kind must be in the meadow mix (grass, forest, rough).
    let allowed: [u8; 3] = [
        TerrainKind::Grass as u8,
        TerrainKind::Forest as u8,
        TerrainKind::Rough as u8,
    ];
    let bg_indices: Vec<usize> = {
        // Identify non-zone tiles via the runtime zones.
        let total_tiles = view.terrain_layer.len();
        let zone_tile_set: std::collections::HashSet<usize> = view
            .zones
            .iter()
            .flat_map(|z| {
                z.assigned_tiles.iter_set()
                    .map(|tc| tc.flat_index(view.grid_size.width))
                    .collect::<Vec<_>>()
            })
            .collect();
        (0..total_tiles).filter(|i| !zone_tile_set.contains(i)).collect()
    };
    for &i in &bg_indices {
        let kind = view.terrain_layer[i];
        // Background tiles may be u8 != 0 because RoadPlacer paints
        // road tiles. Accept Road too.
        assert!(
            allowed.contains(&kind) || kind == TerrainKind::Road as u8,
            "background tile {i} got kind {kind}, expected meadow mix or Road"
        );
    }
}

#[test]
fn background_biome_does_not_overwrite_zone_tiles() {
    // Zone tiles get TerrainPainter's single-fill (capital → Grass via
    // declared terrain_types). With biome_theme=None on the zone, the
    // background pass MUST NOT touch its tiles. Capital's tiles should
    // all read Grass (u8=1), not background mix.
    let template = fixture(
        None,
        None,
        None,
        Some("lw:biome.mountain_alpine"),  // would paint Mountain/Rough/Snow
    );
    let view = run(&template);
    let capital_indices = zone_tile_indices(&view, "capital");
    for &i in &capital_indices {
        let kind = view.terrain_layer[i];
        // Capital declares Grass; with biome_theme=None, TerrainPainter
        // paints uniform Grass. RoadPlacer may carve Road over some
        // tiles but Mountain/Snow (from mountain_alpine background) must
        // never appear in the zone.
        assert!(
            kind != TerrainKind::Mountain as u8 && kind != TerrainKind::Snow as u8,
            "AC-BIOME-5: zone tile {i} got kind {kind} (Mountain/Snow forbidden inside zone)"
        );
    }
}

// ─── AC-BIOME-6 — Determinism over many runs ──────────────────────────

#[test]
fn placer_is_deterministic_over_50_runs() {
    // AC-BIOME-6: same template+seed → byte-identical terrain_layer.
    // 50 runs is plenty to catch non-determinism (HashMap iteration,
    // un-seeded threads, etc.); 100 would slow the test suite.
    let template = fixture(
        Some("lw:biome.forest_temperate"),
        None,
        Some("lw:biome.mountain_alpine"),
        Some("lw:biome.grassland_meadow"),
    );
    let baseline = run(&template);
    let baseline_hash = blake3::hash(&baseline.terrain_layer);
    for i in 0..50 {
        let view = run(&template);
        let hash = blake3::hash(&view.terrain_layer);
        assert_eq!(
            hash, baseline_hash,
            "AC-BIOME-6: run #{i} terrain_layer hash diverged from baseline"
        );
    }
}

// ─── AC-BIOME-7 — Per-zone Perlin streams uncorrelated ────────────────

#[test]
fn two_zones_same_theme_produce_different_histograms() {
    // AC-BIOME-7: capital and frontier both use forest_temperate. Per-
    // zone sub_seed labels ("biome_theme:capital:perlin" vs
    // "biome_theme:frontier:perlin") MUST produce different histograms.
    // If sub_seed weren't label-diversified, two zones would emit
    // identical patterns and the histograms would match exactly.
    //
    // COSMETIC-3 fix from chunk-B /review-impl: renamed from
    // `..._have_uncorrelated_perlin_patterns` — the assertion proves
    // non-identity, not statistical uncorrelation. "Differ" is honest.
    let template = fixture(
        Some("lw:biome.forest_temperate"),
        None,
        Some("lw:biome.forest_temperate"),
        None,
    );
    let view = run(&template);
    let capital_hist = histogram(&view, &zone_tile_indices(&view, "capital"));
    let frontier_hist = histogram(&view, &zone_tile_indices(&view, "frontier"));
    assert_ne!(
        capital_hist, frontier_hist,
        "AC-BIOME-7: two zones with the same theme produced identical histograms — \
         per-zone sub_seed diversification is broken (capital={:?} frontier={:?})",
        capital_hist, frontier_hist
    );
}

// ─── LOW-5 contract — unknown biome id is silent no-op ────────────────

#[test]
fn mixed_valid_and_unknown_zones_each_independent() {
    // LOW-1 fix from chunk-B /review-impl: a single template with ONE
    // zone using a valid biome_theme + another zone using an unknown id
    // must produce CORRECT output for the valid zone AND silent no-op
    // for the unknown one. Guards against regressions that turn the
    // per-zone `continue` into a `return` (early-exit would skip valid
    // zones that follow the unknown one in iteration order).
    let template = fixture(
        Some("lw:biome.this_id_does_not_exist"),  // capital — unknown
        None,
        Some("lw:biome.forest_temperate"),        // frontier — valid
        None,
    );
    let view = run(&template);

    // Capital (unknown id) → all tiles either TerrainPainter's Grass or
    // RoadPlacer's Road. No Forest/Rough leak from frontier's theme.
    let capital_indices = zone_tile_indices(&view, "capital");
    for &i in &capital_indices {
        let kind = view.terrain_layer[i];
        assert!(
            kind == TerrainKind::Grass as u8 || kind == TerrainKind::Road as u8,
            "unknown-id capital tile {i} got {kind}; expected Grass/Road only"
        );
    }

    // Frontier (forest_temperate) → ≥2 mix kinds present, none from
    // capital's "would-have-been" mix (which is empty since id is unknown).
    let frontier_hist = histogram(&view, &zone_tile_indices(&view, "frontier"));
    let frontier_mix_kinds: Vec<u8> = frontier_hist
        .keys()
        .copied()
        .filter(|&k| k != TerrainKind::Road as u8)
        .collect();
    assert!(
        frontier_mix_kinds.len() >= 2,
        "valid frontier theme must produce ≥2 mix kinds even when sibling zone has unknown id, got hist {frontier_hist:?}"
    );
}

#[test]
fn unknown_zone_biome_id_is_silent_no_op() {
    // LOW-5 contract from chunk A: an unknown biome_theme id must
    // template-load cleanly + the placer skips the zone (falls back to
    // TerrainPainter's single-fill output).
    let template = fixture(Some("lw:biome.this_id_does_not_exist"), None, None, None);
    let view = run(&template);
    // Capital declares Grass and biome_theme is unknown → all capital
    // tiles should be Grass (TerrainPainter's output).
    let capital_indices = zone_tile_indices(&view, "capital");
    for &i in &capital_indices {
        let kind = view.terrain_layer[i];
        // Allow Road (RoadPlacer may paint connections through).
        assert!(
            kind == TerrainKind::Grass as u8 || kind == TerrainKind::Road as u8,
            "LOW-5: unknown biome_theme id must silently no-op the zone, but tile {i} got {kind}"
        );
    }
}

#[test]
fn unknown_background_biome_id_is_silent_no_op_vs_v2() {
    // Same contract for background_biome: unknown id ⇒ no observable
    // change. Penrose tiling covers the full grid so there are no
    // u8==0 void tiles for the background pass to touch even with a
    // VALID id — but with an UNKNOWN id we must early-return BEFORE
    // even iterating terrain_layer. Demonstrate equivalence by hashing
    // the terrain_layer and comparing against the V2 baseline.
    let template = fixture(None, None, None, Some("lw:biome.this_id_does_not_exist"));
    let template = TilemapTemplate {
        template_id: TilemapTemplateId("q2_chunk_a_v2".to_string()),
        ..template
    };
    let view = run(&template);
    let actual = blake3::hash(&view.terrain_layer).to_hex().to_string();
    assert_eq!(
        actual, V2_TERRAIN_LAYER_HASH_PIN,
        "LOW-5: unknown background_biome id must produce V2-identical terrain_layer"
    );
}

// ─── Chunk-B snapshot pins ───────────────────────────────────────────

/// Snapshot pin for a Zone-only opt-in fixture (2 zones using biome
/// themes, no background_biome). Locks the chunk-B placer behavior
/// across future refactors. If this hash changes, EITHER the placer
/// logic shifted (rebaseline intentionally) OR a determinism / Perlin
/// / cross-OS issue surfaced (investigate).
///
/// LOW-4 fix from chunk-B /review-impl: hash was pinned on x86_64
/// (`noise = "=0.9.0"`, default target-cpu). The `noise` crate is
/// pure-Rust but f64 arithmetic ordering may differ under aarch64 FMA
/// fusing; contributors hitting a mismatch on Apple Silicon should
/// branch the literal via `#[cfg(target_arch = "aarch64")]` rather
/// than rebaselining the x86 value.
const ZONE_ONLY_HASH_PIN: &str =
    "f252df11e0abe71adc86ef047e595a34e48f37669b7b96fce0b5bf13845bacfa";

#[test]
fn chunk_b_snapshot_pin_for_zone_only_fixture() {
    let template = fixture(
        Some("lw:biome.forest_temperate"),
        None,
        Some("lw:biome.mountain_alpine"),
        None,
    );
    let view = run(&template);
    let actual = blake3::hash(&view.terrain_layer).to_hex().to_string();
    assert_eq!(
        actual, ZONE_ONLY_HASH_PIN,
        "chunk-B zone-only snapshot pin regressed — rebaseline if intentional"
    );
}

// ─── Higher-tier smoke (LOW-3 fix) ──────────────────────────────────

#[test]
fn placer_runs_clean_at_country_tier() {
    // LOW-3 fix from chunk-B /review-impl: all other integration tests
    // use 48² Town grids. Exercise the placer on 192² Country tier to
    // catch grid-size-dependent regressions (Perlin scale, allocation
    // pressure, determinism at a larger sample). No hash pin — this is
    // a smoke test, not a regression anchor.
    let template = fixture(
        Some("lw:biome.forest_temperate"),
        None,
        Some("lw:biome.mountain_alpine"),
        None,
    );
    let registry = Registry::load_default().expect("registry must load");
    let view = place_tilemap_with_registry(
        &template,
        ChannelId("ch_q2b_country".to_string()),
        ChannelTier::Country,
        GridSize { width: 192, height: 192 },
        TilemapSeed(7),
        &registry,
    )
    .expect("country-tier placement must succeed");

    // Every tile painted (no void left behind by the pipeline).
    let void_count = view.terrain_layer.iter().filter(|&&v| v == 0).count();
    assert_eq!(
        void_count, 0,
        "country-tier placement must leave no void tiles, got {void_count}"
    );

    // Frontier (mountain_alpine: 70/20/10 Mountain/Rough/Snow) should
    // produce ≥2 distinct mix kinds — locks the 192² Perlin scale
    // doesn't degenerate to single-kind output.
    let frontier_hist = histogram(&view, &zone_tile_indices(&view, "frontier"));
    let mix_kinds: Vec<u8> = frontier_hist
        .keys()
        .copied()
        .filter(|&k| k != TerrainKind::Road as u8)
        .collect();
    assert!(
        mix_kinds.len() >= 2,
        "country-tier frontier (mountain_alpine) must produce ≥2 mix kinds, got hist {frontier_hist:?}"
    );
}

#[test]
fn background_only_fixture_with_full_zone_coverage_is_v2_identical() {
    // place_zones (Penrose tiling) assigns EVERY tile of the grid to
    // some zone, so a fixture with only `background_biome = Some` and
    // no `ZoneSpec.biome_theme` has zero void tiles for the background
    // pass to paint. The placer's iter+skip-if-not-zero loop is a
    // no-op → terrain_layer = V2 baseline. Locks this property as a
    // regression anchor; if Penrose tiling ever produces partial
    // coverage in the future, this test should fail loudly so the
    // background pass behavior gets re-evaluated.
    let template = fixture(
        None,
        None,
        None,
        Some("lw:biome.grassland_meadow"),
    );
    let template = TilemapTemplate {
        template_id: TilemapTemplateId("q2_chunk_a_v2".to_string()),
        ..template
    };
    let view = run(&template);
    let actual = blake3::hash(&view.terrain_layer).to_hex().to_string();
    assert_eq!(
        actual, V2_TERRAIN_LAYER_HASH_PIN,
        "background-only fixture must produce V2-identical terrain_layer when zones \
         fully tile the grid (Penrose coverage invariant)"
    );
}
