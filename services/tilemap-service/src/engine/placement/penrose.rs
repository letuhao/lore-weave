//! TMP_002 §4 — Penrose P3 tiling for organic zone polygons.
//!
//! Generates an aperiodic, non-repeating vertex field via golden-ratio
//! subdivision of Robinson triangles (the standard P3 construction), assigns
//! each Penrose vertex to its nearest zone centre, then assigns each grid tile
//! to the zone of its nearest vertex (§4.3). The result is a disjoint partition
//! of the grid into irregular, organic-feeling zone regions. Each zone's centre
//! is then recomputed as the centroid of its tiles (§4.4).
//!
//! **Seed correction:** spec §4.2 step 1 loosely says "5 isoceles triangles".
//! The canonical Penrose P3 tiling needs a 10-triangle decagon wheel of acute
//! Robinson triangles (5-fold symmetry × 2 chiralities) for the subdivision
//! rules to produce a valid aperiodic tiling — this module uses the canonical
//! 10. The §4.1 intent ("aperiodic, 5-fold rotational symmetry") is preserved.
//!
//! **Determinism (TMP-A4):** the tiling's only freedom is a rotation angle,
//! drawn from the `"penrose"` sub-stream ([`sub_seed`]). Subdivision is a fixed
//! sequence of `f64` ops; vertex dedup quantizes to integers and sorts, so the
//! vertex list — and therefore the tile assignment — is reproducible.

use std::f64::consts::{PI, TAU};

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;

use crate::seed::{TilemapSeed, sub_seed};
use crate::types::tile::TileCoord;
use crate::types::tile_mask::TileMask;
use crate::types::tilemap::GridSize;

use super::spatial::UniformBuckets;
use super::{PlacedZone, Vec2, ZoneTiles};

/// Golden ratio φ = (1 + √5) / 2.
const PHI: f64 = 1.618_033_988_749_895;
/// 1 / φ — the subdivision split fraction.
const INV_PHI: f64 = 1.0 / PHI;
/// Subdivision depth cap — each pass multiplies the triangle count ~2.5×, so 8
/// passes reach ~150 k triangles, well past any practical zone count.
const MAX_SUBDIVISION_DEPTH: u32 = 8;
/// Vertex dedup quantization — coordinates round to a `1e-6` grid before the
/// integer sort-dedup, so near-coincident subdivision vertices collapse.
const QUANT: f64 = 1.0e6;
/// A normalized-coordinate span below this means the vertices collapsed to a
/// line or point — a degenerate tiling (§4.5).
const DEGENERATE_EPS: f64 = 1.0e-9;

/// Robinson triangle chirality — the two half-rhombus prototiles of the P3
/// tiling. Acute = half of a thin rhombus (36° apex); obtuse = half of a thick
/// rhombus (108° apex).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Robinson {
    Acute,
    Obtuse,
}

/// A Robinson triangle with its three ordered vertices. Vertex order matters —
/// the subdivision rules below reference `a`/`b`/`c` by position.
#[derive(Debug, Clone, Copy)]
struct RTriangle {
    kind: Robinson,
    a: Vec2,
    b: Vec2,
    c: Vec2,
}

