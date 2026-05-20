//! Stage 1 — spherical Voronoi dual-mesh on the unit sphere.
//!
//! **Topology (Phase 1 world-tier redesign, 2026-05-20).** Points are sampled
//! on the unit sphere using a **Fibonacci lattice** — quasi-uniform in solid
//! angle, deterministic given `n`. A seed-driven 3D rotation reorients the
//! whole lattice so different seeds produce different worlds. The adjacency is
//! the **spherical Delaunay triangulation**, which we obtain as the **3D
//! convex hull** of the sample points (every point of an N-point set on a
//! sphere is on its own convex hull → every hull face is a Delaunay triangle).
//! The **spherical Voronoi polygon** of each cell is the loop of
//! sphere-projected circumcentres of its incident Delaunay triangles.
//!
//! There are no edges, no hull corners, no E–W seam, no pole degeneracy by
//! construction — the sphere has none of these. `repair_degree` from the flat
//! mesh is therefore gone.
//!
//! Determinism rules (load-bearing):
//! - Fibonacci index `i ∈ 0..N` is the **cell id**. The seed-driven rotation
//!   does not reorder indices.
//! - 3D Quickhull picks the **farthest** point above each face; ties are
//!   broken by **ascending point index**.
//! - Spherical Voronoi vertices are ordered **CCW around the cell centre**
//!   via tangent-plane angle (`atan2` of an orthonormal-basis projection).

use std::f32::consts::TAU;

use crate::creative_seed::WorldScale;
use crate::rng::Rng;

/// Plane-side epsilon for the 3D Quickhull. Rust 2024 deprecates
/// `std::f64::EPSILON` in favour of the associated-const form below.
const F64_EPS: f64 = f64::EPSILON;

/// The dual mesh — cell centres + symmetric adjacency + spherical Voronoi
/// polygons. **All geometry is on the unit sphere.**
pub struct Mesh {
    /// Cell centres on the unit sphere; index == cell id.
    pub centers: Vec<[f32; 3]>,
    /// `neighbors[i]` sorted ascending + deduped; symmetric.
    pub neighbors: Vec<Vec<u32>>,
    /// `polygons[i]` — cell `i`'s spherical Voronoi polygon — an angle-ordered
    /// vertex ring of unit-sphere points (≥ 3 vertices).
    pub polygons: Vec<Vec<[f32; 3]>>,
}

impl Mesh {
    /// Latitude of cell `i`, radians in `[-π/2, π/2]`. North pole is `+π/2`.
    pub fn lat(&self, i: usize) -> f32 {
        let z = self.centers[i][2].clamp(-1.0, 1.0);
        z.asin()
    }

    /// Longitude of cell `i`, radians in `(-π, π]`. `atan2(y, x)`.
    pub fn lon(&self, i: usize) -> f32 {
        let p = self.centers[i];
        p[1].atan2(p[0])
    }
}

/// Build the dual mesh for `scale`, seeded deterministically by `seed`.
pub fn build(seed: u64, scale: WorldScale) -> Mesh {
    let n = scale.cell_count();
    let mut rng = Rng::for_stage(seed, b"mesh");

    let centers = place_points_sphere(n, &mut rng);
    debug_assert_eq!(centers.len(), n);

    let triangles = convex_hull_3d(&centers);
    let neighbors = adjacency(&triangles, n);
    let polygons = voronoi_polygons_sphere(&centers, &triangles);

    Mesh {
        centers,
        neighbors,
        polygons,
    }
}

// --- Fibonacci sphere placement --------------------------------------------

