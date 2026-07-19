//! TMP_005 §4 — the `ObstaclePlacer` modificator. Per zone: select biomes
//! (§4.1), erode loose appendages into the obstacle region (§4.3), then fill
//! that region largest-first with biome obstacle objects (§4.4).
//!
//! Obstacle fill is a deliberate distinct placement path — *not* via
//! `ObjectManager::place_and_connect_object` (spec D6): an obstacle is a wall,
//! it needs no access path and no distance scoring.

use crate::engine::biome_library::engine_default_biome_selection_rules;
use crate::engine::biome_select::select_biomes;
use crate::engine::build_state::TilemapBuildState;
use crate::engine::geometry::{neighbors4, would_seal_a_gap};
use crate::engine::pipeline::{Modificator, ModificatorContext};
use crate::types::biome::{BiomeObjectType, BiomeSelection, BiomeSelectionRule, BiomeSet};
use crate::types::object::{TilemapObjectKind, TilemapObjectPlacement};
use crate::types::tile::{TerrainKind, TileCoord, TileState};
use crate::types::tile_mask::TileMask;
use crate::types::tilemap::GridSize;
use crate::types::zone::ZoneRole;

/// Whether `object_type` is a river source/sink marker (a `Mountain` source or
/// a `Lake` sink) — the obstacles placed pre-erosion by [`ObstacleSourcePlacer`]
/// so `RiverPlacer` has sources + sinks before the bulk fill (DEFERRED #026).
fn is_river_marker(t: BiomeObjectType) -> bool {
    matches!(t, BiomeObjectType::Mountain | BiomeObjectType::Lake)
}

/// The map-wide passable mask (`Walkable ∪ Open` across every zone) — the
/// global-connectivity reference for the source placer's dual gate (mirrors
/// `RiverPlacer`'s refinement-R1 map-wide check).
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

/// The deterministic biome selection for a non-`Forbidden` zone, or `None` for
/// `Forbidden` (completely blocked — nothing to fill). `select_biomes` is a
/// pure function of `(zone_id, terrain, rules, library, seed)`, so the two
/// passes (`ObstacleSourcePlacer` + `ObstacleFillPlacer`) re-derive an
/// identical selection.
fn zone_selection(ctx: &ModificatorContext<'_>, zone_idx: usize, library: &[BiomeSet]) -> Option<BiomeSelection> {
    if ctx.state.zones[zone_idx].role == ZoneRole::Forbidden {
        return None;
    }
    let zone_id = ctx.state.zones[zone_idx].id.clone();
    let terrain = ctx.state.zone_terrain[zone_idx]
        .expect("TerrainPainter runs before the obstacle placers (dependency edge)");
    let default_rules = engine_default_biome_selection_rules();
    let rules: &[BiomeSelectionRule] = ctx
        .template
        .zones
        .iter()
        .find(|z| z.zone_id == zone_id)
        .and_then(|z| z.biome_selection_rules.as_ref())
        .filter(|r| !r.use_engine_default)
        .map_or(default_rules.as_slice(), |r| r.rules.as_slice());
    Some(select_biomes(&zone_id, terrain, rules, library, ctx.seed))
}

/// TMP_005 §4 / DEFERRED #026 — places the river source/sink obstacles
/// (`Mountain` + `Lake`) on each zone's **`Open` area, pre-erosion**, so
/// `RiverPlacer` carves a wide-open zone (a real barrier, few fords) before the
/// bulk obstacle fill clutters it. No erosion here.
#[derive(Debug)]
pub struct ObstacleSourcePlacer;

impl Modificator for ObstacleSourcePlacer {
    fn name(&self) -> &str {
        "obstacle_source_placer"
    }

    fn dependencies(&self) -> Vec<&str> {
        // After terrain (needs zone terrain for biome selection) + the passable
        // placers. RiverPlacer depends on this pass for its Mountain/Lake tags.
        vec!["terrain_painter", "treasure_placer", "road_placer", "connections_placer"]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        // World-inheritance: if the template carries a world_zone snapshot,
        // the BiomeBridge filters the library before zone_selection picks
        // from it — so a glacier zone can't get hot_desert obstacles.
        let library = crate::engine::biome_select::library_for_template(ctx.template);
        for zone_idx in 0..ctx.state.zones.len() {
            let Some(selection) = zone_selection(ctx, zone_idx, &library) else {
                continue;
            };
            // Place ONLY the river markers, on the still-Open zone area, gated
            // against BOTH the zone's passable region AND the map-wide passable
            // region — a Mountain/Lake sits on a *passable* tile, so (unlike the
            // post-erosion fill) it can split the zone OR sever the sole
            // inter-zone corridor; the dual gate mirrors RiverPlacer's
            // refinement R1 (TMP_006 §4). `map_passable` is recomputed per zone
            // from current state, so it reflects markers placed in earlier zones
            // (now Occupied).
            let target = ctx.state.zone_area_open(zone_idx);
            let zone_pass = ctx.state.zone_passable(zone_idx);
            let map_pass = map_passable(ctx.state, ctx.grid);
            fill_region(
                ctx.state,
                &selection,
                &library,
                &target,
                is_river_marker,
                false,
                vec![zone_pass, map_pass],
                ctx.registry,
            );
        }
        Ok(())
    }
}

/// TMP_005 §4 / DEFERRED #026 — erodes each zone then fills the **non-river**
/// obstacles on the eroded `Obstacle` region, **after** `RiverPlacer`. Erosion
/// skips river `Water` fords; fill skips river `Water` tiles.
#[derive(Debug)]
pub struct ObstacleFillPlacer;

impl Modificator for ObstacleFillPlacer {
    fn name(&self) -> &str {
        "obstacle_fill_placer"
    }

    fn dependencies(&self) -> Vec<&str> {
        // Runs after the river carves (so erosion + fill respect river tiles).
        vec!["river_placer"]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        // World-inheritance — same bridge filter as ObstacleSourcePlacer.
        let library = crate::engine::biome_select::library_for_template(ctx.template);
        for zone_idx in 0..ctx.state.zones.len() {
            let Some(selection) = zone_selection(ctx, zone_idx, &library) else {
                continue;
            };
            erode_zone(ctx.state, zone_idx);
            let target = ctx.state.zone_obstacle(zone_idx);
            // No connectivity gate — the Obstacle region is already
            // non-passable, so an obstacle footprint cannot split the passable
            // region (spec D6).
            fill_region(ctx.state, &selection, &library, &target, |t| !is_river_marker(t), true, Vec::new(), ctx.registry);
        }
        Ok(())
    }
}

