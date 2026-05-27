//! The tilemap generation engine — zone placement (TMP_002) + the modificator
//! pipeline (TMP_003).
//!
//! [`place_tilemap`] is the top-level entry: a `TilemapTemplate` + seed in, a
//! fully-placed [`TilemapView`] out — deterministic per the TMP-A4 axiom.

use std::collections::HashMap;
use std::time::{Duration, Instant};

use crate::engine::build_state::TilemapBuildState;
use crate::engine::modificators::{
    ConnectionsPlacer, ObstacleFillPlacer, ObstacleSourcePlacer, RiverPlacer, RoadPlacer,
    TerrainPainter, TreasurePlacer,
};
use crate::engine::pipeline::{ModificatorContext, ModificatorRegistry};
use crate::engine::placement::place_zones;
use crate::registry::Registry;
use crate::seed::TilemapSeed;
use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::template::TilemapTemplate;
use crate::types::tile::TerrainKind;
use crate::types::tilemap::{GenerationSource, GridSize, TilemapView, ZoneRuntime};

pub mod biome_library;
pub mod biome_select;
pub mod build_state;
pub mod geometry;
pub mod modificators;
pub mod object_manager;
pub mod pipeline;
pub mod placement;
pub mod treasure_pool;
pub mod treasure_select;

/// Generate a complete [`TilemapView`] from a template + seed.
///
/// Runs the full engine: TMP_002 [`place_zones`] (grid seed → Fruchterman-
/// Reingold → Penrose → fractalize) then the TMP_003 modificator pipeline
/// (TerrainPainter → ConnectionsPlacer → TreasurePlacer → ObstaclePlacer).
/// Single-threaded — the determinism axiom (TMP-A4) holds: same
/// `(template, channel_id, tier, grid, seed)` ⇒ byte-identical output.
///
/// `channel_id` + `tier` scope the resulting view (they are channel metadata
/// the placement algorithm does not synthesize — spec AC-1's `(template, seed,
/// grid_size)` sketch is widened here to carry them).
///
/// Errors propagate from §4 Penrose assignment — an empty zone or a degenerate
/// tiling (both template misconfigurations).
pub fn place_tilemap(
    template: &TilemapTemplate,
    channel_id: ChannelId,
    tier: ChannelTier,
    grid: GridSize,
    seed: TilemapSeed,
) -> crate::Result<TilemapView> {
    let registry = Registry::load_default().map_err(|e| crate::Error::Config(e.to_string()))?;
    let (view, _) = place_tilemap_inner(template, channel_id, tier, grid, seed, &registry, false)?;
    Ok(view)
}

/// Same as [`place_tilemap`] but uses an explicit caller-supplied registry —
/// the entry point for per-book worlds (V2). The default-namespace path
/// (`place_tilemap`) is a thin wrapper around this with `Registry::load_default()`.
pub fn place_tilemap_with_registry(
    template: &TilemapTemplate,
    channel_id: ChannelId,
    tier: ChannelTier,
    grid: GridSize,
    seed: TilemapSeed,
    registry: &Registry,
) -> crate::Result<TilemapView> {
    let (view, _) = place_tilemap_inner(template, channel_id, tier, grid, seed, registry, false)?;
    Ok(view)
}

/// Per-stage wall-time breakdown of a `place_tilemap` run — captured by
/// [`place_tilemap_with_timings`] for the `tilemap-service measure` harness
/// (DEFERRED #029). `place_zones` is TMP_002 (Penrose + fractalize);
/// `modificators` is one `(name, Duration)` per modificator in execution
/// order (TerrainPainter → ConnectionsPlacer → TreasurePlacer → RoadPlacer
/// → ObstaclePlacer → RiverPlacer).
#[derive(Debug, Clone)]
pub struct PlacementStageTimings {
    pub place_zones: Duration,
    pub modificators: Vec<(String, Duration)>,
}