/// Place `n` quasi-uniform points on the unit sphere via the Fibonacci lattice,
/// then apply a seed-driven uniform 3D rotation. Returns 3D Cartesian points.
fn place_points_sphere(n: usize, rng: &mut Rng) -> Vec<[f32; 3]> {
    // Golden angle in radians: π · (3 − √5). Used as a precomputed `f64` for
    // sub-f32 precision on the multiplication `i · golden_angle` at large `i`
    // (Gigaplanet pushes `i` up to ~500k — `i · golden_angle` then exceeds
    // 2³², beyond which `f32 mod 2π` becomes lossy).
    const GOLDEN_ANGLE_F64: f64 = std::f64::consts::PI * (3.0 - 2.236_067_977_499_79);

    // Seed-driven uniform-on-SO(3) quaternion (Shoemake 1992).
    let rot = random_quaternion(rng);

    let nf = n as f64;
    let mut points = Vec::with_capacity(n);
    for i in 0..n {
        let z = 1.0 - (2.0 * i as f64 + 1.0) / nf;
        let r = (1.0 - z * z).max(0.0).sqrt();
        // Reduce the multiplication to `[0, 2π)` in f64 *before* casting to
        // f32 — preserves angle precision for huge `n`.
        let phi64 = (i as f64 * GOLDEN_ANGLE_F64) % (std::f64::consts::PI * 2.0);
        let phi = phi64 as f32;
        let x = (r as f32) * phi.cos();
        let y = (r as f32) * phi.sin();
        let p = rotate_q(rot, [x, y, z as f32]);
        // Renormalize against accumulated f32 drift.
        points.push(normalize(p));
    }
    points
}

/// Uniform-on-SO(3) unit quaternion via Shoemake's method.
fn random_quaternion(rng: &mut Rng) -> [f32; 4] {
    let u1 = rng.next_f32();
    let u2 = rng.next_f32();
    let u3 = rng.next_f32();
    let s1 = (1.0 - u1).max(0.0).sqrt();
    let s2 = u1.max(0.0).sqrt();
    let a = TAU * u2;
    let b = TAU * u3;
    let q = [s1 * a.sin(), s1 * a.cos(), s2 * b.sin(), s2 * b.cos()];
    // Renormalize against any f32 drift.
    let n = (q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]).sqrt();
    [q[0] / n, q[1] / n, q[2] / n, q[3] / n]
}

/// Apply unit quaternion `q = (x, y, z, w)` to vector `v`. Rodrigues form:
/// `v' = v + 2 q.xyz × (q.xyz × v + q.w v)`.
fn rotate_q(q: [f32; 4], v: [f32; 3]) -> [f32; 3] {
    let qv = [q[0], q[1], q[2]];
    let w = q[3];
    let t1 = cross(qv, v);
    let t2 = [t1[0] + w * v[0], t1[1] + w * v[1], t1[2] + w * v[2]];
    let t3 = cross(qv, t2);
    [
        v[0] + 2.0 * t3[0],
        v[1] + 2.0 * t3[1],
        v[2] + 2.0 * t3[2],
    ]
}

// --- 3D convex hull (hand-rolled Quickhull) --------------------------------

