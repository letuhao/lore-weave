//! Marching-squares raster → polygon pipeline (v3.2).
//!
//! Shared between [`super::sdf::SdfCapsuleChainGenerator`] (analytical SDF
//! field) and [`MarchingNoiseGenerator`] (noise field with radial falloff).
//! Both feed [`field_to_polygon`] a closure `(f32,f32) -> f32` and a bbox;
//! the pipeline returns a single closed CCW polygon.
//!
//! Pipeline (spec §4.4):
//! 1. Grid sample — eval `field(p)` over a `grid_res × grid_res` lattice.
//! 2. Marching squares — 16 cases per cell, saddle ambiguity resolved by
//!    cell-centre sample.
//! 3. Contour stitching — walk segments edge-to-edge via shared grid edges;
//!    keep largest ring by absolute signed area.
//! 4. Chaikin smoothing — N passes (each pass replaces every vertex with
//!    two `0.75/0.25` linear-combination points; length grows ~×2 per pass).
//! 5. Douglas-Peucker simplify — ε = `simplify_eps_frac × bbox_diagonal`.
//! 6. Centroid alignment — translate so polygon centroid matches the caller-
//!    supplied `target_center` (marching-squares centroid can drift from
//!    the analytical centre by up to one cell on asymmetric noise fields).
//! 7. CCW orientation enforced (signed-area check, reverse if needed).
//!
//! **Determinism:** stitching uses `BTreeMap<(u8, i32, i32), ...>` keyed by
//! integer edge IDs — no f32 hashing, no `HashMap` iteration. Two runs with
//! identical inputs produce bit-identical output. Saddle resolution consumes
//! `rng.next_f32()` only when the cell-centre sample equals `iso` exactly
//! (true tiebreak), so the RNG consumption pattern is stable across seeds.

use std::collections::BTreeMap;

use crate::flatworld::Polygon;
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};

/// Rasterize `field` (negative inside, positive outside; iso typically `0.0`)
/// into one or more closed CCW polygons.
///
/// **v3.3**: returns `Vec<Polygon>` — the largest by area is the primary
/// (sorted to index 0, anchored at `target_center`); any additional rings
/// whose area is ≥ `min_area_frac × bbox_area` ride along as satellites
/// at their own centroid positions. To preserve v3.2 single-component
/// behaviour, callers pass `min_area_frac = f32::INFINITY` (drops every
/// non-largest ring) or `1.0` (drops anything < 100% of bbox = same effect).
/// `0.01` is the v3.3 default — keeps satellites that are ≥ 1% of plate
/// bbox area, archipelago-style.
///
/// Single-component contract (v3.2): if `min_area_frac >= 1.0`, exactly
/// one polygon is returned (the primary), matching the old API.
#[allow(clippy::too_many_arguments)]
pub fn field_to_polygon<F>(
    field: F,
    bbox: (f32, f32, f32, f32),
    iso: f32,
    grid_res: usize,
    chaikin_passes: usize,
    simplify_eps_frac: f32,
    rng: &mut Rng,
    target_center: (f32, f32),
    target_vertex_count_range: Option<(usize, usize)>,
    min_area_frac: f32,
) -> Vec<Polygon>
where
    F: Fn((f32, f32)) -> f32,
{
    debug_assert!(grid_res >= 4, "grid_res must be ≥ 4");
    debug_assert!(chaikin_passes <= 4, "chaikin_passes must be ≤ 4");
    debug_assert!(min_area_frac >= 0.0, "min_area_frac must be ≥ 0");

    // Step 1 — grid sample
    let grid = sample_grid(&field, bbox, grid_res);

    // Step 2 — marching squares → segments keyed by their two edge IDs
    let segments = marching_squares(&grid, iso, &field, rng);

    // Step 3 — stitch + multi-component finalize
    let rings = stitch_rings(segments);
    if rings.is_empty() {
        return vec![vec![
            (target_center.0, target_center.1),
            (target_center.0 + 1.0, target_center.1),
            (target_center.0, target_center.1 + 1.0),
        ]];
    }
    let kept = finalize_multi_component(rings, bbox, min_area_frac);
    if kept.is_empty() {
        return vec![vec![
            (target_center.0, target_center.1),
            (target_center.0 + 1.0, target_center.1),
            (target_center.0, target_center.1 + 1.0),
        ]];
    }

    let diag = ((bbox.2 - bbox.0).hypot(bbox.3 - bbox.1)).max(1e-6);
    let eps = simplify_eps_frac * diag;

    let mut out = Vec::with_capacity(kept.len());
    for (idx, ring) in kept.into_iter().enumerate() {
        // Step 4 — Chaikin smoothing per component
        let smoothed = if ring.len() >= 4 {
            chaikin(&ring, chaikin_passes)
        } else {
            ring
        };
        // Step 5 — DP simplify
        let simplified = douglas_peucker(&smoothed, eps);
        // Step 5b — vertex-count fit (each component independent)
        let fitted = match target_vertex_count_range {
            Some((vmin, vmax)) if vmax >= vmin && vmin >= 3 => {
                fit_vertex_count_range(simplified, vmin, vmax, diag)
            }
            _ => simplified,
        };
        // Step 6 — alignment. Primary aligns to target_center if it's
        // currently outside the polygon (concave-shape fallback). Satellites
        // keep their natural noise/SDF/Boolean position — no alignment.
        let aligned = if idx == 0 {
            align_centroid(fitted, target_center)
        } else {
            fitted
        };
        // Step 7 — CCW
        out.push(ensure_ccw(aligned));
    }
    out
}