/// Whether `tile` (an `Open` tile of zone `zone_idx`) is 4-adjacent to a
/// **wall** — off-map, a neighbouring zone's tile, or an `Obstacle` / `Occupied`
/// tile (TMP_005 §4.3, spec D5).
fn is_wall_adjacent(
    state: &TilemapBuildState,
    zone_assigned: &TileMask,
    tile: TileCoord,
    grid: GridSize,
) -> bool {
    // An off-map neighbour: the tile sits on the grid border.
    if tile.x == 0 || tile.y == 0 || tile.x + 1 == grid.width || tile.y + 1 == grid.height {
        return true;
    }
    neighbors4(tile, grid.width, grid.height).any(|n| {
        // not a member of this zone (a neighbouring zone — the §4.3
        // zone-boundary fade) or an already-blocked tile.
        !zone_assigned.get(n)
            || matches!(
                state.tile_state_at(n),
                TileState::Obstacle | TileState::Occupied
            )
    })
}

/// The local *simple-point* verdict for eroding a single `tile` from
/// `passable` (perf pre-filter — obstacle_placer DEFERRED-#029-successor).
///
/// `would_seal_a_gap` in `erode_zone` is always called with a single-tile
/// blocking footprint, so whether removing `tile` seals a gap has a purely
/// local characterisation:
/// - **`None`** — `tile`'s passable cardinal neighbours form ≥ 2 groups under
///   "linked via a passable diagonal"; removal *might* split ⇒ the caller must
///   run the global `would_seal_a_gap`.
/// - **`Some(true)`** — `tile` is isolated (0 passable cardinal neighbours)
///   AND it is the whole region (`passable_count == 1`) ⇒ removal eliminates.
/// - **`Some(false)`** — a leaf (1 cardinal) or a simple point (≥ 2 cardinals
///   in one local group) ⇒ removal provably cannot split, and the region
///   survives.
///
/// Bit-exact equivalence to `would_seal_a_gap({tile}, passable)` is proven in
/// spec [`docs/specs/2026-05-21-tilemap-erosion-simple-point.md`] §4.
fn local_seal_verdict(
    tile: TileCoord,
    passable: &TileMask,
    passable_count: usize,
    grid: GridSize,
) -> Option<bool> {
    let x = tile.x as i64;
    let y = tile.y as i64;
    let get = |dx: i64, dy: i64| -> bool {
        let nx = x + dx;
        let ny = y + dy;
        nx >= 0
            && ny >= 0
            && nx < grid.width as i64
            && ny < grid.height as i64
            && passable.get(TileCoord::new(nx as u32, ny as u32))
    };
    // Cardinal neighbours N, E, S, W and the diagonals that link adjacent
    // cardinals on the 8-ring (N–E via NE, E–S via SE, S–W via SW, W–N via NW).
    let (n, e, s, w) = (get(0, -1), get(1, 0), get(0, 1), get(-1, 0));
    let cardinals = [n, e, s, w];
    let card_count = cardinals.iter().filter(|&&b| b).count();
    if card_count == 0 {
        // Isolated tile — seals only by eliminating the whole region.
        return Some(passable_count == 1);
    }
    if card_count == 1 {
        // Leaf — removal never splits, region survives.
        return Some(false);
    }
    // ≥ 2 cardinals: count their local groups via union-find over [N,E,S,W].
    // Edges (cyclic): 0(N)-1(E) via NE, 1(E)-2(S) via SE, 2(S)-3(W) via SW,
    // 3(W)-0(N) via NW. An edge exists iff both endpoints AND the diagonal
    // are passable.
    let (ne, se, sw, nw) = (get(1, -1), get(1, 1), get(-1, 1), get(-1, -1));
    let mut parent = [0usize, 1, 2, 3];
    fn find(parent: &mut [usize; 4], i: usize) -> usize {
        let mut r = i;
        while parent[r] != r {
            r = parent[r];
        }
        // path-halving
        let mut c = i;
        while parent[c] != r {
            let next = parent[c];
            parent[c] = r;
            c = next;
        }
        r
    }
    let union = |parent: &mut [usize; 4], a: usize, b: usize| {
        let ra = find(parent, a);
        let rb = find(parent, b);
        if ra != rb {
            parent[ra] = rb;
        }
    };
    if n && e && ne {
        union(&mut parent, 0, 1);
    }
    if e && s && se {
        union(&mut parent, 1, 2);
    }
    if s && w && sw {
        union(&mut parent, 2, 3);
    }
    if w && n && nw {
        union(&mut parent, 3, 0);
    }
    // Count distinct roots among the *passable* cardinals only.
    let mut roots = [false; 4];
    for (i, &present) in cardinals.iter().enumerate() {
        if present {
            roots[find(&mut parent, i)] = true;
        }
    }
    let groups = roots.iter().filter(|&&r| r).count();
    if groups >= 2 {
        None // might split — the caller must run would_seal_a_gap
    } else {
        Some(false) // one local group ⇒ a simple point, removal is safe
    }
}

/// TMP_005 §4.3 / spec D5 — strip loose appendages: iterative passes that turn
/// wall-adjacent `Open` tiles `Obstacle`, each gated by a sequential
/// connectivity check. Returns the set of tiles eroded.
///
/// **Perf:** the per-tile seal check uses [`local_seal_verdict`] — the
/// single-tile simple-point pre-filter — and only falls back to the O(N)
/// `would_seal_a_gap` flood fill for tiles whose passable cardinal neighbours
/// form ≥ 2 local groups (genuine pinch-point candidates). Bit-exact identical
/// eroded set to the pre-fix unconditional flood fill (`erode_zone_naive`,
/// kept under `#[cfg(test)]` as the AC-2 oracle).
fn erode_zone(state: &mut TilemapBuildState, zone_idx: usize) -> TileMask {
    let grid = state.grid;
    let zone_assigned = state.zones[zone_idx].assigned_tiles.clone();
    let mut eroded = TileMask::new(grid.width, grid.height);
    // The running passable mask — kept in sync as tiles erode, so each
    // candidate is checked against the post-this-pass-so-far state (sequential,
    // not batch — spec D5).
    let mut passable = state.zone_passable(zone_idx);
    let mut passable_count = passable.count_ones();
    let mut blocking = TileMask::new(grid.width, grid.height);

    loop {
        let mut blocked_any = false;
        for tile in zone_assigned.iter_set() {
            if state.tile_state_at(tile) != TileState::Open {
                continue;
            }
            // A river ford is a passable tile painted `Water` — erosion must
            // not eat it (it is the river's deliberate crossing). River carved
            // tiles are `Obstacle`, already skipped by the `Open` guard above;
            // this guard additionally protects forded (passable-Water) tiles
            // when ObstacleFillPlacer's erosion runs after RiverPlacer.
            if state.terrain_layer[tile.flat_index(grid.width)] == TerrainKind::Water as u8 {
                continue;
            }
            if !is_wall_adjacent(state, &zone_assigned, tile, grid) {
                continue;
            }
            let seals = match local_seal_verdict(tile, &passable, passable_count, grid) {
                Some(v) => v,
                None => {
                    blocking.set(tile);
                    let s = would_seal_a_gap(&blocking, &passable);
                    blocking.clear(tile);
                    s
                }
            };
            if seals {
                continue;
            }
            state.set_tile_state(tile, TileState::Obstacle);
            passable.clear(tile);
            passable_count -= 1;
            eroded.set(tile);
            blocked_any = true;
        }
        if !blocked_any {
            break;
        }
    }
    eroded
}

