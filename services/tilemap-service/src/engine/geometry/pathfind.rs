//! TMP_007 §5 / TMP_003 §3.4 — grid path search. `search_path` is Dijkstra
//! (uniform-cost search), **not A\*** — Dijkstra is correct for any
//! non-negative cost with no heuristic-admissibility precondition (spec D6; an
//! A\* Manhattan heuristic needs a pinned per-edge cost ≥ 1, which TMP_007 §5
//! curved costs do not guarantee).
//!
//! Determinism (TMP-A4) is fully pinned: the frontier is a min-heap keyed
//! `(cost, flat_index)`; a tile's predecessor is set on the first relaxation
//! that reaches its minimal cost and is never overwritten by an equal-cost
//! alternative; neighbours are relaxed in flat-index order. A fixed
//! `(area, start, goals, cost)` therefore yields exactly one path.

use std::cmp::{Ordering, Reverse};
use std::collections::BinaryHeap;

use crate::types::tile::TileCoord;
use crate::types::tile_mask::TileMask;

use super::neighbors4;

/// An ordered tile sequence from a path's `start` to its reached goal.
pub type Path = Vec<TileCoord>;

/// A Dijkstra frontier entry, ordered by `(cost, flat_index)` — the pinned
/// deterministic settle order (spec D6).
struct Frontier {
    cost: f32,
    flat: usize,
    tile: TileCoord,
}

