//! Stage 1 — Voronoi dual-mesh.
//!
//! Point placement is a **perimeter ring + jittered interior grid** (the
//! Azgaar / Red-Blob boundary-points technique). The ring makes the
//! neighbour-degree bound provable: every interior point is strictly inside
//! the convex hull → closed triangle fan → degree ≥ 3; every non-corner ring
//! point has 2 ring neighbours + ≥ 1 interior neighbour → degree ≥ 3. The 4
//! ring corners are the one residual case and are fixed by `repair_degree`.

use delaunator::{Point, triangulate};

use crate::creative_seed::WorldScale;
use crate::rng::Rng;

/// Interior jitter as a fraction of grid spacing. ≤ 0.55 keeps interior
/// points strictly inside the ring and the grid topology intact.
const JITTER: f32 = 0.55;

/// The dual mesh — cell centres + symmetric adjacency.
pub struct Mesh {
    /// Cell centres in `[0,1]²`; index == cell id.
    pub centers: Vec<(f32, f32)>,
    /// `neighbors[i]` sorted ascending + deduped; symmetric.
    pub neighbors: Vec<Vec<u32>>,
}

/// Build the dual mesh for `scale`, seeded deterministically by `seed`.
pub fn build(seed: u64, scale: WorldScale) -> Mesh {
    let g = scale.grid_side();
    let mut rng = Rng::for_stage(seed, b"mesh");
    let centers = place_points(g, &mut rng);
    debug_assert_eq!(centers.len(), scale.cell_count());

    let mut neighbors = adjacency(&centers);
    repair_degree(&centers, &mut neighbors);

    Mesh { centers, neighbors }
}

/// Place the interior jittered grid (row-major) followed by the perimeter
/// ring (fixed walk order). The ordering is fixed → deterministic.
fn place_points(g: usize, rng: &mut Rng) -> Vec<(f32, f32)> {
    let gf = g as f32;
    let mut centers: Vec<(f32, f32)> = Vec::with_capacity((g - 2) * (g - 2) + 4 * (g - 1));

    // Interior: (g-2) x (g-2) jittered grid, row-major. The +1.5 offset
    // places points in notional grid columns/rows 1..g-1 (inside the ring).
    for j in 0..(g - 2) {
        for i in 0..(g - 2) {
            let jx = (rng.next_f32() - 0.5) * JITTER;
            let jy = (rng.next_f32() - 0.5) * JITTER;
            let x = (i as f32 + 1.5 + jx) / gf;
            let y = (j as f32 + 1.5 + jy) / gf;
            centers.push((x, y));
        }
    }

    // Ring: 4*(g-1) evenly-spaced un-jittered perimeter points. Each of the
    // four corners belongs to exactly one edge (no duplicate corners).
    let per_edge = g - 1;
    let step = 1.0 / per_edge as f32;
    for k in 0..per_edge {
        centers.push((k as f32 * step, 0.0)); // bottom edge, L->R
    }
    for k in 0..per_edge {
        centers.push((1.0, k as f32 * step)); // right edge, B->T
    }
    for k in 0..per_edge {
        centers.push((1.0 - k as f32 * step, 1.0)); // top edge, R->L
    }
    for k in 0..per_edge {
        centers.push((0.0, 1.0 - k as f32 * step)); // left edge, T->B
    }

    centers
}

/// Delaunay-triangulate the centres and collect symmetric adjacency.
fn adjacency(centers: &[(f32, f32)]) -> Vec<Vec<u32>> {
    let points: Vec<Point> = centers
        .iter()
        .map(|&(x, y)| Point {
            x: x as f64,
            y: y as f64,
        })
        .collect();
    let tri = triangulate(&points);

    let mut neighbors: Vec<Vec<u32>> = vec![Vec::new(); centers.len()];
    for t in tri.triangles.chunks_exact(3) {
        // usize -> u32: cell indices are provably <= 16384 << u32::MAX
        // (WorldScale::cell_count table), so this narrowing cannot truncate.
        let a = t[0] as u32;
        let b = t[1] as u32;
        let c = t[2] as u32;
        neighbors[t[0]].push(b);
        neighbors[t[0]].push(c);
        neighbors[t[1]].push(a);
        neighbors[t[1]].push(c);
        neighbors[t[2]].push(a);
        neighbors[t[2]].push(b);
    }
    for list in &mut neighbors {
        list.sort_unstable();
        list.dedup();
    }
    neighbors
}

/// Bring any cell with degree < 3 up to exactly 3 by linking it to its
/// nearest non-neighbour. In practice this touches only the ≤ 4 convex-hull
/// corners. Cells are swept in ascending index order so the set of repair
/// edges is a deterministic function of the (deterministic) input.
fn repair_degree(centers: &[(f32, f32)], neighbors: &mut [Vec<u32>]) {
    let count = centers.len();
    for i in 0..count {
        while neighbors[i].len() < 3 {
            let mut best: Option<usize> = None;
            let mut best_d = f32::INFINITY;
            for j in 0..count {
                if j == i || neighbors[i].contains(&(j as u32)) {
                    continue;
                }
                let dx = centers[i].0 - centers[j].0;
                let dy = centers[i].1 - centers[j].1;
                let d = dx * dx + dy * dy;
                // strict `<` ⇒ ties resolve to the lower index j.
                if d < best_d {
                    best_d = d;
                    best = Some(j);
                }
            }
            let j = best.expect("count >= 1024, so a non-neighbour always exists");
            neighbors[i].push(j as u32);
            neighbors[j].push(i as u32);
            neighbors[i].sort_unstable();
            neighbors[i].dedup();
            neighbors[j].sort_unstable();
            neighbors[j].dedup();
        }
    }
}
