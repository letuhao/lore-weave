//! Stage 7 — route network.
//!
//! Five `RouteKind`s: Road (MST + nearest-neighbour augmentation over
//! `tier ≥ 2` settlements), Trail (small settlement → nearest large), SeaLane
//! (coastal-City water connectivity), MountainPass (mountain edges on Road
//! paths), RiverNavigation (navigable-river runs on Road/Trail paths).

use crate::biome::BiomeKind;
use crate::pathfind::{self, UnionFind};
use crate::world_map::{Route, RouteKind, Settlement, SettlementRole};

/// Build the route network.
// Triangular pairwise iteration over settlement indices (`ia < ib`, plus an
// `ib == ia` skip) — explicit index loops are clearer here than `enumerate`
// gymnastics, and each index addresses several parallel arrays.
#[allow(clippy::needless_range_loop)]
pub fn build(
    centers: &[(f32, f32)],
    neighbors: &[Vec<u32>],
    biomes: &[BiomeKind],
    river_flux: &[f32],
    river_threshold: f32,
    is_coast: &[bool],
    settlements: &[Settlement],
) -> Vec<Route> {
    let cost = |c: usize| biomes[c].terrain_cost();
    let mut sink = RouteSink::new();

    // Road-eligible settlements, sorted by cell id; Dijkstra from each.
    let mut road: Vec<&Settlement> = settlements
        .iter()
        .filter(|s| s.population_tier >= 2)
        .collect();
    road.sort_by_key(|s| s.cell);
    let dij: Vec<(Vec<u32>, Vec<u32>)> = road
        .iter()
        .map(|s| pathfind::single_source_dist(s.cell, cost, neighbors))
        .collect();
    let nr = road.len();
    let mut road_paths: Vec<Vec<u32>> = Vec::new();

    // --- 7a Road: Kruskal MST (one per land component) + augmentation ---
    let mut edges: Vec<(u32, usize, usize)> = Vec::new();
    for ia in 0..nr {
        for ib in (ia + 1)..nr {
            let d = dij[ia].0[road[ib].cell as usize];
            if d != u32::MAX {
                edges.push((d, ia, ib));
            }
        }
    }
    edges.sort_by(|x, y| {
        x.0.cmp(&y.0)
            .then(road[x.1].cell.cmp(&road[y.1].cell))
            .then(road[x.2].cell.cmp(&road[y.2].cell))
    });
    let mut uf = UnionFind::new(nr.max(1));
    let mut mst: Vec<(usize, usize)> = Vec::new();
    for &(_, ia, ib) in &edges {
        if uf.find(ia) != uf.find(ib) {
            uf.union(ia, ib);
            mst.push((ia, ib));
        }
    }
    for &(ia, ib) in &mst {
        emit_road(ia, ib, &road, &dij, &mut sink, &mut road_paths);
    }
    // augmentation: each settlement's nearest non-MST reachable neighbour.
    for ia in 0..nr {
        let mut best: Option<usize> = None;
        let mut best_key = (u32::MAX, u32::MAX);
        for ib in 0..nr {
            if ib == ia {
                continue;
            }
            let d = dij[ia].0[road[ib].cell as usize];
            if d == u32::MAX {
                continue;
            }
            let (lo, hi) = if ia < ib { (ia, ib) } else { (ib, ia) };
            if mst.contains(&(lo, hi)) {
                continue;
            }
            let key = (d, road[ib].cell);
            if key < best_key {
                best_key = key;
                best = Some(ib);
            }
        }
        if let Some(ib) = best {
            emit_road(ia, ib, &road, &dij, &mut sink, &mut road_paths);
        }
    }

    // --- 7b Trail: each tier 0-1 settlement → nearest road settlement ---
    let mut trail_paths: Vec<Vec<u32>> = Vec::new();
    let mut trail: Vec<&Settlement> = settlements
        .iter()
        .filter(|s| s.population_tier <= 1)
        .collect();
    trail.sort_by_key(|s| s.cell);
    for ts in &trail {
        let mut best: Option<usize> = None;
        let mut best_key = (u32::MAX, u32::MAX);
        for (k, dk) in dij.iter().enumerate() {
            let d = dk.0[ts.cell as usize];
            if d == u32::MAX {
                continue;
            }
            let key = (d, road[k].cell);
            if key < best_key {
                best_key = key;
                best = Some(k);
            }
        }
        if let Some(k) = best {
            if sink.push(RouteKind::Trail, ts.cell, road[k].cell, best_key.0) {
                trail_paths.push(pathfind::reconstruct_path(ts.cell, &dij[k].1));
            }
        }
    }

    // --- 7c SeaLane: coastal-City pairs connected over ocean water ---
    let mut cities: Vec<&Settlement> = settlements
        .iter()
        .filter(|s| s.role == SettlementRole::City && is_coast[s.cell as usize])
        .collect();
    cities.sort_by_key(|s| s.cell);
    for i in 0..cities.len() {
        for j in (i + 1)..cities.len() {
            let (cx, cy) = centers[cities[i].cell as usize];
            let (dx, dy) = centers[cities[j].cell as usize];
            let dist2 = (cx - dx) * (cx - dx) + (cy - dy) * (cy - dy);
            if dist2 > 0.25 {
                continue; // beyond 0.5 Euclidean range
            }
            let (src, dst) = (cities[i].cell, cities[j].cell);
            let passable = |c: usize| {
                c == src as usize || c == dst as usize || biomes[c] == BiomeKind::Ocean
            };
            if pathfind::bfs_reachable(src, dst, passable, neighbors) {
                let d = (dist2.sqrt() * 1000.0) as u32;
                sink.push(RouteKind::SeaLane, src, dst, d);
            }
        }
    }

    // --- 7d MountainPass: mountain-adjacent edges on Road paths, top 8 ---
    let mut medges: Vec<(u32, u32)> = Vec::new();
    for path in &road_paths {
        for w in path.windows(2) {
            let (a, b) = (w[0], w[1]);
            if biomes[a as usize] == BiomeKind::Mountain
                || biomes[b as usize] == BiomeKind::Mountain
            {
                medges.push(if a < b { (a, b) } else { (b, a) });
            }
        }
    }
    medges.sort_unstable();
    let mut tally: Vec<((u32, u32), u32)> = Vec::new();
    for e in medges {
        match tally.last_mut() {
            Some(last) if last.0 == e => last.1 += 1,
            _ => tally.push((e, 1)),
        }
    }
    // sort by (count desc, lo_cell, hi_cell)
    tally.sort_by(|x, y| {
        y.1.cmp(&x.1)
            .then(x.0.0.cmp(&y.0.0))
            .then(x.0.1.cmp(&y.0.1))
    });
    for &((lo, hi), _) in tally.iter().take(8) {
        sink.push(RouteKind::MountainPass, lo, hi, 1);
    }

    // --- 7e RiverNavigation: ≥3-cell navigable-river runs on Road/Trail paths ---
    // `river_flux > river_threshold` decides run boundaries (hence which
    // routes are emitted); both are identically-recomputed finite f32 ⇒ this
    // comparison is bit-stable across runs.
    for path in road_paths.iter().chain(trail_paths.iter()) {
        let mut i = 0usize;
        while i < path.len() {
            if river_flux[path[i] as usize] > river_threshold {
                let s = i;
                while i < path.len() && river_flux[path[i] as usize] > river_threshold {
                    i += 1;
                }
                if i - s >= 3 {
                    sink.push(
                        RouteKind::RiverNavigation,
                        path[s],
                        path[i - 1],
                        (i - s) as u32,
                    );
                }
            } else {
                i += 1;
            }
        }
    }

    sink.routes
}

