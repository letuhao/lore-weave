//! TMP_003 §3.5 — `RiverPlacer`: water flow from mountain-obstacle sources to
//! lake/sea sinks, routed by `search_path` over an elevation-weighted cost.
//!
//! Rivers are **functional barriers** (spec PO-2): a carved river tile is
//! impassable (`TileState::Obstacle` + `Water` terrain). Every carve is gated by
//! `would_seal_a_gap` against **both** the owning zone's passable region **and**
//! the map-wide passable region (spec refinement R1) — a tile whose blocking
//! would split either is kept passable as a **ford**. A river tile that
//! coincides with a road tile is a **bridge**. RNG-free: determinism by
//! construction.

use crate::engine::build_state::TilemapBuildState;
use crate::engine::geometry::{search_path, would_seal_a_gap};
use crate::engine::pipeline::{Modificator, ModificatorContext};
use crate::types::biome::BiomeObjectType;
use crate::types::object::TilemapObjectKind;
use crate::types::tile::{TerrainKind, TileCoord, TileState};
use crate::types::tile_mask::TileMask;
use crate::types::tilemap::{CrossingKind, GridSize, RiverCrossing, RiverSegment};
use crate::types::zone::ZoneRole;

/// A guaranteed crossing every `FORD_INTERVAL` carved tiles, so a long river is
/// never an uncrossable wall (TMP_003 §3.5 step 4).
const FORD_INTERVAL: u32 = 12;

/// TMP_003 §3.5 `RiverPlacer` — see module docs.
#[derive(Debug)]
pub struct RiverPlacer;

impl Modificator for RiverPlacer {
    fn name(&self) -> &str {
        "river_placer"
    }

    fn dependencies(&self) -> Vec<&str> {
        // River runs after ObstacleSourcePlacer (which places the `Mountain`/
        // `Lake` source/sink tags pre-erosion, on the Open zone area — DEFERRED
        // #026) and after RoadPlacer (bridge detection). ObstacleFillPlacer
        // then runs *after* the river, filling the bulk obstacles around it.
        vec!["obstacle_source_placer", "road_placer"]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        place_rivers(ctx.state, ctx.grid);
        Ok(())
    }
}

/// A single-tile mask sized to the grid — the `blocking` argument shape
/// `would_seal_a_gap` expects.
fn single(grid: GridSize, t: TileCoord) -> TileMask {
    let mut m = TileMask::new(grid.width, grid.height);
    m.set(t);
    m
}

/// Spec D-Q5 — one river source per mountain-bearing zone: the lowest-flat-index
/// `Mountain` obstacle anchor in that zone. Returned in source flat-index order.
fn river_sources(state: &TilemapBuildState, grid: GridSize) -> Vec<TileCoord> {
    // best[zone_idx] = the lowest-flat-index mountain anchor seen in that zone.
    let mut best: Vec<Option<TileCoord>> = vec![None; state.zones.len()];
    for p in &state.object_placements {
        if p.kind != TilemapObjectKind::Obstacle
            || p.biome_object_type != Some(BiomeObjectType::Mountain)
        {
            continue;
        }
        if let Some(zi) = state.zones.iter().position(|z| z.assigned_tiles.get(p.anchor)) {
            let flat = p.anchor.flat_index(grid.width);
            if best[zi].is_none_or(|c| flat < c.flat_index(grid.width)) {
                best[zi] = Some(p.anchor);
            }
        }
    }
    let mut sources: Vec<TileCoord> = best.into_iter().flatten().collect();
    sources.sort_by_key(|c| c.flat_index(grid.width));
    sources
}

/// Spec D-Q6 — the river sink mask: every `Lake` obstacle anchor ∪ every tile
/// of every `Sea`-role zone.
fn river_sink_mask(state: &TilemapBuildState, grid: GridSize) -> TileMask {
    let mut sinks = TileMask::new(grid.width, grid.height);
    for p in &state.object_placements {
        if p.kind == TilemapObjectKind::Obstacle
            && p.biome_object_type == Some(BiomeObjectType::Lake)
        {
            sinks.set(p.anchor);
        }
    }
    for zone in &state.zones {
        if zone.role == ZoneRole::Sea {
            sinks.union_with(&zone.assigned_tiles);
        }
    }
    sinks
}

