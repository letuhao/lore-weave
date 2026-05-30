//! TMP_007 §3 — the `ConnectionsPlacer` modificator (Phase D): the zone-graph
//! edge-realisation layer. Built in TDD chunks — this chunk lands the pure
//! helpers (the terrain-transition rule, the neighbour-border map, the
//! monolith-tile pick, the passage score); the three placement passes follow.

use std::collections::{BTreeMap, HashSet};

use crate::engine::build_state::TilemapBuildState;
use crate::engine::geometry::{Path, neighbors4, search_path, would_seal_a_gap};
use crate::engine::object_manager::choose_guard;
use crate::engine::pipeline::{Modificator, ModificatorContext};
use crate::types::object::{TilemapObjectKind, TilemapObjectPlacement};
use crate::types::template::TilemapTemplate;
use crate::types::tile::{TerrainKind, TileCoord, TileState};
use crate::types::tile_mask::TileMask;
use crate::types::zone::{PassageKind, RoadOption, ZoneRole};

/// TMP_007 §6 / spec D7 — whether two zone terrains may **not** directly border
/// (a Pass-2 direct passage between them is impossible, so the connection falls
/// to Pass 3).
///
/// V1+30d table: a `Subterranean` zone may not directly border a surface
/// terrain — prohibited iff exactly one side is `Subterranean`. (TMP_007 §6's
/// "Snow ↔ Lava" example is moot — `Lava` is not a V1+30d `TerrainKind`.)
pub fn terrain_prohibits_transition(a: TerrainKind, b: TerrainKind) -> bool {
    (a == TerrainKind::Subterranean) ^ (b == TerrainKind::Subterranean)
}

/// Spec D5 — the V1+30d passage-point score: prefer a tile that is uncrowded
/// (far from existing objects) and near both zone centres.
/// `nearest_object_distance(P) − dist(P, self_center) − dist(P, other_center)`;
/// the highest score wins. Pure.
pub fn score_passage_point(
    p: TileCoord,
    self_center: TileCoord,
    other_center: TileCoord,
    nearest_object_distance: f32,
) -> f32 {
    nearest_object_distance - euclidean(p, self_center) - euclidean(p, other_center)
}

/// TMP_007 §3 `collect_neighbour_zones` / spec D5 — for zone `zone_idx`, a map
/// from each **neighbour** zone's index to the border tiles **of `zone_idx`**
/// that are 4-adjacent to that neighbour.
///
/// Keys iterate in ascending zone-index order (`BTreeMap`); each tile list is
/// flat-index ascending and de-duplicated (a tile touching the same neighbour
/// from two sides is listed once) — so the result is fully deterministic.
pub fn neighbour_border_map(
    state: &TilemapBuildState,
    zone_idx: usize,
) -> BTreeMap<usize, Vec<TileCoord>> {
    let grid = state.grid;
    let mut map: BTreeMap<usize, Vec<TileCoord>> = BTreeMap::new();
    for tile in state.zones[zone_idx].assigned_tiles.iter_set() {
        // Per tile, record it at most once under each distinct neighbour zone.
        let mut recorded: Vec<usize> = Vec::new();
        for nb in neighbors4(tile, grid.width, grid.height) {
            let Some(adj) = zone_at(state, nb) else {
                continue;
            };
            if adj == zone_idx || recorded.contains(&adj) {
                continue;
            }
            recorded.push(adj);
            map.entry(adj).or_default().push(tile);
        }
    }
    map
}

/// Spec D4 — a deterministic interior monolith tile for zone `zone_idx`: a
/// non-edge `Open` tile maximising `nearest_object_distance` (uncrowded), with
/// a lowest-flat-index tie-break. Falls back to *any* `Open` tile if the zone
/// has no non-edge `Open` tile; `None` only when the zone has no `Open` tile.
pub fn monolith_tile(state: &TilemapBuildState, zone_idx: usize) -> Option<TileCoord> {
    let width = state.grid.width;
    let open = state.zone_area_open(zone_idx);
    // `pick(false)` restricts to non-edge tiles; `pick(true)` is the fallback.
    let pick = |allow_edge: bool| -> Option<TileCoord> {
        open.iter_set()
            .filter(|&t| allow_edge || !is_edge(t, state))
            .max_by(|&a, &b| {
                let da = state.nearest_object_distance[a.flat_index(width)];
                let db = state.nearest_object_distance[b.flat_index(width)];
                // (distance desc, flat asc): on an equal distance the
                // lower-flat tile ranks strictly greater, so `max_by` — which
                // returns the last of equally-maximum elements — still lands
                // on the lowest flat index.
                da.total_cmp(&db)
                    .then_with(|| b.flat_index(width).cmp(&a.flat_index(width)))
            })
    };
    pick(false).or_else(|| pick(true))
}

/// Euclidean distance between two tiles.
fn euclidean(a: TileCoord, b: TileCoord) -> f32 {
    let dx = a.x as f32 - b.x as f32;
    let dy = a.y as f32 - b.y as f32;
    (dx * dx + dy * dy).sqrt()
}

/// Whether `tile` lies on the grid border.
fn is_edge(tile: TileCoord, state: &TilemapBuildState) -> bool {
    tile.x == 0
        || tile.y == 0
        || tile.x + 1 == state.grid.width
        || tile.y + 1 == state.grid.height
}

/// The index of the zone owning `tile`, or `None` if no zone does.
fn zone_at(state: &TilemapBuildState, tile: TileCoord) -> Option<usize> {
    state.zones.iter().position(|z| z.assigned_tiles.get(tile))
}

/// TMP_007 §3 — `ConnectionsPlacer`: realises each author zone-connection as a
/// physical passage (a monolith pair, a direct corridor, or a water ferry).
#[derive(Debug)]
pub struct ConnectionsPlacer;

impl Modificator for ConnectionsPlacer {
    fn name(&self) -> &str {
        "connections_placer"
    }

