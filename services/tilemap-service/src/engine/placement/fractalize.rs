//! TMP_002 §5 — fractalize: carve a connected free-path skeleton inside a zone.
//!
//! After Penrose assignment every tile of a zone is `Open`. Fractalize scatters
//! free-path waypoints across the zone (each one farther than a span-scaled
//! threshold from the others), then links the scattered fragments into one
//! connected skeleton via shortest paths over the zone's tiles (§5.2 end).
//!
//! **Phase-1 cut (spec D8):** `ZoneSpec` has no treasure tiers yet, so the §5.2
//! treasure-density scaling of `span_factor`/`margin_factor` is deferred — this
//! uses the base constants. The §5.2 pseudocode computes `block_distance =
//! min_distance × span_factor` but its loop excerpt is incomplete on where that
//! feeds in; Phase 1 uses `block_distance` as the **waypoint coverage
//! threshold** so `span_factor` (and thus the `Sea` special case) actually
//! affects `free_paths`, matching §5.3's "span_factor controls path density".
//!
//! **Special roles (D8):** `Forbidden` → all tiles blocked, `free_paths` empty;
//! `Hub` → a single straight path through the centre; `Sea` → the dense
//! `span_factor`. `assigned_tiles` is never modified.
//!
//! **Determinism (TMP-A4):** the candidate shuffle is the only RNG, drawn from
//! a per-zone `"fractalize:<zone_id>"` sub-stream ([`sub_seed`]) so per-zone
//! work stays reproducible even once it is parallelised. Component linking is a
//! deterministic BFS (fixed N/E/S/W neighbour order).

use std::collections::{HashMap, HashSet, VecDeque};

use rand::SeedableRng;
use rand::seq::SliceRandom;
use rand_chacha::ChaCha8Rng;

use crate::seed::{TilemapSeed, sub_seed};
use crate::types::tile::TileCoord;
use crate::types::tile_mask::TileMask;
use crate::types::zone::{ZoneId, ZoneRole};

use super::ZoneTiles;

/// Base squared-distance constant (`9 × 9`) — TMP_002 §5.2.
const MIN_DISTANCE: f64 = 81.0;
/// Surface `span_factor` (`Wilderness`) — §5.2.
const SPAN_SURFACE: f64 = 0.45;
/// `Sea` `span_factor` — denser free paths, sparser obstacles (§5.2).
const SPAN_SEA: f64 = 0.2;
/// Tiles within this many cells of the grid boundary are excluded as waypoint
/// candidates — paths adjacent to the map edge render badly (§5.4).
const MARGIN: u32 = 3;

/// TMP_002 §5 — fill `zone.free_paths` with a connected free-path skeleton.
///
/// Dispatches on the zone role (D8); `assigned_tiles` is left untouched.
pub fn fractalize_zone(zone: &mut ZoneTiles, seed: TilemapSeed) {
    let w = zone.assigned_tiles.width();
    let h = zone.assigned_tiles.height();
    zone.free_paths = match zone.role {
        // Forbidden — every tile blocked, no free path.
        ZoneRole::Forbidden => TileMask::new(w, h),
        // Hub — a single straight path, not the meandering skeleton.
        ZoneRole::Hub => hub_path(&zone.assigned_tiles, zone.center),
        ZoneRole::Wilderness | ZoneRole::Sea => {
            let span = if zone.role == ZoneRole::Sea {
                SPAN_SEA
            } else {
                SPAN_SURFACE
            };
            scatter_and_connect(&zone.assigned_tiles, zone.center, span, seed, &zone.id)
        }
    };
}

/// Hub free path — the contiguous horizontal run of assigned tiles through the
/// centre. Straight + connected + non-empty by construction.
fn hub_path(assigned: &TileMask, center: TileCoord) -> TileMask {
    let mut path = TileMask::new(assigned.width(), assigned.height());
    path.set(center);
    let mut x = center.x;
    while x > 0 && assigned.get(TileCoord::new(x - 1, center.y)) {
        x -= 1;
        path.set(TileCoord::new(x, center.y));
    }
    let mut x = center.x;
    while x + 1 < assigned.width() && assigned.get(TileCoord::new(x + 1, center.y)) {
        x += 1;
        path.set(TileCoord::new(x, center.y));
    }
    path
}