/// Compute the 3D convex hull of `points` (all assumed to be on the unit
/// sphere). Returns a list of CCW-from-outside triangles `[v0, v1, v2]`.
///
/// Determinism: ties broken by ascending vertex index everywhere.
fn convex_hull_3d(points: &[[f32; 3]]) -> Vec<[u32; 3]> {
    assert!(
        points.len() >= 4,
        "convex hull needs at least 4 non-coplanar points"
    );
    // f64 throughout the hull for numerical robustness.
    let pts: Vec<[f64; 3]> = points
        .iter()
        .map(|p| [p[0] as f64, p[1] as f64, p[2] as f64])
        .collect();

    // Step 1 — initial tetrahedron from 4 extreme indices.
    let tet = initial_tetrahedron(&pts);

    // Step 2 — seed the face list, outward-oriented relative to the initial
    // tetrahedron centroid (a point known to be inside every hull face for
    // the unit-sphere input). The centroid stays a stable interior reference
    // as the hull grows because every new face has the entire convex hull
    // — including the original tet — on its inside.
    let centroid = [
        (pts[tet[0]][0] + pts[tet[1]][0] + pts[tet[2]][0] + pts[tet[3]][0]) / 4.0,
        (pts[tet[0]][1] + pts[tet[1]][1] + pts[tet[2]][1] + pts[tet[3]][1]) / 4.0,
        (pts[tet[0]][2] + pts[tet[1]][2] + pts[tet[2]][2] + pts[tet[3]][2]) / 4.0,
    ];
    let mut faces: Vec<HullFace> = Vec::new();
    let tetra_faces: [[usize; 3]; 4] = [
        [tet[0], tet[1], tet[2]],
        [tet[0], tet[2], tet[3]],
        [tet[0], tet[3], tet[1]],
        [tet[1], tet[3], tet[2]],
    ];
    for f in tetra_faces {
        faces.push(make_outward_face(&pts, f, centroid));
    }

    // Step 3 — assign each non-tetrahedron point to the first face above it.
    // (Tetrahedron vertices are already on the hull; skip them.)
    for (i, p) in pts.iter().enumerate() {
        if i == tet[0] || i == tet[1] || i == tet[2] || i == tet[3] {
            continue;
        }
        for face in faces.iter_mut() {
            if signed_distance(face, p) > F64_EPS {
                face.above.push(i as u32);
                break;
            }
        }
    }

    // Step 4 — iterate. A worklist of face indices with non-empty above-sets.
    let mut work: Vec<usize> = faces
        .iter()
        .enumerate()
        .filter_map(|(i, f)| if !f.above.is_empty() { Some(i) } else { None })
        .collect();
    work.sort_unstable();

    // We expand the hull face by face. Faces are tombstoned (not compacted)
    // for stable indices during the loop; compaction happens at the end.
    let mut alive: Vec<bool> = vec![true; faces.len()];

    while let Some(fi) = work.pop() {
        if !alive[fi] || faces[fi].above.is_empty() {
            continue;
        }
        // Pick the **farthest** above-point — ties resolved by ascending index.
        let apex = farthest_above_index(&faces[fi], &pts);

        // Find all visible faces from `apex` — start at `fi`, BFS outward by
        // shared edges.
        let visible = collect_visible(apex, &faces, &alive, fi, &pts);

        // The horizon is the set of edges of `visible` faces that are shared
        // with a **non-visible** face. CCW orientation of the new triangles
        // follows the horizon edge orientation seen *from a visible face*.
        let horizon = compute_horizon(&visible, &faces);

        // Tombstone all visible faces; gather their orphaned above-points.
        let mut orphans: Vec<u32> = Vec::new();
        for &v in &visible {
            alive[v] = false;
            orphans.append(&mut faces[v].above);
        }
        // Apex is no longer orphan — it is now on the hull.
        orphans.retain(|&i| i as usize != apex);
        // Determinism — sort ascending so re-distribution order is stable.
        orphans.sort_unstable();
        orphans.dedup();

        // Build new faces — one per horizon edge — and re-distribute orphans.
        let mut new_face_ids: Vec<usize> = Vec::with_capacity(horizon.len());
        for (a, b) in horizon {
            // Horizon edge (a, b) was oriented CCW as seen from the visible
            // face's interior; the new face is `[a, b, apex]` with the same
            // CCW orientation as seen from outside (apex is on the outside
            // side of the visible faces' plane).
            let mut nf = make_outward_face(&pts, [a, b, apex], centroid);
            // Distribute orphans to this new face if it's above.
            for &p in &orphans {
                if (p as usize) == apex {
                    continue;
                }
                if signed_distance(&nf, &pts[p as usize]) > F64_EPS {
                    nf.above.push(p);
                }
            }
            faces.push(nf);
            alive.push(true);
            new_face_ids.push(faces.len() - 1);
        }

        // An orphan point may belong to multiple new faces above it; assign
        // each orphan to the **first** new face above it (deterministic). The
        // distribution loop above puts each orphan onto every new face it is
        // above — so we now deduplicate so each orphan lives on exactly one
        // face. This keeps the loop's `above.len()` sum bounded by N.
        let mut seen: std::collections::BTreeSet<u32> = std::collections::BTreeSet::new();
        for &nid in &new_face_ids {
            faces[nid].above.retain(|&p| seen.insert(p));
        }

        // Enqueue new faces that have above-points.
        for nid in new_face_ids {
            if !faces[nid].above.is_empty() {
                work.push(nid);
            }
        }
        work.sort_unstable();
    }

    // Collect surviving faces; emit triangles in ascending face-creation order
    // for stable output.
    let mut tris: Vec<[u32; 3]> = faces
        .iter()
        .zip(alive.iter())
        .filter_map(|(f, &al)| if al { Some(f.v) } else { None })
        .collect();
    // Canonicalize triangle vertex order: rotate so vertex 0 is the smallest,
    // preserving CCW orientation. Stable hash-friendly.
    for t in tris.iter_mut() {
        let mut m = 0usize;
        if t[1] < t[m] {
            m = 1;
        }
        if t[2] < t[m] {
            m = 2;
        }
        t.rotate_left(m);
    }
    // Sort triangle list itself by (v0, v1, v2) ascending — final determinism
    // gate for the per-triangle output order.
    tris.sort_unstable();
    tris
}