/// A template queued for the largest-first fill, with its sort key.
struct FillItem {
    object_type: BiomeObjectType,
    biome_id: String,
    name: String,
    area: usize,
    footprint_cells: Vec<(i32, i32)>,
}

/// TMP_005 §4.4 / spec D6 — fill `target` largest-first with the selected
/// biomes' templates whose `object_type` satisfies `place_type`. Each template
/// places at most one instance; no `would_seal_a_gap` call (an all-blocking
/// footprint on the obstacle region cannot disconnect the passable region —
/// spec D6).
///
/// `target` is the candidate-anchor region (the `Obstacle` region for the
/// post-river fill pass; the `Open` area for the pre-river source pass —
/// DEFERRED #026 reorder). When `skip_water` is set, an anchor is rejected if
/// any footprint cell sits on a `Water`-terrain tile (a river tile) — so the
/// fill never drops an obstacle onto the river.
///
/// Returns the footprint `area()` of each placed obstacle **in placement
/// order** — a non-increasing sequence when the largest-first sort holds.
#[allow(clippy::too_many_arguments)]
fn fill_region(
    state: &mut TilemapBuildState,
    selection: &BiomeSelection,
    library: &[BiomeSet],
    target: &TileMask,
    place_type: impl Fn(BiomeObjectType) -> bool,
    skip_water: bool,
    mut gates: Vec<TileMask>,
    registry: &crate::registry::Registry,
) -> Vec<usize> {
    let grid = state.grid;

    // Gather every template of every selected biome whose type is in scope.
    let mut items: Vec<FillItem> = Vec::new();
    for (&object_type, biome_ids) in &selection.by_type {
        if !place_type(object_type) {
            continue;
        }
        for biome_id in biome_ids {
            let Some(biome) = library.iter().find(|b| &b.biome_id == biome_id) else {
                continue;
            };
            for template in &biome.templates {
                items.push(FillItem {
                    object_type,
                    biome_id: biome_id.0.clone(),
                    name: template.name.clone(),
                    area: template.area(),
                    footprint_cells: template.cells.iter().map(|c| (c.dx, c.dy)).collect(),
                });
            }
        }
    }
    // Largest-first; ties → biome-id then template name (deterministic, D6).
    items.sort_by(|a, b| {
        b.area
            .cmp(&a.area)
            .then_with(|| a.biome_id.cmp(&b.biome_id))
            .then_with(|| a.name.cmp(&b.name))
    });

    let mut placed_areas = Vec::new();
    let mut region = target.clone();
    // When gating (source pass — placing on *passable* Open tiles), each
    // `gates` mask is a passable region the placement must not split (TMP_006
    // §4). Mirroring `RiverPlacer`'s refinement-R1 **dual** gate, the source
    // pass passes BOTH the zone's passable region AND the map-wide passable
    // region — a per-zone-only gate would miss a marker that severs the sole
    // inter-zone corridor (the zone stays internally connected while the map
    // splits). The masks are kept live (each placed footprint subtracted) so
    // checks see the post-this-pass-so-far state. Empty for the fill pass (its
    // target is the already-non-passable Obstacle region — spec D6).
    for item in &items {
        // First region anchor (flat-index order) the footprint fits, clear of
        // river Water (when `skip_water`), and — when gating — whose blocking
        // footprint would not seal ANY gated passable region (TMP_006 §4).
        let placed = region.iter_set().find(|&anchor| {
            if !footprint_fits(&item.footprint_cells, anchor, &region, grid) {
                return false;
            }
            if skip_water && !footprint_clear_of_water(&item.footprint_cells, anchor, state, grid) {
                return false;
            }
            if !gates.is_empty() {
                let footprint = footprint_at(&item.footprint_cells, anchor, grid);
                if gates.iter().any(|g| would_seal_a_gap(&footprint, g)) {
                    return false;
                }
            }
            true
        });
        if let Some(anchor) = placed {
            let footprint = footprint_at(&item.footprint_cells, anchor, grid);
            for tile in footprint.iter_set() {
                state.set_tile_state(tile, TileState::Occupied);
            }
            region.subtract(&footprint);
            for g in gates.iter_mut() {
                g.subtract(&footprint); // the placed footprint is no longer passable
            }
            let v2 = registry.resolve_object_v2(
                TilemapObjectKind::Obstacle,
                Some(item.object_type),
            );
            state.object_placements.push(TilemapObjectPlacement {
                kind: TilemapObjectKind::Obstacle,
                anchor,
                canon_ref: None,
                biome_object_type: Some(item.object_type),
                value: None,
                tier_index: None,
                primitive: Some(v2.primitive),
                tag: Some(v2.tag),
                footprint: Some(v2.footprint),
                orientation: None,
                properties: serde_json::Value::Null,
            });
            placed_areas.push(item.area);
        }
    }
    placed_areas
}

/// Whether every footprint cell at `anchor` is clear of `Water` terrain (a
/// river tile). Callers pass `skip_water = true` for the post-river fill pass
/// so an obstacle is never dropped onto the river (DEFERRED #026).
fn footprint_clear_of_water(
    cells: &[(i32, i32)],
    anchor: TileCoord,
    state: &TilemapBuildState,
    grid: GridSize,
) -> bool {
    cells.iter().all(|&(dx, dy)| {
        let x = anchor.x as i64 + dx as i64;
        let y = anchor.y as i64 + dy as i64;
        if x < 0 || y < 0 || x >= grid.width as i64 || y >= grid.height as i64 {
            return true; // out-of-bounds cells are caught by footprint_fits
        }
        let t = TileCoord::new(x as u32, y as u32);
        state.terrain_layer[t.flat_index(grid.width)] != TerrainKind::Water as u8
    })
}