/// Sort rings by descending area and keep the primary (`[0]`) unconditionally;
/// for satellites (`[1..]`) keep only those with area ≥
/// `min_area_frac × bbox_area`. Setting `min_area_frac ≥ 1.0` drops every
/// satellite (single-component compat mode); `0.01` keeps satellites ≥ 1%
/// of plate bbox (v3.3 default per PO).
fn finalize_multi_component(
    rings: Vec<Polygon>,
    bbox: (f32, f32, f32, f32),
    min_area_frac: f32,
) -> Vec<Polygon> {
    let mut sorted: Vec<(f32, Polygon)> = rings
        .into_iter()
        .map(|p| (signed_area(&p).abs(), p))
        .collect();
    sorted.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));

    if sorted.is_empty() {
        return Vec::new();
    }
    let bbox_area = (bbox.2 - bbox.0).abs() * (bbox.3 - bbox.1).abs();
    let threshold = bbox_area * min_area_frac;

    let mut iter = sorted.into_iter();
    let primary = iter.next().expect("non-empty checked").1;
    let mut out = vec![primary];
    for (area, p) in iter {
        if area >= threshold {
            out.push(p);
        }
    }
    out
}

/// Shape-preserving vertex-count fit: if over-max, re-run DP with geometrically
/// growing eps until count ≤ max; if under-min, subdivide longest edges
/// (insert midpoints) until count ≥ min. Subdivision preserves shape exactly;
/// growing-DP loses detail only by dropping near-collinear runs, never by
/// shortcutting concave corners.
fn fit_vertex_count_range(mut poly: Polygon, vmin: usize, vmax: usize, diag: f32) -> Polygon {
    // Reduce.
    if poly.len() > vmax {
        let mut eps = 0.005 * diag;
        let mut iters = 0;
        while poly.len() > vmax && iters < 20 {
            eps *= 1.5;
            poly = douglas_peucker(&poly, eps);
            iters += 1;
        }
    }
    // Grow.
    let mut grow_iters = 0;
    while poly.len() < vmin && grow_iters < 256 {
        let n = poly.len();
        if n < 2 {
            break;
        }
        let mut longest_idx = 0;
        let mut longest_dist_sq = 0.0f32;
        for i in 0..n {
            let p = poly[i];
            let q = poly[(i + 1) % n];
            let d = (p.0 - q.0).powi(2) + (p.1 - q.1).powi(2);
            if d > longest_dist_sq {
                longest_dist_sq = d;
                longest_idx = i;
            }
        }
        let p = poly[longest_idx];
        let q = poly[(longest_idx + 1) % n];
        let mid = ((p.0 + q.0) * 0.5, (p.1 + q.1) * 0.5);
        poly.insert(longest_idx + 1, mid);
        grow_iters += 1;
    }
    poly
}

/// Evenly distribute `target_count` vertices along the polygon's arc length.
/// Output is a new closed polygon with exactly `target_count` vertices.
///
/// Currently unused in production (replaced by [`fit_vertex_count_range`]
/// which is shape-preserving for non-convex polygons); kept for unit tests
/// and as a building block for future generators that may need exact-count
/// arc-length sampling (e.g. a future closed-loop spline generator).
#[allow(dead_code)]
pub(crate) fn resample_arc_length(poly: &Polygon, target_count: usize) -> Polygon {
    if poly.len() < 3 || target_count < 3 {
        return poly.clone();
    }
    let n = poly.len();
    let mut cum = vec![0.0f32; n + 1];
    for i in 0..n {
        let (x1, y1) = poly[i];
        let (x2, y2) = poly[(i + 1) % n];
        cum[i + 1] = cum[i] + ((x2 - x1).powi(2) + (y2 - y1).powi(2)).sqrt();
    }
    let total = cum[n];
    if total < 1e-9 {
        return poly.clone();
    }
    let step = total / target_count as f32;
    let mut out = Vec::with_capacity(target_count);
    let mut seg = 0usize;
    for k in 0..target_count {
        let target_arc = k as f32 * step;
        while seg < n && cum[seg + 1] < target_arc {
            seg += 1;
            if seg >= n {
                seg = n - 1;
                break;
            }
        }
        let seg_len = cum[seg + 1] - cum[seg];
        let t = if seg_len < 1e-9 { 0.0 } else { ((target_arc - cum[seg]) / seg_len).clamp(0.0, 1.0) };
        let (x1, y1) = poly[seg];
        let (x2, y2) = poly[(seg + 1) % n];
        out.push((x1 + t * (x2 - x1), y1 + t * (y2 - y1)));
    }
    out
}

// =============================================================================
// Step 1 — Grid sampling
// =============================================================================

/// Row-major grid of field samples. `samples[j * res + i]` is the value at
/// corner `(i, j)`, with corner `(0, 0)` at `(bbox.xmin, bbox.ymin)`.
struct Grid {
    res: usize,
    bbox: (f32, f32, f32, f32),
    samples: Vec<f32>,
}

impl Grid {
    fn corner_pos(&self, i: usize, j: usize) -> (f32, f32) {
        let res_f = (self.res - 1) as f32;
        let x = self.bbox.0 + (self.bbox.2 - self.bbox.0) * (i as f32 / res_f);
        let y = self.bbox.1 + (self.bbox.3 - self.bbox.1) * (j as f32 / res_f);
        (x, y)
    }

    fn sample(&self, i: usize, j: usize) -> f32 {
        self.samples[j * self.res + i]
    }
}

fn sample_grid<F: Fn((f32, f32)) -> f32>(
    field: &F,
    bbox: (f32, f32, f32, f32),
    res: usize,
) -> Grid {
    let mut samples = Vec::with_capacity(res * res);
    let res_f = (res - 1) as f32;
    for j in 0..res {
        let ty = j as f32 / res_f;
        let y = bbox.1 + (bbox.3 - bbox.1) * ty;
        for i in 0..res {
            let tx = i as f32 / res_f;
            let x = bbox.0 + (bbox.2 - bbox.0) * tx;
            samples.push(field((x, y)));
        }
    }
    Grid { res, bbox, samples }
}

// =============================================================================
// Step 2 — Marching squares
// =============================================================================

/// Stable edge identifier — `(kind, i, j)` where `kind = 0` is a horizontal
/// edge between corners `(i, j)` and `(i+1, j)`, `kind = 1` is a vertical
/// edge between `(i, j)` and `(i, j+1)`.
type EdgeId = (u8, i32, i32);