/// Result face for the hull algorithm — vertices in CCW-from-outside order,
/// plus a precomputed plane (normal + d) and the set of points still
/// "above" it.
#[derive(Debug, Clone)]
struct HullFace {
    v: [u32; 3],
    /// Plane normal (outward-facing, unit length).
    n: [f64; 3],
    /// `dot(n, v0)` — the plane offset.
    d: f64,
    /// Point indices currently strictly above this face.
    above: Vec<u32>,
}

/// Build a `HullFace` from indices `[a, b, c]`, flipping if needed so the
/// normal points **outward** (away from the reference `interior` point).
fn make_outward_face(pts: &[[f64; 3]], vs: [usize; 3], interior: [f64; 3]) -> HullFace {
    let p0 = pts[vs[0]];
    let p1 = pts[vs[1]];
    let p2 = pts[vs[2]];
    let e1 = sub(p1, p0);
    let e2 = sub(p2, p0);
    let mut n = cross_d(e1, e2);
    let nlen = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt();
    if nlen > 0.0 {
        n[0] /= nlen;
        n[1] /= nlen;
        n[2] /= nlen;
    }
    let d = n[0] * p0[0] + n[1] * p0[1] + n[2] * p0[2];
    // If the interior point is on the positive side of (n, d), flip so
    // outward means *away from* interior.
    let interior_signed = n[0] * interior[0] + n[1] * interior[1] + n[2] * interior[2] - d;
    let (v_out, n_out, d_out) = if interior_signed > 0.0 {
        // Swap vs[1] and vs[2] to flip CCW orientation.
        (
            [vs[0] as u32, vs[2] as u32, vs[1] as u32],
            [-n[0], -n[1], -n[2]],
            -d,
        )
    } else {
        ([vs[0] as u32, vs[1] as u32, vs[2] as u32], n, d)
    };
    let _ = d_out; // silence unused-mut warning; we recompute below.
    let d_final = n_out[0] * p0[0] + n_out[1] * p0[1] + n_out[2] * p0[2];
    HullFace {
        v: v_out,
        n: n_out,
        d: d_final,
        above: Vec::new(),
    }
}

/// Signed plane distance — positive = above (outward) the face.
fn signed_distance(f: &HullFace, p: &[f64; 3]) -> f64 {
    f.n[0] * p[0] + f.n[1] * p[1] + f.n[2] * p[2] - f.d
}

/// Pick the farthest above-point of `f`. Determinism: ties → ascending index.
fn farthest_above_index(f: &HullFace, pts: &[[f64; 3]]) -> usize {
    let mut best: usize = f.above[0] as usize;
    let mut best_d = signed_distance(f, &pts[best]);
    for &i in &f.above[1..] {
        let d = signed_distance(f, &pts[i as usize]);
        // strict `>` for the lower-index tie-break; on a true tie, the
        // earlier-in-`above` (smaller index, since we sort) wins.
        if d > best_d {
            best_d = d;
            best = i as usize;
        }
    }
    best
}