/// TMP_002 §4 — assign every grid tile to a zone via a Penrose vertex field.
///
/// Returns one [`ZoneTiles`] per input zone (in input order) with
/// `assigned_tiles` filled and `center` recomputed (§4.4); `free_paths` is left
/// empty for §5 fractalize. Errors: [`crate::Error::EmptyZone`] if a zone wins
/// no tiles (§4.5 — template misconfiguration), [`crate::Error::Placement`] if
/// the Penrose tiling degenerates.
pub fn assign_zone_tiles(
    zones: &[PlacedZone],
    grid: GridSize,
    seed: TilemapSeed,
) -> crate::Result<Vec<ZoneTiles>> {
    if zones.is_empty() {
        return Ok(Vec::new());
    }

    // Penrose vertex field — target count per §4.2 (max(zones × 10, 200)).
    let target = (zones.len() * 10).max(200);
    let mut rng = ChaCha8Rng::seed_from_u64(sub_seed(seed, "penrose"));
    let rotation = rng.random_range(0.0..TAU);
    let vertices = penrose_vertices(target, rotation)?;

    // §4.3 step 1 — each vertex belongs to its nearest zone centre.
    // Off the per-tile hot path — |vertices| calls only, not bucketed.
    let vertex_zone: Vec<usize> = vertices.iter().map(|&v| nearest_zone(v, zones)).collect();

    // Bucket the vertex field once — `bucket_dim ≈ sqrt(N)` ⇒ ~1 vertex per
    // bucket on average. DEFERRED #018 — promoted by the 2026-05-18 continent
    // measurement. The bucketed nearest-vertex lookup is bit-exact equivalent
    // to the prior linear scan (`nearest_vertex_naive`, kept under
    // `#[cfg(test)]` as the oracle for AC-2/AC-3 in spec §9.3).
    let vbuckets = build_vertex_buckets(&vertices);

    // §4.3 step 2 — each tile belongs to the zone of its nearest vertex.
    let mut masks: Vec<TileMask> = (0..zones.len())
        .map(|_| TileMask::new(grid.width, grid.height))
        .collect();
    for y in 0..grid.height {
        for x in 0..grid.width {
            let p = Vec2::new(
                (x as f64 + 0.5) / grid.width as f64,
                (y as f64 + 0.5) / grid.height as f64,
            );
            let vi = nearest_vertex_bucketed(p, &vbuckets);
            masks[vertex_zone[vi]].set(TileCoord::new(x, y));
        }
    }

    // §4.4 centroid recompute + §4.5 empty-zone guard.
    let mut out = Vec::with_capacity(zones.len());
    for (zone, mask) in zones.iter().zip(masks) {
        let center =
            recompute_center(&mask).ok_or_else(|| crate::Error::EmptyZone(zone.id.0.clone()))?;
        out.push(ZoneTiles {
            id: zone.id.clone(),
            role: zone.role,
            center,
            assigned_tiles: mask,
            free_paths: TileMask::new(grid.width, grid.height),
        });
    }
    Ok(out)
}

/// Build the deduplicated Penrose vertex field, rotated by `rotation` and
/// normalized into the `[0,1]²` square. Subdivides until the count of
/// **distinct** vertices reaches `target` (triangle count over-counts because
/// adjacent triangles share vertices) or the depth cap is hit.
fn penrose_vertices(target: usize, rotation: f64) -> crate::Result<Vec<Vec2>> {
    let mut tris = seed_wheel();
    let mut verts = collect_vertices(&tris, rotation)?;
    let mut depth = 0;
    while verts.len() < target && depth < MAX_SUBDIVISION_DEPTH {
        tris = subdivide(&tris);
        verts = collect_vertices(&tris, rotation)?;
        depth += 1;
    }
    if verts.len() < 3 {
        return Err(crate::Error::Placement(
            "degenerate Penrose tiling — fewer than 3 distinct vertices".to_string(),
        ));
    }
    Ok(verts)
}

/// The canonical P3 seed — a wheel of 10 acute Robinson triangles around the
/// origin (every other one mirrored, giving the 5-fold symmetry of P3).
fn seed_wheel() -> Vec<RTriangle> {
    let mut tris = Vec::with_capacity(10);
    for i in 0..10i32 {
        let ang_b = (2 * i - 1) as f64 * PI / 10.0;
        let ang_c = (2 * i + 1) as f64 * PI / 10.0;
        let mut b = Vec2::new(ang_b.cos(), ang_b.sin());
        let mut c = Vec2::new(ang_c.cos(), ang_c.sin());
        if i % 2 == 0 {
            std::mem::swap(&mut b, &mut c);
        }
        tris.push(RTriangle {
            kind: Robinson::Acute,
            a: Vec2::new(0.0, 0.0),
            b,
            c,
        });
    }
    tris
}

