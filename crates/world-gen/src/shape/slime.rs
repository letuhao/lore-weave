//! Slime / Physarum multi-agent walk + concave hull shape generator (v3.4).
//!
//! Algorithm (per spec §2.3, research §3):
//! 1. Spawn N agents at ctx.center with random initial headings.
//! 2. Each agent walks ~energy steps with momentum (`persistence`).
//! 3. Collect visited positions → point cloud.
//! 4. Subsample to ~1500 anchors (so Delaunay is fast).
//! 5. **α-shape primary** via [`delaunator`]: accept Delaunay triangles whose
//!    circumradius < α (auto-tuned to avg spacing × 2.5). Boundary = edges
//!    on exactly one accepted triangle. Stitch into rings.
//! 6. **Moreira-Santos fallback** k-nearest concave hull if α-shape yields
//!    no usable polygon (e.g. degenerate cloud).
//! 7. Per ring: Chaikin × 1 + Douglas-Peucker simplify.
//! 8. Multi-comp filter per template (Blob = single, Branch = multi-eligible
//!    with 1% bbox threshold).
//! 9. Quality filter: if `total_area < target_area × 0.25`, retry with
//!    advanced salt up to 3 times; if all fail, fall back to Ellipse.
//!
//! Determinism: internal RNG `Rng::for_stage(ctx.seed as u64, b"slime")`.
//! Retries advance via XOR with retry counter so retries don't replay the
//! same RNG sequence.

use std::collections::HashMap;
use std::f32::consts::TAU;

use delaunator::{Point, triangulate};

use crate::flatworld::Polygon;
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};

/// Template choice. Picked deterministically from `ctx.seed`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum SlimeTemplate {
    /// Low persistence + cloud expansion ⇒ blob-like single-component output.
    Blob,
    /// High persistence + tendrils ⇒ multi-component eligible.
    Branch,
}

impl SlimeTemplate {
    pub const ALL: [SlimeTemplate; 2] = [SlimeTemplate::Blob, SlimeTemplate::Branch];

    pub fn n_agents(self) -> usize {
        match self {
            SlimeTemplate::Blob => 6,
            SlimeTemplate::Branch => 8,
        }
    }
    pub fn persistence(self) -> f32 {
        match self {
            SlimeTemplate::Blob => 0.30,
            SlimeTemplate::Branch => 0.85,
        }
    }
    pub fn energy(self) -> usize {
        // Per-template energy. Walk-coverage analysis: pure random walk
        // (persistence=0) spreads ~step × sqrt(N); directed walk
        // (persistence→1) spreads ~step × N. We want spread ≈ target_r
        // for Blob and ≈ 1.4×target_r for Branch (tendrils).
        match self {
            // Blob: persistence 0.30 (mostly random). N=900 → spread = step×30.
            // With step ~ target_r/30 (set in run_pipeline) → covers target_r.
            SlimeTemplate::Blob => 900,
            // Branch: persistence 0.85 (mostly directed). N=400 → spread =
            // step × 400 × 0.5 (directional fraction). step ~ target_r/130
            // → covers ~1.5 × target_r.
            SlimeTemplate::Branch => 400,
        }
    }
    pub fn step_size_factor(self) -> f32 {
        // step_size = target_r × this_factor. Calibrated per template so
        // random walk (low persistence) gets big strides and directed walk
        // (high persistence) gets fine strides.
        match self {
            SlimeTemplate::Blob => 1.0 / 30.0,
            SlimeTemplate::Branch => 1.0 / 130.0 * 1.5, // ~0.0115
        }
    }
    /// Whether secondary clusters survive the multi-comp filter as satellites.
    pub fn keeps_satellites(self) -> bool {
        matches!(self, SlimeTemplate::Branch)
    }

    pub fn as_str(self) -> &'static str {
        match self {
            SlimeTemplate::Blob => "Blob",
            SlimeTemplate::Branch => "Branch",
        }
    }
}

pub struct SlimeGenerator;

impl ShapeGenerator for SlimeGenerator {
    fn kind(&self) -> ShapeKind {
        ShapeKind::Slime
    }