/// BFS-collect every face that is visible from `apex` — i.e. signed
/// distance > F64_EPS — starting from `seed` and crossing only shared edges
/// into already-visible neighbours. Avoids re-collecting the same face twice.
fn collect_visible(
    apex: usize,
    faces: &[HullFace],
    alive: &[bool],
    seed: usize,
    pts: &[[f64; 3]],
) -> Vec<usize> {
    let mut visible: Vec<usize> = Vec::new();
    let mut seen: std::collections::BTreeSet<usize> = std::collections::BTreeSet::new();
    let mut stack: Vec<usize> = vec![seed];
    while let Some(fi) = stack.pop() {
        if !seen.insert(fi) || !alive[fi] {
            continue;
        }
        if signed_distance(&faces[fi], &pts[apex]) > F64_EPS {
            visible.push(fi);
            // Enqueue all faces sharing an edge with `fi`.
            for (j, fj) in faces.iter().enumerate() {
                if !alive[j] || j == fi || seen.contains(&j) {
                    continue;
                }
                if shares_edge(&faces[fi].v, &fj.v) {
                    stack.push(j);
                }
            }
        }
    }
    visible.sort_unstable();
    visible
}

/// True iff `a` and `b` share at least one edge — for triangle faces, "share
/// an edge" means they share **two** vertices.
fn shares_edge(a: &[u32; 3], b: &[u32; 3]) -> bool {
    let mut shared = 0;
    for &av in a {
        for &bv in b {
            if av == bv {
                shared += 1;
                break;
            }
        }
    }
    shared >= 2
}

/// Compute the horizon edges of the visible-face set: every edge of a visible
/// face that is **not** shared with another visible face is on the horizon.
/// Orientation is preserved CCW-as-seen-from-the-visible-face.
fn compute_horizon(visible: &[usize], faces: &[HullFace]) -> Vec<(usize, usize)> {
    use std::collections::BTreeMap;
    // count each directed edge once.
    let mut count: BTreeMap<(u32, u32), i32> = BTreeMap::new();
    for &vi in visible {
        let v = &faces[vi].v;
        let edges = [(v[0], v[1]), (v[1], v[2]), (v[2], v[0])];
        for (a, b) in edges {
            let canon = if a < b { (a, b) } else { (b, a) };
            *count.entry(canon).or_insert(0) += 1;
        }
    }
    // edges with count 1 are on the horizon (only one visible face uses them).
    let mut horizon: Vec<(usize, usize)> = Vec::new();
    for &vi in visible {
        let v = &faces[vi].v;
        let edges = [(v[0], v[1]), (v[1], v[2]), (v[2], v[0])];
        for (a, b) in edges {
            let canon = if a < b { (a, b) } else { (b, a) };
            if count[&canon] == 1 {
                horizon.push((a as usize, b as usize));
            }
        }
    }
    // Determinism: ascending edge first vertex, then second.
    horizon.sort_unstable();
    horizon
}

/// Pick four indices (a, b, c, d) that span 3D — used to seed the hull.
/// Determinism: min-x → max-x → farthest-from-line → farthest-from-plane,
/// ties broken by ascending index.
fn initial_tetrahedron(pts: &[[f64; 3]]) -> [usize; 4] {
    let n = pts.len();
    // 1. min-x (ties → lower index)
    let a = (0..n)
        .min_by(|&i, &j| {
            pts[i][0]
                .total_cmp(&pts[j][0])
                .then(i.cmp(&j))
        })
        .unwrap();
    // 2. max-x (ties → lower index) — distinct from a
    let b = (0..n)
        .filter(|&i| i != a)
        .max_by(|&i, &j| pts[i][0].total_cmp(&pts[j][0]).then(j.cmp(&i)))
        .unwrap();
    // 3. farthest from the line a-b
    let pa = pts[a];
    let pb = pts[b];
    let ab = sub(pb, pa);
    let ab_n2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2];
    let mut c = usize::MAX;
    let mut c_d2 = -1.0_f64;
    for (i, &pi) in pts.iter().enumerate() {
        if i == a || i == b {
            continue;
        }
        let api = sub(pi, pa);
        // perpendicular distance² = |api|² − (api·ab)² / |ab|²
        let d_par = (api[0] * ab[0] + api[1] * ab[1] + api[2] * ab[2]).powi(2) / ab_n2.max(F64_EPS);
        let d2 = api[0] * api[0] + api[1] * api[1] + api[2] * api[2] - d_par;
        if d2 > c_d2 {
            c_d2 = d2;
            c = i;
        }
    }
    assert!(c != usize::MAX);
    // 4. farthest from the plane (a, b, c)
    let pc = pts[c];
    let n_abc = cross_d(sub(pb, pa), sub(pc, pa));
    let nlen = (n_abc[0].powi(2) + n_abc[1].powi(2) + n_abc[2].powi(2)).sqrt();
    let n_abc_u = [n_abc[0] / nlen, n_abc[1] / nlen, n_abc[2] / nlen];
    let plane_d = n_abc_u[0] * pa[0] + n_abc_u[1] * pa[1] + n_abc_u[2] * pa[2];
    let mut d = usize::MAX;
    let mut d_abs = -1.0_f64;
    for (i, &pi) in pts.iter().enumerate() {
        if i == a || i == b || i == c {
            continue;
        }
        let s = (n_abc_u[0] * pi[0] + n_abc_u[1] * pi[1] + n_abc_u[2] * pi[2] - plane_d).abs();
        if s > d_abs {
            d_abs = s;
            d = i;
        }
    }
    assert!(d != usize::MAX);
    [a, b, c, d]
}