/// §5.2 main loop — scatter waypoints, then link fragments into one skeleton.
fn scatter_and_connect(
    assigned: &TileMask,
    center: TileCoord,
    span_factor: f64,
    seed: TilemapSeed,
    zone_id: &ZoneId,
) -> TileMask {
    let w = assigned.width();
    let h = assigned.height();
    // block_distance — the squared coverage radius (see module docs).
    let coverage_sq = (MIN_DISTANCE * span_factor) as i64;

    let mut cleared = TileMask::new(w, h);
    cleared.set(center);

    // Candidate waypoints — assigned tiles clear of the boundary margin.
    let mut candidates: Vec<TileCoord> = assigned
        .iter_set()
        .filter(|t| t.x >= MARGIN && t.y >= MARGIN && t.x + MARGIN < w && t.y + MARGIN < h)
        .collect();
    let mut rng = ChaCha8Rng::seed_from_u64(sub_seed(seed, &format!("fractalize:{}", zone_id.0)));
    candidates.shuffle(&mut rng);

    // Greedy scatter — keep a tile only if it is farther than the coverage
    // radius from every waypoint placed so far (§5.2: a closer tile is already
    // covered and gets ignored).
    for t in candidates {
        if nearest_cleared_dist_sq(t, &cleared) > coverage_sq {
            cleared.set(t);
        }
    }

    connect_components(&mut cleared, assigned);
    cleared
}

/// Squared distance from `t` to the nearest set tile of `cleared` (which always
/// holds at least the zone centre, so this never sees an empty mask).
fn nearest_cleared_dist_sq(t: TileCoord, cleared: &TileMask) -> i64 {
    let mut best = i64::MAX;
    for c in cleared.iter_set() {
        let dx = t.x as i64 - c.x as i64;
        let dy = t.y as i64 - c.y as i64;
        let d = dx * dx + dy * dy;
        if d < best {
            best = d;
        }
    }
    best
}

/// §5.2 end — connected-components fixup. Links scattered waypoint fragments
/// into a single connected skeleton by BFS-routing each later fragment to the
/// deterministic main fragment over the zone's tiles. A fragment in an
/// isolated patch of `assigned` (a disconnected zone region) is left as-is.
fn connect_components(cleared: &mut TileMask, assigned: &TileMask) {
    loop {
        let comps = components(cleared);
        if comps.len() <= 1 {
            return;
        }
        // comps[0] is the deterministic main (lowest flat-index tile). Connect
        // the first later fragment that can reach it through `assigned`.
        let mut progress = false;
        for other in comps.iter().skip(1) {
            if let Some(path) = shortest_path(other, &comps[0], assigned) {
                for t in path {
                    cleared.set(t);
                }
                progress = true;
                break;
            }
        }
        if !progress {
            return; // remaining fragments sit in isolated `assigned` patches
        }
    }
}

/// 4-connected components of `mask`, ordered by each component's lowest
/// flat-index tile (deterministic — `iter_set` walks flat order).
fn components(mask: &TileMask) -> Vec<Vec<TileCoord>> {
    let w = mask.width();
    let h = mask.height();
    let mut visited = TileMask::new(w, h);
    let mut comps: Vec<Vec<TileCoord>> = Vec::new();
    for start in mask.iter_set() {
        if visited.get(start) {
            continue;
        }
        let mut comp = Vec::new();
        let mut queue = VecDeque::new();
        visited.set(start);
        queue.push_back(start);
        while let Some(c) = queue.pop_front() {
            comp.push(c);
            for nb in neighbours(c, w, h) {
                if mask.get(nb) && !visited.get(nb) {
                    visited.set(nb);
                    queue.push_back(nb);
                }
            }
        }
        comps.push(comp);
    }
    comps
}

/// Shortest 4-connected path from any `from` tile to any `to` tile, travelling
/// only over `assigned` tiles. Multi-source BFS with a fixed neighbour order —
/// deterministic. `None` if `to` is unreachable from `from` within `assigned`.
fn shortest_path(
    from: &[TileCoord],
    to: &[TileCoord],
    assigned: &TileMask,
) -> Option<Vec<TileCoord>> {
    let w = assigned.width();
    let h = assigned.height();
    let to_set: HashSet<TileCoord> = to.iter().copied().collect();
    let mut pred: HashMap<TileCoord, TileCoord> = HashMap::new();
    let mut queue: VecDeque<TileCoord> = VecDeque::new();

    // Seed sources in a deterministic order.
    let mut starts: Vec<TileCoord> = from.to_vec();
    starts.sort_unstable_by_key(|c| (c.y, c.x));
    for &s in &starts {
        if pred.insert(s, s).is_none() {
            queue.push_back(s);
        }
    }

    while let Some(cur) = queue.pop_front() {
        for nb in neighbours(cur, w, h) {
            if !assigned.get(nb) || pred.contains_key(&nb) {
                continue;
            }
            pred.insert(nb, cur);
            if to_set.contains(&nb) {
                // Reconstruct nb → … → source (source's predecessor is itself).
                let mut path = vec![nb];
                let mut step = nb;
                while pred[&step] != step {
                    step = pred[&step];
                    path.push(step);
                }
                return Some(path);
            }
            queue.push_back(nb);
        }
    }
    None
}