/// A single contour segment, identified by the two grid edges it touches.
#[derive(Debug, Clone, Copy)]
struct Segment {
    a: EdgeId,
    b: EdgeId,
    a_pos: (f32, f32),
    b_pos: (f32, f32),
}

fn marching_squares<F: Fn((f32, f32)) -> f32>(
    g: &Grid,
    iso: f32,
    field: &F,
    rng: &mut Rng,
) -> Vec<Segment> {
    let res = g.res;
    let mut out = Vec::new();

    for j in 0..res - 1 {
        for i in 0..res - 1 {
            // Corner samples: bl, br, tr, tl.
            let bl = g.sample(i, j);
            let br = g.sample(i + 1, j);
            let tr = g.sample(i + 1, j + 1);
            let tl = g.sample(i, j + 1);

            // Bit mask — bit set when corner is INSIDE (sample ≤ iso).
            let mut mask = 0u8;
            if bl <= iso { mask |= 0b0001; }
            if br <= iso { mask |= 0b0010; }
            if tr <= iso { mask |= 0b0100; }
            if tl <= iso { mask |= 0b1000; }

            if mask == 0 || mask == 0b1111 {
                continue;
            }

            // Edge IDs of this cell.
            //   bottom edge — (0, i, j)
            //   right edge  — (1, i+1, j)
            //   top edge    — (0, i, j+1)
            //   left edge   — (1, i, j)
            let e_bot: EdgeId = (0, i as i32, j as i32);
            let e_right: EdgeId = (1, (i + 1) as i32, j as i32);
            let e_top: EdgeId = (0, i as i32, (j + 1) as i32);
            let e_left: EdgeId = (1, i as i32, j as i32);

            // Edge crossing positions (linear interp).
            let p_bot = lerp_edge(g.corner_pos(i, j), bl, g.corner_pos(i + 1, j), br, iso);
            let p_right = lerp_edge(
                g.corner_pos(i + 1, j), br,
                g.corner_pos(i + 1, j + 1), tr, iso,
            );
            let p_top = lerp_edge(
                g.corner_pos(i, j + 1), tl,
                g.corner_pos(i + 1, j + 1), tr, iso,
            );
            let p_left = lerp_edge(g.corner_pos(i, j), bl, g.corner_pos(i, j + 1), tl, iso);

            // Helper closures for pushing segments (captures `out` by mut ref).
            let push = |out: &mut Vec<Segment>, a: EdgeId, a_pos, b: EdgeId, b_pos| {
                out.push(Segment { a, b, a_pos, b_pos });
            };

            // Look up case — each non-saddle case pushes 1 segment; saddles
            // push 2. Direction convention: each segment is oriented so the
            // INSIDE region is on the LEFT of `a→b` walk (CCW around inside).
            // Final polygon orientation is normalized by `ensure_ccw` below;
            // segments only need to be internally consistent.
            match mask {
                // BL inside (SW triangle): walk bot→left, inside (SW) on left.
                0b0001 => push(&mut out, e_bot, p_bot, e_left, p_left),
                // BR inside (SE triangle): walk right→bot.
                0b0010 => push(&mut out, e_right, p_right, e_bot, p_bot),
                // BL+BR inside (south strip): walk right→left.
                0b0011 => push(&mut out, e_right, p_right, e_left, p_left),
                // TR inside (NE triangle): walk top→right.
                0b0100 => push(&mut out, e_top, p_top, e_right, p_right),
                0b0101 => {
                    // SADDLE — BL + TR inside, BR + TL outside.
                    let center_inside = saddle_center_inside(g, i, j, iso, field, rng);
                    if center_inside {
                        // Diagonal strip (inside connects BL↔TR through centre).
                        // Two outside corners. Boundary CCW around the strip:
                        // bot→right (along SE side) + top→left (along NW side).
                        push(&mut out, e_bot, p_bot, e_right, p_right);
                        push(&mut out, e_top, p_top, e_left, p_left);
                    } else {
                        // Two separate inside corners: around BL (bot→left) +
                        // around TR (top→right).
                        push(&mut out, e_bot, p_bot, e_left, p_left);
                        push(&mut out, e_top, p_top, e_right, p_right);
                    }
                }
                // BR+TR inside (east strip): walk top→bot.
                0b0110 => push(&mut out, e_top, p_top, e_bot, p_bot),
                // BL+BR+TR inside (TL is outside corner): walk top→left.
                0b0111 => push(&mut out, e_top, p_top, e_left, p_left),
                // TL inside (NW triangle): walk left→top.
                0b1000 => push(&mut out, e_left, p_left, e_top, p_top),
                // BL+TL inside (west strip): walk bot→top.
                0b1001 => push(&mut out, e_bot, p_bot, e_top, p_top),
                0b1010 => {
                    // SADDLE — BR + TL inside, BL + TR outside.
                    let center_inside = saddle_center_inside(g, i, j, iso, field, rng);
                    if center_inside {
                        // Anti-diagonal strip (inside connects BR↔TL through
                        // centre). Boundary CCW: right→top (NE side) +
                        // left→bot (SW side).
                        push(&mut out, e_right, p_right, e_top, p_top);
                        push(&mut out, e_left, p_left, e_bot, p_bot);
                    } else {
                        // Two separate inside corners: around BR (right→bot) +
                        // around TL (left→top).
                        push(&mut out, e_right, p_right, e_bot, p_bot);
                        push(&mut out, e_left, p_left, e_top, p_top);
                    }
                }
                // BL+BR+TL inside (TR is outside corner): walk right→top.
                0b1011 => push(&mut out, e_right, p_right, e_top, p_top),
                // TR+TL inside (north strip): walk left→right.
                0b1100 => push(&mut out, e_left, p_left, e_right, p_right),
                // BL+TR+TL inside (BR is outside corner): walk bot→right.
                0b1101 => push(&mut out, e_bot, p_bot, e_right, p_right),
                // BR+TR+TL inside (BL is outside corner): walk left→bot.
                0b1110 => push(&mut out, e_left, p_left, e_bot, p_bot),
                _ => unreachable!("mask {mask} should be impossible"),
            };
        }
    }
    out
}