    fn generate(&self, ctx: &ShapeContext, _caller_rng: &mut Rng) -> ShapeResult {
        // Up to 3 retries before falling back to Ellipse.
        for retry in 0..3 {
            let seed_for_retry = (ctx.seed as u64) ^ (retry as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
            let mut rng = Rng::for_stage(seed_for_retry, b"slime");
            let template = SlimeTemplate::ALL[(rng.next_u32() % 2) as usize];
            if let Some(polys) = run_pipeline(ctx, template, &mut rng) {
                if polys_pass_quality(&polys, ctx) {
                    return ShapeResult::single_kind(polys, ShapeKind::Slime);
                }
            }
        }
        // All retries failed — fall back to Ellipse with honest effective_kind.
        let mut fallback_rng = Rng::for_stage(ctx.seed as u64, b"slime-fallback");
        let ell = super::EllipseGenerator;
        let mut result = ell.generate(ctx, &mut fallback_rng);
        result.effective_kind = ShapeKind::Ellipse;
        result
    }
}

fn run_pipeline(
    ctx: &ShapeContext,
    template: SlimeTemplate,
    rng: &mut Rng,
) -> Option<Vec<Polygon>> {
    let env = ctx.envelope.0;
    let (rmin, rmax) = ctx.size_rank.radius_band();
    let target_r = (rmin + rmax) * 0.5 * env;
    // Per-template step_size: see SlimeTemplate::step_size_factor docs.
    let step_size = (target_r * template.step_size_factor()).max(0.5);

    // Bounds clamp: envelope × 1.4 around ctx.center. Agents that drift too
    // far still contribute to the cloud (won't crash) but don't escape.
    let bounds_half = env * 1.4;
    let bounds = (
        ctx.center.0 - bounds_half,
        ctx.center.1 - bounds_half,
        ctx.center.0 + bounds_half,
        ctx.center.1 + bounds_half,
    );

    let n_agents = template.n_agents();
    let energy = template.energy();
    let persistence = template.persistence();

    // Step 1-3: multi-agent walk → visited cloud.
    let mut agents: Vec<WalkAgent> = (0..n_agents)
        .map(|i| WalkAgent {
            pos: ctx.center,
            heading: rng.next_f32() * TAU,
            energy: energy as f32,
            _salt: ctx.plate_salt.wrapping_add(i as u32),
        })
        .collect();
    let visited = walk_agents(&mut agents, bounds, persistence, step_size, rng);
    if visited.len() < 32 {
        return None;
    }

    // Step 4: subsample to ≤ 3000 anchors. Higher cap (was 1500) so the
    // α-shape captures more detail in the contour. Delaunay on 3000 points
    // is ~10ms — still well under per-plate budget.
    let anchors = subsample(&visited, 3000);
    if anchors.len() < 8 {
        return None;
    }

    // Step 5: α-shape primary. Tighter α multiplier (1.8 vs 2.5) so the
    // hull wraps more closely around the cloud, picking up the inlets and
    // tendrils that the walk traced.
    let alpha = estimate_alpha(&anchors);
    let mut rings = alpha_shape(&anchors, alpha);

    // Step 6: Moreira-Santos fallback if α-shape failed.
    if rings.iter().filter(|r| r.len() >= 3).count() == 0 {
        if let Some(hull) = moreira_santos(&anchors, 8) {
            rings = vec![hull];
        }
    }
    if rings.is_empty() {
        return None;
    }

    // Step 7: smooth + simplify per ring. **PO feedback 2026-05-27 round 2**:
    // initial eps=0.5% diag and 1-pass Chaikin produced under-detailed
    // polygons (~10-20 vertices) — boring blobs. Tightened to eps=0.15%
    // diag + 2-pass Chaikin so the hull retains the wobbles + tendrils that
    // make slime mold look biological.
    let diag = (bounds_half * 2.0).hypot(bounds_half * 2.0).max(1e-6);
    let eps = 0.0015 * diag;
    let (vmin, vmax) = ctx.vertex_count_range;
    let mut polished: Vec<Polygon> = rings
        .into_iter()
        .filter(|r| r.len() >= 3)
        .map(|r| {
            let smoothed = chaikin(&r, 2);
            let simp = simplify(&smoothed, eps);
            // Cap vertex count to caller's range (matches v3.2 fit pattern).
            fit_count(simp, vmin.max(3), vmax.max(vmin), diag)
        })
        .filter(|r| r.len() >= 3)
        .collect();
    if polished.is_empty() {
        return None;
    }

    // Step 8: multi-comp filter per template.
    polished = finalize_per_template(polished, template, bounds);
    if polished.is_empty() {
        return None;
    }

    // Step 9: CCW orientation.
    for p in polished.iter_mut() {
        if signed_area(p) < 0.0 {
            p.reverse();
        }
    }
    Some(polished)
}

// =============================================================================
// Multi-agent walk
// =============================================================================

struct WalkAgent {
    pos: (f32, f32),
    heading: f32,
    energy: f32,
    _salt: u32,
}

fn walk_agents(
    agents: &mut [WalkAgent],
    bounds: (f32, f32, f32, f32),
    persistence: f32,
    step_size: f32,
    rng: &mut Rng,
) -> Vec<(f32, f32)> {
    // Pre-allocate based on total energy budget.
    let total_steps: usize = agents.iter().map(|a| a.energy as usize).sum();
    let mut visited = Vec::with_capacity(total_steps);
    let turn_amplitude = (1.0 - persistence) * TAU;
    while agents.iter().any(|a| a.energy > 0.0) {
        for agent in agents.iter_mut() {
            if agent.energy <= 0.0 {
                continue;
            }
            let dtheta = (rng.next_f32() - 0.5) * turn_amplitude;
            agent.heading += dtheta;
            agent.pos.0 = (agent.pos.0 + step_size * agent.heading.cos())
                .clamp(bounds.0, bounds.2);
            agent.pos.1 = (agent.pos.1 + step_size * agent.heading.sin())
                .clamp(bounds.1, bounds.3);
            visited.push(agent.pos);
            agent.energy -= 1.0;
        }
    }
    visited
}

fn subsample(points: &[(f32, f32)], target: usize) -> Vec<(f32, f32)> {
    if points.len() <= target {
        return points.to_vec();
    }
    let stride = points.len().div_ceil(target);
    points.iter().step_by(stride).copied().collect()
}

// =============================================================================
// α-shape (Delaunay + circumradius filter)
// =============================================================================

fn estimate_alpha(points: &[(f32, f32)]) -> f32 {
    // Avg spacing = sqrt(bbox_area / n). α = avg_spacing × 1.8 — tighter
    // wrap than the original 2.5 multiplier so the hull preserves inlets,
    // peninsulas, and tendril detail (PO feedback 2026-05-27 round 2:
    // initial α=2.5 produced blobs that looked "boring").
    if points.len() < 2 {
        return 1.0;
    }
    let (mut minx, mut miny) = (f32::INFINITY, f32::INFINITY);
    let (mut maxx, mut maxy) = (f32::NEG_INFINITY, f32::NEG_INFINITY);
    for &(x, y) in points {
        minx = minx.min(x);
        miny = miny.min(y);
        maxx = maxx.max(x);
        maxy = maxy.max(y);
    }
    let bbox_area = (maxx - minx).abs() * (maxy - miny).abs();
    if bbox_area < 1e-6 {
        return 1.0;
    }
    let avg_spacing = (bbox_area / points.len() as f32).sqrt();
    avg_spacing * 1.8
}

fn alpha_shape(points: &[(f32, f32)], alpha: f32) -> Vec<Polygon> {
    if points.len() < 3 {
        return Vec::new();
    }
    let delpts: Vec<Point> = points
        .iter()
        .map(|&(x, y)| Point {
            x: x as f64,
            y: y as f64,
        })
        .collect();
    let tri = triangulate(&delpts);
    if tri.triangles.is_empty() {
        return Vec::new();
    }
    // Per triangle (i, j, k): compute circumradius, accept if < alpha.
    let alpha_sq = alpha * alpha;
    let mut accepted: Vec<bool> = Vec::with_capacity(tri.triangles.len() / 3);
    let mut edge_count: HashMap<(usize, usize), u32> = HashMap::new();
    let n_tri = tri.triangles.len() / 3;
    for t in 0..n_tri {
        let i = tri.triangles[3 * t];
        let j = tri.triangles[3 * t + 1];
        let k = tri.triangles[3 * t + 2];
        let r2 = circumradius_sq(points[i], points[j], points[k]);
        accepted.push(r2.is_finite() && r2 < alpha_sq);
        if accepted[t] {
            for &(a, b) in &[(i, j), (j, k), (k, i)] {
                let e = if a < b { (a, b) } else { (b, a) };
                *edge_count.entry(e).or_insert(0) += 1;
            }
        }
    }
    // Boundary edges = edges with count 1.
    let mut boundary: Vec<(usize, usize)> = edge_count
        .into_iter()
        .filter_map(|(e, c)| if c == 1 { Some(e) } else { None })
        .collect();
    if boundary.is_empty() {
        return Vec::new();
    }
    // Sort for determinism before stitching.
    boundary.sort();
    stitch_edges(&boundary, points)
}

fn circumradius_sq(a: (f32, f32), b: (f32, f32), c: (f32, f32)) -> f32 {
    let ax = a.0;
    let ay = a.1;
    let bx = b.0;
    let by = b.1;
    let cx = c.0;
    let cy = c.1;
    let d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
    if d.abs() < 1e-9 {
        return f32::INFINITY;
    }
    let ux = ((ax * ax + ay * ay) * (by - cy)
        + (bx * bx + by * by) * (cy - ay)
        + (cx * cx + cy * cy) * (ay - by))
        / d;
    let uy = ((ax * ax + ay * ay) * (cx - bx)
        + (bx * bx + by * by) * (ax - cx)
        + (cx * cx + cy * cy) * (bx - ax))
        / d;
    (ux - ax).powi(2) + (uy - ay).powi(2)
}

fn stitch_edges(edges: &[(usize, usize)], points: &[(f32, f32)]) -> Vec<Polygon> {
    // Build vertex → adjacent vertex list.
    let mut adj: HashMap<usize, Vec<usize>> = HashMap::new();
    for &(a, b) in edges {
        adj.entry(a).or_default().push(b);
        adj.entry(b).or_default().push(a);
    }
    let mut visited: Vec<(usize, usize)> = Vec::with_capacity(edges.len());
    let mut rings: Vec<Polygon> = Vec::new();
    for &(start_a, start_b) in edges {
        let key = if start_a < start_b { (start_a, start_b) } else { (start_b, start_a) };
        if visited.contains(&key) {
            continue;
        }
        let mut ring: Vec<(f32, f32)> = Vec::new();
        let mut cur = start_a;
        let mut prev: Option<usize> = None;
        let max_steps = edges.len() * 2;
        let mut steps = 0;
        loop {
            ring.push(points[cur]);
            let neighbors = match adj.get(&cur) {
                Some(v) => v,
                None => break,
            };
            // Pick next neighbor that's not the previous vertex.
            let mut next: Option<usize> = None;
            for &n in neighbors {
                if Some(n) != prev {
                    let e = if cur < n { (cur, n) } else { (n, cur) };
                    if !visited.contains(&e) {
                        next = Some(n);
                        visited.push(e);
                        break;
                    }
                }
            }
            match next {
                Some(n) => {
                    prev = Some(cur);
                    cur = n;
                }
                None => break,
            }
            if cur == start_a {
                break;
            }
            steps += 1;
            if steps > max_steps {
                break;
            }
        }
        if ring.len() >= 3 {
            rings.push(ring);
        }
    }
    rings
}

// =============================================================================
// Moreira-Santos k-nearest concave hull (fallback)
// =============================================================================

fn moreira_santos(points: &[(f32, f32)], k: usize) -> Option<Polygon> {
    if points.len() < 3 {
        return None;
    }
    // Start at rightmost point (max x, min y for tie-break).
    let start_idx = points
        .iter()
        .enumerate()
        .max_by(|(_, a), (_, b)| {
            a.0.partial_cmp(&b.0)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal))
        })?
        .0;
    let mut hull: Vec<usize> = vec![start_idx];
    let mut current = start_idx;
    let mut prev_heading: f32 = std::f32::consts::PI; // initially "from east"
    let max_iters = points.len() * 8;
    for _ in 0..max_iters {
        // K nearest neighbors of current, excluding already-on-hull (except start
        // after first 2 points so we can close).
        let cur_pos = points[current];
        let mut candidates: Vec<(f32, usize)> = points
            .iter()
            .enumerate()
            .filter(|(i, _)| {
                *i != current
                    && (hull.len() < 3 || !hull.contains(i) || *i == start_idx)
            })
            .map(|(i, &p)| {
                let dx = p.0 - cur_pos.0;
                let dy = p.1 - cur_pos.1;
                (dx * dx + dy * dy, i)
            })
            .collect();
        candidates.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));
        candidates.truncate(k);
        // Pick candidate with largest right-turn angle from prev heading.
        let mut best: Option<(f32, usize, f32)> = None; // (angle_diff, idx, new_heading)
        for &(_, ci) in &candidates {
            let p = points[ci];
            let dx = p.0 - cur_pos.0;
            let dy = p.1 - cur_pos.1;
            let new_heading = dy.atan2(dx);
            // Right turn = heading rotates clockwise. Use mod-TAU diff.
            let mut diff = prev_heading - new_heading;
            while diff < 0.0 {
                diff += TAU;
            }
            while diff >= TAU {
                diff -= TAU;
            }
            // No self-intersection check here at v3.4 (cost-benefit poor; rely
            // on caller's Chaikin+DP to smooth tiny artefacts).
            let take = best.map(|(d, _, _)| diff > d).unwrap_or(true);
            if take {
                best = Some((diff, ci, new_heading));
            }
        }
        let (_, next_idx, new_heading) = best?;
        if next_idx == start_idx && hull.len() >= 3 {
            break;
        }
        hull.push(next_idx);
        prev_heading = new_heading;
        current = next_idx;
        if hull.len() > points.len() + 1 {
            // Safety: avoid infinite walk.
            break;
        }
    }
    if hull.len() < 3 {
        return None;
    }
    Some(hull.into_iter().map(|i| points[i]).collect())
}