/// Emit a Road for road-settlement indices `ia,ib`; record its path (once) if
/// the route was newly added.
fn emit_road(
    ia: usize,
    ib: usize,
    road: &[&Settlement],
    dij: &[(Vec<u32>, Vec<u32>)],
    sink: &mut RouteSink,
    road_paths: &mut Vec<Vec<u32>>,
) {
    let d = dij[ia].0[road[ib].cell as usize];
    if d == u32::MAX {
        return;
    }
    if sink.push(RouteKind::Road, road[ia].cell, road[ib].cell, d) {
        road_paths.push(pathfind::reconstruct_path(road[ib].cell, &dij[ia].1));
    }
}

/// Collects routes, deduplicating one per `(kind, lo_cell, hi_cell)`.
struct RouteSink {
    routes: Vec<Route>,
    seen: Vec<(u8, u32, u32)>,
}

impl RouteSink {
    fn new() -> Self {
        RouteSink {
            routes: Vec::new(),
            seen: Vec::new(),
        }
    }

    /// Push a route; returns `true` if it was newly added (not a duplicate or
    /// a degenerate self-loop).
    fn push(&mut self, kind: RouteKind, a: u32, b: u32, distance: u32) -> bool {
        if a == b {
            return false;
        }
        let (lo, hi) = if a < b { (a, b) } else { (b, a) };
        let key = (kind.tag(), lo, hi);
        if self.seen.contains(&key) {
            return false;
        }
        self.seen.push(key);
        self.routes.push(Route {
            kind,
            from_cell: lo,
            to_cell: hi,
            distance,
        });
        true
    }
}