// --- adjacency -------------------------------------------------------------

/// Collect symmetric adjacency from the spherical Delaunay triangle list.
fn adjacency(triangles: &[[u32; 3]], count: usize) -> Vec<Vec<u32>> {
    let mut neighbors: Vec<Vec<u32>> = vec![Vec::new(); count];
    for t in triangles {
        neighbors[t[0] as usize].push(t[1]);
        neighbors[t[0] as usize].push(t[2]);
        neighbors[t[1] as usize].push(t[0]);
        neighbors[t[1] as usize].push(t[2]);
        neighbors[t[2] as usize].push(t[0]);
        neighbors[t[2] as usize].push(t[1]);
    }
    for list in &mut neighbors {
        list.sort_unstable();
        list.dedup();
    }
    neighbors
}

// --- spherical Voronoi polygons --------------------------------------------

/// Assemble each cell's spherical Voronoi polygon: the unit-normalized
/// circumcentres of its incident Delaunay triangles, ordered CCW around the
/// cell centre via tangent-plane angle.
fn voronoi_polygons_sphere(centers: &[[f32; 3]], triangles: &[[u32; 3]]) -> Vec<Vec<[f32; 3]>> {
    let n = centers.len();

    // Precompute each triangle's spherical circumcentre — for points on the
    // unit sphere, this is the unit-normalized triangle plane normal (the
    // intersection of the perpendicular bisectors *of the great-circle
    // edges* meets at the triangle's outward normal).
    let circ: Vec<[f32; 3]> = triangles
        .iter()
        .map(|t| {
            let a = centers[t[0] as usize];
            let b = centers[t[1] as usize];
            let c = centers[t[2] as usize];
            let ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
            let ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
            let n = cross(ab, ac);
            normalize(n)
        })
        .collect();

    // Incident triangle ids per cell.
    let mut inc: Vec<Vec<u32>> = vec![Vec::new(); n];
    for (ti, t) in triangles.iter().enumerate() {
        inc[t[0] as usize].push(ti as u32);
        inc[t[1] as usize].push(ti as u32);
        inc[t[2] as usize].push(ti as u32);
    }

    let mut polygons: Vec<Vec<[f32; 3]>> = vec![Vec::new(); n];
    for (i, inc_i) in inc.iter().enumerate() {
        let c = centers[i];
        // Tangent-plane basis at c: any vector perpendicular to c, then a
        // second perpendicular to both.
        let (ex, ey) = tangent_basis(c);
        let mut verts: Vec<(f32, [f32; 3])> = inc_i
            .iter()
            .map(|&t| {
                let v = circ[t as usize];
                // Angle of `v − c` projected onto tangent basis.
                let dv = [v[0] - c[0], v[1] - c[1], v[2] - c[2]];
                let u = dv[0] * ex[0] + dv[1] * ex[1] + dv[2] * ex[2];
                let w = dv[0] * ey[0] + dv[1] * ey[1] + dv[2] * ey[2];
                (w.atan2(u), v)
            })
            .collect();
        verts.sort_by(|a, b| a.0.total_cmp(&b.0));
        // Deduplicate vertices that came out at the same circumcentre (rare —
        // would indicate degenerate adjacent triangles).
        let mut ring: Vec<[f32; 3]> = Vec::with_capacity(verts.len());
        for (_, v) in verts {
            if let Some(last) = ring.last() {
                if (v[0] - last[0]).abs() < 1e-6
                    && (v[1] - last[1]).abs() < 1e-6
                    && (v[2] - last[2]).abs() < 1e-6
                {
                    continue;
                }
            }
            ring.push(v);
        }
        if ring.len() < 3 {
            // Degenerate cell — emit a tiny triangle around c so the polygon
            // is always ≥ 3 vertices for downstream consumers.
            let eps = 1e-3;
            let v1 = normalize([
                c[0] + eps * ex[0],
                c[1] + eps * ex[1],
                c[2] + eps * ex[2],
            ]);
            let v2 = normalize([
                c[0] + eps * (-0.5 * ex[0] + 0.866 * ey[0]),
                c[1] + eps * (-0.5 * ex[1] + 0.866 * ey[1]),
                c[2] + eps * (-0.5 * ex[2] + 0.866 * ey[2]),
            ]);
            let v3 = normalize([
                c[0] + eps * (-0.5 * ex[0] - 0.866 * ey[0]),
                c[1] + eps * (-0.5 * ex[1] - 0.866 * ey[1]),
                c[2] + eps * (-0.5 * ex[2] - 0.866 * ey[2]),
            ]);
            ring = vec![v1, v2, v3];
        }
        polygons[i] = ring;
    }
    polygons
}

