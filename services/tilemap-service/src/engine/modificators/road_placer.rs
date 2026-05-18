//! TMP_003 §3.4 — `RoadPlacer`: a minimum spanning tree over road anchors
//! (zone centres + connection passages + guard lairs — spec PO-1), each MST
//! edge routed by `search_path` and realised as a `TerrainKind::Road` polyline.
//!
//! Roads paint the terrain layer only — `TileState` is left untouched, so road
//! tiles stay passable (spec finding F-2). RNG-free: determinism by
//! construction (MST + Dijkstra + flat-index iteration order).

use crate::engine::build_state::TilemapBuildState;
use crate::engine::geometry::{minimum_spanning_tree, neighbors4, search_path};
use crate::engine::pipeline::{Modificator, ModificatorContext};
use crate::types::object::TilemapObjectKind;
use crate::types::tile::{TerrainKind, TileCoord};
use crate::types::tile_mask::TileMask;
use crate::types::tilemap::{GridSize, RoadSegment};
use crate::types::zone::ZoneRole;

/// TMP_003 §3.4 `RoadPlacer` — see module docs.
#[derive(Debug)]
pub struct RoadPlacer;

impl Modificator for RoadPlacer {
    fn name(&self) -> &str {
        "road_placer"
    }

    fn dependencies(&self) -> Vec<&str> {
        // TMP_006 §7 step 6 — roads run after connection guards (Pass-2 records
        // `road_nodes`) and treasure guards (`MonsterLair` anchors), and need
        // the painted terrain layer for the road-reuse cost. `ObstaclePlacer`
        // declares `road_placer` itself, so the topo-sort runs Obstacles after.
        vec!["terrain_painter", "connections_placer", "treasure_placer"]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        place_roads(ctx.state, ctx.grid);
        Ok(())
    }
}

/// The road search area: every passable tile **except** `Sea`-role zone tiles —
/// roads do not cross open sea (that is the ferry's job, TMP_007 §7).
fn road_search_area(state: &TilemapBuildState, grid: GridSize) -> TileMask {
    let mut sea = TileMask::new(grid.width, grid.height);
    for zone in &state.zones {
        if zone.role == ZoneRole::Sea {
            sea.union_with(&zone.assigned_tiles);
        }
    }
    let mut area = TileMask::new(grid.width, grid.height);
    for y in 0..grid.height {
        for x in 0..grid.width {
            let t = TileCoord::new(x, y);
            if state.tile_state_at(t).is_passable() && !sea.get(t) {
                area.set(t);
            }
        }
    }
    area
}

/// Spec D-Q1 — the tile `search_path` should actually route from/to for an
/// anchor: the anchor itself if passable, else its lowest-flat-index passable
/// 4-neighbour (`neighbors4` yields flat-index order), else `None` (drop it).
fn routing_proxy(state: &TilemapBuildState, anchor: TileCoord, grid: GridSize) -> Option<TileCoord> {
    if state.tile_state_at(anchor).is_passable() {
        return Some(anchor);
    }
    neighbors4(anchor, grid.width, grid.height).find(|&n| state.tile_state_at(n).is_passable())
}

/// Spec D-Q3 — per-tile road-routing cost (by the destination tile): an
/// already-`Road` tile is cheap so later edges reuse earlier roads; an `Open`
/// tile costs more than a `Walkable` one. `to` is always inside the road search
/// area, so it is passable.
fn road_cost(state: &TilemapBuildState, to: TileCoord, width: u32) -> f32 {
    use crate::types::tile::TileState;
    if state.terrain_layer[to.flat_index(width)] == TerrainKind::Road as u8 {
        0.5
    } else if state.tile_state_at(to) == TileState::Walkable {
        1.0
    } else {
        2.0
    }
}

/// Spec PO-1 — every road anchor: the centre of each non-`Forbidden` zone, every
/// connection-passage tile (`road_nodes`), and every `MonsterLair` anchor.
fn collect_anchors(state: &TilemapBuildState) -> Vec<TileCoord> {
    let mut anchors: Vec<TileCoord> = Vec::new();
    for zone in &state.zones {
        if zone.role != ZoneRole::Forbidden {
            anchors.push(zone.center);
        }
    }
    anchors.extend(state.road_nodes.iter().copied());
    for p in &state.object_placements {
        if p.kind == TilemapObjectKind::MonsterLair {
            anchors.push(p.anchor);
        }
    }
    anchors
}