/// Saddle disambiguation — sample cell centre against `iso`. Tiebreak
/// (sample exactly equal) consumes one `rng.next_f32()`.
fn saddle_center_inside<F: Fn((f32, f32)) -> f32>(
    g: &Grid,
    i: usize,
    j: usize,
    iso: f32,
    field: &F,
    rng: &mut Rng,
) -> bool {
    let (cx, cy) = g.corner_pos(i, j);
    let (cx2, cy2) = g.corner_pos(i + 1, j + 1);
    let mid = ((cx + cx2) * 0.5, (cy + cy2) * 0.5);
    let center_val = field(mid);
    if (center_val - iso).abs() < 1e-9 {
        rng.next_f32() < 0.5
    } else {
        center_val <= iso
    }
}

/// Linear interpolation between two corner positions weighted by where
/// `iso` crosses between `fa` and `fb`.
fn lerp_edge(
    a: (f32, f32), fa: f32,
    b: (f32, f32), fb: f32,
    iso: f32,
) -> (f32, f32) {
    let denom = fb - fa;
    let t = if denom.abs() < 1e-9 { 0.5 } else { (iso - fa) / denom };
    let t = t.clamp(0.0, 1.0);
    (a.0 + t * (b.0 - a.0), a.1 + t * (b.1 - a.1))
}

// =============================================================================
// Step 3 — Contour stitching
// =============================================================================

/// Walk segments edge-to-edge to form closed rings. Adjacency via shared
/// `EdgeId` — each interior edge is shared by exactly two cells, so a
/// closed contour's edges have valence 2.
fn stitch_rings(segments: Vec<Segment>) -> Vec<Polygon> {
    // EdgeId → list of segment indices touching it.
    let mut adj: BTreeMap<EdgeId, Vec<usize>> = BTreeMap::new();
    for (idx, s) in segments.iter().enumerate() {
        adj.entry(s.a).or_default().push(idx);
        adj.entry(s.b).or_default().push(idx);
    }

    let mut visited = vec![false; segments.len()];
    let mut rings: Vec<Polygon> = Vec::new();

    for start in 0..segments.len() {
        if visited[start] {
            continue;
        }
        let mut ring: Vec<(f32, f32)> = Vec::new();
        let mut cur = start;
        let mut from_edge: Option<EdgeId> = None;
        loop {
            if visited[cur] {
                break;
            }
            visited[cur] = true;
            let seg = segments[cur];

            // Append the endpoint we entered FROM (or `a` on the first hop).
            let (this_in, next_edge) = match from_edge {
                None => (seg.a_pos, seg.b),
                Some(e) if e == seg.a => (seg.a_pos, seg.b),
                Some(e) if e == seg.b => (seg.b_pos, seg.a),
                Some(_) => break, // shouldn't happen — adjacency violated
            };
            ring.push(this_in);

            // Find next segment that shares `next_edge` (and is not `cur`).
            let candidates = match adj.get(&next_edge) {
                Some(v) => v,
                None => break,
            };
            let mut found = None;
            for &c in candidates {
                if c != cur && !visited[c] {
                    found = Some(c);
                    break;
                }
            }
            from_edge = Some(next_edge);
            match found {
                Some(nxt) => cur = nxt,
                None => break, // open chain or closed loop terminating
            }
        }
        if ring.len() >= 3 {
            rings.push(ring);
        }
    }
    rings
}

fn signed_area(poly: &Polygon) -> f32 {
    let n = poly.len();
    if n < 3 {
        return 0.0;
    }
    let mut a = 0.0f32;
    for i in 0..n {
        let (x1, y1) = poly[i];
        let (x2, y2) = poly[(i + 1) % n];
        a += x1 * y2 - x2 * y1;
    }
    a * 0.5
}

// =============================================================================
// Step 4 — Chaikin smoothing
// =============================================================================

fn chaikin(poly: &Polygon, passes: usize) -> Polygon {
    let mut current = poly.clone();
    for _ in 0..passes {
        if current.len() > 512 {
            break;
        }
        let n = current.len();
        let mut next = Vec::with_capacity(n * 2);
        for i in 0..n {
            let p = current[i];
            let q = current[(i + 1) % n];
            // 1/4 + 3/4 and 3/4 + 1/4 (closed curve Chaikin).
            next.push((0.75 * p.0 + 0.25 * q.0, 0.75 * p.1 + 0.25 * q.1));
            next.push((0.25 * p.0 + 0.75 * q.0, 0.25 * p.1 + 0.75 * q.1));
        }
        current = next;
    }
    current
}

// =============================================================================
// Step 5 — Douglas-Peucker simplification
// =============================================================================

fn douglas_peucker(poly: &Polygon, eps: f32) -> Polygon {
    let n = poly.len();
    if n <= 3 || eps <= 0.0 {
        return poly.clone();
    }

    // Recursive DP on the *closed* polyline: pick farthest-apart pair as
    // initial anchors, then DP both halves.
    let mut idx_max = 0usize;
    let mut d_max = 0.0f32;
    for i in 1..n {
        let d = ((poly[i].0 - poly[0].0).powi(2) + (poly[i].1 - poly[0].1).powi(2)).sqrt();
        if d > d_max {
            d_max = d;
            idx_max = i;
        }
    }

    let mut keep = vec![false; n];
    keep[0] = true;
    keep[idx_max] = true;

    dp_recurse(poly, 0, idx_max, eps, &mut keep);
    dp_recurse_wrap(poly, idx_max, 0, eps, &mut keep);

    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        if keep[i] {
            out.push(poly[i]);
        }
    }
    out
}