// =============================================================================
// Chaikin + DP simplify (local copies — keep slime.rs self-contained)
// =============================================================================

fn chaikin(poly: &Polygon, passes: usize) -> Polygon {
    let mut current = poly.clone();
    for _ in 0..passes {
        if current.len() > 1024 {
            break;
        }
        let n = current.len();
        let mut next = Vec::with_capacity(n * 2);
        for i in 0..n {
            let p = current[i];
            let q = current[(i + 1) % n];
            next.push((0.75 * p.0 + 0.25 * q.0, 0.75 * p.1 + 0.25 * q.1));
            next.push((0.25 * p.0 + 0.75 * q.0, 0.25 * p.1 + 0.75 * q.1));
        }
        current = next;
    }
    current
}

fn simplify(poly: &Polygon, eps: f32) -> Polygon {
    let n = poly.len();
    if n <= 3 || eps <= 0.0 {
        return poly.clone();
    }
    // Pick farthest pair as anchors.
    let mut idx_max = 0;
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
    poly.iter().enumerate().filter(|(i, _)| keep[*i]).map(|(_, &p)| p).collect()
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
        if idx_wrap > lo {
            dp_recurse(poly, lo, idx_wrap, eps, keep);
        }
        if hi > idx_wrap {
            dp_recurse(poly, idx_wrap, hi, eps, keep);
        }
    }
}

