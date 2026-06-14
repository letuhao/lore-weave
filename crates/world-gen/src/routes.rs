//! Stage 7 — route network.
//!
//! Five `RouteKind`s:
//! - **Road** — Kruskal MST + nearest-neighbour augmentation over `tier ≥ 2`
//!   settlements (terrain-cost Dijkstra).
//! - **Trail** — each `tier ≤ 1` settlement → its nearest road settlement.
//! - **SeaLane** — coastal City/Capital pairs within range, connected over an
//!   `{Ocean, Coast}` water corridor (GEO_004 §5.2 phase 4).
//! - **MountainPass** — the top Mountain/Hill edges by settlement-pair
//!   edge-betweenness (GEO_004 §5.2 phase 5, Brandes-style).
//! - **RiverNavigation** — ≥3-cell navigable-river runs on Road/Trail paths.
//!
//! Every emitted `Route` carries the full cell `path` it traverses.

use std::collections::BTreeMap;

use crate::biome::BiomeKind;
use crate::params::RouteParams;
use crate::pathfind::{self, UnionFind};
use crate::world_map::{Route, RouteKind, Settlement};

/// Build the route network using the **default** tuning. Thin wrapper over
/// [`build_with`] for callers that don't tune it (the civ adapter + tests).
pub fn build(
    centers: &[[f32; 3]],
    neighbors: &[Vec<u32>],
    biomes: &[BiomeKind],
    river_flux: &[f32],
    river_threshold: f32,
    is_coast: &[bool],
    settlements: &[Settlement],
) -> Vec<Route> {
    build_with(
        centers, neighbors, biomes, river_flux, river_threshold, is_coast, settlements,
        &RouteParams::default(),
    )
}