fn dp_recurse(poly: &Polygon, lo: usize, hi: usize, eps: f32, keep: &mut [bool]) {
    if hi <= lo + 1 {
        return;
    }
    let a = poly[lo];
    let b = poly[hi];
    let mut idx = lo;
    let mut d_max = 0.0f32;
    for (i, vertex) in poly.iter().enumerate().take(hi).skip(lo + 1) {
        let d = perp_distance(*vertex, a, b);
        if d > d_max {
            d_max = d;
            idx = i;
        }
    }
    if d_max > eps {
        keep[idx] = true;
        dp_recurse(poly, lo, idx, eps, keep);
        dp_recurse(poly, idx, hi, eps, keep);
    }
}

fn dp_recurse_wrap(poly: &Polygon, lo: usize, hi: usize, eps: f32, keep: &mut [bool]) {
    let n = poly.len();
    let a = poly[lo];
    let b = poly[hi];
    let segment_len = (n - lo) + hi;
    if segment_len <= 1 {
        return;
    }
    let mut idx_wrap = lo;
    let mut d_max = 0.0f32;
    for step in 1..segment_len {
        let i = (lo + step) % n;
        let d = perp_distance(poly[i], a, b);
        if d > d_max {
            d_max = d;
            idx_wrap = i;
        }
    }
    if d_max > eps {
        keep[idx_wrap] = true;
        let left_len = if idx_wrap > lo { idx_wrap - lo } else { idx_wrap + n - lo };
        let right_len = if hi > idx_wrap { hi - idx_wrap } else { hi + n - idx_wrap };
        if left_len > 1 {
            if idx_wrap > lo {
                dp_recurse(poly, lo, idx_wrap, eps, keep);
            } else {
                dp_recurse_wrap(poly, lo, idx_wrap, eps, keep);
            }
        }
        if right_len > 1 {
            if hi > idx_wrap {
                dp_recurse(poly, idx_wrap, hi, eps, keep);
            } else {
                dp_recurse_wrap(poly, idx_wrap, hi, eps, keep);
            }
        }
    }
}

fn perp_distance(p: (f32, f32), a: (f32, f32), b: (f32, f32)) -> f32 {
    let dx = b.0 - a.0;
    let dy = b.1 - a.1;
    let len_sq = dx * dx + dy * dy;
    if len_sq < 1e-12 {
        return ((p.0 - a.0).powi(2) + (p.1 - a.1).powi(2)).sqrt();
    }
    let t = ((p.0 - a.0) * dx + (p.1 - a.1) * dy) / len_sq;
    let t = t.clamp(0.0, 1.0);
    let proj = (a.0 + t * dx, a.1 + t * dy);
    ((p.0 - proj.0).powi(2) + (p.1 - proj.1).powi(2)).sqrt()
}

// =============================================================================
// Step 6 — Centroid alignment (only when target is outside polygon)
// =============================================================================

/// Translate the polygon so its centroid coincides with `target` — but ONLY
/// if `target` is currently outside the polygon. For convex shapes the
/// centroid is always inside, so alignment is safe. For non-convex shapes
/// (Y-branch / CrabRadial / etc.) the centroid can lie in a "concave gap"
/// outside the polygon — aligning would translate the polygon away from
/// where its actual inside-region overlaps `target`. Skipping in that case
/// preserves the SDF / noise-field's natural positioning (the field is
/// already centred at `target`, so the polygon naturally surrounds it).
fn align_centroid(poly: Polygon, target: (f32, f32)) -> Polygon {
    if poly.is_empty() {
        return poly;
    }
    if point_in_polygon(&poly, target) {
        return poly;
    }
    let cx = poly.iter().map(|p| p.0).sum::<f32>() / poly.len() as f32;
    let cy = poly.iter().map(|p| p.1).sum::<f32>() / poly.len() as f32;
    let dx = target.0 - cx;
    let dy = target.1 - cy;
    poly.into_iter().map(|(x, y)| (x + dx, y + dy)).collect()
}

fn point_in_polygon(poly: &Polygon, point: (f32, f32)) -> bool {
    let n = poly.len();
    if n < 3 {
        return false;
    }
    let mut inside = false;
    for i in 0..n {
        let (xi, yi) = poly[i];
        let (xj, yj) = poly[(i + 1) % n];
        let cond = ((yi > point.1) != (yj > point.1))
            && (point.0 < (xj - xi) * (point.1 - yi) / (yj - yi + f32::EPSILON) + xi);
        if cond {
            inside = !inside;
        }
    }
    inside
}

// =============================================================================
// Step 7 — CCW enforcement
// =============================================================================

fn ensure_ccw(mut poly: Polygon) -> Polygon {
    if signed_area(&poly) < 0.0 {
        poly.reverse();
    }
    poly
}

// =============================================================================
// MarchingNoiseGenerator
// =============================================================================

/// Generator that builds a continent silhouette from a noise field with a
/// radial falloff. The falloff guarantees a closed inside region near
/// `ctx.center` regardless of the noise's global behaviour, so
/// `field_to_polygon` is guaranteed to return a non-degenerate ring.
pub struct MarchingNoiseGenerator;

impl ShapeGenerator for MarchingNoiseGenerator {
    fn kind(&self) -> ShapeKind {
        ShapeKind::MarchingNoise
    }

