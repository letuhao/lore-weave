//! TMP_006 §5 / TMP_003 §3.6 — the `ObjectManager` placement service. It is a
//! plain function module, not a registered pipeline pass (spec D3): the placers
//! of Phases B–E call [`place_and_connect_object`] directly.
//!
//! `place_and_connect_object` is the one entry that places an object while
//! honouring the "never seal a gap" invariant (TMP_006 §4); it also maintains
//! the map-wide nearest-object-distance oracle (spec D10). [`choose_guard`]
//! picks a V1+30d guard flavour for a terrain.

use std::cmp::Ordering;

use crate::engine::build_state::TilemapBuildState;
use crate::engine::geometry::{Path, neighbors4, search_path, would_seal_a_gap};
use crate::types::object::{TilemapObjectKind, TilemapObjectPlacement};
use crate::types::object_template::TilemapObjectTemplate;
use crate::types::tile::{TerrainKind, TileCoord, TileState};
use crate::types::tile_mask::TileMask;
use crate::types::tilemap::GridSize;

/// How [`place_and_connect_object`] scores a surviving candidate anchor
/// (TMP_006 §5.2).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OptimizeType {
    /// Maximise distance from existing objects.
    Distance,
    /// Balance distance from objects with closeness to the zone centre — the
    /// treasure default.
    BothDistanceAndCenter,
    /// Minimise distance from the zone centre.
    Center,
}

/// A successful placement (TMP_006 §5.2).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlacementResult {
    /// The chosen anchor tile.
    pub anchor: TileCoord,
    /// The object's full occupied footprint at `anchor`.
    pub footprint: TileMask,
    /// The pinned access route from a footprint-adjacent tile to the zone's
    /// `free_paths` skeleton — shares no tile with `footprint`.
    pub access_path: Path,
}

/// Why a placement could not be made.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum PlacementError {
    /// No candidate anchor survived footprint / connectivity / distance / access
    /// filtering.
    #[error("no candidate tile survived placement filtering")]
    NoSpace,
    /// `zone_idx` is out of range for the build state's zone list — a caller
    /// bug surfaced as a typed error rather than a slice-index panic (D12).
    #[error("zone index {0} is out of range")]
    NoSuchZone(usize),
}

/// A V1+30d monster guard — `strength` carried from the request, `terrain_tag` a
/// terrain-appropriate flavour (TMP_006 §5.3). The faction-weighted creature
/// pool is V2.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MonsterTemplate {
    pub strength: u32,
    pub terrain_tag: &'static str,
}

/// Euclidean distance between two tiles.
fn euclidean(a: TileCoord, b: TileCoord) -> f32 {
    let dx = a.x as f32 - b.x as f32;
    let dy = a.y as f32 - b.y as f32;
    (dx * dx + dy * dy).sqrt()
}

/// A surviving candidate carried from the scoring phase to the commit phase.
struct Candidate {
    anchor: TileCoord,
    /// `anchor.flat_index` — the explicit integer tie-break key (spec §6.3
    /// step 3, TMP-A4): an exact-equal score resolves to the lowest flat index.
    flat: usize,
    footprint: TileMask,
    blocking: TileMask,
    access_path: Path,
    score: f32,
}