impl PartialEq for Frontier {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}
impl Eq for Frontier {}
impl PartialOrd for Frontier {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for Frontier {
    fn cmp(&self, other: &Self) -> Ordering {
        // `cost` is finite and ≥ 0 by the `search_path` contract, so `total_cmp`
        // is a sound total order here.
        self.cost
            .total_cmp(&other.cost)
            .then(self.flat.cmp(&other.flat))
    }
}

/// Shortest path from `start` to the nearest set tile of `goals`, over
/// 4-connected moves restricted to `area` (spec D6). `cost(from, to)` must be
/// finite and `≥ 0`. Returns `None` if `start` is outside `area` or no goal is
/// reachable.
///
/// The returned [`Path`] runs `[start, …, goal]`; if `start` is itself a goal
/// it is the singleton `[start]`.
pub fn search_path(
    area: &TileMask,
    start: TileCoord,
    goals: &TileMask,
    cost: impl Fn(TileCoord, TileCoord) -> f32,
) -> Option<Path> {
    let width = area.width();
    let height = area.height();
    if !area.get(start) {
        return None;
    }
    let n = area.tile_count();
    let mut dist = vec![f32::INFINITY; n];
    let mut prev: Vec<Option<TileCoord>> = vec![None; n];
    let mut settled = vec![false; n];

    let start_flat = start.flat_index(width);
    dist[start_flat] = 0.0;
    let mut heap: BinaryHeap<Reverse<Frontier>> = BinaryHeap::new();
    heap.push(Reverse(Frontier { cost: 0.0, flat: start_flat, tile: start }));

    while let Some(Reverse(Frontier { cost: c, flat, tile })) = heap.pop() {
        if settled[flat] {
            continue; // a stale heap entry — this tile already settled cheaper
        }
        settled[flat] = true;

        // Tiles settle in (cost, flat) order, so the first settled goal is the
        // lowest-flat-index goal at minimal cost (spec D6).
        if goals.get(tile) {
            return Some(reconstruct(&prev, width, start, tile));
        }

        for nb in neighbors4(tile, width, height) {
            if !area.get(nb) {
                continue;
            }
            let nb_flat = nb.flat_index(width);
            if settled[nb_flat] {
                continue;
            }
            let nd = c + cost(tile, nb);
            // Strictly-lower replaces; an equal-cost alternative does NOT
            // overwrite `prev` — this pins the chosen path (spec D6).
            if nd < dist[nb_flat] {
                dist[nb_flat] = nd;
                prev[nb_flat] = Some(tile);
                heap.push(Reverse(Frontier { cost: nd, flat: nb_flat, tile: nb }));
            }
        }
    }
    None
}

/// Walk `prev` from `goal` back to `start`, returning `[start, …, goal]`.
fn reconstruct(prev: &[Option<TileCoord>], width: u32, start: TileCoord, goal: TileCoord) -> Path {
    let mut path = vec![goal];
    let mut cur = goal;
    while cur != start {
        cur = prev[cur.flat_index(width)]
            .expect("prev chain from a settled goal must reach start");
        path.push(cur);
    }
    path.reverse();
    path
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a `TileMask` from ASCII rows — `'#'` sets a tile.
    fn grid(rows: &[&str]) -> TileMask {
        let height = rows.len() as u32;
        let width = rows[0].len() as u32;
        let mut m = TileMask::new(width, height);
        for (y, row) in rows.iter().enumerate() {
            for (x, ch) in row.chars().enumerate() {
                if ch == '#' {
                    m.set(TileCoord::new(x as u32, y as u32));
                }
            }
        }
        m
    }

    fn c(x: u32, y: u32) -> TileCoord {
        TileCoord::new(x, y)
    }

    fn uniform(_: TileCoord, _: TileCoord) -> f32 {
        1.0
    }

    /// A goal mask with a single set tile.
    fn goal_at(w: u32, h: u32, t: TileCoord) -> TileMask {
        let mut m = TileMask::new(w, h);
        m.set(t);
        m
    }

    #[test]
    fn finds_a_contiguous_shortest_path() {
        // AC-4 — a 1×5 open line: the path is contiguous and shortest.
        let area = grid(&["#####"]);
        let path = search_path(&area, c(0, 0), &goal_at(5, 1, c(4, 0)), uniform).unwrap();
        assert_eq!(path.first(), Some(&c(0, 0)));
        assert_eq!(path.last(), Some(&c(4, 0)));
        assert_eq!(path.len(), 5, "shortest path on a 1×5 line");
        for w in path.windows(2) {
            let step = (w[0].x as i32 - w[1].x as i32).abs()
                + (w[0].y as i32 - w[1].y as i32).abs();
            assert_eq!(step, 1, "non-adjacent step {:?} -> {:?}", w[0], w[1]);
        }
    }

    #[test]
    fn returns_none_when_no_goal_is_reachable() {
        // AC-4 — the area is split by a gap; the goal is on the far side.
        let area = grid(&["##.##"]);
        assert!(search_path(&area, c(0, 0), &goal_at(5, 1, c(4, 0)), uniform).is_none());
    }

    #[test]
    fn returns_none_when_start_is_outside_area() {
        let area = grid(&["#.#"]);
        assert!(search_path(&area, c(1, 0), &goal_at(3, 1, c(0, 0)), uniform).is_none());
    }

    #[test]
    fn start_already_at_a_goal_is_a_singleton_path() {
        let area = grid(&["###"]);
        let path = search_path(&area, c(1, 0), &goal_at(3, 1, c(1, 0)), uniform).unwrap();
        assert_eq!(path, vec![c(1, 0)]);
    }

    #[test]
    fn nearest_goal_tiebreak_picks_the_lower_flat_index_goal() {
        // AC-4 — `start` is equidistant (2 steps) from goals (0,0) and (4,0);
        // D6 pins the lower-flat-index goal — (0,0), flat 0.
        let area = grid(&["#####"]);
        let mut goals = TileMask::new(5, 1);
        goals.set(c(0, 0));
        goals.set(c(4, 0));
        let path = search_path(&area, c(2, 0), &goals, uniform).unwrap();
        assert_eq!(path, vec![c(2, 0), c(1, 0), c(0, 0)]);
    }

    #[test]
    fn equal_length_paths_resolve_to_the_pinned_route() {
        // AC-4 — a 3×3 open block has many shortest (0,0)→(2,2) routes; D6's
        // pinned tie-break (frontier keyed (cost, flat); neighbours up/left/
        // right/down; `prev` set on strict-<) yields exactly this route.
        let area = grid(&["###", "###", "###"]);
        let path = search_path(&area, c(0, 0), &goal_at(3, 3, c(2, 2)), uniform).unwrap();
        assert_eq!(path, vec![c(0, 0), c(1, 0), c(2, 0), c(2, 1), c(2, 2)]);
    }

    #[test]
    fn search_path_is_deterministic() {
        let area = grid(&["###", "###", "###"]);
        let g = goal_at(3, 3, c(2, 2));
        assert_eq!(
            search_path(&area, c(0, 0), &g, uniform),
            search_path(&area, c(0, 0), &g, uniform),
        );
    }
}