    fn generate(&self, ctx: &ShapeContext, _caller_rng: &mut Rng) -> ShapeResult {
        // Internal RNG so caller stream stays invariant (matches spine.rs /
        // polar.rs / csg.rs discipline).
        let mut rng = Rng::for_stage(ctx.seed as u64, b"marching-noise");
        let (cx, cy) = ctx.center;
        let env = ctx.envelope.0;
        let salt = ctx.plate_salt;
        let (rmin, rmax) = ctx.size_rank.radius_band();
        let target_r = (rmin + rmax) * 0.5;

        // **v3.3 redesign (post-PO diagnosis 2026-05-27)**: archipelago =
        // a GROUP of distinct islands, NOT a single noise-perturbed blob.
        // The v3.3-round-1 field `(r - target_r) - n * amp` was fundamentally
        // a blob generator — it produced at best 1 main blob + tiny fringe
        // satellites. True archipelago needs MULTIPLE seed centres scattered
        // across the plate bbox; each centre gets its own SDF disk warped by
        // its own noise; field = min(per-island SDF) so marching squares
        // produces N disjoint contours naturally.

        // Island count: 2..=6 per plate. Picked uniformly so most plates have
        // 3-4 islands (Indonesia / Japan / Philippines scale typical).
        let n_islands = 2 + (rng.next_u32() % 5) as usize;

        // Place island centres inside a disk of radius `target_r * 0.9 * env`
        // (wider than v3.3-r3 0.7 so Poisson-disk rejection has room to
        // separate islands without collapsing into the disk centre).
        let placement_radius = target_r * 0.9 * env;
        // Per-island base radius: Pareto-ish distribution — most islands
        // medium, occasional small ones. Total area is calibrated against
        // `target_r * env * PI` (the equivalent single-blob area) so a
        // multi-island plate has comparable total land area to a single-blob
        // plate at the same rank.
        let total_target_area = std::f32::consts::PI * (target_r * env).powi(2);

        // Step 1 — pick per-island size weights upfront so we know each
        // island's radius BEFORE Poisson-disk placement.
        let size_weights: Vec<f32> = (0..n_islands)
            .map(|_| 1.0 - rng.next_f32().sqrt())
            .collect();
        let total_w: f32 = size_weights.iter().sum::<f32>().max(1e-6);
        let radii: Vec<f32> = size_weights
            .iter()
            .map(|w| {
                let area_share = (w / total_w) * total_target_area;
                (area_share / std::f32::consts::PI).sqrt()
            })
            .collect();

        // Step 2 — Poisson-disk-style placement with minimum-separation
        // rejection. Two islands i, j are "too close" when their centres are
        // within `(radii[i] + radii[j]) * (1 + SEPARATION_GAP)`. The 0.45 gap
        // factor leaves clear water between island coasts when the noise
        // warp is at its mean — visible PNG-scale separation even after
        // ±30% coast jitter.
        const SEPARATION_GAP: f32 = 0.45;
        const MAX_PLACEMENT_TRIES: usize = 24;
        let mut placed: Vec<(f32, f32)> = Vec::with_capacity(n_islands);
        for i in 0..n_islands {
            let r_i = radii[i];
            let mut chosen: Option<(f32, f32)> = None;
            for _ in 0..MAX_PLACEMENT_TRIES {
                let t = rng.next_f32();
                let r = t.sqrt() * placement_radius;
                let theta = rng.next_f32() * std::f32::consts::TAU;
                let pos = (cx + r * theta.cos(), cy + r * theta.sin());
                let mut clear = true;
                for (j, &p_pos) in placed.iter().enumerate() {
                    let d = ((pos.0 - p_pos.0).powi(2) + (pos.1 - p_pos.1).powi(2)).sqrt();
                    let min_dist = (r_i + radii[j]) * (1.0 + SEPARATION_GAP);
                    if d < min_dist {
                        clear = false;
                        break;
                    }
                }
                if clear {
                    chosen = Some(pos);
                    break;
                }
            }
            // If rejection sampling failed all tries (very crowded plate),
            // place at the LAST candidate position — caller still gets the
            // requested island count, even if it overlaps. Better to render
            // a merged blob than to drop islands silently.
            let final_pos = chosen.unwrap_or_else(|| {
                let t = rng.next_f32();
                let r = t.sqrt() * placement_radius;
                let theta = rng.next_f32() * std::f32::consts::TAU;
                (cx + r * theta.cos(), cy + r * theta.sin())
            });
            placed.push(final_pos);
        }

        // Step 3 — bundle (position, size_w_unused, per-island noise salt)
        // for the field closure. size_w is no longer used directly because
        // radii is the authoritative list.
        let islands: Vec<((f32, f32), f32, u32)> = placed
            .into_iter()
            .enumerate()
            .map(|(i, pos)| (pos, size_weights[i], salt.wrapping_add((i as u32).wrapping_mul(0x9E37_79B9))))
            .collect();

        // Frequency for per-island noise warp: high enough that each island
        // gets a wobbly coast within its diameter.
        let coast_freq = 4.0 / env;

        // Compute bbox before moving `radii` into the closure.
        let max_radius = radii.iter().cloned().fold(0.0_f32, f32::max);
        let bbox_half = placement_radius + max_radius * 1.4;
        let bbox = (cx - bbox_half, cy - bbox_half, cx + bbox_half, cy + bbox_half);

        let field = move |p: (f32, f32)| -> f32 {
            // SDF: min across all islands. Inside = below 0.
            let mut best = 1e6_f32;
            for (i, &(ipos, _, island_salt)) in islands.iter().enumerate() {
                let dx = p.0 - ipos.0;
                let dy = p.1 - ipos.1;
                let d = (dx * dx + dy * dy).sqrt();
                let n = crate::noise::fbm(
                    p.0 * coast_freq,
                    p.1 * coast_freq,
                    island_salt,
                    3,
                );
                // Coast warp: ±30% of base radius.
                let warped_r = radii[i] * (1.0 + n * 0.30);
                let island_sdf = d - warped_r;
                if island_sdf < best {
                    best = island_sdf;
                }
            }
            best
        };

        // Shape-preserving fit to caller's vertex-count range.
        let range = (
            ctx.vertex_count_range.0.max(3),
            ctx.vertex_count_range.1.max(ctx.vertex_count_range.0),
        );
        // Multi-component output per PO directive: min_area_frac=0.01 keeps
        // every island ≥ 1% of plate bbox. With N=2-6 distinct centres, the
        // pipeline emits N polygons naturally.
        let polys = field_to_polygon(
            field, bbox, 0.0, 256, 2, 0.005, &mut rng, ctx.center, Some(range), 0.01,
        );
        ShapeResult::single_kind(polys, ShapeKind::MarchingNoise)
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;

    fn unit_circle_field(r: f32) -> impl Fn((f32, f32)) -> f32 {
        move |p: (f32, f32)| (p.0 * p.0 + p.1 * p.1).sqrt() - r
    }

    fn make_rng() -> Rng {
        Rng::for_stage(42, b"raster-tests")
    }

    fn test_ctx(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (100.0, 100.0),
            envelope: (50.0, 50.0),
            size_rank: SizeRank::Medium,
            seed,
            plate_salt: 0x1234_5678,
            parent_path: vec![],
            world_theme: None,
            edge_jitter: 0.0,
            vertex_count_range: (24, 96),
        }
    }