/// TMP_003 §3.4 — collect anchors, build the MST, route + paint each edge.
pub(crate) fn place_roads(state: &mut TilemapBuildState, grid: GridSize) {
    let width = grid.width;
    let road_area = road_search_area(state, grid);

    // Anchor → routing proxy; keep only proxies inside the road search area
    // (this drops sea-located anchors uniformly). Dedup by flat index so two
    // anchors that proxy to the same tile become one MST node.
    let mut proxies: Vec<TileCoord> = collect_anchors(state)
        .iter()
        .filter_map(|&a| routing_proxy(state, a, grid))
        .filter(|p| road_area.get(*p))
        .collect();
    proxies.sort_by_key(|c| c.flat_index(width));
    proxies.dedup();
    if proxies.len() < 2 {
        return; // AC-13 — nothing to connect
    }

    for (a, b) in minimum_spanning_tree(&proxies) {
        let start = proxies[a];
        let mut goal = TileMask::new(grid.width, grid.height);
        goal.set(proxies[b]);
        // `search_path` borrows `state` immutably via the cost closure and
        // returns an owned path; the borrow ends before we paint below.
        let path = search_path(&road_area, start, &goal, |_, to| road_cost(state, to, width));
        if let Some(path) = path {
            for &t in &path {
                state.terrain_layer[t.flat_index(width)] = TerrainKind::Road as u8;
            }
            state.road_segments.push(RoadSegment { waypoints: path });
        }
        // AC-5 — an edge with no passable route is silently skipped.
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::placement::ZoneTiles;
    use crate::types::object::TilemapObjectPlacement;
    use crate::types::tile::TileState;
    use crate::types::zone::ZoneId;

    fn full_mask(grid: GridSize, pred: impl Fn(u32, u32) -> bool) -> TileMask {
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
            assigned_tiles: full_mask(grid, &in_zone),
            free_paths: TileMask::new(grid.width, grid.height),
        }
    }

    fn lair(at: (u32, u32)) -> TilemapObjectPlacement {
        TilemapObjectPlacement {
            kind: TilemapObjectKind::MonsterLair,
            anchor: TileCoord::new(at.0, at.1),
            canon_ref: None,
            biome_object_type: None,
            value: Some(1),
        }
    }

    #[test]
    fn two_zone_centres_get_one_road_painted_and_left_passable() {
        // AC-3/AC-4 — two zone centres ⇒ one MST edge ⇒ one RoadSegment whose
        // waypoints are painted Road and stay passable.
        let grid = GridSize { width: 9, height: 3 };
        let mut state = TilemapBuildState::from_zones(
            vec![
                zone("a", ZoneRole::Wilderness, grid, (2, 1), |x, _| x < 5),
                zone("b", ZoneRole::Wilderness, grid, (6, 1), |x, _| x >= 5),
            ],
            grid,
        );
        place_roads(&mut state, grid);

        assert_eq!(state.road_segments.len(), 1, "one MST edge ⇒ one road");
        let wp = &state.road_segments[0].waypoints;
        assert_eq!(wp.first().copied(), Some(TileCoord::new(2, 1)));
        assert_eq!(wp.last().copied(), Some(TileCoord::new(6, 1)));
        for &t in wp {
            assert_eq!(
                state.terrain_layer[t.flat_index(grid.width)],
                TerrainKind::Road as u8,
                "waypoint {t:?} must be painted Road",
            );
            assert!(state.tile_state_at(t).is_passable(), "road tile {t:?} stays passable");
        }
    }

    #[test]
    fn routing_proxy_falls_back_to_a_neighbour_and_drops_a_blocked_anchor() {
        // D-Q1 — an Occupied anchor proxies to a passable neighbour; an anchor
        // walled in by Obstacle has no proxy.
        let grid = GridSize { width: 3, height: 3 };
        let mut state = TilemapBuildState::from_zones(
            vec![zone("z", ZoneRole::Wilderness, grid, (1, 1), |_, _| true)],
            grid,
        );
        // Occupy the centre — proxy must fall back to a neighbour (Open).
        state.set_tile_state(TileCoord::new(1, 1), TileState::Occupied);
        assert_eq!(
            routing_proxy(&state, TileCoord::new(1, 1), grid),
            Some(TileCoord::new(1, 0)),
            "lowest-flat-index passable neighbour is (1,0)",
        );
        // Wall the corner (0,0) in: its only neighbours (1,0) and (0,1) Obstacle.
        state.set_tile_state(TileCoord::new(1, 0), TileState::Obstacle);
        state.set_tile_state(TileCoord::new(0, 1), TileState::Obstacle);
        state.set_tile_state(TileCoord::new(0, 0), TileState::Obstacle);
        assert_eq!(routing_proxy(&state, TileCoord::new(0, 0), grid), None);
    }

    #[test]
    fn anchors_separated_by_a_sea_zone_place_no_road() {
        // AC-5 — two land zones with a Sea zone between them and no land route:
        // the road search area excludes the sea, `search_path` fails, no panic.
        let grid = GridSize { width: 9, height: 1 };
        let mut state = TilemapBuildState::from_zones(
            vec![
                zone("a", ZoneRole::Wilderness, grid, (1, 0), |x, _| x < 3),
                zone("sea", ZoneRole::Sea, grid, (4, 0), |x, _| (3..6).contains(&x)),
                zone("b", ZoneRole::Wilderness, grid, (7, 0), |x, _| x >= 6),
            ],
            grid,
        );
        place_roads(&mut state, grid);
        assert!(state.road_segments.is_empty(), "no land route ⇒ no road");
    }

    #[test]
    fn a_single_zone_places_no_road() {
        // AC-13 — one anchor ⇒ < 2 proxies ⇒ no road, no panic.
        let grid = GridSize { width: 5, height: 5 };
        let mut state = TilemapBuildState::from_zones(
            vec![zone("solo", ZoneRole::Wilderness, grid, (2, 2), |_, _| true)],
            grid,
        );
        place_roads(&mut state, grid);
        assert!(state.road_segments.is_empty());
    }

    #[test]
    fn monster_lair_anchors_are_collected_into_the_mst() {
        // AC-3 — a MonsterLair placement is a road anchor. One zone + two lairs
        // ⇒ 3 anchors ⇒ a 2-edge MST ⇒ two road segments.
        let grid = GridSize { width: 9, height: 3 };
        let mut state = TilemapBuildState::from_zones(
            vec![zone("z", ZoneRole::Wilderness, grid, (4, 1), |_, _| true)],
            grid,
        );
        state.object_placements.push(lair((0, 0)));
        state.object_placements.push(lair((8, 2)));
        assert_eq!(collect_anchors(&state).len(), 3, "centre + 2 lairs");
        place_roads(&mut state, grid);
        assert_eq!(state.road_segments.len(), 2, "3 anchors ⇒ 2 MST edges");
    }
}