/// Build the route network with caller-tuned [`RouteParams`] (parameterization
/// P5). Default params ⇒ byte-identical to the prior consts.
///
/// **Phase 1 Stage B (2026-05-20):** `centers` is now 3D unit-sphere points;
/// the port-anchor distance step uses spherical distance.
// Triangular pairwise iteration over settlement indices, plus index loops that
// each address several parallel arrays — clearer than `enumerate` gymnastics.
#[allow(clippy::needless_range_loop, clippy::too_many_arguments)]
pub fn build_with(
    centers: &[[f32; 3]],
    neighbors: &[Vec<u32>],
    biomes: &[BiomeKind],
    river_flux: &[f32],
    river_threshold: f32,
    is_coast: &[bool],
    settlements: &[Settlement],
    rp: &RouteParams,
) -> Vec<Route> {
    let cost = |c: usize| biomes[c].terrain_cost();
    let mut sink = RouteSink::new();
    // Road + Trail cell paths — scanned by RiverNavigation (7e).
    let mut land_paths: Vec<Vec<u32>> = Vec::new();

    // Road-eligible settlements, sorted by cell id; Dijkstra from each.
    let mut road: Vec<&Settlement> = settlements
        .iter()
        .filter(|s| s.population_tier as u32 >= rp.road_tier_min)
        .collect();
    road.sort_by_key(|s| s.cell);
    let dij: Vec<(Vec<u32>, Vec<u32>)> = road
        .iter()
        .map(|s| pathfind::single_source_dist(s.cell, cost, neighbors))
        .collect();
    let nr = road.len();

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
        emit_road(ia, ib, &road, &dij, &mut sink, &mut land_paths);
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
            emit_road(ia, ib, &road, &dij, &mut sink, &mut land_paths);
        }
    }

    // --- 7b Trail: each tier 0-1 settlement → nearest road settlement ---
    let mut trail: Vec<&Settlement> = settlements
        .iter()
        .filter(|s| s.population_tier as u32 <= rp.trail_tier_max)
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
            // Path through the road settlement's Dijkstra tree, root → ts.cell.
            let path = pathfind::reconstruct_path(ts.cell, &dij[k].1);
            if sink.push(RouteKind::Trail, path.clone(), best_key.0) {
                land_paths.push(path);
            }
        }
    }

    // --- 7c SeaLane: bridge separate landmasses via per-component ports ---
    // GEO_004's pairwise coastal-City SeaLane cannot connect an archipelago:
    // most island settlements sit inland, coastal Cities are far too rare to
    // pair, and the ROUTE-V12 range cap blocks the open-ocean hops islands
    // need. Instead, give every inhabited land component one coastal *port*
    // and build a minimum spanning tree of SeaLanes over the ports — every
    // island becomes reachable with the fewest open-ocean crossings, and an
    // MST never produces a pointless cross-map route, so no range cap is
    // needed. The water corridor is BFS-passable over {Ocean, Coast} cells
    // (GEO_004 §5.2 step 11a).
    let is_land: Vec<bool> = biomes.iter().map(|b| !b.is_water()).collect();
    let comps = pathfind::land_components(&is_land, neighbors);
    let mut comp_of = vec![u32::MAX; centers.len()];
    for (ci, comp) in comps.iter().enumerate() {
        for &c in comp {
            comp_of[c as usize] = ci as u32;
        }
    }
    // One port per inhabited component: the coastal cell nearest the
    // component's highest-tier settlement.
    let mut ports: Vec<u32> = Vec::new();
    for (ci, comp) in comps.iter().enumerate() {
        let anchor = settlements
            .iter()
            .filter(|s| comp_of[s.cell as usize] == ci as u32)
            .max_by(|a, b| {
                a.population_tier
                    .cmp(&b.population_tier)
                    .then(b.cell.cmp(&a.cell)) // tie → lower cell id
            });
        let Some(anchor) = anchor else {
            continue; // uninhabited landmass — nothing to connect
        };
        let a3 = centers[anchor.cell as usize];
        let mut best_port: Option<u32> = None;
        let mut best_d = f32::INFINITY;
        for &c in comp {
            if !is_coast[c as usize] {
                continue;
            }
            let c3 = centers[c as usize];
            // `1 − dot` is monotone-equivalent to great-circle distance on
            // unit-sphere vectors and stays in f32 (no acos branch).
            let dot = a3[0] * c3[0] + a3[1] * c3[1] + a3[2] * c3[2];
            let d = 1.0 - dot;
            if d < best_d {
                best_d = d;
                best_port = Some(c);
            }
        }
        if let Some(p) = best_port {
            ports.push(p);
        }
    }
    ports.sort_unstable();
    // Sea distance (BFS hop count over {Ocean, Coast}) between every port pair.
    let mut sea_edges: Vec<(usize, usize, usize, Vec<u32>)> = Vec::new();
    for i in 0..ports.len() {
        for j in (i + 1)..ports.len() {
            let (src, dst) = (ports[i], ports[j]);
            let passable = |c: usize| {
                c == src as usize
                    || c == dst as usize
                    || matches!(biomes[c], BiomeKind::Ocean | BiomeKind::Coast)
            };
            if let Some(path) = pathfind::bfs_path(src, dst, passable, neighbors) {
                sea_edges.push((path.len(), i, j, path));
            }
        }
    }
    // Kruskal MST over the ports → the minimal SeaLane set linking every
    // sea-reachable landmass.
    sea_edges.sort_by(|x, y| {
        x.0.cmp(&y.0)
            .then(ports[x.1].cmp(&ports[y.1]))
            .then(ports[x.2].cmp(&ports[y.2]))
    });
    let mut sea_uf = UnionFind::new(ports.len().max(1));
    for (len, i, j, path) in sea_edges {
        if sea_uf.find(i) != sea_uf.find(j) {
            sea_uf.union(i, j);
            sink.push(RouteKind::SeaLane, path, len as u32);
        }
    }

    // --- 7d MountainPass: top Mountain/Hill edges by settlement-pair
    //     edge-betweenness (GEO_004 §5.2 phase 5) ---
    // Tally every cell-graph edge lying on a shortest path between a pair of
    // road settlements; the highest-betweenness Mountain/Hill edges are the
    // chokepoint passes. (A Road *itself* routes around cost-8 Mountains, so
    // the earlier "scan Road paths for mountain cells" proxy almost never
    // fired — betweenness over the cell graph finds the true chokepoints.)
    // BTreeMap, not HashMap — deterministic key-order iteration.
    let mut betweenness: BTreeMap<(u32, u32), u32> = BTreeMap::new();
    for ia in 0..nr {
        for ib in (ia + 1)..nr {
            if dij[ia].0[road[ib].cell as usize] == u32::MAX {
                continue;
            }
            let path = pathfind::reconstruct_path(road[ib].cell, &dij[ia].1);
            for w in path.windows(2) {
                let edge = if w[0] < w[1] { (w[0], w[1]) } else { (w[1], w[0]) };
                *betweenness.entry(edge).or_insert(0) += 1;
            }
        }
    }
    let mut eligible: Vec<((u32, u32), u32)> = betweenness
        .into_iter()
        .filter(|&((a, b), _)| {
            matches!(biomes[a as usize], BiomeKind::Mountain | BiomeKind::Hill)
                || matches!(biomes[b as usize], BiomeKind::Mountain | BiomeKind::Hill)
        })
        .collect();
    // Highest betweenness first; (lo, hi) cell tie-break → deterministic.
    eligible.sort_by(|x, y| y.1.cmp(&x.1).then(x.0.cmp(&y.0)));
    for &((a, b), _) in eligible.iter().take(rp.mountain_pass_target as usize) {
        sink.push(RouteKind::MountainPass, vec![a, b], 1);
    }

    // --- 7e RiverNavigation: ≥3-cell navigable-river runs on Road/Trail paths ---
    // `river_flux > river_threshold` decides run boundaries; both are
    // identically-recomputed finite f32 ⇒ this comparison is bit-stable.
    for path in &land_paths {
        let mut i = 0usize;
        while i < path.len() {
            if river_flux[path[i] as usize] > river_threshold {
                let s = i;
                while i < path.len() && river_flux[path[i] as usize] > river_threshold {
                    i += 1;
                }
                if (i - s) as u32 >= rp.river_nav_min_run {
                    sink.push(RouteKind::RiverNavigation, path[s..i].to_vec(), (i - s) as u32);
                }
            } else {
                i += 1;
            }
        }
    }

    sink.routes
}