    fn dependencies(&self) -> Vec<&str> {
        // TerrainPainter paints terrain first (the §6 transition check and
        // `choose_guard` read it). `TreasurePlacer` / `ObstaclePlacer` already
        // declare `connections_placer` in their own dependencies, so the Kahn
        // topo-sort runs Connections first among the placers (TMP_006 §7).
        vec!["terrain_painter"]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        let edges = collect_edges(ctx.template, ctx.state);
        // §4.1 mutual-completion dedup — a canonicalised zone-pair realised
        // once across all three passes (the single-threaded replacement for
        // TMP_007 §4's dining-philosopher mutex — roadmap §6).
        let mut completed: HashSet<(usize, usize)> = HashSet::new();
        let mut monolith_counter: u32 = 0;
        let mut water_route_zones: HashSet<usize> = HashSet::new();

        // Pass 1 — Portal connections → monolith pairs (D4).
        for edge in &edges {
            if edge.kind == PassageKind::Portal
                && completed.insert(canonical_pair(edge.a, edge.b))
            {
                place_monolith_pair(ctx.state, edge.a, edge.b, &mut monolith_counter, ctx.registry);
            }
        }

        // Pass 2 — direct passages between bordering zones (D5).
        for edge in &edges {
            if edge.kind == PassageKind::Portal {
                continue; // realised in Pass 1
            }
            let pair = canonical_pair(edge.a, edge.b);
            if !completed.contains(&pair) && place_direct_passage(ctx.state, edge, ctx.registry) {
                completed.insert(pair);
            }
        }

        // Pass 3 — indirect: a water route when a Sea zone lies between the
        // zones, else a monolith pair (the always-succeeds fallback — so every
        // connection is realised, D6). A `Threshold`'s `guard_strength` is not
        // carried here — a Pass-3 monolith pair / ferry is an unguarded
        // teleport-or-ferry crossing by design (only a Pass-2 direct corridor
        // is guarded). AC-6 covers this.
        for edge in &edges {
            if edge.kind == PassageKind::Portal {
                continue;
            }
            let pair = canonical_pair(edge.a, edge.b);
            if completed.contains(&pair) {
                continue;
            }
            if place_water_route(ctx.state, edge.a, edge.b, ctx.registry) {
                water_route_zones.insert(edge.a);
                water_route_zones.insert(edge.b);
            } else {
                place_monolith_pair(ctx.state, edge.a, edge.b, &mut monolith_counter, ctx.registry);
            }
            completed.insert(pair);
        }

        // §3.1 border separation + §9 coast sealing (D9).
        seal_borders(ctx.state, &water_route_zones);
        Ok(())
    }
}

/// A zone-connection edge to realise — `a` / `b` are the two zones' indices.
struct Edge {
    a: usize,
    b: usize,
    kind: PassageKind,
    guard_strength: u32,
    road: RoadOption,
}

/// Gather every realisable zone-connection edge. `Hint` / `Adversarial`
/// connections place nothing physical (D3); a dangling `to_zone` or a
/// self-connection is skipped.
fn collect_edges(template: &TilemapTemplate, state: &TilemapBuildState) -> Vec<Edge> {
    let mut edges = Vec::new();
    for (a, zone) in state.zones.iter().enumerate() {
        let Some(spec) = template.zones.iter().find(|z| z.zone_id == zone.id) else {
            continue;
        };
        for conn in &spec.connections {
            if matches!(conn.kind, PassageKind::Hint | PassageKind::Adversarial) {
                continue;
            }
            let Some(b) = state.zones.iter().position(|z| z.id == conn.to_zone) else {
                continue;
            };
            if a != b {
                edges.push(Edge {
                    a,
                    b,
                    kind: conn.kind,
                    guard_strength: conn.guard_strength,
                    road: conn.road,
                });
            }
        }
    }
    edges
}

/// The order-independent key for a zone pair — the §4.1 dedup key.
fn canonical_pair(a: usize, b: usize) -> (usize, usize) {
    (a.min(b), a.max(b))
}

/// TMP_007 §3 Pass 1 / §8 / spec D4 — place a teleport monolith pair: one
/// `Monolith` object carrying a shared `pair_id` in each zone. Always succeeds
/// (every zone has at least one tile).
fn place_monolith_pair(
    state: &mut TilemapBuildState,
    a: usize,
    b: usize,
    counter: &mut u32,
    registry: &crate::registry::Registry,
) {
    let pair_id = *counter;
    *counter += 1;
    for zone_idx in [a, b] {
        if let Some(tile) = monolith_target(state, zone_idx) {
            place_connection_object(state, tile, TilemapObjectKind::Monolith, Some(pair_id), registry);
        }
    }
}

/// A gap-safe monolith tile for `zone_idx`. For a zone with `Open` area: the
/// chunk-2 `monolith_tile` pick (uncrowded interior) if placing there does not
/// seal a gap, else the first flat-order `Open` tile that is gap-safe. For a
/// `Forbidden` zone (all-`Obstacle`, no passable region) a non-edge `Obstacle`
/// tile — TMP_007 §2: a Forbidden zone is Portal-only-enterable, so its
/// monolith still needs a home.
fn monolith_target(state: &TilemapBuildState, zone_idx: usize) -> Option<TileCoord> {
    let open = state.zone_area_open(zone_idx);
    if !open.is_empty() {
        let passable = state.zone_passable(zone_idx);
        let mut footprint = TileMask::new(state.grid.width, state.grid.height);
        let preferred = monolith_tile(state, zone_idx);
        for t in preferred.into_iter().chain(open.iter_set()) {
            footprint.set(t);
            let seals = would_seal_a_gap(&footprint, &passable);
            footprint.clear(t);
            if !seals {
                return Some(t);
            }
        }
        // Every `Open` tile would seal a gap — a degenerate zone (e.g. 1-wide)
        // in which every tile is a cut-vertex. This is the one place
        // ConnectionsPlacer may seal a gap: D4 chooses AC-8 (realise the
        // connection) over AC-10 (never seal a gap), since an unrealised
        // connection is the worse outcome. Documented as the AC-10 carve-out;
        // unreachable from `place_zones` geometry (no zone is this thin).
        return preferred.or_else(|| open.iter_set().next());
    }
    let obstacle = state.zone_obstacle(zone_idx);
    obstacle
        .iter_set()
        .find(|&t| !is_edge(t, state))
        .or_else(|| obstacle.iter_set().next())
}

/// Place a 1×1 connection object at `tile`: mark it `Occupied`, append the
/// placement record, and refresh the map-wide nearest-object-distance oracle so
/// the downstream placers space against it (mirrors `place_and_connect_object`).
fn place_connection_object(
    state: &mut TilemapBuildState,
    tile: TileCoord,
    kind: TilemapObjectKind,
    value: Option<u32>,
    registry: &crate::registry::Registry,
) {
    state.set_tile_state(tile, TileState::Occupied);
    let v2 = registry.resolve_object_v2(kind, None);
    state.object_placements.push(TilemapObjectPlacement {
        kind,
        anchor: tile,
        canon_ref: None,
        biome_object_type: None,
        value,
        primitive: Some(v2.primitive),
        tag: Some(v2.tag),
        footprint: Some(v2.footprint),
        orientation: None,
        family: None,
        properties: serde_json::Value::Null,
    });
    let grid = state.grid;
    for y in 0..grid.height {
        for x in 0..grid.width {
            let here = TileCoord::new(x, y);
            let d = euclidean(here, tile);
            let idx = here.flat_index(grid.width);
            if d < state.nearest_object_distance[idx] {
                state.nearest_object_distance[idx] = d;
            }
        }
    }
}