/// One P3 subdivision pass — golden-ratio decomposition of each Robinson
/// triangle (acute → 2 children, obtuse → 3 children).
fn subdivide(tris: &[RTriangle]) -> Vec<RTriangle> {
    let mut out = Vec::with_capacity(tris.len() * 3);
    for t in tris {
        match t.kind {
            Robinson::Acute => {
                let p = lerp(t.a, t.b, INV_PHI);
                out.push(RTriangle {
                    kind: Robinson::Acute,
                    a: t.c,
                    b: p,
                    c: t.b,
                });
                out.push(RTriangle {
                    kind: Robinson::Obtuse,
                    a: p,
                    b: t.c,
                    c: t.a,
                });
            }
            Robinson::Obtuse => {
                let q = lerp(t.b, t.a, INV_PHI);
                let r = lerp(t.b, t.c, INV_PHI);
                out.push(RTriangle {
                    kind: Robinson::Obtuse,
                    a: r,
                    b: t.c,
                    c: t.a,
                });
                out.push(RTriangle {
                    kind: Robinson::Obtuse,
                    a: q,
                    b: r,
                    c: t.b,
                });
                out.push(RTriangle {
                    kind: Robinson::Acute,
                    a: r,
                    b: q,
                    c: t.a,
                });
            }
        }
    }
    out
}

/// Collect every triangle vertex, rotate about the origin, normalize the
/// bounding box into `[0,1]²`, and deduplicate via integer quantization.
fn collect_vertices(tris: &[RTriangle], rotation: f64) -> crate::Result<Vec<Vec2>> {
    let (sin_r, cos_r) = rotation.sin_cos();
    let mut pts: Vec<Vec2> = Vec::with_capacity(tris.len() * 3);
    for t in tris {
        for v in [t.a, t.b, t.c] {
            pts.push(Vec2::new(
                v.x * cos_r - v.y * sin_r,
                v.x * sin_r + v.y * cos_r,
            ));
        }
    }

    let mut min = Vec2::new(f64::INFINITY, f64::INFINITY);
    let mut max = Vec2::new(f64::NEG_INFINITY, f64::NEG_INFINITY);
    for p in &pts {
        min = Vec2::new(min.x.min(p.x), min.y.min(p.y));
        max = Vec2::new(max.x.max(p.x), max.y.max(p.y));
    }
    let span = max - min;
    if span.x < DEGENERATE_EPS || span.y < DEGENERATE_EPS {
        return Err(crate::Error::Placement(
            "degenerate Penrose tiling — vertices collapsed to a line or point".to_string(),
        ));
    }

    // Quantize to integers so dedup is exact + deterministic (a plain f64 sort
    // would leave near-duplicate subdivision vertices distinct).
    let mut quant: Vec<(i64, i64)> = pts
        .iter()
        .map(|p| {
            let nx = (p.x - min.x) / span.x;
            let ny = (p.y - min.y) / span.y;
            ((nx * QUANT).round() as i64, (ny * QUANT).round() as i64)
        })
        .collect();
    quant.sort_unstable();
    quant.dedup();

    Ok(quant
        .iter()
        .map(|&(x, y)| Vec2::new(x as f64 / QUANT, y as f64 / QUANT))
        .collect())
}

/// Index of the zone whose centre is nearest `v` (ties → lower index).
fn nearest_zone(v: Vec2, zones: &[PlacedZone]) -> usize {
    let mut best = 0;
    let mut best_d = f64::INFINITY;
    for (i, z) in zones.iter().enumerate() {
        let d = v.distance_sq(z.pos);
        if d < best_d {
            best_d = d;
            best = i;
        }
    }
    best
}

/// Build the vertex bucket grid over `[0,1]²`. `bucket_dim = ceil(sqrt(N))`
/// ⇒ ~1 vertex per cell on average; `.max(1)` so the empty-vertex case is
/// still a valid 1×1 grid (defensive — `penrose_vertices` errors on <3).
fn build_vertex_buckets(vertices: &[Vec2]) -> UniformBuckets<Vec2> {
    let bucket_dim = (vertices.len() as f64).sqrt().ceil().max(1.0) as i32;
    let bucket_size = 1.0 / bucket_dim as f64;
    let mut vb: UniformBuckets<Vec2> =
        UniformBuckets::new((0.0, 0.0), bucket_size, bucket_dim, bucket_dim);
    for (i, &v) in vertices.iter().enumerate() {
        vb.insert(i, v);
    }
    vb
}