/// Whether every footprint cell at `anchor` lands inside `area` (in-bounds and
/// an `Obstacle`-region member).
fn footprint_fits(cells: &[(i32, i32)], anchor: TileCoord, area: &TileMask, grid: GridSize) -> bool {
    cells.iter().all(|&(dx, dy)| {
        let x = anchor.x as i64 + dx as i64;
        let y = anchor.y as i64 + dy as i64;
        x >= 0
            && y >= 0
            && x < grid.width as i64
            && y < grid.height as i64
            && area.get(TileCoord::new(x as u32, y as u32))
    })
}

/// Project a footprint onto a **grid-sized** mask at `anchor` (callers
/// guarantee in-bounds via [`footprint_fits`], so every cell lands on-grid).
fn footprint_at(cells: &[(i32, i32)], anchor: TileCoord, grid: GridSize) -> TileMask {
    let mut mask = TileMask::new(grid.width, grid.height);
    for &(dx, dy) in cells {
        mask.set(TileCoord::new(
            (anchor.x as i64 + dx as i64) as u32,
            (anchor.y as i64 + dy as i64) as u32,
        ));
    }
    mask
}

/// The pre-perf `erode_zone` — an unconditional `would_seal_a_gap` flood fill
/// per candidate. Kept under `#[cfg(test)]` as the bit-exact oracle for AC-2.
#[cfg(test)]
fn erode_zone_naive(state: &mut TilemapBuildState, zone_idx: usize) -> TileMask {
    let grid = state.grid;
    let zone_assigned = state.zones[zone_idx].assigned_tiles.clone();
    let mut eroded = TileMask::new(grid.width, grid.height);
    let mut passable = state.zone_passable(zone_idx);
    let mut blocking = TileMask::new(grid.width, grid.height);

    loop {
        let mut blocked_any = false;
        for tile in zone_assigned.iter_set() {
            if state.tile_state_at(tile) != TileState::Open {
                continue;
            }
            if !is_wall_adjacent(state, &zone_assigned, tile, grid) {
                continue;
            }
            blocking.set(tile);
            let seals = would_seal_a_gap(&blocking, &passable);
            blocking.clear(tile);
            if seals {
                continue;
            }
            state.set_tile_state(tile, TileState::Obstacle);
            passable.clear(tile);
            eroded.set(tile);
            blocked_any = true;
        }
        if !blocked_any {
            break;
        }
    }
    eroded
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::biome_library::engine_biome_library;
    use crate::engine::placement::ZoneTiles;
    use crate::types::biome::BiomeId;
    use crate::seed::TilemapSeed;
    use crate::types::tile::TerrainKind;
    use crate::types::zone::ZoneId;
    use rand::{Rng, SeedableRng};
    use rand_chacha::ChaCha8Rng;
    use std::sync::OnceLock;

    /// Default `lw:` registry — the standard `&Registry` arg in tests.
    fn default_reg() -> &'static crate::registry::Registry {
        static REG: OnceLock<crate::registry::Registry> = OnceLock::new();
        REG.get_or_init(|| crate::registry::Registry::load_default().unwrap())
    }

    /// A single-`Wilderness`-zone build state covering a `w × h` grid; `free`
    /// tiles are the `Walkable` skeleton, the rest `Open`.
    fn state(w: u32, h: u32, free: &[(u32, u32)]) -> TilemapBuildState {
        let mut assigned = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                assigned.set(TileCoord::new(x, y));
            }
        }
        let mut free_paths = TileMask::new(w, h);
        for &(x, y) in free {
            free_paths.set(TileCoord::new(x, y));
        }
        let zone = ZoneTiles {
            id: ZoneId("z".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(w / 2, h / 2),
            assigned_tiles: assigned,
            free_paths,
        };
        TilemapBuildState::from_zones(vec![zone], GridSize { width: w, height: h })
    }

    #[test]
    fn erosion_only_blocks_open_tiles_and_terminates() {
        // AC-5 — erosion turns Open→Obstacle only, never touches Walkable, and
        // reaches a fixed point (the call returns).
        let mut st = state(8, 8, &[(4, 4), (4, 5), (5, 4)]);
        let before_walkable = st.zone_passable(0); // Walkable + Open
        let eroded = erode_zone(&mut st, 0);
        for tile in eroded.iter_set() {
            // every eroded tile is now Obstacle
            assert_eq!(st.tile_state_at(tile), TileState::Obstacle);
        }
        // the 3 Walkable tiles are untouched
        for &(x, y) in &[(4, 4), (4, 5), (5, 4)] {
            assert_eq!(st.tile_state_at(TileCoord::new(x, y)), TileState::Walkable);
        }
        assert!(!before_walkable.is_empty());
    }

    /// Independent 4-connected flood-fill — the reachability oracle for the
    /// AC-5 erosion tests. Deliberately *not* `would_seal_a_gap` (the erosion
    /// gate's own primitive) nor `geometry::connected_components`, so the check
    /// shares no implementation with the code under test.
    fn reachable_from(start: TileCoord, region: &TileMask, grid: GridSize) -> TileMask {
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

    /// `state` with `walls` forced to `Obstacle` — carves rooms/corridors
    /// inside the single full-grid zone so the erosion fixtures can pose a real
    /// "two regions linked by a corridor" topology.
    fn carved_state(w: u32, h: u32, free: &[(u32, u32)], walls: &[(u32, u32)]) -> TilemapBuildState {
        let mut st = state(w, h, free);
        for &(x, y) in walls {
            st.set_tile_state(TileCoord::new(x, y), TileState::Obstacle);
        }
        st
    }

    #[test]
    fn erosion_never_seals_a_gap() {
        // AC-5 — erosion never strands a passable region. Verified with an
        // independent flood-fill (`reachable_from`), NOT the `would_seal_a_gap`
        // the erosion gate itself uses — that would be tautological. Each
        // random zone starts as one passable component (a full grid of
        // Open ∪ Walkable), so after erosion the surviving passable region must
        // still be exactly one component.
        let mut rng = ChaCha8Rng::seed_from_u64(0xE0DE);
        for _ in 0..200 {
            let mut free = Vec::new();
            for y in 0..9 {
                for x in 0..9 {
                    if rng.random_bool(0.35) {
                        free.push((x, y));
                    }
                }
            }
            if free.is_empty() {
                free.push((4, 4)); // a zone must keep some passable tile
            }
            let mut st = state(9, 9, &free);
            let _ = erode_zone(&mut st, 0);
            let post = st.zone_passable(0);
            assert!(!post.is_empty(), "erosion eliminated the whole passable region");
            let start = post.iter_set().next().unwrap();
            assert_eq!(
                reachable_from(start, &post, st.grid),
                post,
                "erosion split the passable region into ≥2 components",
            );
        }
    }

    /// A random passable mask on a `w × h` grid at `density` (AC-1/AC-2).
    fn random_passable(rng: &mut ChaCha8Rng, w: u32, h: u32, density: f64) -> TileMask {
        let mut m = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                if rng.random_bool(density) {
                    m.set(TileCoord::new(x, y));
                }
            }
        }
        m
    }

    #[test]
    fn ac1_local_seal_verdict_matches_would_seal_a_gap_oracle() {
        // AC-1 — the per-tile bit-exact gate (spec §4). For every passable
        // tile T of a random-mask corpus, the local simple-point verdict must
        // agree with the global would_seal_a_gap({T}, passable). Where the
        // verdict is `None` (groups ≥ 2), the caller would flood-fill anyway,
        // so we only need to confirm: when `Some(v)`, `v == would_seal_a_gap`.
        let grid = GridSize { width: 9, height: 9 };
        let mut rng = ChaCha8Rng::seed_from_u64(0x513_42E0);
        let mut some_true = 0usize;
        let mut some_false = 0usize;
        let mut none_count = 0usize;
        for _ in 0..400 {
            let density = *[0.3, 0.5, 0.7].get(rng.random_range(0..3)).unwrap();
            let passable = random_passable(&mut rng, 9, 9, density);
            let count = passable.count_ones();
            for tile in passable.iter_set() {
                let mut blocking = TileMask::new(9, 9);
                blocking.set(tile);
                let oracle = would_seal_a_gap(&blocking, &passable);
                match local_seal_verdict(tile, &passable, count, grid) {
                    Some(v) => {
                        assert_eq!(
                            v, oracle,
                            "local verdict {v} != oracle {oracle} for tile {tile:?}\npassable={passable:?}",
                        );
                        if v { some_true += 1; } else { some_false += 1; }
                    }
                    None => {
                        // `None` means "flood-fill required" — legitimate only
                        // when the tile has ≥2 cardinal groups. We don't assert
                        // the oracle value here (either verdict is valid for a
                        // genuine pinch candidate); the caller runs the oracle.
                        none_count += 1;
                    }
                }
            }
        }
        // Sanity — the corpus exercises all three resolutions in quantity.
        assert!(some_false > 100, "too few Some(false): {some_false}");
        assert!(none_count > 50, "too few None (flood-fill) cases: {none_count}");
        let _ = some_true; // elimination is rare; presence not required
    }

    #[test]
    fn ac2_erode_zone_matches_naive_on_random_zones() {
        // AC-2 — the score-first/local-verdict erode_zone must produce a
        // bit-identical eroded mask + post-state to the unconditional-flood-
        // fill erode_zone_naive, across random carved zones.
        let mut rng = ChaCha8Rng::seed_from_u64(0xE00_DE50);
        for _ in 0..200 {
            let mut free = Vec::new();
            for y in 0..9 {
                for x in 0..9 {
                    if rng.random_bool(0.3) {
                        free.push((x, y));
                    }
                }
            }
            if free.is_empty() {
                free.push((4, 4));
            }
            // Carve some random walls to create non-trivial topology.
            let mut walls = Vec::new();
            for y in 0..9 {
                for x in 0..9 {
                    if rng.random_bool(0.15) {
                        walls.push((x, y));
                    }
                }
            }
            let mut prod = state(9, 9, &free);
            let mut naive = state(9, 9, &free);
            for &(x, y) in &walls {
                prod.set_tile_state(TileCoord::new(x, y), TileState::Obstacle);
                naive.set_tile_state(TileCoord::new(x, y), TileState::Obstacle);
            }
            let prod_eroded = erode_zone(&mut prod, 0);
            let naive_eroded = erode_zone_naive(&mut naive, 0);
            assert_eq!(prod_eroded, naive_eroded, "eroded mask diverged");
            assert_eq!(
                prod.zone_passable(0), naive.zone_passable(0),
                "post-erosion passable diverged",
            );
        }
    }

    #[test]
    fn ac3_simple_point_unit_cases() {
        // AC-3 — one assertion per §4 branch. Build a `passable` mask directly
        // and probe `local_seal_verdict` + cross-check would_seal_a_gap.
        let grid = GridSize { width: 5, height: 5 };
        let probe = |tiles: &[(u32, u32)], t: (u32, u32)| {
            let mut p = TileMask::new(5, 5);
            for &(x, y) in tiles {
                p.set(TileCoord::new(x, y));
            }
            let tile = TileCoord::new(t.0, t.1);
            let count = p.count_ones();
            let verdict = local_seal_verdict(tile, &p, count, grid);
            let mut b = TileMask::new(5, 5);
            b.set(tile);
            let oracle = would_seal_a_gap(&b, &p);
            (verdict, oracle)
        };

        // Isolated single tile — eliminates the whole region.
        let (v, o) = probe(&[(2, 2)], (2, 2));
        assert_eq!(v, Some(true));
        assert!(o);

        // Isolated tile among other isolated tiles — drops a singleton, safe.
        let (v, o) = probe(&[(0, 0), (2, 2), (4, 4)], (2, 2));
        assert_eq!(v, Some(false));
        assert!(!o);

        // Leaf stub — one cardinal neighbour, safe.
        let (v, o) = probe(&[(2, 2), (2, 3)], (2, 2));
        assert_eq!(v, Some(false));
        assert!(!o);

        // Solid 3×3 interior boundary tile (the centre's neighbours all link)
        // — a simple point, groups==1, safe, NO flood fill.
        let solid: Vec<(u32, u32)> = (1..=3).flat_map(|y| (1..=3).map(move |x| (x, y))).collect();
        let (v, o) = probe(&solid, (2, 2));
        assert_eq!(v, Some(false), "solid interior is a simple point");
        assert!(!o);

        // 1-wide horizontal corridor middle — 2 cardinals (E,W), no diagonal
        // link ⇒ groups==2 ⇒ None ⇒ caller flood-fills ⇒ seals.
        let (v, o) = probe(&[(1, 2), (2, 2), (3, 2)], (2, 2));
        assert_eq!(v, None, "corridor middle needs the flood fill");
        assert!(o);

        // T-junction — 3 cardinals not all linked ⇒ groups≥2 ⇒ None.
        let (v, _o) = probe(&[(2, 1), (1, 2), (2, 2), (3, 2)], (2, 2));
        assert_eq!(v, None, "T-junction needs the flood fill");
    }

    #[test]
    fn erosion_keeps_a_two_wide_sole_corridor_passable() {
        // AC-5 (a) — a 2-wide corridor that is the *sole* passable link between
        // two regions erodes to 1-wide, never sealed. Layout (7×4): rows y=1,2
        // are the corridor, (0,1)/(0,2) and (6,1)/(6,2) are Walkable anchors
        // (regions A and B), rows y=0 and y=3 are Obstacle wall.
        //   # # # # # # #
        //   W . . . . . W
        //   W . . . . . W
        //   # # # # # # #
        let mut walls: Vec<(u32, u32)> = Vec::new();
        for x in 0..7 {
            walls.push((x, 0));
            walls.push((x, 3));
        }
        let mut st = carved_state(7, 4, &[(0, 1), (0, 2), (6, 1), (6, 2)], &walls);
        let eroded = erode_zone(&mut st, 0);

        // The wall-adjacent upper row erodes; the lower row is the sole link
        // and is kept — eroding it would split A from B.
        assert_eq!(eroded.count_ones(), 5, "exactly the upper corridor row erodes");
        for x in 1..=5 {
            assert!(eroded.get(TileCoord::new(x, 1)), "({x},1) should erode");
            assert_eq!(st.tile_state_at(TileCoord::new(x, 1)), TileState::Obstacle);
            assert_eq!(
                st.tile_state_at(TileCoord::new(x, 2)),
                TileState::Open,
                "({x},2) is the surviving 1-wide link",
            );
        }
        // A and B stay connected: the post-erosion passable region is one
        // component under the independent flood-fill.
        let post = st.zone_passable(0);
        let start = post.iter_set().next().unwrap();
        assert_eq!(reachable_from(start, &post, st.grid), post, "the sole corridor was sealed");
    }

    #[test]
    fn erosion_fully_consumes_a_two_wide_dead_end_appendage() {
        // AC-5 (b) — a 2-wide dead-end appendage (no Walkable core, leads
        // nowhere) erodes away completely. Layout (6×5): the 2×3 Walkable block
        // x=1,2 / y=1,2,3 is the zone core; the 2×2 Open block x=3,4 / y=2,3 is
        // the dead-end appendage; everything else is Obstacle wall.
        //   # # # # # #
        //   # W W # # #
        //   # W W . . #
        //   # W W . . #
        //   # # # # # #
        let mut walls: Vec<(u32, u32)> = Vec::new();
        for x in 0..6 {
            walls.push((x, 0));
            walls.push((x, 4));
        }
        for y in 1..4 {
            walls.push((0, y));
            walls.push((5, y));
        }
        walls.push((3, 1));
        walls.push((4, 1));
        let core = [(1, 1), (2, 1), (1, 2), (2, 2), (1, 3), (2, 3)];
        let mut st = carved_state(6, 5, &core, &walls);
        let eroded = erode_zone(&mut st, 0);

        // The whole appendage is gone; the Walkable core is untouched.
        assert_eq!(eroded.count_ones(), 4, "exactly the 4 appendage tiles erode");
        for &(x, y) in &[(3, 2), (4, 2), (3, 3), (4, 3)] {
            assert!(eroded.get(TileCoord::new(x, y)), "({x},{y}) should erode away");
            assert_eq!(st.tile_state_at(TileCoord::new(x, y)), TileState::Obstacle);
        }
        for &(x, y) in &core {
            assert_eq!(
                st.tile_state_at(TileCoord::new(x, y)),
                TileState::Walkable,
                "core ({x},{y}) must be untouched",
            );
        }
    }

    /// Every 4-connected component of `region`, each as its own mask — built on
    /// `reachable_from`, independent of `would_seal_a_gap` / `connected_components`.
    fn components(region: &TileMask, grid: GridSize) -> Vec<TileMask> {
        let mut remaining = region.clone();
        let mut out = Vec::new();
        while !remaining.is_empty() {
            let start = remaining.iter_set().next().expect("non-empty mask has a set tile");
            let comp = reachable_from(start, &remaining, grid);
            remaining.subtract(&comp);
            out.push(comp);
        }
        out
    }

    #[test]
    fn erosion_preserves_a_multi_component_passable_region() {
        // AC-5 (c) — `erode_zone`'s `passable` is the zone's whole assigned set,
        // which a Penrose assignment need not hand over 4-connected. Two Open
        // pockets split by a full-height wall column (each with a Walkable
        // anchor) make a 2-component pre-erosion passable region — the
        // split-while-eliminating case a count oracle misses (lesson 9ba274f5).
        // Erosion must neither merge, split, nor eliminate a pocket.
        let walls: Vec<(u32, u32)> = (0..5).map(|y| (4, y)).collect();
        let mut st = carved_state(9, 5, &[(2, 1), (6, 1)], &walls);
        let pre = st.zone_passable(0);
        assert_eq!(
            components(&pre, st.grid).len(),
            2,
            "fixture must present erode_zone a 2-component passable region",
        );
        let eroded = erode_zone(&mut st, 0);
        assert!(
            !would_seal_a_gap(&eroded, &pre),
            "erosion split or eliminated a component of a multi-component zone",
        );
        // Independent: each pre-component keeps ≥1 survivor, all mutually reachable.
        let post = st.zone_passable(0);
        for comp in components(&pre, st.grid) {
            let survivors: Vec<TileCoord> = comp.iter_set().filter(|&t| post.get(t)).collect();
            assert!(!survivors.is_empty(), "erosion eliminated a whole pocket");
            let reached = reachable_from(survivors[0], &post, st.grid);
            for &s in &survivors {
                assert!(reached.get(s), "erosion split a pocket");
            }
        }
    }

    #[test]
    fn fill_places_obstacles_only_in_the_obstacle_region() {
        // AC-6 — run the full ObstaclePlacer; every obstacle footprint lands on
        // tiles that were `Obstacle`, now `Occupied`; placements are tagged.
        let mut st = state(16, 16, &[(8, 8)]);
        // erode + fill via the helpers (process needs a ModificatorContext).
        let _ = erode_zone(&mut st, 0);
        let obstacle_before = st.zone_obstacle(0);
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let sel = select_biomes(&ZoneId("z".to_string()), TerrainKind::Grass, &rules, &lib, TilemapSeed(1));
        let target = st.zone_obstacle(0);
        fill_region(&mut st, &sel, &lib, &target, |_| true, false, Vec::new(), default_reg());
        for p in &st.object_placements {
            assert_eq!(p.kind, TilemapObjectKind::Obstacle);
            assert!(p.biome_object_type.is_some(), "obstacle placement must be tagged");
            // the anchor was in the pre-fill Obstacle region
            assert!(obstacle_before.get(p.anchor), "obstacle placed outside the Obstacle region");
            assert_eq!(st.tile_state_at(p.anchor), TileState::Occupied);
        }
        // AC-6 full-footprint containment — every tile fill turned `Occupied`
        // (the union of all placed footprints, non-anchor cells included) was
        // in the `Obstacle` region before fill. The per-placement loop above
        // sees only the anchor — one cell of a 2-to-9-tile footprint.
        for tile in st.zones[0].assigned_tiles.iter_set() {
            if st.tile_state_at(tile) == TileState::Occupied {
                assert!(
                    obstacle_before.get(tile),
                    "fill marked a non-Obstacle tile {tile:?} Occupied",
                );
            }
        }
    }

    #[test]
    fn fill_is_largest_first() {
        // AC-6 — obstacles are placed largest-first. `fill_zone` reports each
        // placement's area in fill order; the placed grid cannot reveal
        // per-obstacle area (adjacent footprints merge into one `Occupied`
        // blob). Two independent anchors keep the check honest: (1) `areas[0]`
        // must equal the largest template area in the selection — computed
        // here straight from the library, so an inverted sort is caught
        // head-on, not merely re-derived from `fill_zone`'s own sorted order;
        // (2) `areas` has exactly one entry per `object_placements` record.
        let mut st = state(20, 20, &[(10, 10)]);
        let _ = erode_zone(&mut st, 0);
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let sel = select_biomes(&ZoneId("z".to_string()), TerrainKind::Grass, &rules, &lib, TilemapSeed(2));

        // Independently enumerate every candidate template area from the
        // selection — the test's own ground truth, not `fill_zone`'s report.
        let max_area = sel
            .by_type
            .values()
            .flatten()
            .filter_map(|id| lib.iter().find(|b| &b.biome_id == id))
            .flat_map(|b| b.templates.iter().map(|t| t.area()))
            .max()
            .expect("the Grass selection has at least one template");

        let target = st.zone_obstacle(0);
        let areas = fill_region(&mut st, &sel, &lib, &target, |_| true, false, Vec::new(), default_reg());
        assert_eq!(areas.len(), st.object_placements.len(), "one reported area per placement");
        assert!(areas.len() >= 2, "fixture must place ≥2 obstacles to test ordering: {areas:?}");
        assert_eq!(areas[0], max_area, "the first obstacle placed is not the largest template");
        assert!(
            areas.iter().min() < areas.iter().max(),
            "areas show no size gradient — a non-increasing check would be vacuous: {areas:?}",
        );
        for w in areas.windows(2) {
            assert!(w[0] >= w[1], "fill not largest-first: {areas:?}");
        }
    }

    #[test]
    fn mountain_and_lake_biomes_tag_their_object_type() {
        // AC-7 — a Mountain-object biome yields Some(Mountain), a Lake biome
        // Some(Lake) (the Phase-E river source/sink discovery tags).
        let lib = engine_biome_library();

        // Mountain — the §2.3 Mountain rule (count 1..=1) always selects one,
        // so a real `select_biomes` run reliably places a Mountain obstacle.
        let mut st = state(16, 16, &[(8, 8)]);
        let _ = erode_zone(&mut st, 0);
        let rules = engine_default_biome_selection_rules();
        let sel = select_biomes(&ZoneId("z".to_string()), TerrainKind::Grass, &rules, &lib, TilemapSeed(9));
        let target = st.zone_obstacle(0);
        fill_region(&mut st, &sel, &lib, &target, |_| true, false, Vec::new(), default_reg());
        let mountain_kinds: Vec<_> = st
            .object_placements
            .iter()
            .filter_map(|p| p.biome_object_type)
            .collect();
        assert!(
            mountain_kinds.contains(&BiomeObjectType::Mountain),
            "no Mountain obstacle tagged: {mountain_kinds:?}",
        );

        // Lake — the §2.3 Lake rule is `0..=1` behind the xor, so it is not
        // reliably selected by a seeded run; drive `fill_zone` with a
        // hand-built selection holding one Lake biome and assert the tag.
        let mut lake_st = state(16, 16, &[(8, 8)]);
        let _ = erode_zone(&mut lake_st, 0);
        let mut lake_sel = BiomeSelection::default();
        lake_sel.push(BiomeObjectType::Lake, BiomeId("grass_lake".to_string()));
        let lake_target = lake_st.zone_obstacle(0);
        fill_region(&mut lake_st, &lake_sel, &lib, &lake_target, |_| true, false, Vec::new(), default_reg());
        assert!(!lake_st.object_placements.is_empty(), "the Lake biome placed no obstacle");
        assert!(
            lake_st
                .object_placements
                .iter()
                .all(|p| p.biome_object_type == Some(BiomeObjectType::Lake)),
            "a Lake-biome obstacle is not tagged Some(Lake)",
        );
    }

    #[test]
    fn ac1_source_placer_places_only_river_markers_on_open_area_gated() {
        // AC-1 (DEFERRED #026) — the source pass places ONLY Mountain/Lake
        // markers, on Open tiles, gated against the passable region. No
        // erosion happened (the zone stays mostly Open), and no non-marker
        // obstacle was placed.
        let mut st = state(16, 16, &[(8, 8)]);
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let sel = select_biomes(&ZoneId("z".to_string()), TerrainKind::Grass, &rules, &lib, TilemapSeed(1));
        let open_before = st.zone_area_open(0);
        let target = st.zone_area_open(0);
        let passable = st.zone_passable(0);
        fill_region(&mut st, &sel, &lib, &target, is_river_marker, false, vec![passable], default_reg());

        assert!(!st.object_placements.is_empty(), "the source pass placed a marker");
        for p in &st.object_placements {
            // Only river markers (Mountain/Lake).
            assert!(
                p.biome_object_type.is_some_and(is_river_marker),
                "the source pass placed a non-marker obstacle: {:?}",
                p.biome_object_type,
            );
            // On a tile that was Open before the pass.
            assert!(open_before.get(p.anchor), "marker placed off the Open area");
        }
        // Gate held — the surviving passable region is still one component.
        let post = st.zone_passable(0);
        let start = post.iter_set().next().unwrap();
        assert_eq!(
            reachable_from(start, &post, st.grid),
            post,
            "the gated source pass split the zone's passable region",
        );
    }

    #[test]
    fn source_placer_dual_gate_rejects_a_marker_on_the_sole_inter_zone_corridor() {
        // /review-impl HIGH-1 — a Mountain marker on the single passable tile
        // linking zone A to zone B must be rejected by the MAP-WIDE arm of the
        // dual gate: carving it leaves zone A internally connected (so a
        // per-zone-only gate would pass it) but severs A↔B. Fixture: 5×5, A =
        // x<3, B = x>=3, the mutual border walled to Obstacle except the lone
        // tile (2,2). A 1×1 Mountain marker must NOT land on (2,2).
        let grid = GridSize { width: 5, height: 5 };
        let mut a = TileMask::new(5, 5);
        let mut b = TileMask::new(5, 5);
        for y in 0..5 {
            for x in 0..3 {
                a.set(TileCoord::new(x, y));
            }
            for x in 3..5 {
                b.set(TileCoord::new(x, y));
            }
        }
        let zone_a = ZoneTiles {
            id: ZoneId("a".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(1, 2),
            assigned_tiles: a,
            free_paths: TileMask::new(5, 5),
        };
        let zone_b = ZoneTiles {
            id: ZoneId("b".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(4, 2),
            assigned_tiles: b,
            free_paths: TileMask::new(5, 5),
        };
        let mut st = TilemapBuildState::from_zones(vec![zone_a, zone_b], grid);
        // Wall the A↔B border except the sole corridor (2,2).
        for wall in [(2, 0), (2, 1), (2, 3), (2, 4)] {
            st.set_tile_state(TileCoord::new(wall.0, wall.1), TileState::Obstacle);
        }
        // A hand-built selection with one Mountain biome.
        let lib = engine_biome_library();
        let mut sel = BiomeSelection::default();
        // Find a real Mountain biome id from the library to drive a placement.
        let mountain_biome = lib
            .iter()
            .find(|bset| !bset.templates.is_empty() && bset.biome_id.0.contains("mountain"))
            .map(|bset| bset.biome_id.clone())
            .expect("library stocks a mountain biome");
        sel.push(BiomeObjectType::Mountain, mountain_biome);

        // Drive the source-pass fill on zone A with the dual gate.
        let target = st.zone_area_open(0);
        let zone_pass = st.zone_passable(0);
        let map_pass = map_passable(&st, grid);
        fill_region(&mut st, &sel, &lib, &target, is_river_marker, false, vec![zone_pass, map_pass], default_reg());

        // The corridor (2,2) must remain passable — the map-wide gate refused
        // to place a marker there.
        assert!(
            st.tile_state_at(TileCoord::new(2, 2)).is_passable(),
            "the dual gate let a marker sever the sole A↔B corridor (2,2)",
        );
        // Independent flood-fill from any surviving passable tile must cover
        // the whole map-wide passable region — i.e. no severance. (Flooding
        // from a fixed corner is wrong: the marker may have legitimately
        // occupied it.)
        let post = map_passable(&st, grid);
        let start = post.iter_set().next().expect("a passable tile survives");
        assert_eq!(
            reachable_from(start, &post, grid),
            post,
            "the source pass split the map-wide passable region (A severed from B)",
        );
    }

    #[test]
    fn ac3_fill_skips_river_water_tiles() {
        // AC-3 (DEFERRED #026) — with skip_water, the fill never drops an
        // obstacle footprint onto a river Water tile.
        let mut st = state(16, 16, &[(8, 8)]);
        let _ = erode_zone(&mut st, 0);
        // Paint a band of Water across the eroded obstacle region.
        for x in 0..16 {
            st.terrain_layer[TileCoord::new(x, 0).flat_index(16)] = TerrainKind::Water as u8;
        }
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let sel = select_biomes(&ZoneId("z".to_string()), TerrainKind::Grass, &rules, &lib, TilemapSeed(3));
        let target = st.zone_obstacle(0);
        fill_region(&mut st, &sel, &lib, &target, |_| true, true, Vec::new(), default_reg());
        // No placed obstacle footprint may sit on a Water tile.
        for p in &st.object_placements {
            assert_ne!(
                st.terrain_layer[p.anchor.flat_index(16)],
                TerrainKind::Water as u8,
                "fill dropped an obstacle on a river Water tile at {:?}",
                p.anchor,
            );
        }
    }

    #[test]
    fn ac4_erosion_does_not_eat_a_river_ford() {
        // AC-4 (DEFERRED #026) — a forded river tile is passable + Water
        // terrain; the post-river erosion pass must not erode it. A 5×1
        // corridor with the centre forded: erosion would otherwise peel the
        // wall-adjacent centre, but the Water guard protects it.
        let mut st = state(5, 1, &[(0, 0), (4, 0)]);
        // (2,0) is a ford — passable (Open) with Water terrain.
        st.terrain_layer[TileCoord::new(2, 0).flat_index(5)] = TerrainKind::Water as u8;
        let eroded = erode_zone(&mut st, 0);
        assert!(
            !eroded.get(TileCoord::new(2, 0)),
            "erosion ate the river ford at (2,0)",
        );
        assert!(
            st.tile_state_at(TileCoord::new(2, 0)).is_passable(),
            "the forded tile must stay passable after erosion",
        );
    }

    #[test]
    fn is_wall_adjacent_treats_a_neighbouring_zone_as_a_wall() {
        // D5 / TMP_005 §4.3 zone-boundary fade — a tile whose only non-zone-A
        // neighbour is a *zone-B* tile (not the grid edge, not an Obstacle)
        // still counts as wall-adjacent. The single-full-grid-zone fixtures
        // elsewhere in this module only ever exercise the grid-border arm of
        // `is_wall_adjacent`; this is the only test of the neighbouring-zone
        // arm. 8×4 grid split into zone A (x 0..4) and zone B (x 4..8).
        let grid = GridSize { width: 8, height: 4 };
        let mut a_tiles = TileMask::new(8, 4);
        let mut b_tiles = TileMask::new(8, 4);
        for y in 0..4 {
            for x in 0..4 {
                a_tiles.set(TileCoord::new(x, y));
            }
            for x in 4..8 {
                b_tiles.set(TileCoord::new(x, y));
            }
        }
        let zone_a = ZoneTiles {
            id: ZoneId("a".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(1, 1),
            assigned_tiles: a_tiles.clone(),
            free_paths: TileMask::new(8, 4),
        };
        let zone_b = ZoneTiles {
            id: ZoneId("b".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(6, 1),
            assigned_tiles: b_tiles,
            free_paths: TileMask::new(8, 4),
        };
        let st = TilemapBuildState::from_zones(vec![zone_a, zone_b], grid);

        // (3,1): off the grid border; its only non-zone-A neighbour is the
        // zone-B tile (4,1) — wall-adjacent via the §4.3 boundary-fade clause
        // alone.
        assert!(
            is_wall_adjacent(&st, &a_tiles, TileCoord::new(3, 1), grid),
            "a neighbouring-zone tile must count as a wall (§4.3 zone-boundary fade)",
        );
        // (1,1): wrapped by same-zone Open tiles on all 4 sides, off the grid
        // border — nothing makes it wall-adjacent.
        assert!(
            !is_wall_adjacent(&st, &a_tiles, TileCoord::new(1, 1), grid),
            "an interior tile with only same-zone Open neighbours is not wall-adjacent",
        );
    }
}