/// TMP_007 §3 Pass 2 / spec D5 — realise a direct passage for `edge` between
/// two bordering zones. Returns `true` on success; `false` (leaving the
/// connection for Pass 3) if the terrains forbid a transition, the zones do
/// not share a border, no candidate passage point survives, or a path search
/// fails.
fn place_direct_passage(
    state: &mut TilemapBuildState,
    edge: &Edge,
    registry: &crate::registry::Registry,
) -> bool {
    let terrain_a = state.zone_terrain[edge.a]
        .expect("TerrainPainter runs before ConnectionsPlacer (dependency edge)");
    let terrain_b = state.zone_terrain[edge.b]
        .expect("TerrainPainter runs before ConnectionsPlacer (dependency edge)");
    // §6 — a prohibited terrain transition cannot be a direct passage.
    if terrain_prohibits_transition(terrain_a, terrain_b) {
        return false;
    }
    // Candidate passage points: zone `a`'s border tiles 4-adjacent to `b`.
    let border = neighbour_border_map(state, edge.a);
    let Some(candidates) = border.get(&edge.b) else {
        return false; // the zones do not share a border
    };
    let Some(p) = best_passage_point(state, edge.a, edge.b, candidates) else {
        return false;
    };
    // Both corridor halves must route — a passage joined on only one side is
    // no connection.
    let Some(our_path) = path_to_free_paths(state, edge.a, p) else {
        return false;
    };
    let Some(their_path) = path_to_free_paths(state, edge.b, p) else {
        return false;
    };
    // Attach the corridor first (`Open → Walkable`) so the guard, placed next,
    // picks an `Open` tile *beside* the now-`Walkable` corridor — never on it.
    attach_walkable_path(state, &our_path);
    attach_walkable_path(state, &their_path);
    // §2 — only a `Threshold` passage is guarded; an `Open` border never is.
    if edge.kind == PassageKind::Threshold && edge.guard_strength > 0 {
        place_connection_guard(state, edge.a, p, edge.guard_strength, registry);
    }
    if edge.road != RoadOption::False {
        state.road_nodes.push(p);
    }
    true
}

/// Spec D5 — the best passage point among `candidates` (zone `a`'s border
/// tiles adjacent to `b`): reject a 3-way junction, a crowded tile, or one
/// failing the safety check; score the survivors; return the highest. The
/// strict `>` keeps the first (lowest-flat — `candidates` is flat-ascending)
/// on a score tie.
fn best_passage_point(
    state: &TilemapBuildState,
    a: usize,
    b: usize,
    candidates: &[TileCoord],
) -> Option<TileCoord> {
    let width = state.grid.width;
    let self_center = state.zones[a].center;
    let other_center = state.zones[b].center;
    let mut best: Option<(TileCoord, f32)> = None;
    for &p in candidates {
        // `p` must itself be passable — a corridor routes *through* it. A
        // non-passable candidate is already excluded incidentally (a Forbidden
        // zone fails `passage_is_safe`; an `Occupied` tile reads
        // `nearest_object_distance == 0` and fails the crowding check below),
        // but the explicit guard keeps the invariant robust under future
        // tuning of those checks.
        if !state.tile_state_at(p).is_passable() {
            continue;
        }
        // Reject a 3-way junction — `p` 4-touches a zone other than `a` / `b`.
        let three_way = neighbors4(p, width, state.grid.height)
            .any(|n| zone_at(state, n).is_some_and(|z| z != a && z != b));
        if three_way {
            continue;
        }
        // Reject a crowded tile (TMP_007 §3 — too close to existing objects).
        let dist = state.nearest_object_distance[p.flat_index(width)];
        if dist <= 3.0 {
            continue;
        }
        if !passage_is_safe(state, p, a, b) {
            continue;
        }
        let score = score_passage_point(p, self_center, other_center, dist);
        if best.is_none_or(|(_, bs)| score > bs) {
            best = Some((p, score));
        }
    }
    best.map(|(p, _)| p)
}

/// Spec D5 safety check — `p` must have a passable 4-neighbour inside zone `a`
/// **and** one inside zone `b`, so a corridor can route to each zone's
/// free_paths through it.
fn passage_is_safe(state: &TilemapBuildState, p: TileCoord, a: usize, b: usize) -> bool {
    let mut touches_a = false;
    let mut touches_b = false;
    for n in neighbors4(p, state.grid.width, state.grid.height) {
        if !state.tile_state_at(n).is_passable() {
            continue;
        }
        match zone_at(state, n) {
            Some(z) if z == a => touches_a = true,
            Some(z) if z == b => touches_b = true,
            _ => {}
        }
    }
    touches_a && touches_b
}

/// Spec D-Q6 — `search_path` (uniform cost) from the passage point `p` to the
/// nearest `free_paths` tile of zone `zone_idx`, over that zone's passable area
/// plus `p` (so `p` bridges in even when it belongs to the other zone). `None`
/// if no `free_paths` tile is reachable.
fn path_to_free_paths(state: &TilemapBuildState, zone_idx: usize, p: TileCoord) -> Option<Path> {
    let mut area = state.zone_passable(zone_idx);
    area.set(p);
    search_path(&area, p, &state.zones[zone_idx].free_paths, |_, _| 1.0)
}

/// TMP_007 §5 — attach a routed corridor: each `Open` path tile becomes
/// `Walkable`, and every path tile joins its zone's `free_paths` skeleton.
fn attach_walkable_path(state: &mut TilemapBuildState, path: &[TileCoord]) {
    for &t in path {
        if state.tile_state_at(t) == TileState::Open {
            state.set_tile_state(t, TileState::Walkable);
        }
        if let Some(z) = zone_at(state, t) {
            state.zones[z].free_paths.set(t);
        }
    }
}

/// Spec D5 / D10 — place a `MonsterLair` connection guard on a gap-safe `Open`
/// tile 4-adjacent to the passage point `p`, inside zone `zone_idx`. If no
/// gap-safe `Open` neighbour exists the passage is left unguarded — valid; an
/// unguarded crossing is still a crossing.
fn place_connection_guard(
    state: &mut TilemapBuildState,
    zone_idx: usize,
    p: TileCoord,
    strength: u32,
    registry: &crate::registry::Registry,
) {
    let terrain = state.zone_terrain[zone_idx]
        .expect("TerrainPainter runs before ConnectionsPlacer (dependency edge)");
    let guard = choose_guard(terrain, strength);
    let grid = state.grid;
    let open = state.zone_area_open(zone_idx);
    let passable = state.zone_passable(zone_idx);
    let mut footprint = TileMask::new(grid.width, grid.height);
    for n in neighbors4(p, grid.width, grid.height) {
        if !open.get(n) {
            continue; // not an `Open` tile of this zone
        }
        footprint.set(n);
        let seals = would_seal_a_gap(&footprint, &passable);
        footprint.clear(n);
        if !seals {
            place_connection_object(state, n, TilemapObjectKind::MonsterLair, Some(guard.strength), registry);
            return;
        }
    }
}