/// Spec D-Q7 — the river search area: every non-`Obstacle` tile, plus the
/// `source` tile and every sink tile (so start + goal are routable).
fn river_search_area(
    state: &TilemapBuildState,
    grid: GridSize,
    source: TileCoord,
    sinks: &TileMask,
) -> TileMask {
    let mut area = TileMask::new(grid.width, grid.height);
    for y in 0..grid.height {
        for x in 0..grid.width {
            let t = TileCoord::new(x, y);
            if state.tile_state_at(t) != TileState::Obstacle {
                area.set(t);
            }
        }
    }
    area.set(source);
    area.union_with(sinks);
    area
}

/// Spec D-Q7 — terrain elevation proxy: the river prefers to descend toward
/// water.
fn elevation_cost(state: &TilemapBuildState, to: TileCoord, width: u32) -> f32 {
    let terrain = state.terrain_layer[to.flat_index(width)];
    if terrain == TerrainKind::Mountain as u8 {
        10.0
    } else if terrain == TerrainKind::Snow as u8 || terrain == TerrainKind::Rough as u8 {
        4.0
    } else if terrain == TerrainKind::Water as u8 {
        0.5
    } else {
        2.0
    }
}

/// The map-wide passable mask (`Walkable ∪ Open`) — the global-connectivity
/// reference for the refinement-R1 carve gate.
fn map_passable_mask(state: &TilemapBuildState, grid: GridSize) -> TileMask {
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

/// TMP_003 §3.5 — route every source to its nearest sink and carve the river.
pub(crate) fn place_rivers(state: &mut TilemapBuildState, grid: GridSize) {
    let width = grid.width;
    let sinks = river_sink_mask(state, grid);
    if sinks.is_empty() {
        return; // AC-13 — nowhere for water to flow
    }
    let max_len = (grid.width + grid.height) as usize;
    // Map-wide passable, maintained incrementally — a carve removes exactly the
    // carved tile.
    let mut map_passable = map_passable_mask(state, grid);

    for source in river_sources(state, grid) {
        // Re-derived per source so river N routes around river <N's carved tiles.
        let area = river_search_area(state, grid, source, &sinks);
        let path = match search_path(&area, source, &sinks, |_, to| elevation_cost(state, to, width)) {
            Some(p) if p.len() <= max_len => p,
            _ => continue, // unreachable, or beyond the Manhattan range cap
        };

        let mut crossings: Vec<RiverCrossing> = Vec::new();
        let mut since_crossing: u32 = 0;
        for &t in &path {
            // The mountain source + the lake/sea sink are recorded but never
            // carved.
            if t == source || sinks.get(t) {
                continue;
            }
            // Bridge — the river runs under an existing road.
            if state.terrain_layer[t.flat_index(width)] == TerrainKind::Road as u8 {
                crossings.push(RiverCrossing { at: t, kind: CrossingKind::Bridge });
                since_crossing = 0;
                continue;
            }
            // Ford — carving `t` would split its owning zone's passable region
            // or the map-wide passable region (refinement R1). A `Forbidden`
            // zone has an empty passable mask, so its per-zone check is a
            // natural false — no special case.
            let zone_pass = state
                .zones
                .iter()
                .position(|z| z.assigned_tiles.get(t))
                .map(|zi| state.zone_passable(zi));
            let blocking = single(grid, t);
            let splits_zone = zone_pass.is_some_and(|zp| would_seal_a_gap(&blocking, &zp));
            let splits_map = would_seal_a_gap(&blocking, &map_passable);
            if splits_zone || splits_map {
                crossings.push(RiverCrossing { at: t, kind: CrossingKind::Ford });
                since_crossing = 0;
                paint_water(state, t, width);
                continue;
            }
            // Every-Nth guaranteed ford on a long river.
            since_crossing += 1;
            if since_crossing >= FORD_INTERVAL {
                crossings.push(RiverCrossing { at: t, kind: CrossingKind::Ford });
                since_crossing = 0;
                paint_water(state, t, width);
                continue;
            }
            // Carve — paint Water; a passable tile drops to `Obstacle`.
            paint_water(state, t, width);
            if state.tile_state_at(t).is_passable() {
                state.set_tile_state(t, TileState::Obstacle);
                map_passable.clear(t);
            }
        }
        state.river_segments.push(RiverSegment { tiles: path, crossings });
    }
}

/// Paint a river tile's terrain `Water`.
fn paint_water(state: &mut TilemapBuildState, t: TileCoord, width: u32) {
    state.terrain_layer[t.flat_index(width)] = TerrainKind::Water as u8;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::geometry::neighbors4;
    use crate::engine::placement::ZoneTiles;
    use crate::types::object::TilemapObjectPlacement;
    use crate::types::zone::ZoneId;

    fn obstacle(at: (u32, u32), kind: BiomeObjectType) -> TilemapObjectPlacement {
        TilemapObjectPlacement {
            kind: TilemapObjectKind::Obstacle,
            anchor: TileCoord::new(at.0, at.1),
            canon_ref: None,
            biome_object_type: Some(kind),
            value: None,
        }
    }

    fn mask(grid: GridSize, pred: impl Fn(u32, u32) -> bool) -> TileMask {
        let mut m = TileMask::new(grid.width, grid.height);
        for y in 0..grid.height {
            for x in 0..grid.width {
                if pred(x, y) {
                    m.set(TileCoord::new(x, y));
                }
            }
        }
        m
    }

    fn zone(id: &str, role: ZoneRole, grid: GridSize, c: (u32, u32), in_zone: impl Fn(u32, u32) -> bool) -> ZoneTiles {
        ZoneTiles {
            id: ZoneId(id.to_string()),
            role,
            center: TileCoord::new(c.0, c.1),
            assigned_tiles: mask(grid, &in_zone),
            free_paths: TileMask::new(grid.width, grid.height),
        }
    }

    /// Independent 4-connected flood-fill from `start` over `region`.
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

    #[test]
    fn sources_are_one_lowest_flat_mountain_per_zone_sinks_span_lake_and_sea() {
        // D-Q5 / D-Q6 — two mountains in one zone collapse to the lower flat
        // index; the sink mask carries the lake anchor and every Sea tile.
        let grid = GridSize { width: 10, height: 3 };
        let mut state = TilemapBuildState::from_zones(
            vec![
                zone("land", ZoneRole::Wilderness, grid, (2, 1), |x, _| x < 7),
                zone("sea", ZoneRole::Sea, grid, (8, 1), |x, _| x >= 7),
            ],
            grid,
        );
        state.object_placements.push(obstacle((5, 2), BiomeObjectType::Mountain));
        state.object_placements.push(obstacle((1, 0), BiomeObjectType::Mountain)); // lower flat
        state.object_placements.push(obstacle((3, 1), BiomeObjectType::Lake));

        let sources = river_sources(&state, grid);
        assert_eq!(sources, vec![TileCoord::new(1, 0)], "lowest-flat mountain in the land zone");
        let sinks = river_sink_mask(&state, grid);
        assert!(sinks.get(TileCoord::new(3, 1)), "the lake anchor is a sink");
        assert!(sinks.get(TileCoord::new(7, 0)), "every Sea tile is a sink");
        assert!(sinks.get(TileCoord::new(9, 2)), "every Sea tile is a sink");
        assert!(!sinks.get(TileCoord::new(0, 0)), "a plain land tile is not a sink");
    }

    #[test]
    fn a_river_carves_obstacle_water_tiles_between_a_mountain_and_a_lake() {
        // AC-7 — a short river deep inside a wide-open zone carves impassable
        // Water tiles. The mountain (4,3) → lake (4,5) sit in the interior of a
        // 9×9 zone, so the 1-tile river stub strands nothing and needs no ford.
        let grid = GridSize { width: 9, height: 9 };
        let mut state = TilemapBuildState::from_zones(
            vec![zone("z", ZoneRole::Wilderness, grid, (4, 4), |_, _| true)],
            grid,
        );
        state.set_tile_state(TileCoord::new(4, 3), TileState::Obstacle); // the mountain tile
        state.set_tile_state(TileCoord::new(4, 5), TileState::Obstacle); // the lake tile
        state.object_placements.push(obstacle((4, 3), BiomeObjectType::Mountain));
        state.object_placements.push(obstacle((4, 5), BiomeObjectType::Lake));

        place_rivers(&mut state, grid);

        assert_eq!(state.river_segments.len(), 1, "one source → one river");
        let seg = &state.river_segments[0];
        assert_eq!(seg.tiles.first().copied(), Some(TileCoord::new(4, 3)), "tiles start at the source");
        let carved: Vec<TileCoord> = seg
            .tiles
            .iter()
            .copied()
            .filter(|&t| {
                t != TileCoord::new(4, 3)
                    && t != TileCoord::new(4, 5)
                    && state.tile_state_at(t) == TileState::Obstacle
            })
            .collect();
        assert!(!carved.is_empty(), "the river carved interior tiles");
        for &t in &carved {
            assert_eq!(
                state.terrain_layer[t.flat_index(grid.width)],
                TerrainKind::Water as u8,
                "carved tile {t:?} painted Water",
            );
        }
        assert!(seg.crossings.is_empty(), "an interior river stub needs no crossing");
    }

    #[test]
    fn a_river_crossing_a_road_records_a_bridge_and_leaves_the_tile_passable() {
        // AC-9 — where the river meets a road tile it bridges, not carves.
        let grid = GridSize { width: 9, height: 3 };
        let mut state = TilemapBuildState::from_zones(
            vec![zone("z", ZoneRole::Wilderness, grid, (4, 1), |_, _| true)],
            grid,
        );
        state.set_tile_state(TileCoord::new(0, 1), TileState::Obstacle);
        state.set_tile_state(TileCoord::new(8, 1), TileState::Obstacle);
        state.object_placements.push(obstacle((0, 1), BiomeObjectType::Mountain));
        state.object_placements.push(obstacle((8, 1), BiomeObjectType::Lake));
        // A road tile straddling the river's straight y=1 path.
        state.terrain_layer[TileCoord::new(4, 1).flat_index(grid.width)] = TerrainKind::Road as u8;

        place_rivers(&mut state, grid);

        let seg = &state.river_segments[0];
        let bridge = seg.crossings.iter().find(|c| c.kind == CrossingKind::Bridge);
        assert_eq!(
            bridge.map(|c| c.at),
            Some(TileCoord::new(4, 1)),
            "the road tile becomes a Bridge crossing",
        );
        assert!(state.tile_state_at(TileCoord::new(4, 1)).is_passable(), "a bridge stays passable");
        assert_eq!(
            state.terrain_layer[TileCoord::new(4, 1).flat_index(grid.width)],
            TerrainKind::Road as u8,
            "a bridge keeps its Road terrain",
        );
    }

    #[test]
    fn a_river_through_an_isthmus_fords_it_and_never_splits_the_zone() {
        // AC-8 (unit) — an hourglass zone joined by the single tile (2,2): the
        // river must ford the isthmus, not carve it. Verified with an
        // independent flood-fill — the zone stays connected.
        let grid = GridSize { width: 5, height: 5 };
        // Zone A — every tile except the row-2 tiles other than (2,2).
        let in_a = |x: u32, y: u32| y != 2 || x == 2;
        let mut state = TilemapBuildState::from_zones(
            vec![
                zone("a", ZoneRole::Wilderness, grid, (2, 1), in_a),
                zone("walls", ZoneRole::Forbidden, grid, (0, 2), |x, y| y == 2 && x != 2),
            ],
            grid,
        );
        state.set_tile_state(TileCoord::new(2, 0), TileState::Obstacle); // mountain
        state.set_tile_state(TileCoord::new(2, 4), TileState::Obstacle); // lake
        state.object_placements.push(obstacle((2, 0), BiomeObjectType::Mountain));
        state.object_placements.push(obstacle((2, 4), BiomeObjectType::Lake));

        let pre_passable = {
            let mut m = TileMask::new(grid.width, grid.height);
            for t in state.zones[0].assigned_tiles.iter_set() {
                if state.tile_state_at(t).is_passable() {
                    m.set(t);
                }
            }
            m
        };

        place_rivers(&mut state, grid);

        let seg = &state.river_segments[0];
        let isthmus = TileCoord::new(2, 2);
        assert!(
            seg.crossings.iter().any(|c| c.at == isthmus && c.kind == CrossingKind::Ford),
            "the isthmus (2,2) must be a Ford — carving it would split zone A",
        );
        assert!(state.tile_state_at(isthmus).is_passable(), "the forded isthmus stays passable");
        // Independent flood-fill — zone A's surviving passable region is one
        // component.
        let post: Vec<TileCoord> = pre_passable
            .iter_set()
            .filter(|&t| state.tile_state_at(t).is_passable())
            .collect();
        let reached = flood(post[0], &{
            let mut m = TileMask::new(grid.width, grid.height);
            for &t in &post {
                m.set(t);
            }
            m
        }, grid);
        for &t in &post {
            assert!(reached.get(t), "the river split zone A's passable region at {t:?}");
        }
    }

    #[test]
    fn a_long_river_gets_periodic_fords() {
        // TMP_003 §3.5 step 4 — a long straight river with no connectivity
        // ford gets a guaranteed crossing every FORD_INTERVAL carved tiles.
        let grid = GridSize { width: 30, height: 3 };
        let mut state = TilemapBuildState::from_zones(
            vec![zone("z", ZoneRole::Wilderness, grid, (15, 1), |_, _| true)],
            grid,
        );
        state.set_tile_state(TileCoord::new(0, 1), TileState::Obstacle);
        state.set_tile_state(TileCoord::new(29, 1), TileState::Obstacle);
        state.object_placements.push(obstacle((0, 1), BiomeObjectType::Mountain));
        state.object_placements.push(obstacle((29, 1), BiomeObjectType::Lake));

        place_rivers(&mut state, grid);

        let seg = &state.river_segments[0];
        let fords = seg.crossings.iter().filter(|c| c.kind == CrossingKind::Ford).count();
        assert_eq!(fords, 2, "28 interior tiles ⇒ a ford at the 12th and 24th");
        assert!(
            seg.crossings.iter().all(|c| c.kind == CrossingKind::Ford),
            "no road in the fixture ⇒ no bridges",
        );
    }

    #[test]
    fn a_bridge_mid_river_resets_the_periodic_ford_counter() {
        // DEFERRED #027 — the every-`FORD_INTERVAL` guaranteed ford and the
        // bridge / connectivity-ford share one `since_crossing` counter. A
        // bridge must RESET it, so the next periodic ford lands FORD_INTERVAL
        // carved tiles *after the bridge*, not after the river start. Fixture:
        // a 30×3 zone (so a y=1 carve never seals — players route via y=0/y=2),
        // a straight river (0,1)→(29,1), a road at (6,1).
        //
        // Counter walk (FORD_INTERVAL = 12): carves x=1..5 (sc 1..5), bridge at
        // x=6 (sc→0), carves x=7..18 (sc 1..12) ⇒ the periodic ford lands at
        // x=18 — NOT x=12 (which is where it would land if the bridge did not
        // reset the counter).
        let grid = GridSize { width: 30, height: 3 };
        let mut state = TilemapBuildState::from_zones(
            vec![zone("z", ZoneRole::Wilderness, grid, (15, 1), |_, _| true)],
            grid,
        );
        state.set_tile_state(TileCoord::new(0, 1), TileState::Obstacle);
        state.set_tile_state(TileCoord::new(29, 1), TileState::Obstacle);
        state.object_placements.push(obstacle((0, 1), BiomeObjectType::Mountain));
        state.object_placements.push(obstacle((29, 1), BiomeObjectType::Lake));
        // A road straddling the straight y=1 river path.
        state.terrain_layer[TileCoord::new(6, 1).flat_index(grid.width)] = TerrainKind::Road as u8;

        place_rivers(&mut state, grid);

        let seg = &state.river_segments[0];
        // Exactly one bridge, at the road.
        let bridges: Vec<TileCoord> = seg
            .crossings
            .iter()
            .filter(|c| c.kind == CrossingKind::Bridge)
            .map(|c| c.at)
            .collect();
        assert_eq!(bridges, vec![TileCoord::new(6, 1)], "one bridge, at the road tile");
        // The periodic ford reset by the bridge: present at x=18, absent at x=12.
        let fords: Vec<u32> = seg
            .crossings
            .iter()
            .filter(|c| c.kind == CrossingKind::Ford)
            .map(|c| c.at.x)
            .collect();
        assert!(fords.contains(&18), "the bridge-reset periodic ford lands at x=18: {fords:?}");
        assert!(
            !fords.contains(&12),
            "a ford at x=12 means the bridge did NOT reset the counter: {fords:?}",
        );
    }

    #[test]
    fn the_map_wide_gate_fords_the_sole_corridor_linking_two_zones() {
        // AC-8 / refinement R1 — a river crossing the single passable tile that
        // links zone A to zone B must FORD it. Carving (2,2) splits neither
        // zone *internally* (it is a leaf of A's passable region), so a
        // per-zone-only gate would carve it and sever A↔B; the map-wide gate
        // catches it. Fixture: a 5×5 grid, A = x0..2, B = x3..4, their mutual
        // border walled to Obstacle except the lone tile (2,2).
        let grid = GridSize { width: 5, height: 5 };
        let mut state = TilemapBuildState::from_zones(
            vec![
                zone("a", ZoneRole::Wilderness, grid, (1, 2), |x, _| x < 3),
                zone("b", ZoneRole::Wilderness, grid, (4, 2), |x, _| x >= 3),
            ],
            grid,
        );
        for wall in [(2, 0), (2, 1), (2, 3), (2, 4)] {
            state.set_tile_state(TileCoord::new(wall.0, wall.1), TileState::Obstacle);
        }
        state.set_tile_state(TileCoord::new(0, 2), TileState::Obstacle); // mountain
        state.set_tile_state(TileCoord::new(4, 2), TileState::Obstacle); // lake
        state.object_placements.push(obstacle((0, 2), BiomeObjectType::Mountain));
        state.object_placements.push(obstacle((4, 2), BiomeObjectType::Lake));

        place_rivers(&mut state, grid);

        let seg = &state.river_segments[0];
        assert!(
            seg.crossings.iter().any(|c| c.at == TileCoord::new(2, 2) && c.kind == CrossingKind::Ford),
            "the sole A↔B corridor (2,2) must be a Ford (the map-wide gate)",
        );
        // Independent flood-fill — a tile in A still reaches a tile in B.
        let map_passable = {
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
        };
        let reached = flood(TileCoord::new(0, 0), &map_passable, grid);
        assert!(
            reached.get(TileCoord::new(4, 4)),
            "the river severed zone A from zone B — the map-wide gate failed",
        );
    }

    #[test]
    fn two_mountain_zones_place_two_deterministic_rivers() {
        // Two mountain-bearing zones ⇒ two rivers in one `place_rivers` call.
        // River 2's search area excludes river 1's carved Obstacle tiles, so
        // the rivers route independently; the whole multi-river run is
        // deterministic (TMP-A4).
        let build = || {
            let grid = GridSize { width: 20, height: 6 };
            let mut state = TilemapBuildState::from_zones(
                vec![
                    zone("a", ZoneRole::Wilderness, grid, (10, 1), |_, y| y < 3),
                    zone("b", ZoneRole::Wilderness, grid, (10, 4), |_, y| y >= 3),
                ],
                grid,
            );
            for (t, k) in [
                ((0, 1), BiomeObjectType::Mountain),
                ((0, 4), BiomeObjectType::Mountain),
                ((19, 1), BiomeObjectType::Lake),
                ((19, 4), BiomeObjectType::Lake),
            ] {
                state.set_tile_state(TileCoord::new(t.0, t.1), TileState::Obstacle);
                state.object_placements.push(obstacle(t, k));
            }
            place_rivers(&mut state, grid);
            state.river_segments
        };
        let first = build();
        assert_eq!(first.len(), 2, "two mountain-bearing zones ⇒ two rivers");
        assert!(first.iter().all(|s| !s.tiles.is_empty()), "each river has tiles");
        assert_eq!(first, build(), "a multi-river run is deterministic");
    }

    #[test]
    fn no_mountains_places_no_river() {
        // AC-13 — a template with no mountain obstacles places no river.
        let grid = GridSize { width: 8, height: 4 };
        let mut state = TilemapBuildState::from_zones(
            vec![zone("sea", ZoneRole::Sea, grid, (4, 2), |_, _| true)],
            grid,
        );
        // A sink exists (the Sea zone) but there is no source.
        place_rivers(&mut state, grid);
        assert!(state.river_segments.is_empty());
    }
}