/// TMP_006 §5.2 / spec D9 + §6.3 — place `template` (an object of `kind`) on the
/// best-scoring tile of `search_area` within zone `zone_idx`.
///
/// An anchor is rejected if its blocking footprint would seal a gap (TMP_006
/// §4), if it sits closer than `min_distance` to an existing object, or if no
/// footprint-adjacent tile can reach the zone's `free_paths`. Survivors are
/// scored per `optimize`; the best (ties → lowest flat-index anchor) is placed —
/// its blocking footprint → `Occupied`, a [`TilemapObjectPlacement`] appended,
/// the distance oracle updated. Returns the placement, or [`PlacementError`].
///
/// `search_area` must share the build-state grid's dimensions (debug-asserted);
/// every in-tree caller builds it from `zone_area_open` / `zone_passable`.
pub fn place_and_connect_object(
    state: &mut TilemapBuildState,
    zone_idx: usize,
    template: &TilemapObjectTemplate,
    kind: TilemapObjectKind,
    search_area: &TileMask,
    min_distance: f32,
    optimize: OptimizeType,
) -> Result<PlacementResult, PlacementError> {
    if zone_idx >= state.zones.len() {
        return Err(PlacementError::NoSuchZone(zone_idx));
    }
    let grid = state.grid;
    // `fits` bounds-checks footprint cells against `search_area`'s dimensions
    // while `footprint_at` checks against `grid`; the `expect("fits ⇒
    // in-bounds")` in the candidate loop is sound only when the two agree.
    debug_assert_eq!(
        (search_area.width(), search_area.height()),
        (grid.width, grid.height),
        "search_area dimensions must match the build-state grid",
    );
    let width = grid.width;
    let zone_passable = state.zone_passable(zone_idx);
    let free_paths = state.zones[zone_idx].free_paths.clone();
    let zone_center = state.zones[zone_idx].center;
    // Spec §6.3 step 3 first-placement fallback — with no object on the map yet
    // every `nearest_object_distance` is INFINITY, so the distance term is
    // undefined; `Distance`/`BothDistanceAndCenter` fall back to the centre term.
    let first_placement = state.object_placements.is_empty();

    let mut best: Option<Candidate> = None;
    for anchor in search_area.iter_set() {
        // (1) candidate — the full footprint fits inside `search_area`.
        if !template.fits(anchor, search_area) {
            continue;
        }
        // `fits` implies in-bounds, so both projections are `Some`.
        let footprint = template.footprint_at(anchor, grid).expect("fits ⇒ in-bounds");
        let blocking = template.blocking_footprint_at(anchor, grid).expect("fits ⇒ in-bounds");

        // (2a) connectivity — the blocking footprint must not seal a gap.
        if would_seal_a_gap(&blocking, &zone_passable) {
            continue;
        }
        // (2b) spacing — far enough from every existing object (D10 oracle).
        if state.nearest_object_distance[anchor.flat_index(width)] < min_distance {
            continue;
        }
        // (2c) access — a footprint-adjacent tile must reach `free_paths`.
        let access_path = match find_access_path(&zone_passable, &footprint, &free_paths, grid) {
            Some(path) => path,
            None => continue,
        };

        // (3) score the survivor.
        let flat = anchor.flat_index(width);
        let dist = state.nearest_object_distance[flat];
        let score = score_anchor(optimize, first_placement, anchor, zone_center, dist);
        // Explicit `(score desc, flat asc)` tie-break (spec §6.3 step 3, TMP-A4):
        // a higher score wins; an exact-equal score resolves to the lower flat
        // index. `total_cmp` is a total order, so the choice never rests on
        // `f32` `>`/`==` and the tie-break is pinned, not implied by iteration.
        let better = best.as_ref().is_none_or(|b| match score.total_cmp(&b.score) {
            Ordering::Greater => true,
            Ordering::Less => false,
            Ordering::Equal => flat < b.flat,
        });
        if better {
            best = Some(Candidate { anchor, flat, footprint, blocking, access_path, score });
        }
    }

    let Candidate { anchor, footprint, blocking, access_path, .. } =
        best.ok_or(PlacementError::NoSpace)?;

    // (4) commit — blocking cells → Occupied; record the placement.
    for tile in blocking.iter_set() {
        state.set_tile_state(tile, TileState::Occupied);
    }
    state.object_placements.push(TilemapObjectPlacement {
        kind,
        anchor,
        canon_ref: None,
        biome_object_type: None,
    });
    // D10 — refresh the whole map-wide nearest-object-distance oracle.
    for y in 0..grid.height {
        for x in 0..grid.width {
            let tile = TileCoord::new(x, y);
            let d = euclidean(tile, anchor);
            let idx = tile.flat_index(width);
            if d < state.nearest_object_distance[idx] {
                state.nearest_object_distance[idx] = d;
            }
        }
    }

    Ok(PlacementResult { anchor, footprint, access_path })
}