/// Index of the vertex nearest `p` (ties → lower index) — bucketed spiral
/// search over a `UniformBuckets<Vec2>` built by [`build_vertex_buckets`].
///
/// Bit-exact equivalent to [`nearest_vertex_naive`] (kept under `#[cfg(test)]`)
/// because the spiral exhausts every bucket within `best_d` before terminating
/// — any tie has been considered — and the update rule
/// `(d == best_d && i < best_i)` preserves the lowest-index tie-break.
fn nearest_vertex_bucketed(p: Vec2, vb: &UniformBuckets<Vec2>) -> usize {
    let (cx, cy) = vb.bucket_xy(p);
    let mut best_d = f64::INFINITY;
    let mut best_i = 0usize;

    let max_ring = vb.max_dim();
    let mut ring = 0i32;
    loop {
        vb.for_each_in_ring(cx, cy, ring, |i, v| {
            let d = p.distance_sq(v);
            if d < best_d || (d == best_d && i < best_i) {
                best_d = d;
                best_i = i;
            }
        });

        // Lower bound on any vertex in ring `ring+1`: its bucket starts at
        // Chebyshev distance `ring+1` from p's bucket, so the closest
        // possible point is ≥ `ring * bucket_size` Euclidean (worst case: p
        // sits on the far edge of its bucket toward ring r+1). Strict `>`
        // so any d == best_d in an outer ring is still considered.
        let next_lb = (ring as f64) * vb.bucket_size();
        if best_d.is_finite() && next_lb * next_lb > best_d {
            break;
        }
        ring += 1;
        if ring > max_ring {
            break; // safety — every vertex already scanned
        }
    }

    best_i
}

/// The pre-perf linear scan — kept under `#[cfg(test)]` as the oracle for
/// AC-2 (`nearest_vertex_matches_naive_oracle`).
#[cfg(test)]
fn nearest_vertex_naive(p: Vec2, vertices: &[Vec2]) -> usize {
    let mut best = 0;
    let mut best_d = f64::INFINITY;
    for (i, &v) in vertices.iter().enumerate() {
        let d = p.distance_sq(v);
        if d < best_d {
            best_d = d;
            best = i;
        }
    }
    best
}

/// TMP_002 §4.4 — centroid of the assigned tiles, snapped to the nearest member
/// tile if the raw integer centroid falls outside the mask (a concave or
/// annular region). `None` when the mask is empty (§4.5 empty-zone).
fn recompute_center(mask: &TileMask) -> Option<TileCoord> {
    let mut sum_x = 0u64;
    let mut sum_y = 0u64;
    let mut count = 0u64;
    for c in mask.iter_set() {
        sum_x += c.x as u64;
        sum_y += c.y as u64;
        count += 1;
    }
    if count == 0 {
        return None;
    }
    let cx = (sum_x / count) as u32;
    let cy = (sum_y / count) as u32;
    let centroid = TileCoord::new(cx, cy);
    if mask.get(centroid) {
        return Some(centroid);
    }
    // Snap to the assigned tile nearest the centroid (iter_set is flat-index
    // ascending, so the distance tie-break is deterministic).
    let mut best: Option<(u64, TileCoord)> = None;
    for c in mask.iter_set() {
        let dx = c.x as i64 - cx as i64;
        let dy = c.y as i64 - cy as i64;
        let d = (dx * dx + dy * dy) as u64;
        if best.is_none_or(|(bd, _)| d < bd) {
            best = Some((d, c));
        }
    }
    best.map(|(_, c)| c)
}