/// Emit a Road for road-settlement indices `ia,ib`; record its cell path
/// (once) into `land_paths` if the route was newly added.
fn emit_road(
    ia: usize,
    ib: usize,
    road: &[&Settlement],
    dij: &[(Vec<u32>, Vec<u32>)],
    sink: &mut RouteSink,
    land_paths: &mut Vec<Vec<u32>>,
) {
    let d = dij[ia].0[road[ib].cell as usize];
    if d == u32::MAX {
        return;
    }
    let path = pathfind::reconstruct_path(road[ib].cell, &dij[ia].1);
    if sink.push(RouteKind::Road, path.clone(), d) {
        land_paths.push(path);
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

    /// Push a route from the cell `path` it traverses; returns `true` if it
    /// was newly added (not a duplicate `(kind, pair)` or a degenerate
    /// self-loop / single-cell path). The stored path is oriented
    /// `from_cell (= lo) … to_cell (= hi)`.
    fn push(&mut self, kind: RouteKind, mut path: Vec<u32>, distance: u32) -> bool {
        if path.len() < 2 {
            return false;
        }
        let (a, b) = (path[0], path[path.len() - 1]);
        if a == b {
            return false;
        }
        let (lo, hi) = if a < b { (a, b) } else { (b, a) };
        let key = (kind.tag(), lo, hi);
        if self.seen.contains(&key) {
            return false;
        }
        self.seen.push(key);
        if a != lo {
            path.reverse(); // orient lo → hi so path[0] == from_cell
        }
        self.routes.push(Route {
            kind,
            from_cell: lo,
            to_cell: hi,
            distance,
            path,
        });
        true
    }
}