/// Spec §6.3 step 2(c) — the access route. The search space is `zone_passable`
/// minus the candidate's own footprint, so the path cannot thread the
/// not-yet-placed object. Returns the shortest path from a footprint-adjacent
/// passable tile to `free_paths`; ties break to the lower-flat-index start.
fn find_access_path(
    zone_passable: &TileMask,
    footprint: &TileMask,
    free_paths: &TileMask,
    grid: GridSize,
) -> Option<Path> {
    let mut search_space = zone_passable.clone();
    search_space.subtract(footprint);

    // Footprint-adjacent passable tiles, de-duplicated, ascending flat-index.
    let mut seen = TileMask::new(grid.width, grid.height);
    let mut adj: Vec<TileCoord> = Vec::new();
    for fp in footprint.iter_set() {
        for n in neighbors4(fp, grid.width, grid.height) {
            if search_space.get(n) && !seen.get(n) {
                seen.set(n);
                adj.push(n);
            }
        }
    }
    adj.sort_by_key(|t| t.flat_index(grid.width));

    let mut best: Option<Path> = None;
    for start in adj {
        if let Some(path) = search_path(&search_space, start, free_paths, |_, _| 1.0) {
            // Strict `<` keeps the first (lowest-flat-index `start`) at the
            // shortest length — the pinned tie-break (spec D6 / §6.3 step 2c).
            if best.as_ref().is_none_or(|b| path.len() < b.len()) {
                best = Some(path);
            }
        }
    }
    best
}

/// Score a candidate anchor per `optimize` (spec §6.3 step 3).
fn score_anchor(
    optimize: OptimizeType,
    first_placement: bool,
    anchor: TileCoord,
    zone_center: TileCoord,
    nearest_object_distance: f32,
) -> f32 {
    let center_term = -euclidean(anchor, zone_center);
    match optimize {
        OptimizeType::Center => center_term,
        OptimizeType::Distance => {
            if first_placement {
                center_term
            } else {
                nearest_object_distance
            }
        }
        OptimizeType::BothDistanceAndCenter => {
            if first_placement {
                center_term
            } else {
                nearest_object_distance + center_term
            }
        }
    }
}