/// Linear interpolation `from + (to - from) * t`.
fn lerp(from: Vec2, to: Vec2, t: f64) -> Vec2 {
    from + (to - from).scale(t)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::zone::{ZoneId, ZoneRole};

    fn placed(id: &str, x: f64, y: f64) -> PlacedZone {
        PlacedZone {
            id: ZoneId(id.to_string()),
            role: ZoneRole::Wilderness,
            size: 100,
            pos: Vec2::new(x, y),
        }
    }

    fn grid(w: u32, h: u32) -> GridSize {
        GridSize { width: w, height: h }
    }

    #[test]
    fn subdivision_grows_the_triangle_count() {
        let wheel = seed_wheel();
        assert_eq!(wheel.len(), 10);
        let once = subdivide(&wheel);
        assert!(once.len() > wheel.len(), "subdivision must add triangles");
        let twice = subdivide(&once);
        assert!(twice.len() > once.len());
    }

    #[test]
    fn penrose_vertices_reach_the_target_and_stay_in_unit_square() {
        let verts = penrose_vertices(200, 0.3).unwrap();
        assert!(verts.len() >= 200, "got only {} vertices", verts.len());
        for v in &verts {
            assert!(
                (0.0..=1.0).contains(&v.x) && (0.0..=1.0).contains(&v.y),
                "vertex {v:?} escaped the unit square",
            );
        }
    }

    #[test]
    fn penrose_vertices_are_deduplicated() {
        let verts = penrose_vertices(200, 0.0).unwrap();
        let mut q: Vec<(i64, i64)> = verts
            .iter()
            .map(|v| ((v.x * QUANT) as i64, (v.y * QUANT) as i64))
            .collect();
        let before = q.len();
        q.sort_unstable();
        q.dedup();
        assert_eq!(before, q.len(), "vertex list still has duplicates");
    }

    #[test]
    fn assignment_is_a_disjoint_partition() {
        // AC-2 — every tile assigned to exactly one zone, no overlaps.
        let zones = [
            placed("a", 0.2, 0.2),
            placed("b", 0.8, 0.2),
            placed("c", 0.5, 0.8),
        ];
        let g = grid(24, 24);
        let tiled = assign_zone_tiles(&zones, g, TilemapSeed(99)).unwrap();
        assert_eq!(tiled.len(), 3);

        // Union covers the whole grid.
        let mut union = TileMask::new(g.width, g.height);
        for z in &tiled {
            union.union_with(&z.assigned_tiles);
        }
        assert_eq!(union.count_ones(), g.tile_count(), "tiles left unassigned");

        // Pairwise disjoint.
        for i in 0..tiled.len() {
            for j in (i + 1)..tiled.len() {
                assert!(
                    !tiled[i].assigned_tiles.intersects(&tiled[j].assigned_tiles),
                    "zones {i} and {j} share a tile",
                );
            }
        }
    }

    #[test]
    fn centroid_is_inside_assigned_tiles() {
        // AC-1 — every zone centre is a member of its own mask.
        let zones = [
            placed("a", 0.25, 0.25),
            placed("b", 0.75, 0.75),
        ];
        let tiled = assign_zone_tiles(&zones, grid(32, 32), TilemapSeed(7)).unwrap();
        for z in &tiled {
            assert!(
                z.assigned_tiles.get(z.center),
                "zone {} centre {:?} is not in its mask",
                z.id.0,
                z.center,
            );
        }
    }

    #[test]
    fn deterministic_same_seed_same_assignment() {
        let zones = [
            placed("a", 0.3, 0.3),
            placed("b", 0.7, 0.3),
            placed("c", 0.5, 0.7),
        ];
        let g = grid(20, 20);
        let r1 = assign_zone_tiles(&zones, g, TilemapSeed(0x5EED)).unwrap();
        let r2 = assign_zone_tiles(&zones, g, TilemapSeed(0x5EED)).unwrap();
        for (a, b) in r1.iter().zip(&r2) {
            assert_eq!(a.id, b.id);
            assert_eq!(a.center, b.center);
            assert_eq!(a.assigned_tiles, b.assigned_tiles, "tiling not reproducible");
        }
    }

    #[test]
    fn different_seed_rotates_the_tiling() {
        let zones = [placed("a", 0.3, 0.3), placed("b", 0.7, 0.7)];
        let g = grid(24, 24);
        let r1 = assign_zone_tiles(&zones, g, TilemapSeed(1)).unwrap();
        let r2 = assign_zone_tiles(&zones, g, TilemapSeed(2)).unwrap();
        // A different rotation must change at least one zone's tile set.
        let differs = r1
            .iter()
            .zip(&r2)
            .any(|(a, b)| a.assigned_tiles != b.assigned_tiles);
        assert!(differs, "different seeds produced an identical tiling");
    }

    #[test]
    fn empty_template_yields_no_zones() {
        let tiled = assign_zone_tiles(&[], grid(16, 16), TilemapSeed(1)).unwrap();
        assert!(tiled.is_empty());
    }

    #[test]
    fn ac2_nearest_vertex_matches_naive_oracle() {
        // AC-2 — DEFERRED #018 promote. The bucketed spiral search must return
        // the same vertex index as the naive linear scan for arbitrary query
        // points over real Penrose vertex fields. Iterates 200 query points ×
        // 3 vertex-field configurations.
        use rand::Rng;
        use rand_chacha::ChaCha8Rng;

        // Targets span the production vertex-count regime — `penrose_vertices`
        // over-shoots `target` by subdividing until the count is reached, so
        // a continent (target 200) lands at ~500-1200 vertices in practice.
        // The (0.3, 1500, 4) case exercises the dense-grid spiral.
        for (rotation, target, seed) in [(0.3, 200, 1u64), (1.7, 500, 2), (2.5, 200, 3), (0.3, 1500, 4)] {
            let vertices = penrose_vertices(target, rotation).unwrap();
            let vb = build_vertex_buckets(&vertices);
            let mut rng = ChaCha8Rng::seed_from_u64(seed);
            for _ in 0..200 {
                let p = Vec2::new(rng.random_range(0.0..1.0), rng.random_range(0.0..1.0));
                let bucketed = nearest_vertex_bucketed(p, &vb);
                let naive = nearest_vertex_naive(p, &vertices);
                assert_eq!(
                    bucketed, naive,
                    "bucketed lookup diverged from naive at p={p:?} seed={seed} target={target}",
                );
            }
        }
    }

    #[test]
    fn ac3_nearest_vertex_tie_break_prefers_lower_index() {
        // AC-3 — hand-constructed cross-bucket tie. Query point at (0.5, 0.5);
        // vertices at (0.4, 0.5) and (0.6, 0.5) sit at exactly equal Euclidean
        // distance, in *different* buckets (bucket_dim sqrt(2)≈2, bucket_size
        // 0.5 ⇒ buckets (0,1) and (1,1)). The tie-break must return the
        // lower index (vertex 0), regardless of bucket iteration order.
        let vertices = vec![
            Vec2::new(0.4, 0.5), // index 0
            Vec2::new(0.6, 0.5), // index 1
        ];
        let vb = build_vertex_buckets(&vertices);
        let query = Vec2::new(0.5, 0.5);
        assert_eq!(nearest_vertex_bucketed(query, &vb), 0);

        // And if we flip insertion order — index 0 is now the (0.6, 0.5)
        // vertex — the tie-break still returns the (new) lower index.
        let vertices_flipped = vec![
            Vec2::new(0.6, 0.5), // index 0
            Vec2::new(0.4, 0.5), // index 1
        ];
        let vb_flipped = build_vertex_buckets(&vertices_flipped);
        assert_eq!(nearest_vertex_bucketed(query, &vb_flipped), 0);
    }

    #[test]
    fn zone_with_no_tiles_is_an_empty_zone_error() {
        // A 1×1 grid has one tile — the second zone necessarily wins nothing.
        let zones = [placed("a", 0.4, 0.4), placed("b", 0.6, 0.6)];
        let err = assign_zone_tiles(&zones, grid(1, 1), TilemapSeed(1)).unwrap_err();
        assert!(
            matches!(err, crate::Error::EmptyZone(_)),
            "expected EmptyZone, got {err:?}",
        );
    }
}