    // -- Step 1+2+3 happy paths ------------------------------------------------

    #[test]
    fn unit_circle_renders_closed_ccw_polygon() {
        let mut rng = make_rng();
        let polys = field_to_polygon(
            unit_circle_field(1.0),
            (-2.0, -2.0, 2.0, 2.0),
            0.0,
            64,
            2,
            0.005,
            &mut rng,
            (0.0, 0.0),
            None::<(usize, usize)>,
            1.0, // single-component (v3.2 compat)
        );
        assert_eq!(polys.len(), 1, "single-component circle should yield 1 polygon");
        let poly = &polys[0];
        assert!(poly.len() >= 3, "polygon should have ≥3 vertices, got {}", poly.len());
        assert!(signed_area(poly) > 0.0, "polygon should be CCW (positive signed area)");
        // Centroid should be ~near origin.
        let cx = poly.iter().map(|p| p.0).sum::<f32>() / poly.len() as f32;
        let cy = poly.iter().map(|p| p.1).sum::<f32>() / poly.len() as f32;
        assert!(cx.abs() < 0.1, "centroid x should be near 0, got {cx}");
        assert!(cy.abs() < 0.1, "centroid y should be near 0, got {cy}");
    }

    #[test]
    fn rotated_square_field_renders_4_corners_approximately() {
        let square_field = |p: (f32, f32)| p.0.abs().max(p.1.abs()) - 1.0;
        let mut rng = make_rng();
        let polys = field_to_polygon(
            square_field,
            (-2.0, -2.0, 2.0, 2.0),
            0.0,
            64,
            2,
            0.005,
            &mut rng,
            (0.0, 0.0),
            None::<(usize, usize)>,
            1.0,
        );
        let poly = &polys[0];
        assert!(poly.len() >= 4, "square needs ≥4 vertices, got {}", poly.len());
        // Area of unit square = 4 (since side = 2).
        let area = signed_area(poly).abs();
        assert!((area - 4.0).abs() < 0.3, "area should be ~4.0 ± 0.3, got {area}");
    }

    #[test]
    fn off_center_circle_centroid_aligns_to_target() {
        let mut rng = make_rng();
        let target = (50.0, 50.0);
        // Circle in world coords centred at (50, 50), radius 10.
        let field = |p: (f32, f32)| ((p.0 - 50.0).powi(2) + (p.1 - 50.0).powi(2)).sqrt() - 10.0;
        let polys = field_to_polygon(
            field,
            (35.0, 35.0, 65.0, 65.0),
            0.0,
            64,
            2,
            0.005,
            &mut rng,
            target,
            None::<(usize, usize)>,
            1.0,
        );
        let poly = &polys[0];
        let cx = poly.iter().map(|p| p.0).sum::<f32>() / poly.len() as f32;
        let cy = poly.iter().map(|p| p.1).sum::<f32>() / poly.len() as f32;
        assert!((cx - target.0).abs() < 0.5, "centroid x off by {}", (cx - target.0).abs());
        assert!((cy - target.1).abs() < 0.5, "centroid y off by {}", (cy - target.1).abs());
    }

    // -- v3.3 multi-component ------------------------------------------------

    #[test]
    fn two_distant_disks_render_as_two_components() {
        // Two non-overlapping unit disks at (-5, 0) and (5, 0). bbox = 16×6.
        // Each disk area ≈ π ≈ 3.14; bbox area = 96. Ratio per disk ≈ 3.3%
        // → passes 1% threshold.
        let field = |p: (f32, f32)| {
            let d_left = ((p.0 + 5.0).powi(2) + p.1.powi(2)).sqrt() - 1.0;
            let d_right = ((p.0 - 5.0).powi(2) + p.1.powi(2)).sqrt() - 1.0;
            d_left.min(d_right)
        };
        let mut rng = make_rng();
        let polys = field_to_polygon(
            field,
            (-8.0, -3.0, 8.0, 3.0),
            0.0,
            96,
            2,
            0.005,
            &mut rng,
            (-5.0, 0.0),
            None::<(usize, usize)>,
            0.01,
        );
        assert_eq!(polys.len(), 2, "two-disk field should produce 2 components");
        // Primary [0] is the LARGEST (by area, descending sort). Satellite [1]
        // is the smaller (or equal-and-after-tie) ring. The disks have
        // nominally equal area but Chaikin / DP can introduce tiny variance,
        // so we don't compare areas strictly — just confirm the sort order.
        let area_primary = signed_area(&polys[0]).abs();
        let area_sat = signed_area(&polys[1]).abs();
        assert!(
            area_primary >= area_sat - 0.01,
            "polys[0] must be at least as large as polys[1] (primary={area_primary}, sat={area_sat})"
        );
    }

    #[test]
    fn tiny_islands_below_area_threshold_are_dropped() {
        // One big disk (area ≈ π) + one tiny disk (area ≈ π × 0.04 = 0.13).
        // bbox ≈ 16×6 = 96. Tiny ratio ≈ 0.13% < 1% → dropped.
        let field = |p: (f32, f32)| {
            let d_big = ((p.0 + 5.0).powi(2) + p.1.powi(2)).sqrt() - 1.0;
            let d_tiny = ((p.0 - 5.0).powi(2) + p.1.powi(2)).sqrt() - 0.2;
            d_big.min(d_tiny)
        };
        let mut rng = make_rng();
        let polys = field_to_polygon(
            field,
            (-8.0, -3.0, 8.0, 3.0),
            0.0,
            96,
            2,
            0.005,
            &mut rng,
            (-5.0, 0.0),
            None::<(usize, usize)>,
            0.01,
        );
        assert_eq!(polys.len(), 1, "tiny island below 1% threshold should be dropped");
    }