/// TMP_006 §5.3 / spec D11 — pick a V1+30d guard for `terrain` at `strength`.
/// The flavour table is total over all 10 `TerrainKind`, so `choose_guard` is
/// infallible; whether to place a guard at all is the caller's decision.
pub fn choose_guard(terrain: TerrainKind, strength: u32) -> MonsterTemplate {
    let terrain_tag = match terrain {
        TerrainKind::Grass => "plains_raider",
        TerrainKind::Forest => "forest_stalker",
        TerrainKind::Mountain => "mountain_troll",
        TerrainKind::Water => "deep_serpent",
        TerrainKind::Sand => "dune_lurker",
        TerrainKind::Snow => "frost_wight",
        TerrainKind::Swamp => "bog_horror",
        TerrainKind::Road => "highwayman",
        TerrainKind::Rough => "scrub_marauder",
        TerrainKind::Subterranean => "cave_dweller",
    };
    MonsterTemplate { strength, terrain_tag }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::placement::ZoneTiles;
    use crate::types::object_template::FootprintCell;
    use crate::types::zone::{ZoneId, ZoneRole};

    fn mask(w: u32, h: u32, tiles: &[(u32, u32)]) -> TileMask {
        let mut m = TileMask::new(w, h);
        for &(x, y) in tiles {
            m.set(TileCoord::new(x, y));
        }
        m
    }

    /// A single-zone `TilemapBuildState`: a `w × h` `Wilderness` zone covering
    /// the grid, `free` tiles as the `free_paths` skeleton, `center` explicit.
    fn build_state(
        w: u32,
        h: u32,
        free: &[(u32, u32)],
        center: (u32, u32),
    ) -> TilemapBuildState {
        let mut assigned = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                assigned.set(TileCoord::new(x, y));
            }
        }
        let zone = ZoneTiles {
            id: ZoneId("z".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(center.0, center.1),
            assigned_tiles: assigned,
            free_paths: mask(w, h, free),
        };
        TilemapBuildState::from_zones(vec![zone], GridSize { width: w, height: h })
    }

    /// A 1×1 blocking object.
    fn unit() -> TilemapObjectTemplate {
        TilemapObjectTemplate {
            name: "unit".to_string(),
            cells: vec![FootprintCell::blocking(0, 0)],
        }
    }

    #[test]
    fn places_an_object_marks_occupied_and_returns_an_access_path() {
        // AC-6 — a 5×5 zone, free_paths along the top row.
        let mut state = build_state(5, 5, &[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], (2, 2));
        let search = state.zone_area_open(0); // rows 1-4
        let result = place_and_connect_object(
            &mut state,
            0,
            &unit(),
            TilemapObjectKind::Treasure,
            &search,
            0.0,
            OptimizeType::Center,
        )
        .expect("placement on an open zone must succeed");

        // Center optimisation → the open tile nearest the centre (2,2).
        assert_eq!(result.anchor, TileCoord::new(2, 2));
        assert_eq!(state.object_placements.len(), 1);
        assert_eq!(state.tile_state_at(result.anchor), TileState::Occupied);
        assert_eq!(state.nearest_object_distance[result.anchor.flat_index(5)], 0.0);
        // The access path ends in free_paths and starts adjacent to the object.
        assert!(!result.access_path.is_empty());
        assert_eq!(result.access_path.last().unwrap().y, 0, "path reaches the free-path row");
    }

    #[test]
    fn access_path_never_overlaps_the_footprint() {
        // AC-6 — a 2×2 object: the access path must not thread the object.
        let mut state = build_state(6, 6, &[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0)], (3, 3));
        let two_by_two = TilemapObjectTemplate {
            name: "2x2".to_string(),
            cells: vec![
                FootprintCell::blocking(0, 0),
                FootprintCell::blocking(1, 0),
                FootprintCell::blocking(0, 1),
                FootprintCell::blocking(1, 1),
            ],
        };
        let search = state.zone_area_open(0);
        let result = place_and_connect_object(
            &mut state,
            0,
            &two_by_two,
            TilemapObjectKind::Landmark,
            &search,
            0.0,
            OptimizeType::Center,
        )
        .unwrap();
        for tile in result.footprint.iter_set() {
            assert!(
                !result.access_path.contains(&tile),
                "access path threads footprint tile {tile:?}",
            );
        }
    }

    #[test]
    fn rejects_a_placement_that_would_seal_a_gap() {
        // A 3×1 corridor zone, free path at (0,0). search_area = {(1,0),(2,0)};
        // a unit at (1,0) splits the corridor → rejected; (2,0) survives.
        let mut state = build_state(3, 1, &[(0, 0)], (0, 0));
        let search = state.zone_area_open(0); // {(1,0),(2,0)}
        let result = place_and_connect_object(
            &mut state,
            0,
            &unit(),
            TilemapObjectKind::Treasure,
            &search,
            0.0,
            OptimizeType::Center,
        )
        .unwrap();
        assert_eq!(result.anchor, TileCoord::new(2, 0), "the sealing anchor (1,0) is rejected");
    }

    #[test]
    fn unsatisfiable_min_distance_yields_no_space() {
        // AC-6 — place one object, then demand an impossible separation.
        let mut state = build_state(5, 5, &[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], (2, 2));
        let search = state.zone_area_open(0);
        place_and_connect_object(
            &mut state, 0, &unit(), TilemapObjectKind::Treasure, &search, 0.0, OptimizeType::Center,
        )
        .unwrap();
        let search = state.zone_area_open(0);
        let err = place_and_connect_object(
            &mut state, 0, &unit(), TilemapObjectKind::Treasure, &search, 100.0, OptimizeType::Distance,
        )
        .unwrap_err();
        assert_eq!(err, PlacementError::NoSpace);
    }

    #[test]
    fn empty_search_area_yields_no_space() {
        let mut state = build_state(4, 4, &[(0, 0)], (0, 0));
        let empty = TileMask::new(4, 4);
        let err = place_and_connect_object(
            &mut state, 0, &unit(), TilemapObjectKind::Treasure, &empty, 0.0, OptimizeType::Center,
        )
        .unwrap_err();
        assert_eq!(err, PlacementError::NoSpace);
    }

    #[test]
    fn first_placement_under_both_is_centre_biased_not_a_corner() {
        // AC-6 / spec F2 — with no object yet, BothDistanceAndCenter must fall
        // back to the centre term, so the first pile is centred, not at the
        // lowest-flat-index (corner) anchor.
        let mut state = build_state(5, 5, &[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], (2, 2));
        let search = state.zone_area_open(0);
        let result = place_and_connect_object(
            &mut state,
            0,
            &unit(),
            TilemapObjectKind::Treasure,
            &search,
            0.0,
            OptimizeType::BothDistanceAndCenter,
        )
        .unwrap();
        assert_eq!(result.anchor, TileCoord::new(2, 2), "first pile is centre-biased");
        assert_ne!(result.anchor, TileCoord::new(0, 1), "not the lowest-flat-index open tile");
    }

    #[test]
    fn choose_guard_covers_every_terrain() {
        // AC-7 — the flavour table is total; choose_guard is infallible.
        for terrain in [
            TerrainKind::Grass,
            TerrainKind::Forest,
            TerrainKind::Mountain,
            TerrainKind::Water,
            TerrainKind::Sand,
            TerrainKind::Snow,
            TerrainKind::Swamp,
            TerrainKind::Road,
            TerrainKind::Rough,
            TerrainKind::Subterranean,
        ] {
            let guard = choose_guard(terrain, 1500);
            assert_eq!(guard.strength, 1500);
            assert!(!guard.terrain_tag.is_empty(), "{terrain:?} has no guard flavour");
        }
    }

    /// An all-tiles-set mask of a `w × h` grid.
    fn full(w: u32, h: u32) -> TileMask {
        let mut m = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                m.set(TileCoord::new(x, y));
            }
        }
        m
    }

    #[test]
    fn find_access_path_picks_the_shortest_route_not_the_first_adjacent() {
        // AC-6(b) — footprint {(2,2)}; the only free path is (2,4). The
        // lowest-flat-index adjacent tile (2,1) has a 6-tile detour around the
        // footprint; the highest, (2,3), reaches (2,4) in 2 — `find_access_path`
        // must pin the *shortest* route, not the first adjacent tile.
        let grid = GridSize { width: 5, height: 5 };
        let path = find_access_path(
            &full(5, 5),
            &mask(5, 5, &[(2, 2)]),
            &mask(5, 5, &[(2, 4)]),
            grid,
        )
        .unwrap();
        assert_eq!(
            path,
            vec![TileCoord::new(2, 3), TileCoord::new(2, 4)],
            "the shortest route wins over the lowest-flat-index adjacent tile",
        );
    }

    #[test]
    fn find_access_path_breaks_equal_length_ties_by_lowest_flat_index_start() {
        // AC-6(b) — footprint {(2,2)}; free paths at (2,0) AND (2,4) give the
        // adjacent tiles (2,1) and (2,3) equal 2-tile routes. The tie breaks to
        // the lower-flat-index start — (2,1), flat 11, over (2,3), flat 17.
        let grid = GridSize { width: 5, height: 5 };
        let path = find_access_path(
            &full(5, 5),
            &mask(5, 5, &[(2, 2)]),
            &mask(5, 5, &[(2, 0), (2, 4)]),
            grid,
        )
        .unwrap();
        assert_eq!(
            path,
            vec![TileCoord::new(2, 1), TileCoord::new(2, 0)],
            "an equal-length tie resolves to the lower-flat-index start",
        );
    }

    #[test]
    fn mixed_footprint_marks_only_blocking_cells_occupied() {
        // D9 — a 2×1 template: blocking at the anchor, non-blocking to its
        // right. Only the blocking cell becomes `Occupied`; the non-blocking
        // cell stays `Open`; `PlacementResult.footprint` carries both.
        let mut state = build_state(5, 5, &[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], (2, 2));
        let mixed = TilemapObjectTemplate {
            name: "mixed".to_string(),
            cells: vec![
                FootprintCell::blocking(0, 0),
                FootprintCell { dx: 1, dy: 0, blocking: false },
            ],
        };
        let search = state.zone_area_open(0);
        let result = place_and_connect_object(
            &mut state,
            0,
            &mixed,
            TilemapObjectKind::Landmark,
            &search,
            0.0,
            OptimizeType::Center,
        )
        .unwrap();
        assert_eq!(result.anchor, TileCoord::new(2, 2));
        assert_eq!(
            state.tile_state_at(TileCoord::new(2, 2)),
            TileState::Occupied,
            "the blocking cell is Occupied",
        );
        assert_eq!(
            state.tile_state_at(TileCoord::new(3, 2)),
            TileState::Open,
            "the non-blocking cell stays Open",
        );
        assert_eq!(result.footprint.count_ones(), 2, "footprint carries both cells");
        assert!(result.footprint.get(TileCoord::new(3, 2)), "incl. the non-blocking cell");
    }

    #[test]
    fn nearest_object_distance_oracle_spans_zone_boundaries() {
        // D10 — the oracle is map-wide: an object placed in zone 0 lowers the
        // distance for tiles of zone 1 (the stated reason §5.1's per-zone grid
        // is rejected).
        let grid = GridSize { width: 6, height: 3 };
        let mut left = TileMask::new(6, 3);
        let mut right = TileMask::new(6, 3);
        for y in 0..3 {
            for x in 0..3 {
                left.set(TileCoord::new(x, y));
            }
            for x in 3..6 {
                right.set(TileCoord::new(x, y));
            }
        }
        let zone0 = ZoneTiles {
            id: ZoneId("left".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(1, 1),
            assigned_tiles: left,
            free_paths: mask(6, 3, &[(0, 0), (1, 0), (2, 0)]),
        };
        let zone1 = ZoneTiles {
            id: ZoneId("right".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(4, 1),
            assigned_tiles: right,
            free_paths: mask(6, 3, &[(3, 0), (4, 0), (5, 0)]),
        };
        let mut state = TilemapBuildState::from_zones(vec![zone0, zone1], grid);
        let search = state.zone_area_open(0);
        let result = place_and_connect_object(
            &mut state,
            0,
            &unit(),
            TilemapObjectKind::Treasure,
            &search,
            0.0,
            OptimizeType::Center,
        )
        .unwrap();
        // A zone-1 tile now reads a finite distance to the zone-0 anchor.
        let zone1_tile = TileCoord::new(5, 2);
        let got = state.nearest_object_distance[zone1_tile.flat_index(6)];
        let dx = 5.0 - result.anchor.x as f32;
        let dy = 2.0 - result.anchor.y as f32;
        let want = (dx * dx + dy * dy).sqrt();
        assert!(got.is_finite(), "a cross-zone tile must read a finite distance");
        assert!((got - want).abs() < 1e-4, "cross-zone distance: got {got}, want {want}");
    }

    #[test]
    fn equal_score_anchors_break_to_the_lowest_flat_index() {
        // F2 — (1,2) and (3,2) are equidistant from the zone centre (2,2), so
        // `OptimizeType::Center` scores them identically; the tie must resolve
        // to the lower flat-index anchor — (1,2), flat 11, over (3,2), flat 13.
        let mut state = build_state(5, 5, &[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], (2, 2));
        let search = mask(5, 5, &[(1, 2), (3, 2)]);
        let result = place_and_connect_object(
            &mut state,
            0,
            &unit(),
            TilemapObjectKind::Treasure,
            &search,
            0.0,
            OptimizeType::Center,
        )
        .unwrap();
        assert_eq!(
            result.anchor,
            TileCoord::new(1, 2),
            "an equal-score tie resolves to the lowest flat-index anchor",
        );
    }

    #[test]
    fn out_of_range_zone_idx_is_a_typed_error() {
        // F3 / D12 — an out-of-range `zone_idx` returns a typed error, never a
        // slice-index panic.
        let mut state = build_state(4, 4, &[(0, 0)], (0, 0));
        let search = state.zone_area_open(0);
        let err = place_and_connect_object(
            &mut state,
            99,
            &unit(),
            TilemapObjectKind::Treasure,
            &search,
            0.0,
            OptimizeType::Center,
        )
        .unwrap_err();
        assert_eq!(err, PlacementError::NoSuchZone(99));
    }
}