/// Build an orthonormal tangent basis `(ex, ey)` at unit-sphere point `c`.
/// Deterministic: picks the more-stable cross-axis based on `c`'s smallest
/// absolute component.
fn tangent_basis(c: [f32; 3]) -> ([f32; 3], [f32; 3]) {
    // Pick a helper axis least-aligned with c.
    let ax = c[0].abs();
    let ay = c[1].abs();
    let az = c[2].abs();
    let helper = if ax <= ay && ax <= az {
        [1.0, 0.0, 0.0]
    } else if ay <= az {
        [0.0, 1.0, 0.0]
    } else {
        [0.0, 0.0, 1.0]
    };
    let ex = normalize(cross(c, helper));
    let ey = cross(c, ex);
    (ex, ey)
}

// --- 3-vector helpers ------------------------------------------------------

fn cross(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn cross_d(a: [f64; 3], b: [f64; 3]) -> [f64; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn sub(a: [f64; 3], b: [f64; 3]) -> [f64; 3] {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

fn normalize(v: [f32; 3]) -> [f32; 3] {
    let len = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
    if len > 0.0 {
        [v[0] / len, v[1] / len, v[2] / len]
    } else {
        [0.0, 0.0, 1.0]
    }
}

// --- tests -----------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pocket_mesh_has_correct_cell_count() {
        let m = build(7, WorldScale::Pocket);
        assert_eq!(m.centers.len(), WorldScale::Pocket.cell_count());
    }

    #[test]
    fn all_centers_are_unit_vectors() {
        let m = build(11, WorldScale::Pocket);
        for (i, p) in m.centers.iter().enumerate() {
            let len2 = p[0] * p[0] + p[1] * p[1] + p[2] * p[2];
            assert!(
                (len2 - 1.0).abs() < 1e-4,
                "cell {i} not on unit sphere: |p|² = {len2}"
            );
        }
    }

    #[test]
    fn adjacency_is_symmetric() {
        let m = build(13, WorldScale::Pocket);
        for (i, list) in m.neighbors.iter().enumerate() {
            for &j in list {
                assert!(
                    m.neighbors[j as usize].contains(&(i as u32)),
                    "asymmetric adjacency: {i} → {j} but not back"
                );
            }
        }
    }

    #[test]
    fn cell_degrees_are_in_a_reasonable_range() {
        // Fibonacci sphere: degree distribution is tight around 6 (Euler:
        // average degree ≈ 6 for a triangulated sphere). Allow 4..=10.
        let m = build(17, WorldScale::Pocket);
        for (i, list) in m.neighbors.iter().enumerate() {
            let d = list.len();
            assert!(
                (4..=10).contains(&d),
                "cell {i} has unexpected degree {d}"
            );
        }
    }

    #[test]
    fn polygons_have_three_or_more_vertices() {
        let m = build(19, WorldScale::Pocket);
        for (i, poly) in m.polygons.iter().enumerate() {
            assert!(poly.len() >= 3, "cell {i} polygon has only {} verts", poly.len());
            for v in poly {
                let len2 = v[0] * v[0] + v[1] * v[1] + v[2] * v[2];
                assert!((len2 - 1.0).abs() < 1e-3, "polygon vertex not on unit sphere");
            }
        }
    }

    #[test]
    fn determinism_same_seed_byte_identical() {
        let a = build(42, WorldScale::Pocket);
        let b = build(42, WorldScale::Pocket);
        assert_eq!(a.centers.len(), b.centers.len());
        for i in 0..a.centers.len() {
            for k in 0..3 {
                assert_eq!(a.centers[i][k].to_bits(), b.centers[i][k].to_bits());
            }
        }
        assert_eq!(a.neighbors, b.neighbors);
        // polygons compared by exact f32 bits
        for i in 0..a.polygons.len() {
            assert_eq!(a.polygons[i].len(), b.polygons[i].len());
            for k in 0..a.polygons[i].len() {
                for c in 0..3 {
                    assert_eq!(
                        a.polygons[i][k][c].to_bits(),
                        b.polygons[i][k][c].to_bits(),
                        "polygon {i}.{k}.{c} differs"
                    );
                }
            }
        }
    }

    #[test]
    fn distinct_seeds_distinct_orientations() {
        let a = build(1, WorldScale::Pocket);
        let b = build(2, WorldScale::Pocket);
        // At least one cell centre should differ — the seed-driven rotation
        // is the only source of seed dependence here.
        let any_diff = (0..a.centers.len()).any(|i| {
            (0..3).any(|k| a.centers[i][k].to_bits() != b.centers[i][k].to_bits())
        });
        assert!(any_diff, "distinct seeds produced identical meshes");
    }

    #[test]
    fn east_west_wrap_adjacency_exists() {
        // After seed-driven rotation we can't pin specific lon-0 / lon-π
        // cells, but we *can* assert the graph is connected (a single
        // component) — which is the seamless-sphere invariant.
        let m = build(23, WorldScale::Pocket);
        let n = m.centers.len();
        // BFS from cell 0.
        let mut seen = vec![false; n];
        let mut stack = vec![0u32];
        seen[0] = true;
        let mut count = 1;
        while let Some(u) = stack.pop() {
            for &v in &m.neighbors[u as usize] {
                if !seen[v as usize] {
                    seen[v as usize] = true;
                    count += 1;
                    stack.push(v);
                }
            }
        }
        assert_eq!(count, n, "mesh has {} disconnected cells", n - count);
    }

    #[test]
    fn lat_lon_helpers_match_definition() {
        let m = build(29, WorldScale::Pocket);
        for i in 0..m.centers.len() {
            let lat = m.lat(i);
            let lon = m.lon(i);
            assert!((-std::f32::consts::FRAC_PI_2..=std::f32::consts::FRAC_PI_2).contains(&lat));
            assert!((-std::f32::consts::PI..=std::f32::consts::PI).contains(&lon));
            // Round-trip check.
            let p = m.centers[i];
            let recon = [
                lat.cos() * lon.cos(),
                lat.cos() * lon.sin(),
                lat.sin(),
            ];
            for k in 0..3 {
                assert!(
                    (p[k] - recon[k]).abs() < 1e-3,
                    "lat/lon round-trip diverges at cell {i}.{k}: {} vs {}",
                    p[k],
                    recon[k]
                );
            }
        }
    }
}