/// TMP_007 §3 Pass 3 / §7 / spec D8 — realise a connection between two
/// non-bordering zones by a water-route ferry. Returns `true` on success;
/// `false` (so the caller falls back to a monolith pair) when there is no Sea
/// zone, a zone has no gap-safe shore, or no navigable route links the shores.
fn place_water_route(
    state: &mut TilemapBuildState,
    a: usize,
    b: usize,
    registry: &crate::registry::Registry,
) -> bool {
    let Some(sea) = state.zones.iter().position(|z| z.role == ZoneRole::Sea) else {
        return false;
    };
    let shore_a = gap_safe_shore(state, a, sea);
    let shore_b = gap_safe_shore(state, b, sea);
    let Some(start) = shore_a.iter_set().next() else {
        return false; // zone `a` has no gap-safe shore on this Sea
    };
    if shore_b.is_empty() {
        return false; // zone `b` has no gap-safe shore on this Sea
    }
    // Confirm a navigable route shore_a → Sea water → shore_b exists.
    let mut area = state.zone_passable(sea);
    area.union_with(&shore_a);
    area.union_with(&shore_b);
    let Some(path) = search_path(&area, start, &shore_b, |_, _| 1.0) else {
        return false;
    };
    let end = *path.last().expect("a found water route ends at a shore tile");
    // V1+30d: a ferry crossing at each shore — click → instant transit. The Sea
    // route itself is not marked (the ferry teleports; nothing walks the
    // water), so the Sea zone's own passable region is left intact.
    place_connection_object(state, start, TilemapObjectKind::Ferry, None, registry);
    place_connection_object(state, end, TilemapObjectKind::Ferry, None, registry);
    true
}

/// The **gap-safe** shore tiles of zone `zone_idx`: its `Open` tiles 4-adjacent
/// to a tile of Sea zone `sea_idx` whose removal would not split the zone's
/// passable region — so a ferry placed on one cannot seal a gap.
fn gap_safe_shore(state: &TilemapBuildState, zone_idx: usize, sea_idx: usize) -> TileMask {
    let grid = state.grid;
    let open = state.zone_area_open(zone_idx);
    let passable = state.zone_passable(zone_idx);
    let sea = &state.zones[sea_idx].assigned_tiles;
    let mut shore = TileMask::new(grid.width, grid.height);
    let mut footprint = TileMask::new(grid.width, grid.height);
    for t in open.iter_set() {
        if !neighbors4(t, grid.width, grid.height).any(|n| sea.get(n)) {
            continue; // not a shore tile
        }
        footprint.set(t);
        let seals = would_seal_a_gap(&footprint, &passable);
        footprint.clear(t);
        if !seals {
            shore.set(t);
        }
    }
    shore
}

