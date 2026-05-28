//! Stage 1 — spherical Voronoi dual-mesh on the unit sphere.
//!
//! **Topology (Phase 1 world-tier redesign, 2026-05-20).** Points are sampled
//! on the unit sphere using a **Fibonacci lattice** — quasi-uniform in solid
//! angle, deterministic given `n`. A seed-driven 3D rotation reorients the
//! whole lattice so different seeds produce different worlds. The adjacency is
//! the **spherical Delaunay triangulation**, obtained in **O(N log N)** via a
//! **stereographic projection + 2D Delaunay** ([`delaunator`]) — see
//! [`spherical_delaunay`] (Phase 2 quality pass; replaced an O(N²) hand-rolled
//! 3D Quickhull so the generator can afford high cell counts). The
//! **spherical Voronoi polygon** of each cell is the loop of sphere-projected
//! circumcentres of its incident Delaunay triangles.
//!
//! There are no edges, no hull corners, no E–W seam, no pole degeneracy by
//! construction — the sphere has none of these. `repair_degree` from the flat
//! mesh is therefore gone.
//!
//! Determinism rules (load-bearing):
//! - Fibonacci index `i ∈ 0..N` is the **cell id**. The seed-driven rotation
//!   does not reorder indices.
//! - `delaunator` is deterministic; the triangle list is canonicalized
//!   (smallest vertex first) + sorted, independent of emission order.
//! - Spherical Voronoi vertices are ordered **CCW around the cell centre**
//!   via tangent-plane angle (`atan2` of an orthonormal-basis projection).

use std::f32::consts::TAU;

use delaunator::{Point, triangulate};

use crate::creative_seed::WorldScale;
use crate::rng::Rng;

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

    let triangles = spherical_delaunay(&centers);
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

// --- spherical Delaunay (stereographic projection + 2D Delaunay) -----------

/// Build the spherical Delaunay triangulation of `points` (all on the unit
/// sphere) — the dual of the spherical Voronoi diagram — in **O(N log N)** via
/// a stereographic projection + 2D Delaunay ([`delaunator`]). This replaced an
/// O(N²) hand-rolled 3D Quickhull (Phase 2 quality pass) so the generator can
/// afford the high cell counts that give each continent natural detail.
///
/// Method (the d3-geo-voronoi closure): pick a projection centre `c` (cell 0),
/// rotate it to the `+z` pole, stereographically project the *other* `N-1`
/// points to the plane, triangulate them, then close the back cap by fanning
/// the projection's 2D convex-hull edges to `c` (which is "at infinity" in the
/// projection). Returns triangles `[v0, v1, v2]` in original cell indices.
///
/// The Delaunay triangulation is unique for points in general position, so the
/// adjacency matches the former 3D-hull result; only near-co-circular quartets
/// may resolve differently. Triangle winding is *not* guaranteed consistent —
/// [`voronoi_polygons_sphere`] is robust to it.
///
/// Determinism: `delaunator` is deterministic; the triangle list is
/// canonicalized (smallest vertex first) + sorted at the end.
fn spherical_delaunay(points: &[[f32; 3]]) -> Vec<[u32; 3]> {
    let n = points.len();
    assert!(n >= 4, "spherical Delaunay needs at least 4 points");

    // Projection centre = cell 0; rotate it onto the +z pole.
    let q = quat_from_to(points[0], [0.0, 0.0, 1.0]);

    // Stereographic-project the other N-1 points from the +z pole:
    // (x, y, z) → (x/(1−z), y/(1−z)). The centre maps to infinity (excluded).
    let mut proj: Vec<Point> = Vec::with_capacity(n - 1);
    let mut orig: Vec<u32> = Vec::with_capacity(n - 1); // proj index → cell id
    for (i, &p) in points.iter().enumerate().skip(1) {
        let r = rotate_q(q, p);
        let denom = (1.0 - r[2]).max(1e-9);
        proj.push(Point {
            x: (r[0] / denom) as f64,
            y: (r[1] / denom) as f64,
        });
        orig.push(i as u32);
    }

    let tri = triangulate(&proj);

    let mut triangles: Vec<[u32; 3]> =
        Vec::with_capacity(tri.triangles.len() / 3 + tri.hull.len());

    // Interior triangles — map projected indices back to cell ids.
    for t in tri.triangles.chunks_exact(3) {
        triangles.push([orig[t[0]], orig[t[1]], orig[t[2]]]);
    }

    // Back cap — fan the projection's convex hull to the centre (cell 0). Each
    // consecutive hull edge closes through the centre, which lies on the
    // far side of the sphere from the projection plane.
    let h = &tri.hull;
    let hl = h.len();
    for k in 0..hl {
        let a = orig[h[k]];
        let b = orig[h[(k + 1) % hl]];
        triangles.push([a, b, 0]);
    }

    canonicalize_triangles(&mut triangles);
    triangles
}

/// Unit quaternion `(x, y, z, w)` rotating unit vector `from` onto unit `to`.
fn quat_from_to(from: [f32; 3], to: [f32; 3]) -> [f32; 4] {
    let d = (from[0] * to[0] + from[1] * to[1] + from[2] * to[2]).clamp(-1.0, 1.0);
    if d > 0.999_999 {
        return [0.0, 0.0, 0.0, 1.0]; // already aligned
    }
    if d < -0.999_999 {
        // antipodal — a π rotation about any axis perpendicular to `from`.
        let axis = perp(from);
        return [axis[0], axis[1], axis[2], 0.0];
    }
    let c = cross(from, to);
    let w = 1.0 + d;
    let inv = 1.0 / (c[0] * c[0] + c[1] * c[1] + c[2] * c[2] + w * w).sqrt();
    [c[0] * inv, c[1] * inv, c[2] * inv, w * inv]
}

/// Some unit vector perpendicular to `v` (via the least-aligned helper axis).
fn perp(v: [f32; 3]) -> [f32; 3] {
    let helper = if v[0].abs() <= v[1].abs() && v[0].abs() <= v[2].abs() {
        [1.0, 0.0, 0.0]
    } else if v[1].abs() <= v[2].abs() {
        [0.0, 1.0, 0.0]
    } else {
        [0.0, 0.0, 1.0]
    };
    normalize(cross(v, helper))
}

/// Canonicalize each triangle (rotate so the smallest vertex is first) then
/// sort + dedup the list — a stable, deterministic output independent of the
/// triangulator's emission order.
fn canonicalize_triangles(tris: &mut Vec<[u32; 3]>) {
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
    tris.sort_unstable();
    tris.dedup();
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
            let cc = normalize(cross(ab, ac));
            // Two antipodal circumcentres exist; take the one on the same
            // hemisphere as the triangle (its centroid). This makes the
            // Voronoi vertex correct regardless of the triangle's winding —
            // so the mesh builder needn't guarantee a consistent orientation.
            let centroid = [a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]];
            if cc[0] * centroid[0] + cc[1] * centroid[1] + cc[2] * centroid[2] < 0.0 {
                [-cc[0], -cc[1], -cc[2]]
            } else {
                cc
            }
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