    #[test]
    fn resample_arc_length_produces_target_count() {
        let circle: Polygon = (0..32)
            .map(|i| {
                let a = i as f32 * std::f32::consts::TAU / 32.0;
                (a.cos(), a.sin())
            })
            .collect();
        for n in [3, 8, 24, 48, 96] {
            let r = resample_arc_length(&circle, n);
            assert_eq!(r.len(), n, "expected {n} vertices, got {}", r.len());
        }
    }

    // -- Step 4 Chaikin -------------------------------------------------------

    #[test]
    fn chaikin_doubles_vertex_count_per_pass() {
        let square: Polygon = vec![(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)];
        let p1 = chaikin(&square, 1);
        assert_eq!(p1.len(), 8);
        let p2 = chaikin(&square, 2);
        assert_eq!(p2.len(), 16);
        let p3 = chaikin(&square, 3);
        assert_eq!(p3.len(), 32);
    }

    #[test]
    fn chaikin_caps_at_512_vertices() {
        // 100-vertex polygon × 4 passes would be 25,600 — should cap.
        let big: Polygon = (0..100).map(|i| (i as f32, (i % 7) as f32)).collect();
        let p = chaikin(&big, 4);
        assert!(p.len() <= 1024, "chaikin should cap output below 1024, got {}", p.len());
    }

    // -- Step 5 Douglas-Peucker ----------------------------------------------

    #[test]
    fn dp_simplify_reduces_collinear_run() {
        // 50 collinear points on a square's bottom edge.
        let mut poly: Polygon = Vec::new();
        for i in 0..50 {
            poly.push((i as f32 * 0.2, 0.0));
        }
        poly.push((10.0, 10.0));
        poly.push((0.0, 10.0));
        let simplified = douglas_peucker(&poly, 0.05);
        // The 50-point line should collapse down significantly.
        assert!(
            simplified.len() < poly.len() / 2,
            "DP should reduce collinear run; got {} vs original {}",
            simplified.len(),
            poly.len()
        );
    }

    // -- Step 7 CCW -----------------------------------------------------------

    #[test]
    fn ccw_orientation_enforced_for_clockwise_input() {
        // Clockwise square.
        let cw: Polygon = vec![(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)];
        let result = ensure_ccw(cw);
        assert!(signed_area(&result) > 0.0, "ensure_ccw must produce CCW polygon");
    }

    // -- Determinism ----------------------------------------------------------

    #[test]
    fn field_to_polygon_bit_identical_two_runs() {
        let mut rng_a = Rng::for_stage(7, b"det-test");
        let mut rng_b = Rng::for_stage(7, b"det-test");
        let pa_all = field_to_polygon(
            unit_circle_field(1.0),
            (-2.0, -2.0, 2.0, 2.0),
            0.0,
            48,
            2,
            0.005,
            &mut rng_a,
            (0.0, 0.0),
            None::<(usize, usize)>,
            1.0,
        );
        let pb_all = field_to_polygon(
            unit_circle_field(1.0),
            (-2.0, -2.0, 2.0, 2.0),
            0.0,
            48,
            2,
            0.005,
            &mut rng_b,
            (0.0, 0.0),
            None::<(usize, usize)>,
            1.0,
        );
        let pa = &pa_all[0];
        let pb = &pb_all[0];
        assert_eq!(pa.len(), pb.len(), "polygon lengths must match");
        for (a, b) in pa.iter().zip(pb.iter()) {
            assert_eq!(a.0.to_bits(), b.0.to_bits(), "x bits diverge");
            assert_eq!(a.1.to_bits(), b.1.to_bits(), "y bits diverge");
        }
    }

    // -- MarchingNoiseGenerator ----------------------------------------------

    #[test]
    fn marching_noise_returns_single_component() {
        let generator = MarchingNoiseGenerator;
        let mut rng = make_rng();
        let result = generator.generate(&test_ctx(123), &mut rng);
        assert_eq!(result.polygons.len(), 1, "v3.2 invariant: single component only");
        assert_eq!(result.effective_kind, ShapeKind::MarchingNoise);
    }

    #[test]
    fn marching_noise_polygon_contains_center() {
        let generator = MarchingNoiseGenerator;
        let mut rng = make_rng();
        let ctx = test_ctx(987);
        let result = generator.generate(&ctx, &mut rng);
        let poly = &result.polygons[0];
        // Point-in-polygon: ctx.center must be inside the rendered polygon.
        // (Centroid drift is OK for non-convex noise shapes; alignment is
        // skipped when the target is already inside the polygon — see
        // `align_centroid` docs.)
        assert!(
            point_in_polygon(poly, ctx.center),
            "polygon does not contain ctx.center"
        );
    }

    #[test]
    fn marching_noise_does_not_perturb_caller_rng() {
        let generator = MarchingNoiseGenerator;
        let mut caller_a = Rng::for_stage(100, b"caller");
        let mut caller_b = Rng::for_stage(100, b"caller");
        let _ = generator.generate(&test_ctx(1), &mut caller_a);
        // caller_b is untouched. caller_a should have the same next value.
        assert_eq!(caller_a.next_u32(), caller_b.next_u32(), "caller RNG was perturbed by MarchingNoiseGenerator");
    }

    #[test]
    fn marching_noise_deterministic_same_ctx() {
        let generator = MarchingNoiseGenerator;
        let mut rng_a = make_rng();
        let mut rng_b = make_rng();
        let ra = generator.generate(&test_ctx(555), &mut rng_a);
        let rb = generator.generate(&test_ctx(555), &mut rng_b);
        assert_eq!(ra.polygons[0].len(), rb.polygons[0].len());
        for (a, b) in ra.polygons[0].iter().zip(rb.polygons[0].iter()) {
            assert_eq!(a.0.to_bits(), b.0.to_bits());
            assert_eq!(a.1.to_bits(), b.1.to_bits());
        }
    }
}