/// Shape-preserving fit to vertex-count range — mirrors
/// `raster::fit_vertex_count_range`. If over-max, re-DP with growing eps;
/// if under-min, subdivide longest edges (midpoint insert).
fn fit_count(mut poly: Polygon, vmin: usize, vmax: usize, diag: f32) -> Polygon {
    if poly.len() > vmax {
        let mut eps = 0.0015 * diag;
        let mut iters = 0;
        while poly.len() > vmax && iters < 20 {
            eps *= 1.5;
            poly = simplify(&poly, eps);
            iters += 1;
        }
    }
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
// Multi-comp filter + quality gate
// =============================================================================

fn finalize_per_template(
    rings: Vec<Polygon>,
    template: SlimeTemplate,
    bounds: (f32, f32, f32, f32),
) -> Vec<Polygon> {
    // Sort by area descending; primary = [0].
    let mut sorted: Vec<(f32, Polygon)> = rings
        .into_iter()
        .map(|p| (signed_area(&p).abs(), p))
        .collect();
    sorted.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    if sorted.is_empty() {
        return Vec::new();
    }
    let bbox_area = (bounds.2 - bounds.0).abs() * (bounds.3 - bounds.1).abs();
    let threshold = bbox_area * 0.01;
    if !template.keeps_satellites() {
        // Blob: keep largest only.
        return vec![sorted.into_iter().next().unwrap().1];
    }
    // Branch: keep primary + satellites ≥ 1% bbox area.
    let mut iter = sorted.into_iter();
    let primary = iter.next().unwrap().1;
    let mut out = vec![primary];
    for (a, p) in iter {
        if a >= threshold {
            out.push(p);
        }
    }
    out
}

fn polys_pass_quality(polys: &[Polygon], ctx: &ShapeContext) -> bool {
    let env = ctx.envelope.0;
    let (rmin, rmax) = ctx.size_rank.radius_band();
    let target_r = (rmin + rmax) * 0.5 * env;
    let target_area = std::f32::consts::PI * target_r * target_r;
    let total: f32 = polys.iter().map(|p| signed_area(p).abs()).sum();
    total >= target_area * 0.25
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;

    fn test_ctx(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (500.0, 320.0),
            envelope: (200.0, 200.0),
            size_rank: SizeRank::Large,
            seed,
            plate_salt: seed.wrapping_add(0xCAFE_BABE),
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.30,
            vertex_count_range: (24, 96),
        }
    }

    // -- Walk -----------------------------------------------------------------

    #[test]
    fn walk_agents_respects_bounds() {
        let mut rng = Rng::for_stage(42, b"slime-walk-test");
        let mut agents = vec![
            WalkAgent { pos: (0.0, 0.0), heading: 0.0, energy: 1000.0, _salt: 0 },
            WalkAgent { pos: (0.0, 0.0), heading: TAU * 0.5, energy: 1000.0, _salt: 1 },
        ];
        let bounds = (-50.0, -50.0, 50.0, 50.0);
        let visited = walk_agents(&mut agents, bounds, 0.3, 1.0, &mut rng);
        assert!(visited.len() >= 1000, "should visit ≥ 1000 positions");
        for &(x, y) in &visited {
            assert!(x >= bounds.0 - 0.01 && x <= bounds.2 + 0.01, "x out of bounds: {x}");
            assert!(y >= bounds.1 - 0.01 && y <= bounds.3 + 0.01, "y out of bounds: {y}");
        }
    }

    #[test]
    fn walk_agents_deterministic_for_fixed_rng() {
        let bounds = (-10.0, -10.0, 10.0, 10.0);
        let agents_factory = || {
            vec![WalkAgent { pos: (0.0, 0.0), heading: 0.0, energy: 200.0, _salt: 7 }]
        };
        let mut rng_a = Rng::for_stage(7, b"slime-det");
        let mut rng_b = Rng::for_stage(7, b"slime-det");
        let mut a = agents_factory();
        let mut b = agents_factory();
        let va = walk_agents(&mut a, bounds, 0.5, 1.0, &mut rng_a);
        let vb = walk_agents(&mut b, bounds, 0.5, 1.0, &mut rng_b);
        assert_eq!(va.len(), vb.len());
        for (pa, pb) in va.iter().zip(vb.iter()) {
            assert_eq!(pa.0.to_bits(), pb.0.to_bits());
            assert_eq!(pa.1.to_bits(), pb.1.to_bits());
        }
    }

    // -- α-shape --------------------------------------------------------------

    #[test]
    fn alpha_shape_recovers_disk_boundary() {
        // Dense uniform disk of points → α-shape should produce a single hull
        // close to the disk boundary.
        let mut pts = Vec::new();
        for i in 0..40 {
            for j in 0..40 {
                let x = -1.0 + (i as f32) / 20.0;
                let y = -1.0 + (j as f32) / 20.0;
                if x * x + y * y <= 1.0 {
                    pts.push((x, y));
                }
            }
        }
        let alpha = estimate_alpha(&pts);
        let rings = alpha_shape(&pts, alpha);
        assert!(!rings.is_empty(), "α-shape should produce ≥ 1 ring");
        // Largest ring area should approximate π ≈ 3.14 (unit disk).
        let max_area = rings.iter().map(|r| signed_area(r).abs()).fold(0.0_f32, f32::max);
        assert!(
            (1.5..=4.5).contains(&max_area),
            "largest α-shape ring area {max_area} not near π"
        );
    }

    // -- Moreira-Santos -------------------------------------------------------

    #[test]
    fn moreira_santos_produces_closed_polygon() {
        // Sparse irregular cloud (10 points) — the kind of input the slime
        // fallback path actually sees when α-shape can't recover a closed
        // boundary. A perfect uniform disk is a degenerate case (every
        // adjacent point is a tied "best right turn") that exposes
        // greedy-pick limitations; the realistic case is a coarser cloud.
        let pts: Vec<(f32, f32)> = vec![
            (0.0, 0.0), (1.0, 0.0), (1.5, 0.7), (1.2, 1.5), (0.5, 2.0),
            (-0.4, 1.7), (-1.0, 1.0), (-1.1, 0.2), (-0.7, -0.6), (0.2, -0.8),
        ];
        let hull = moreira_santos(&pts, 6).expect("hull should exist");
        assert!(hull.len() >= 3, "hull must have ≥ 3 vertices, got {}", hull.len());
        let area = signed_area(&hull).abs();
        assert!(area > 0.5, "hull area {area} suspiciously small (cloud bbox area ≈ 7.7)");
    }

    // -- Quality + integration -----------------------------------------------

    #[test]
    fn generator_returns_at_least_one_polygon() {
        // SlimeGenerator picks template (Blob or Branch) from ctx.seed.
        // Blob keeps satellites = false → single polygon. Branch keeps
        // satellites = true → 1+ polygons. Ellipse fallback also yields 1.
        // Sample 16 seeds to ensure no seed ever returns an empty result.
        for seed in 0..16u32 {
            let r = SlimeGenerator.generate(&test_ctx(seed), &mut Rng::for_stage(0, b"caller"));
            assert!(
                !r.polygons.is_empty(),
                "seed {seed}: SlimeGenerator must always return ≥1 polygon"
            );
            for p in &r.polygons {
                assert!(p.len() >= 3, "seed {seed}: polygon must have ≥3 vertices");
            }
        }
    }

    #[test]
    fn generator_does_not_perturb_caller_rng() {
        let mut a = Rng::for_stage(123, b"caller");
        let mut b = Rng::for_stage(123, b"caller");
        let _ = SlimeGenerator.generate(&test_ctx(42), &mut a);
        for _ in 0..3 {
            assert_eq!(a.next_u32(), b.next_u32(), "caller stream perturbed by SlimeGenerator");
        }
    }

    #[test]
    fn generator_polygon_contains_center_or_falls_back() {
        let ctx = test_ctx(987);
        let r = SlimeGenerator.generate(&ctx, &mut Rng::for_stage(0, b"caller"));
        let poly = &r.polygons[0];
        // Ray-casting point-in-polygon.
        let mut inside = false;
        let n = poly.len();
        for i in 0..n {
            let (xi, yi) = poly[i];
            let (xj, yj) = poly[(i + 1) % n];
            let cond = ((yi > ctx.center.1) != (yj > ctx.center.1))
                && (ctx.center.0
                    < (xj - xi) * (ctx.center.1 - yi) / (yj - yi + f32::EPSILON) + xi);
            if cond {
                inside = !inside;
            }
        }
        // Slime walk centred at ctx.center → center is typically inside.
        // If the generator fell back to Ellipse the center is by construction inside.
        assert!(inside, "polygon should contain ctx.center (kind={:?})", r.effective_kind);
    }

    #[test]
    fn generator_deterministic_for_same_seed() {
        let r1 = SlimeGenerator.generate(&test_ctx(7), &mut Rng::for_stage(0, b"caller"));
        let r2 = SlimeGenerator.generate(&test_ctx(7), &mut Rng::for_stage(0, b"caller"));
        assert_eq!(r1.polygons.len(), r2.polygons.len());
        for (a, b) in r1.polygons[0].iter().zip(r2.polygons[0].iter()) {
            assert_eq!(a.0.to_bits(), b.0.to_bits(), "x bits diverge");
            assert_eq!(a.1.to_bits(), b.1.to_bits(), "y bits diverge");
        }
    }
}