/// In-bounds 4-neighbours of `c` in fixed N, E, S, W order (determinism).
fn neighbours(c: TileCoord, w: u32, h: u32) -> Vec<TileCoord> {
    let mut n = Vec::with_capacity(4);
    if c.y > 0 {
        n.push(TileCoord::new(c.x, c.y - 1));
    }
    if c.x + 1 < w {
        n.push(TileCoord::new(c.x + 1, c.y));
    }
    if c.y + 1 < h {
        n.push(TileCoord::new(c.x, c.y + 1));
    }
    if c.x > 0 {
        n.push(TileCoord::new(c.x - 1, c.y));
    }
    n
}

#[cfg(test)]
mod tests {
    use super::*;

    fn full_rect(w: u32, h: u32) -> TileMask {
        let mut m = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                m.set(TileCoord::new(x, y));
            }
        }
        m
    }

    fn rect_zone(id: &str, role: ZoneRole, w: u32, h: u32, cx: u32, cy: u32) -> ZoneTiles {
        ZoneTiles {
            id: ZoneId(id.to_string()),
            role,
            center: TileCoord::new(cx, cy),
            assigned_tiles: full_rect(w, h),
            free_paths: TileMask::new(w, h),
        }
    }

    #[test]
    fn scatter_and_connect_yields_one_connected_component() {
        let assigned = full_rect(24, 24);
        let paths = scatter_and_connect(
            &assigned,
            TileCoord::new(12, 12),
            SPAN_SURFACE,
            TilemapSeed(1),
            &ZoneId("z".to_string()),
        );
        assert!(!paths.is_empty());
        assert!(paths.get(TileCoord::new(12, 12)), "centre missing from path");
        assert_eq!(
            components(&paths).len(),
            1,
            "free paths must be a single connected skeleton",
        );
    }

    #[test]
    fn forbidden_zone_has_empty_free_paths() {
        let mut z = rect_zone("f", ZoneRole::Forbidden, 16, 16, 8, 8);
        let assigned_before = z.assigned_tiles.clone();
        fractalize_zone(&mut z, TilemapSeed(1));
        assert!(z.free_paths.is_empty(), "Forbidden zone must block all tiles");
        assert_eq!(z.assigned_tiles, assigned_before, "assigned_tiles untouched");
    }

    #[test]
    fn hub_zone_path_is_straight_and_connected() {
        let mut z = rect_zone("h", ZoneRole::Hub, 20, 20, 10, 7);
        fractalize_zone(&mut z, TilemapSeed(1));
        assert!(!z.free_paths.is_empty());
        assert!(z.free_paths.get(TileCoord::new(10, 7)));
        for t in z.free_paths.iter_set() {
            assert_eq!(t.y, 7, "Hub path must be a single straight row");
        }
        assert_eq!(components(&z.free_paths).len(), 1);
    }

    #[test]
    fn sea_free_paths_are_denser_than_wilderness() {
        let assigned = full_rect(24, 24);
        let centre = TileCoord::new(12, 12);
        let sea = scatter_and_connect(
            &assigned,
            centre,
            SPAN_SEA,
            TilemapSeed(5),
            &ZoneId("s".to_string()),
        );
        let land = scatter_and_connect(
            &assigned,
            centre,
            SPAN_SURFACE,
            TilemapSeed(5),
            &ZoneId("s".to_string()),
        );
        assert!(
            sea.count_ones() > land.count_ones(),
            "Sea ({}) should have denser free paths than Wilderness ({})",
            sea.count_ones(),
            land.count_ones(),
        );
    }

    #[test]
    fn fractalize_is_deterministic() {
        let mk = || rect_zone("z", ZoneRole::Wilderness, 20, 20, 10, 10);
        let mut a = mk();
        let mut b = mk();
        fractalize_zone(&mut a, TilemapSeed(0xF00D));
        fractalize_zone(&mut b, TilemapSeed(0xF00D));
        assert_eq!(a.free_paths, b.free_paths);
    }

    #[test]
    fn small_zone_inside_the_margin_still_has_a_centre_path() {
        // Every tile sits within MARGIN of the boundary — no candidates — but
        // the centre is still a valid (single-tile) free path.
        let mut z = rect_zone("tiny", ZoneRole::Wilderness, 5, 5, 2, 2);
        fractalize_zone(&mut z, TilemapSeed(1));
        assert!(!z.free_paths.is_empty());
        assert!(z.free_paths.get(TileCoord::new(2, 2)));
    }
}