/// TMP_007 §3.1 + §9 / spec D9 — seal the `Open` border tiles of every non-Sea
/// zone: a land-land border always (§3.1 separation), a sea-facing coast only
/// when the zone has **no** water-route connection (§9 — a water-route zone
/// keeps its shore open). Each seal is `would_seal_a_gap`-gated against the
/// running passable mask, so it never disconnects a zone; only `Open` tiles are
/// sealed, so a realised passage corridor (`Walkable`) is preserved.
fn seal_borders(state: &mut TilemapBuildState, water_route_zones: &HashSet<usize>) {
    let grid = state.grid;
    for zone_idx in 0..state.zones.len() {
        if state.zones[zone_idx].role == ZoneRole::Sea {
            continue; // a Sea zone's edge is the other zones' coast
        }
        let open = state.zone_area_open(zone_idx);
        let mut passable = state.zone_passable(zone_idx);
        let mut footprint = TileMask::new(grid.width, grid.height);
        let has_water_route = water_route_zones.contains(&zone_idx);
        for t in open.iter_set() {
            // Seal `t` iff it 4-touches another land zone (§3.1), or a Sea zone
            // while this zone has no water route (§9).
            let mut seal = false;
            for n in neighbors4(t, grid.width, grid.height) {
                match zone_at(state, n) {
                    Some(z) if z == zone_idx => {}
                    Some(z) if state.zones[z].role == ZoneRole::Sea => {
                        seal |= !has_water_route;
                    }
                    Some(_) => seal = true,
                    None => {}
                }
            }
            if !seal {
                continue;
            }
            footprint.set(t);
            let seals_gap = would_seal_a_gap(&footprint, &passable);
            footprint.clear(t);
            if !seals_gap {
                state.set_tile_state(t, TileState::Obstacle);
                passable.clear(t); // keep the running mask in sync (sequential)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::placement::ZoneTiles;
    use crate::seed::TilemapSeed;
    use crate::types::template::{TemplateConnection, TilemapTemplateId, ZoneSpec};
    use crate::types::tilemap::GridSize;
    use crate::types::zone::ZoneId;

    /// A single `Wilderness` zone covering a `w × h` grid (no `free_paths`, so
    /// every tile is `Open`).
    fn solo_zone_state(w: u32, h: u32) -> TilemapBuildState {
        let mut assigned = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                assigned.set(TileCoord::new(x, y));
            }
        }
        let zone = ZoneTiles {
            id: ZoneId("z".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(w / 2, h / 2),
            assigned_tiles: assigned,
            free_paths: TileMask::new(w, h),
        };
        TilemapBuildState::from_zones(vec![zone], GridSize { width: w, height: h })
    }

    /// A `w × h` grid split into two `Wilderness` columns — zone 0 is `x < w/2`,
    /// zone 1 is `x ≥ w/2`.
    fn two_column_state(w: u32, h: u32) -> TilemapBuildState {
        let mut left = TileMask::new(w, h);
        let mut right = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                if x < w / 2 {
                    left.set(TileCoord::new(x, y));
                } else {
                    right.set(TileCoord::new(x, y));
                }
            }
        }
        let zone = |id: &str, x: u32, tiles: TileMask| ZoneTiles {
            id: ZoneId(id.to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(x, h / 2),
            assigned_tiles: tiles,
            free_paths: TileMask::new(w, h),
        };
        TilemapBuildState::from_zones(
            vec![zone("left", w / 4, left), zone("right", 3 * w / 4, right)],
            GridSize { width: w, height: h },
        )
    }

    /// A two-zone template — `from` has one connection (`kind`,
    /// `guard_strength`, road `True`) to `to`.
    fn template_with_connection(
        from: &str,
        to: &str,
        kind: PassageKind,
        guard_strength: u32,
    ) -> TilemapTemplate {
        let spec = |id: &str, conns: Vec<TemplateConnection>| ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns,
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        };
        TilemapTemplate {
            template_id: TilemapTemplateId("connections_test".to_string()),
            zones: vec![
                spec(
                    from,
                    vec![TemplateConnection {
                        to_zone: ZoneId(to.to_string()),
                        kind,
                        guard_strength,
                        road: RoadOption::True,
                    }],
                ),
                spec(to, vec![]),
            ],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
            decoration_family_density: None,
        }
    }

    /// Run `ConnectionsPlacer` over `state` with `template`.
    fn run_connections(state: &mut TilemapBuildState, template: &TilemapTemplate) {
        let grid = state.grid;
        let reg = crate::registry::Registry::load_default().unwrap();
        let mut ctx = ModificatorContext {
            template,
            grid,
            seed: TilemapSeed(1),
            state,
            registry: &reg,
        };
        ConnectionsPlacer
            .process(&mut ctx)
            .expect("ConnectionsPlacer::process must not error");
    }

    /// A `w × h` grid as two `Wilderness` columns (zone 0 `x < w/2`, zone 1
    /// else); each zone's `free_paths` is its outer-edge column; `zone_terrain`
    /// is pre-set so `place_direct_passage` can read it.
    fn bordering_zones(w: u32, h: u32) -> TilemapBuildState {
        let mut left = TileMask::new(w, h);
        let mut right = TileMask::new(w, h);
        let mut left_free = TileMask::new(w, h);
        let mut right_free = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                if x < w / 2 {
                    left.set(TileCoord::new(x, y));
                    if x == 0 {
                        left_free.set(TileCoord::new(x, y));
                    }
                } else {
                    right.set(TileCoord::new(x, y));
                    if x == w - 1 {
                        right_free.set(TileCoord::new(x, y));
                    }
                }
            }
        }
        let zone = |id: &str, cx: u32, tiles: TileMask, free: TileMask| ZoneTiles {
            id: ZoneId(id.to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(cx, h / 2),
            assigned_tiles: tiles,
            free_paths: free,
        };
        let mut state = TilemapBuildState::from_zones(
            vec![
                zone("left", w / 4, left, left_free),
                zone("right", 3 * w / 4, right, right_free),
            ],
            GridSize { width: w, height: h },
        );
        state.zone_terrain.fill(Some(TerrainKind::Grass));
        state
    }

    /// Whether a 4-connected path of `Walkable` tiles links `from` to `to`.
    fn walkable_reaches(state: &TilemapBuildState, from: TileCoord, to: TileCoord) -> bool {
        if state.tile_state_at(from) != TileState::Walkable {
            return false;
        }
        let grid = state.grid;
        let mut seen = TileMask::new(grid.width, grid.height);
        seen.set(from);
        let mut stack = vec![from];
        while let Some(t) = stack.pop() {
            for n in neighbors4(t, grid.width, grid.height) {
                if state.tile_state_at(n) == TileState::Walkable && !seen.get(n) {
                    seen.set(n);
                    stack.push(n);
                }
            }
        }
        seen.get(to)
    }

    /// A `w × h` grid as three columns — `left` (`Wilderness`), `middle` (`Sea`
    /// if `middle_is_sea`, else `Wilderness`), `right` (`Wilderness`). `left`
    /// and `right` share no border. `zone_terrain` is pre-set.
    fn three_zones(w: u32, h: u32, middle_is_sea: bool) -> TilemapBuildState {
        let third = w / 3;
        let mut left = TileMask::new(w, h);
        let mut middle = TileMask::new(w, h);
        let mut right = TileMask::new(w, h);
        let mut left_free = TileMask::new(w, h);
        let mut right_free = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                let t = TileCoord::new(x, y);
                if x < third {
                    left.set(t);
                    if x == 0 {
                        left_free.set(t);
                    }
                } else if x < 2 * third {
                    middle.set(t);
                } else {
                    right.set(t);
                    if x == w - 1 {
                        right_free.set(t);
                    }
                }
            }
        }
        let zone = |id: &str, role: ZoneRole, cx: u32, tiles: TileMask, free: TileMask| ZoneTiles {
            id: ZoneId(id.to_string()),
            role,
            center: TileCoord::new(cx, h / 2),
            assigned_tiles: tiles,
            free_paths: free,
        };
        let mid_role = if middle_is_sea { ZoneRole::Sea } else { ZoneRole::Wilderness };
        let mut state = TilemapBuildState::from_zones(
            vec![
                zone("left", ZoneRole::Wilderness, third / 2, left, left_free),
                zone("middle", mid_role, w / 2, middle, TileMask::new(w, h)),
                zone("right", ZoneRole::Wilderness, w - third / 2, right, right_free),
            ],
            GridSize { width: w, height: h },
        );
        state.zone_terrain.fill(Some(TerrainKind::Grass));
        state
    }

    #[test]
    fn terrain_prohibits_only_subterranean_to_surface() {
        // D7 — a Subterranean↔surface transition is prohibited; like-to-like
        // (incl. Subterranean↔Subterranean) and surface↔surface are allowed.
        use TerrainKind::*;
        assert!(terrain_prohibits_transition(Subterranean, Grass));
        assert!(terrain_prohibits_transition(Forest, Subterranean));
        assert!(!terrain_prohibits_transition(Subterranean, Subterranean));
        assert!(!terrain_prohibits_transition(Grass, Water));
        assert!(!terrain_prohibits_transition(Snow, Mountain));
    }

    #[test]
    fn score_passage_point_prefers_uncrowded_and_central() {
        // D5 — a higher nearest-object distance and a smaller centre distance
        // both raise the score.
        let self_c = TileCoord::new(0, 0);
        let other_c = TileCoord::new(10, 0);
        let central_open = score_passage_point(TileCoord::new(5, 0), self_c, other_c, 8.0);
        let central_crowded = score_passage_point(TileCoord::new(5, 0), self_c, other_c, 1.0);
        let off_centre_open = score_passage_point(TileCoord::new(5, 9), self_c, other_c, 8.0);
        assert!(central_open > central_crowded, "an uncrowded point must score higher");
        assert!(central_open > off_centre_open, "a central point must score higher");
    }

    #[test]
    fn neighbour_border_map_records_border_tiles_per_neighbour() {
        // D5 — zone 0's border with zone 1 is exactly its column-2 tiles
        // (each 4-adjacent to a zone-1 tile at x=3).
        let state = two_column_state(6, 2);
        let map = neighbour_border_map(&state, 0);
        assert_eq!(map.len(), 1, "zone 0 has exactly one neighbour");
        assert_eq!(
            map[&1],
            vec![TileCoord::new(2, 0), TileCoord::new(2, 1)],
            "zone 0's border-with-1 tiles, flat-index ascending",
        );
    }

    #[test]
    fn monolith_tile_picks_an_interior_uncrowded_tile() {
        // D4 — with no objects placed every distance is INFINITY-equal, so the
        // pick is the lowest-flat non-edge tile: (1,1) on a 6×6 zone.
        let mut state = solo_zone_state(6, 6);
        let first = monolith_tile(&state, 0).expect("a 6×6 open zone has interior tiles");
        assert_eq!(first, TileCoord::new(1, 1), "lowest-flat non-edge tile on an all-tie zone");

        // Make (3,3) the uncrowded outlier — every other tile reads as crowded.
        for d in &mut state.nearest_object_distance {
            *d = 1.0;
        }
        let far = TileCoord::new(3, 3);
        state.nearest_object_distance[far.flat_index(6)] = 99.0;
        assert_eq!(
            monolith_tile(&state, 0),
            Some(far),
            "must pick the max-nearest-object-distance interior tile",
        );
    }

    #[test]
    fn ac1_portal_connection_places_a_monolith_pair() {
        // AC-1 — a Portal connection places one Monolith in each zone, the two
        // sharing a pair_id; the connection is realised across the zone pair.
        let mut state = two_column_state(8, 6);
        let template = template_with_connection("left", "right", PassageKind::Portal, 0);
        run_connections(&mut state, &template);

        let monoliths: Vec<&TilemapObjectPlacement> = state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::Monolith)
            .collect();
        assert_eq!(monoliths.len(), 2, "a Portal connection places exactly two monoliths");
        assert!(monoliths[0].value.is_some(), "a monolith carries Some(pair_id)");
        assert_eq!(monoliths[0].value, monoliths[1].value, "the pair shares one pair_id");
        // One monolith in each zone — zone 0 (`left`) is x < 4, zone 1 x ≥ 4.
        assert_eq!(
            monoliths.iter().filter(|p| p.anchor.x < 4).count(),
            1,
            "exactly one monolith in zone 0",
        );
        assert_eq!(
            monoliths.iter().filter(|p| p.anchor.x >= 4).count(),
            1,
            "exactly one monolith in zone 1",
        );
        // The monolith tiles are now Occupied.
        for m in &monoliths {
            assert_eq!(state.tile_state_at(m.anchor), TileState::Occupied);
        }
    }

    #[test]
    fn ac2_open_connection_places_a_direct_passage_no_guard() {
        // AC-2 — an Open connection between two bordering zones places a direct
        // passage: no guard, no monolith, and the two free_paths are joined.
        let mut state = bordering_zones(12, 8);
        let template = template_with_connection("left", "right", PassageKind::Open, 0);
        run_connections(&mut state, &template);
        assert!(
            state.object_placements.is_empty(),
            "an Open direct passage places no guard and no monolith",
        );
        assert!(
            walkable_reaches(&state, TileCoord::new(0, 0), TileCoord::new(11, 0)),
            "the corridor must join the two zones' free_paths",
        );
    }

    #[test]
    fn ac3_threshold_connection_places_a_guarded_passage() {
        // AC-3 — a Threshold connection with guard_strength > 0 places one
        // MonsterLair guard (carrying the strength) and joins the free_paths.
        let mut state = bordering_zones(12, 8);
        let template = template_with_connection("left", "right", PassageKind::Threshold, 5000);
        run_connections(&mut state, &template);
        let guards: Vec<&TilemapObjectPlacement> = state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::MonsterLair)
            .collect();
        assert_eq!(guards.len(), 1, "a guarded Threshold passage places one MonsterLair");
        assert_eq!(guards[0].value, Some(5000), "the guard carries its strength (D10)");
        assert!(
            walkable_reaches(&state, TileCoord::new(0, 0), TileCoord::new(11, 0)),
            "the guarded corridor must still join the two zones' free_paths",
        );
    }

    #[test]
    fn ac5_hint_and_adversarial_connections_place_nothing() {
        // AC-5 — Hint / Adversarial connections place no physical passage.
        for kind in [PassageKind::Hint, PassageKind::Adversarial] {
            let mut state = bordering_zones(12, 8);
            let template = template_with_connection("left", "right", kind, 0);
            run_connections(&mut state, &template);
            assert!(state.object_placements.is_empty(), "{kind:?} places no object");
            assert!(
                !walkable_reaches(&state, TileCoord::new(0, 0), TileCoord::new(11, 0)),
                "{kind:?} places no passage — the zones stay unjoined",
            );
        }
    }

    #[test]
    fn ac4_passage_point_avoids_a_three_way_junction() {
        // AC-4 — the passage point never 4-touches a third zone. Fixture: a
        // 12×9 grid — `top` (y 0..3), `bl` (y 3..9, x 0..6), `br` (y 3..9,
        // x 6..12). The bl↔br border is bl's column 5; its lowest tile (5,3)
        // — the lowest flat index, the one a tie-broken scan picks first —
        // 4-touches `top`, so it is rejected and the passage lands at (5,4).
        let grid = GridSize { width: 12, height: 9 };
        let mut top = TileMask::new(12, 9);
        let mut bl = TileMask::new(12, 9);
        let mut br = TileMask::new(12, 9);
        let mut bl_free = TileMask::new(12, 9);
        let mut br_free = TileMask::new(12, 9);
        for y in 0..9 {
            for x in 0..12 {
                let t = TileCoord::new(x, y);
                if y < 3 {
                    top.set(t);
                } else if x < 6 {
                    bl.set(t);
                    if x == 0 {
                        bl_free.set(t);
                    }
                } else {
                    br.set(t);
                    if x == 11 {
                        br_free.set(t);
                    }
                }
            }
        }
        let zt = |id: &str, c: (u32, u32), tiles: TileMask, free: TileMask| ZoneTiles {
            id: ZoneId(id.to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(c.0, c.1),
            assigned_tiles: tiles,
            free_paths: free,
        };
        let mut state = TilemapBuildState::from_zones(
            vec![
                zt("top", (6, 1), top, TileMask::new(12, 9)),
                zt("bl", (3, 6), bl, bl_free),
                zt("br", (9, 6), br, br_free),
            ],
            grid,
        );
        state.zone_terrain.fill(Some(TerrainKind::Grass));
        let spec = |id: &str, conns: Vec<TemplateConnection>| ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns,
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        };
        let template = TilemapTemplate {
            template_id: TilemapTemplateId("ac4".to_string()),
            zones: vec![
                spec("top", vec![]),
                spec(
                    "bl",
                    vec![TemplateConnection::new(ZoneId("br".to_string()), PassageKind::Threshold)],
                ),
                spec("br", vec![]),
            ],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
            decoration_family_density: None,
        };
        run_connections(&mut state, &template);

        assert_eq!(state.road_nodes.len(), 1, "the bl↔br passage records one road node");
        let p = state.road_nodes[0];
        assert_ne!(p, TileCoord::new(5, 3), "the 3-way border tile (5,3) must be rejected");
        assert_eq!(p, TileCoord::new(5, 4), "the passage lands at the lowest clean border tile");
        // The passage point 4-touches no zone other than `bl` (1) / `br` (2).
        for n in neighbors4(p, 12, 9) {
            if let Some(z) = state.zones.iter().position(|zz| zz.assigned_tiles.get(n)) {
                assert!(z == 1 || z == 2, "passage point 4-touches zone {z} — a third zone");
            }
        }
    }

    #[test]
    fn ac6_terrain_prohibited_connection_falls_to_pass_3() {
        // AC-6 — a Subterranean↔surface connection cannot be a direct (Pass 2)
        // passage; with no Sea zone it is realised by the Pass 3 monolith
        // fallback, not a Walkable corridor. The Threshold carries
        // `guard_strength = 5000`, but a Pass-3 monolith pair is unguarded by
        // design — `guard_strength` is not carried to the fallback.
        let mut state = bordering_zones(12, 8);
        state.zone_terrain[0] = Some(TerrainKind::Subterranean); // `left` is underground
        let template = template_with_connection("left", "right", PassageKind::Threshold, 5000);
        run_connections(&mut state, &template);
        let monoliths = state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::Monolith)
            .count();
        assert_eq!(monoliths, 2, "a prohibited transition falls to a Pass-3 monolith pair");
        assert!(
            state.object_placements.iter().all(|p| p.kind != TilemapObjectKind::MonsterLair),
            "a Pass-3 monolith fallback is unguarded — guard_strength is not carried",
        );
        assert!(
            !walkable_reaches(&state, TileCoord::new(0, 0), TileCoord::new(11, 0)),
            "a prohibited transition places no direct Walkable corridor",
        );
    }

    #[test]
    fn ac7_non_bordering_zones_water_route_or_monolith_fallback() {
        // AC-7 — two zones that share no border: a water-route ferry when a Sea
        // zone lies between them, a monolith pair when no Sea is available.
        let template = template_with_connection("left", "right", PassageKind::Threshold, 0);

        // (a) a Sea zone between the two — a Ferry at each shore. `three_zones`
        // is 18 wide: `left` is x < 6, the Sea is 6..12, `right` is x ≥ 12.
        let mut sea_state = three_zones(18, 8, true);
        run_connections(&mut sea_state, &template);
        let ferry_anchors: Vec<TileCoord> = sea_state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::Ferry)
            .map(|p| p.anchor)
            .collect();
        assert_eq!(ferry_anchors.len(), 2, "a Sea between the zones yields a Ferry at each shore");
        assert_eq!(
            ferry_anchors.iter().filter(|a| a.x < 6).count(),
            1,
            "exactly one Ferry on zone left's shore",
        );
        assert_eq!(
            ferry_anchors.iter().filter(|a| a.x >= 12).count(),
            1,
            "exactly one Ferry on zone right's shore",
        );
        assert!(
            sea_state.object_placements.iter().all(|p| p.kind != TilemapObjectKind::Monolith),
            "a water route is preferred over the monolith fallback",
        );
        // §9 — a water-route zone keeps its Sea-facing coast Open: `seal_borders`
        // must not seal `left`'s x=5 coast column (it has a realised route).
        assert!(
            sea_state.zone_area_open(0).iter_set().any(|t| t.x == 5),
            "§9 — a water-route zone's Sea-facing coast stays Open, not sealed",
        );

        // (b) no Sea — the connection falls back to a monolith pair.
        let mut land_state = three_zones(18, 8, false);
        run_connections(&mut land_state, &template);
        let monoliths = land_state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::Monolith)
            .count();
        assert_eq!(monoliths, 2, "no Sea ⇒ the connection falls back to a monolith pair");
        assert!(
            land_state.object_placements.iter().all(|p| p.kind != TilemapObjectKind::Ferry),
            "no Sea ⇒ no ferry",
        );
    }

    /// 4-connected flood-fill from `start` over `region` — the AC-10
    /// connectivity oracle, sharing no implementation with `would_seal_a_gap`.
    fn flood(start: TileCoord, region: &TileMask, grid: GridSize) -> TileMask {
        let mut seen = TileMask::new(grid.width, grid.height);
        if !region.get(start) {
            return seen;
        }
        seen.set(start);
        let mut stack = vec![start];
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
    fn ac8_every_author_connection_is_realized() {
        // AC-8 — no Threshold/Open/Portal connection is left un-completed. The
        // fixture forces all three connections through the Pass-3 monolith
        // fallback: `three_zones`' `middle` has no free_paths, so neither
        // `left↔middle` nor `middle↔right` can route a direct passage, and
        // `left↔right` shares no border; with no Sea zone there is no water
        // route either. Each of the 3 connections must still be realized — the
        // monolith fallback is the completeness guarantee (Pass-1 / Pass-2
        // realization is covered by AC-1 / AC-2 / AC-3).
        let spec = |id: &str, conns: Vec<TemplateConnection>| ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns,
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        };
        let template = TilemapTemplate {
            template_id: TilemapTemplateId("ac8".to_string()),
            zones: vec![
                spec(
                    "left",
                    vec![
                        TemplateConnection::new(ZoneId("middle".to_string()), PassageKind::Threshold),
                        TemplateConnection::new(ZoneId("right".to_string()), PassageKind::Threshold),
                    ],
                ),
                spec(
                    "middle",
                    vec![TemplateConnection::new(ZoneId("right".to_string()), PassageKind::Threshold)],
                ),
                spec("right", vec![]),
            ],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
            decoration_family_density: None,
        };
        let mut state = three_zones(24, 9, false);
        run_connections(&mut state, &template);

        let monoliths: Vec<&TilemapObjectPlacement> = state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::Monolith)
            .collect();
        assert_eq!(
            monoliths.len(),
            6,
            "3 connections × 2 endpoints — none dropped across the three passes",
        );
        let pair_ids: HashSet<u32> = monoliths.iter().filter_map(|p| p.value).collect();
        assert_eq!(pair_ids.len(), 3, "each connection is realized with its own pair_id");
        for id in &pair_ids {
            assert_eq!(
                monoliths.iter().filter(|p| p.value == Some(*id)).count(),
                2,
                "pair_id {id} places exactly one monolith per zone",
            );
        }
    }

    #[test]
    fn ac9_a_shared_connection_is_realized_exactly_once() {
        // AC-9 — §4.1 mutual completion: when both zones name each other,
        // `collect_edges` yields two edges but the canonical-pair dedup
        // realizes the connection once — one monolith pair, not two.
        let bidir = |id: &str, to: &str| ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: vec![TemplateConnection::new(
                ZoneId(to.to_string()),
                PassageKind::Portal,
            )],
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        };
        let template = TilemapTemplate {
            template_id: TilemapTemplateId("ac9".to_string()),
            zones: vec![bidir("left", "right"), bidir("right", "left")],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
            decoration_family_density: None,
        };
        let mut state = two_column_state(8, 6);
        run_connections(&mut state, &template);

        let monoliths: Vec<&TilemapObjectPlacement> = state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::Monolith)
            .collect();
        assert_eq!(
            monoliths.len(),
            2,
            "a bidirectional connection is realized once — one monolith pair, not two",
        );
        let pair_ids: HashSet<u32> = monoliths.iter().filter_map(|p| p.value).collect();
        assert_eq!(pair_ids.len(), 1, "both directions share a single pair_id");
    }

    #[test]
    fn ac9_a_bidirectional_open_connection_realizes_one_corridor() {
        // AC-9 — the Pass-2 dedup (the Portal case above only exercises Pass 1).
        // When two bordering zones each name the other with an `Open`
        // connection, `collect_edges` yields two edges; the canonical-pair
        // dedup must realize ONE direct passage — one corridor, one road node —
        // not two. (Without the `!completed.contains` guard in Pass 2 the
        // second edge re-runs `place_direct_passage`: a doubled corridor and a
        // second `road_nodes` entry — this test catches that.)
        let bidir = |id: &str, to: &str| ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: vec![TemplateConnection::new(
                ZoneId(to.to_string()),
                PassageKind::Open,
            )],
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        };
        let template = TilemapTemplate {
            template_id: TilemapTemplateId("ac9_open".to_string()),
            zones: vec![bidir("left", "right"), bidir("right", "left")],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
            decoration_family_density: None,
        };
        let mut state = bordering_zones(14, 9);
        run_connections(&mut state, &template);

        assert_eq!(
            state.road_nodes.len(),
            1,
            "the shared connection records exactly one road node — not doubled",
        );
        assert!(
            state.object_placements.is_empty(),
            "an Open passage places no object; the dedup keeps it from re-placing",
        );
        assert!(
            walkable_reaches(&state, TileCoord::new(0, 0), TileCoord::new(13, 0)),
            "the single realized passage still joins the two zones",
        );
    }

    #[test]
    fn ac10_a_passage_joins_the_zones_without_splitting_either() {
        // AC-10 — connectivity. A realized direct passage (a) joins the two
        // zones' free_paths into one walkable region, and (b) never splits
        // either zone's passable region — verified with an independent
        // 4-connected flood-fill (`flood` / `components`), sharing nothing with
        // `would_seal_a_gap`.
        let mut state = bordering_zones(14, 9);
        let pre: Vec<TileMask> =
            (0..state.zones.len()).map(|i| state.zone_passable(i)).collect();
        let template = template_with_connection("left", "right", PassageKind::Threshold, 4000);
        run_connections(&mut state, &template);

        // (a) cross-zone: the corridor joins left's free_path column (x=0) to
        // right's (x=13) into one 4-connected walkable region.
        assert!(
            walkable_reaches(&state, TileCoord::new(0, 0), TileCoord::new(13, 0)),
            "the realized passage must join the two zones into one walkable region",
        );

        // (b) no-split: every pre-pipeline passable component that keeps a
        // survivor keeps all its survivors mutually reachable.
        for (i, pre_passable) in pre.iter().enumerate() {
            let post = state.zone_passable(i);
            assert!(!post.is_empty(), "zone {i}: ConnectionsPlacer sealed the entire zone");
            for comp in components(pre_passable, state.grid) {
                let survivors: Vec<TileCoord> =
                    comp.iter_set().filter(|&t| post.get(t)).collect();
                if survivors.is_empty() {
                    continue;
                }
                let reached = flood(survivors[0], &post, state.grid);
                for &s in &survivors {
                    assert!(
                        reached.get(s),
                        "zone {i}: ConnectionsPlacer split the zone's passable region",
                    );
                }
            }
        }
    }

    #[test]
    fn ac10_seal_borders_never_severs_a_zone_at_a_border_cut_vertex() {
        // AC-10 — `seal_borders` (§3.1) seals a zone's `Open` border tiles, but
        // each seal is `would_seal_a_gap`-gated. Fixture: a 5×3 grid with a
        // C-shaped `left` zone whose tile (0,1) is BOTH a left↔right border
        // tile AND the only link between left's top and bottom — a cut-vertex.
        // §3.1 wants to seal it; the gap-check must veto that, or `left` is
        // severed in two. This is the dedicated proof that `seal_borders`'
        // connectivity gate is wired — without it (1,0)+(0,1)+(1,2) all seal
        // and the test fails.
        //
        //   y=0: L L R R R
        //   y=1: L R R R R   left = the "C": x=0 column + (1,0) + (1,2)
        //   y=2: L L R R R
        let grid = GridSize { width: 5, height: 3 };
        let mut left = TileMask::new(5, 3);
        let mut right = TileMask::new(5, 3);
        for y in 0..3 {
            for x in 0..5 {
                let t = TileCoord::new(x, y);
                if x == 0 || (x == 1 && (y == 0 || y == 2)) {
                    left.set(t);
                } else {
                    right.set(t);
                }
            }
        }
        let zt = |id: &str, c: (u32, u32), tiles: TileMask| ZoneTiles {
            id: ZoneId(id.to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(c.0, c.1),
            assigned_tiles: tiles,
            free_paths: TileMask::new(5, 3),
        };
        let mut state = TilemapBuildState::from_zones(
            vec![zt("left", (0, 1), left), zt("right", (3, 1), right)],
            grid,
        );
        state.zone_terrain.fill(Some(TerrainKind::Grass));
        // No connections — `seal_borders` still runs as the tail of `process`.
        let template = TilemapTemplate {
            template_id: TilemapTemplateId("ac10_cut_vertex".to_string()),
            zones: vec![],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
            decoration_family_density: None,
        };
        run_connections(&mut state, &template);

        // The cut-vertex (0,1) must survive — sealing it would strand (0,0).
        assert!(
            state.tile_state_at(TileCoord::new(0, 1)).is_passable(),
            "seal_borders must not seal the border cut-vertex (0,1)",
        );
        // left's passable region is still one 4-connected component.
        let left_passable = state.zone_passable(0);
        assert!(!left_passable.is_empty(), "left was not sealed away entirely");
        assert_eq!(
            components(&left_passable, grid).len(),
            1,
            "seal_borders never severs a zone's passable region",
        );
    }
}