/// Same as [`place_tilemap`] but returns per-stage timings alongside the
/// view (DEFERRED #029 — narrows the 687-s continent cost onto a specific
/// placer). The view is bit-identical to what `place_tilemap` returns for
/// the same inputs.
pub fn place_tilemap_with_timings(
    template: &TilemapTemplate,
    channel_id: ChannelId,
    tier: ChannelTier,
    grid: GridSize,
    seed: TilemapSeed,
) -> crate::Result<(TilemapView, PlacementStageTimings)> {
    let registry = Registry::load_default().map_err(|e| crate::Error::Config(e.to_string()))?;
    let (view, timings) =
        place_tilemap_inner(template, channel_id, tier, grid, seed, &registry, true)?;
    Ok((view, timings.expect("collect_timings=true must return Some")))
}

/// Shared body of [`place_tilemap`] + [`place_tilemap_with_timings`].
/// `collect_timings = false` means production-path: zero `Instant` calls,
/// zero `Vec` alloc for timings. `true` means measure-path: time
/// `place_zones` + per-modificator via [`ModificatorRegistry::execute_with_timing`].
fn place_tilemap_inner(
    template: &TilemapTemplate,
    channel_id: ChannelId,
    tier: ChannelTier,
    grid: GridSize,
    seed: TilemapSeed,
    registry: &Registry,
    collect_timings: bool,
) -> crate::Result<(TilemapView, Option<PlacementStageTimings>)> {
    // TMP_002 §3-§5 — placed zones with assigned_tiles + free_paths.
    let t_zones = collect_timings.then(Instant::now);
    let tiled = place_zones(template, grid, seed)?;
    let zones_elapsed = t_zones.map(|t| t.elapsed());

    // TMP_003 — build the mutable generation state and run the modificator
    // pipeline. The Kahn topo-sort orders it by the `dependencies()` edges
    // regardless of `add` order: TerrainPainter → ConnectionsPlacer →
    // TreasurePlacer → RoadPlacer → ObstacleSourcePlacer → RiverPlacer →
    // ObstacleFillPlacer (DEFERRED #026 — the obstacle pass is split so the
    // river carves a wide-open zone *before* the bulk fill clutters it, making
    // rivers real barriers; ObstacleSourcePlacer places only the Mountain/Lake
    // river source/sink tags pre-erosion, ObstacleFillPlacer erodes + fills the
    // rest post-river).
    let mut state = TilemapBuildState::from_zones(tiled, grid);
    let mut modificators = ModificatorRegistry::new();
    modificators.add(Box::new(TerrainPainter));
    modificators.add(Box::new(ConnectionsPlacer));
    modificators.add(Box::new(TreasurePlacer));
    modificators.add(Box::new(RoadPlacer));
    modificators.add(Box::new(ObstacleSourcePlacer));
    modificators.add(Box::new(RiverPlacer));
    modificators.add(Box::new(ObstacleFillPlacer));
    let modificator_timings = {
        let mut ctx = ModificatorContext {
            template,
            grid,
            seed,
            state: &mut state,
            registry,
        };
        if collect_timings {
            Some(modificators.execute_with_timing(&mut ctx)?)
        } else {
            modificators.execute(&mut ctx)?;
            None
        }
    };

    // Assemble the per-zone runtime records from the build state.
    let zones: Vec<ZoneRuntime> = state
        .zones
        .into_iter()
        .zip(state.zone_terrain)
        .map(|(zone, terrain)| ZoneRuntime {
            zone_id: zone.id,
            zone_role: zone.role,
            center_position: zone.center,
            assigned_tiles: zone.assigned_tiles,
            free_paths: zone.free_paths,
            // TerrainPainter paints every zone; the fallback is defensive only.
            terrain_type: terrain.unwrap_or(TerrainKind::Grass),
        })
        .collect();

    let view = TilemapView {
        channel_id,
        tier,
        grid_size: grid,
        template_id: template.template_id.clone(),
        seed: seed.raw(),
        zones,
        terrain_layer: state.terrain_layer,
        // V2 — dictionary indexed by `terrain_layer` u8 values. Built from
        // the active registry so per-book registries (`xianxia:`, etc.) get
        // their own primitive/tag mapping for the V1 wire-shape u8 slots.
        terrain_vocabulary: registry.build_default_terrain_vocabulary(),
        registry_ref: Some(registry.reference().clone()),
        object_placements: state.object_placements,
        road_segments: state.road_segments,
        river_segments: state.river_segments,
        child_cell_anchors: HashMap::new(),
        generation_source: GenerationSource::EngineGenerated,
        regional_narration: None,
        prompt_template_version: 0,
    };

    let timings = match (zones_elapsed, modificator_timings) {
        (Some(place_zones), Some(modificators)) => Some(PlacementStageTimings {
            place_zones,
            modificators,
        }),
        _ => None,
    };
    Ok((view, timings))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::geometry::neighbors4;
    use crate::types::template::{TemplateConnection, TilemapTemplateId, ZoneSpec};
    use crate::types::tile::TileCoord;
    use crate::types::tile_mask::TileMask;
    use crate::types::zone::{PassageKind, ZoneId, ZoneRole};

    /// A `ZoneSpec` with the given role + connections (mirrors the proven
    /// `tests/determinism.rs` fixture, so `place_zones` runs on a known-good
    /// multi-zone template).
    fn zone(id: &str, role: ZoneRole, conns: &[(&str, PassageKind)]) -> ZoneSpec {
        ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: role,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns
                .iter()
                .map(|(to, kind)| TemplateConnection::new(ZoneId(to.to_string()), *kind))
                .collect(),
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
        }
    }

    /// A 5-zone fixture covering every `ZoneRole`.
    fn fixture() -> TilemapTemplate {
        TilemapTemplate {
            template_id: TilemapTemplateId("ac10_connectivity".to_string()),
            zones: vec![
                zone("capital", ZoneRole::Wilderness, &[("crossroad", PassageKind::Threshold)]),
                zone("crossroad", ZoneRole::Hub, &[("frontier", PassageKind::Open)]),
                zone("frontier", ZoneRole::Wilderness, &[("rival", PassageKind::Adversarial)]),
                zone("inland_sea", ZoneRole::Sea, &[]),
                zone("rival", ZoneRole::Forbidden, &[]),
            ],
            seed_offset: 0,
            world_zone: None,
        }
    }

    /// Independent 4-connected flood-fill from `start` over `region` — the
    /// AC-10 reachability oracle, sharing no implementation with
    /// `would_seal_a_gap` or `connected_components`.
    fn flood(start: TileCoord, region: &TileMask, grid: GridSize) -> TileMask {
        let mut seen = TileMask::new(grid.width, grid.height);
        if !region.get(start) {
            return seen;
        }
        let mut stack = vec![start];
        seen.set(start);
        while let Some(t) = stack.pop() {
            for n in neighbors4(t, grid.width, grid.height) {
                if region.get(n) && !seen.get(n) {
                    seen.set(n);
                    stack.push(n);
                }
            }
        }
        seen
    }

    /// Every 4-connected component of `region`, each as its own mask.
    fn components(region: &TileMask, grid: GridSize) -> Vec<TileMask> {
        let mut remaining = region.clone();
        let mut out = Vec::new();
        while !remaining.is_empty() {
            let start = remaining.iter_set().next().expect("non-empty mask has a set tile");
            let comp = flood(start, &remaining, grid);
            remaining.subtract(&comp);
            out.push(comp);
        }
        out
    }

    #[test]
    fn ac10_place_tilemap_pipeline_never_splits_a_zone_passable_region() {
        // AC-10 — end-to-end: after the `place_tilemap` modificator pipeline no
        // non-Forbidden zone's passable region (`Walkable ∪ Open`) has been
        // split. `place_tilemap` returns a `TilemapView` that drops the
        // build-internal `TileState`, so the test drives the *same* pipeline at
        // the `TilemapBuildState` level — where `zone_passable` is observable —
        // and verifies with an INDEPENDENT 4-connected flood-fill (not
        // `connected_components`, not `would_seal_a_gap`): every pre-pipeline
        // passable component that keeps a survivor keeps all its survivors
        // mutually reachable. Eroding an already-isolated `Open` pocket away
        // entirely is permitted — it strands nothing. AC-10 is a *universal*
        // property, so the check runs over several seeds — each a different
        // `place_zones` geometry — not one (a single-seed test for a universal
        // property is falsely green).
        let template = fixture();
        let grid = GridSize { width: 64, height: 64 };
        let reg = Registry::load_default().unwrap();
        // No-op detector — RiverPlacer carves a real river on at least one
        // seed, so the per-zone connectivity check is not vacuous w.r.t. it.
        let mut any_river = false;
        for raw_seed in [0xA11CE_u64, 1, 2, 0xB0B, 0xC0FFEE] {
            let seed = TilemapSeed(raw_seed);
            let tiled = place_zones(&template, grid, seed).expect("place_zones on the fixture");
            let mut state = TilemapBuildState::from_zones(tiled, grid);
            let pre: Vec<TileMask> =
                (0..state.zones.len()).map(|i| state.zone_passable(i)).collect();

            // The exact modificator set `place_tilemap` registers, run the same
            // way — all six, incl. the Phase-E RoadPlacer (roads only paint
            // terrain — connectivity-neutral) and RiverPlacer, whose carve is
            // `would_seal_a_gap`-gated per-zone (AC-8). TreasurePlacer no-ops
            // here — `fixture()` declares no `treasure_tiers`.
            let mut modificators = ModificatorRegistry::new();
            modificators.add(Box::new(TerrainPainter));
            modificators.add(Box::new(ConnectionsPlacer));
            modificators.add(Box::new(TreasurePlacer));
            modificators.add(Box::new(RoadPlacer));
            modificators.add(Box::new(ObstacleSourcePlacer));
            modificators.add(Box::new(RiverPlacer));
            modificators.add(Box::new(ObstacleFillPlacer));
            {
                let mut ctx = ModificatorContext {
                    template: &template,
                    grid,
                    seed,
                    state: &mut state,
                    registry: &reg,
                };
                modificators.execute(&mut ctx).expect("modificator pipeline");
            }
            any_river |= !state.river_segments.is_empty();

            for (i, pre_passable) in pre.iter().enumerate() {
                if state.zones[i].role == ZoneRole::Forbidden {
                    continue; // a Forbidden zone is all-Obstacle — no passable region
                }
                let zone_id = &state.zones[i].id.0;
                let post = state.zone_passable(i);
                assert!(
                    !post.is_empty(),
                    "seed {raw_seed:#x} zone {zone_id}: the pipeline sealed the entire zone",
                );
                for comp in components(pre_passable, grid) {
                    let survivors: Vec<TileCoord> =
                        comp.iter_set().filter(|&t| post.get(t)).collect();
                    if survivors.is_empty() {
                        continue; // an isolated pocket eroded away — not a split
                    }
                    let reached = flood(survivors[0], &post, grid);
                    for &s in &survivors {
                        assert!(
                            reached.get(s),
                            "seed {raw_seed:#x} zone {zone_id}: \
                             the pipeline split the zone's passable region",
                        );
                    }
                }
            }
        }
        assert!(
            any_river,
            "no seed placed a river — RiverPlacer's end-to-end connectivity coverage is vacuous",
        );
    }

    /// Map-wide passable region (`Walkable ∪ Open`) — the global-connectivity
    /// reference for the AC-8 refinement-R1 end-to-end check.
    fn map_passable(state: &TilemapBuildState, grid: GridSize) -> TileMask {
        let mut m = TileMask::new(grid.width, grid.height);
        for y in 0..grid.height {
            for x in 0..grid.width {
                let t = TileCoord::new(x, y);
                if state.tile_state_at(t).is_passable() {
                    m.set(t);
                }
            }
        }
        m
    }

    #[test]
    fn ace8_river_carve_preserves_map_wide_connectivity_end_to_end() {
        // AC-8 (end-to-end, map-wide) — refinement R1 through the real
        // `place_tilemap` modificator stack. Run every placer up to
        // ObstaclePlacer, snapshot the map-wide passable region, then run
        // RiverPlacer alone and confirm — with an INDEPENDENT flood-fill — that
        // no river carve split the global passable region. ObstaclePlacer's
        // §2.3 Mountain rule places ≥1 mountain per non-Forbidden zone and the
        // fixture's `inland_sea` is a sink, so a river reliably carves.
        let template = fixture();
        let grid = GridSize { width: 64, height: 64 };
        let reg = Registry::load_default().unwrap();
        let mut any_river = false;
        for raw_seed in [0xA11CE_u64, 1, 2, 0xB0B, 0xC0FFEE] {
            let seed = TilemapSeed(raw_seed);
            let tiled = place_zones(&template, grid, seed).expect("place_zones on the fixture");
            let mut state = TilemapBuildState::from_zones(tiled, grid);

            // Half 1 — the pipeline up to (and including) the river source
            // placer, the river's Mountain/Lake tags now placed pre-erosion.
            let mut pre_river = ModificatorRegistry::new();
            pre_river.add(Box::new(TerrainPainter));
            pre_river.add(Box::new(ConnectionsPlacer));
            pre_river.add(Box::new(TreasurePlacer));
            pre_river.add(Box::new(RoadPlacer));
            pre_river.add(Box::new(ObstacleSourcePlacer));
            {
                let mut ctx = ModificatorContext { template: &template, grid, seed, state: &mut state, registry: &reg };
                pre_river.execute(&mut ctx).expect("pre-river pipeline");
            }
            let map_pre = map_passable(&state, grid);

            // Half 2 — RiverPlacer alone, on the same state.
            let mut river = ModificatorRegistry::new();
            river.add(Box::new(RiverPlacer));
            {
                let mut ctx = ModificatorContext { template: &template, grid, seed, state: &mut state, registry: &reg };
                river.execute(&mut ctx).expect("river pipeline");
            }
            any_river |= !state.river_segments.is_empty();

            // Every pre-river passable component that keeps a survivor keeps
            // all its survivors mutually reachable — the river split nothing.
            let map_post = map_passable(&state, grid);
            for comp in components(&map_pre, grid) {
                let survivors: Vec<TileCoord> =
                    comp.iter_set().filter(|&t| map_post.get(t)).collect();
                if survivors.is_empty() {
                    continue;
                }
                let reached = flood(survivors[0], &map_post, grid);
                for &s in &survivors {
                    assert!(
                        reached.get(s),
                        "seed {raw_seed:#x}: a river carve split the map-wide passable region",
                    );
                }
            }
        }
        assert!(any_river, "no seed placed a river — the AC-8 map-wide check is vacuous");
    }

    #[test]
    fn ac7_treasure_pipeline_never_splits_a_zone_passable_region() {
        // AC-7 — connectivity end-to-end for the Phase-C pipeline. After
        // TerrainPainter → TreasurePlacer → ObstaclePlacer, no non-Forbidden
        // zone's passable region (`Walkable ∪ Open`) has been split.
        //
        // Unlike the Phase-B `ac10` test (`place_zones`' per-seed-varying
        // geometry), this fixture is HAND-BUILT with pinned tile counts: a
        // 60×20 grid as three 20×20 columns — two `Wilderness` zones, each
        // carrying a `min ≥ 2000` treasure tier with a wide `[min, max]`
        // (`max` ≫ the pool's total object value, so `compose_pile` succeeds
        // for every seed), plus one `Forbidden` column. The geometry is
        // guard-placeable (`free_paths` along the top edge, a wide `Open`
        // interior), so the pipeline deterministically emits Treasure +
        // MonsterLair records — the `≥ 1` assertions below are robust no-op
        // detectors, not false-RED risks. Verified with the independent
        // flood-fill oracle (`flood` / `components`), as for `ac10`.
        use crate::engine::placement::ZoneTiles;
        use crate::types::object::TilemapObjectKind;
        use crate::types::treasure::TreasureTierSpec;

        let grid = GridSize { width: 60, height: 20 };
        // A hand-built 20-wide column at `x0`: `Wilderness` columns get a
        // top-row `free_paths` skeleton (the rest `Open`); a `Forbidden` column
        // gets none (`from_zones` makes it all-`Obstacle`).
        let column = |id: &str, role: ZoneRole, x0: u32| -> ZoneTiles {
            let mut assigned = TileMask::new(grid.width, grid.height);
            let mut free = TileMask::new(grid.width, grid.height);
            for y in 0..grid.height {
                for x in x0..x0 + 20 {
                    assigned.set(TileCoord::new(x, y));
                }
            }
            if role != ZoneRole::Forbidden {
                for x in x0..x0 + 20 {
                    free.set(TileCoord::new(x, 0));
                }
            }
            ZoneTiles {
                id: ZoneId(id.to_string()),
                role,
                center: TileCoord::new(x0 + 10, 10),
                assigned_tiles: assigned,
                free_paths: free,
            }
        };
        // The matching `ZoneSpec`: a `Wilderness` column carries the wide
        // `min ≥ 2000` tier (density 6 ⇒ target_count 2 per 400-tile column —
        // headroom so a stray placement NoSpace still leaves ≥ 1 guarded pile).
        let spec = |id: &str, role: ZoneRole| -> ZoneSpec {
            let treasure_tiers = if role == ZoneRole::Forbidden {
                vec![]
            } else {
                vec![TreasureTierSpec { min: 2000, max: 30000, density: 6 }]
            };
            ZoneSpec {
                zone_id: ZoneId(id.to_string()),
                zone_role: role,
                size: 100,
                terrain_types: vec![],
                monster_strength: None,
                connections: vec![],
                treasure_tiers,
                biome_selection_rules: None,
                inherit_treasure_from: None,
            }
        };
        let template = TilemapTemplate {
            template_id: TilemapTemplateId("ac7_treasure_connectivity".to_string()),
            zones: vec![
                spec("col_a", ZoneRole::Wilderness),
                spec("col_b", ZoneRole::Wilderness),
                spec("col_c", ZoneRole::Forbidden),
            ],
            seed_offset: 0,
            world_zone: None,
        };

        let reg = Registry::load_default().unwrap();
        for raw_seed in [0xA11CE_u64, 7, 99, 0xC0FFEE] {
            let seed = TilemapSeed(raw_seed);
            let zones = vec![
                column("col_a", ZoneRole::Wilderness, 0),
                column("col_b", ZoneRole::Wilderness, 20),
                column("col_c", ZoneRole::Forbidden, 40),
            ];
            let mut state = TilemapBuildState::from_zones(zones, grid);
            let pre: Vec<TileMask> =
                (0..state.zones.len()).map(|i| state.zone_passable(i)).collect();

            // The same modificator set `place_tilemap` registers. `fixture()`
            // declares no connections, so ConnectionsPlacer only runs §3.1/§9
            // border sealing here — itself `would_seal_a_gap`-gated.
            let mut modificators = ModificatorRegistry::new();
            modificators.add(Box::new(TerrainPainter));
            modificators.add(Box::new(ConnectionsPlacer));
            modificators.add(Box::new(TreasurePlacer));
            modificators.add(Box::new(RoadPlacer));
            modificators.add(Box::new(ObstacleSourcePlacer));
            modificators.add(Box::new(RiverPlacer));
            modificators.add(Box::new(ObstacleFillPlacer));
            {
                let mut ctx = ModificatorContext {
                    template: &template,
                    grid,
                    seed,
                    state: &mut state,
                    registry: &reg,
                };
                modificators.execute(&mut ctx).expect("modificator pipeline");
            }

            // No-op detector — the pipeline genuinely placed Phase-C objects,
            // so the connectivity check below is not vacuously satisfied.
            assert!(
                state.object_placements.iter().any(|p| p.kind == TilemapObjectKind::Treasure),
                "seed {raw_seed:#x}: AC-7 placed no Treasure — connectivity check vacuous",
            );
            assert!(
                state.object_placements.iter().any(|p| p.kind == TilemapObjectKind::MonsterLair),
                "seed {raw_seed:#x}: AC-7 placed no MonsterLair — the guard path went untested",
            );

            // Connectivity — no non-Forbidden zone's passable region was split.
            for (i, pre_passable) in pre.iter().enumerate() {
                if state.zones[i].role == ZoneRole::Forbidden {
                    continue; // a Forbidden zone is all-Obstacle — no passable region
                }
                let zone_id = &state.zones[i].id.0;
                let post = state.zone_passable(i);
                assert!(
                    !post.is_empty(),
                    "seed {raw_seed:#x} zone {zone_id}: the pipeline sealed the entire zone",
                );
                for comp in components(pre_passable, grid) {
                    let survivors: Vec<TileCoord> =
                        comp.iter_set().filter(|&t| post.get(t)).collect();
                    if survivors.is_empty() {
                        continue; // an isolated pocket eroded away — not a split
                    }
                    let reached = flood(survivors[0], &post, grid);
                    for &s in &survivors {
                        assert!(
                            reached.get(s),
                            "seed {raw_seed:#x} zone {zone_id}: the Phase-C pipeline \
                             split the zone's passable region",
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn ac2_place_tilemap_with_timings_returns_the_same_view_as_place_tilemap() {
        // AC-2 — DEFERRED #029 instrumentation. The timed variant must produce
        // a `TilemapView` byte-identical to the production `place_tilemap`,
        // and the per-stage timings must cover all 6 modificators in the
        // expected topological order.
        let template = fixture();
        let grid = GridSize { width: 48, height: 48 };
        let plain = place_tilemap(
            &template,
            crate::types::channel::ChannelId("ch".to_string()),
            crate::types::channel::ChannelTier::Country,
            grid,
            TilemapSeed(0xA17_EAD),
        )
        .unwrap();
        let (timed_view, timings) = place_tilemap_with_timings(
            &template,
            crate::types::channel::ChannelId("ch".to_string()),
            crate::types::channel::ChannelTier::Country,
            grid,
            TilemapSeed(0xA17_EAD),
        )
        .unwrap();
        assert_eq!(plain, timed_view, "timing instrumentation must not change the view");
        // 7 modificators in topological order — DEFERRED #026 split the
        // obstacle pass into source (pre-river) + fill (post-river).
        let names: Vec<&str> = timings.modificators.iter().map(|(n, _)| n.as_str()).collect();
        assert_eq!(
            names,
            [
                "terrain_painter",
                "connections_placer",
                "treasure_placer",
                "road_placer",
                "obstacle_source_placer",
                "river_placer",
                "obstacle_fill_placer",
            ],
            "per-modificator timing must list all seven in topological order",
        );
        // Total of per-stage durations should be the bulk of wall time
        // (impossible to assert an exact equality — Instant::now overhead /
        // assemble-zones loop / serialisation aren't timed — but each entry
        // should be a non-negative Duration).
        for (name, d) in &timings.modificators {
            assert!(d.as_nanos() > 0, "modificator {name} reported zero duration");
        }
    }
}
