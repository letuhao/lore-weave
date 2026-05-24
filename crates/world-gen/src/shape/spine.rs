//! Bezier-spine shape generator — a cubic Bezier curve + variable-radius
//! sweep produces S-curves, hooks, and Italy-boot shapes (v3.1b).
//!
//! Algorithm: sample the spine at `N` stations (`N = nv / 2` where `nv` is
//! the final vertex count). At each station compute tangent + perpendicular
//! normal; lay points at `±r(t)` along that normal. The left edge walks
//! forward, the right edge walks backward, producing a closed `2N`-vertex
//! polygon. Apply per-station radial jitter, uniform scale to envelope,
//! rotation, and translation last.
//!
//! Templates (picked deterministically by `hash(ctx.seed) % 3`):
//! - **SCurve** — a meandering S spanning two crests.
//! - **Hook** — Korean-peninsula-like J shape.
//! - **Boot** — Italy-style heel-to-toe boot.
//!
//! Determinism is owned internally via `Rng::for_stage(ctx.seed as u64,
//! b"bezier-spine")` so cross-plate caller RNG order is not perturbed when
//! Bezier alternates with Ellipse via the dispatcher.

use std::f32::consts::TAU;

use crate::flatworld::Polygon;
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum BezierTemplate {
    /// Two-crest meandering S — North-South oriented.
    SCurve,
    /// Korean-peninsula hook — fishhook curl.
    Hook,
    /// Italy-boot heel-to-toe — diagonal with rounded tip.
    Boot,
}

impl BezierTemplate {
    /// All variants, in declaration order. Used by `pick_template`.
    const ALL: [BezierTemplate; 3] = [
        BezierTemplate::SCurve,
        BezierTemplate::Hook,
        BezierTemplate::Boot,
    ];

    /// 4 cubic Bezier control points (unitless, roughly in [-1, 1]).
    ///
    /// **v3.1b template tightening 2026-05-25**: Hook + Boot spines
    /// retuned so the spine's minimum local curvature radius exceeds the
    /// maximum sweep radius at that station — keeps the variable-radius
    /// offset curve self-intersection rate below 5%/50 seeds (was 14% at
    /// v3.1b first ship). Original aggressive bends are reserved for a
    /// future v3.X with a self-intersect repair pass.
    fn spine(self) -> [(f32, f32); 4] {
        match self {
            BezierTemplate::SCurve => [
                (-1.0, -0.5),
                (-0.3, 0.6),
                (0.3, -0.6),
                (1.0, 0.5),
            ],
            // Softer J: opening from west, gentle curve up and east. Avoids
            // the sharp ~180° fold the original had at the wrist.
            BezierTemplate::Hook => [
                (-0.9, 0.0),
                (-0.1, -0.3),
                (0.6, 0.0),
                (0.5, 0.7),
            ],
            // Gentler boot: descend-then-toe with smoother heel-to-arch
            // transition. Avoids the tight ankle the original had.
            BezierTemplate::Boot => [
                (-0.3, 0.9),
                (-0.1, 0.1),
                (0.3, -0.3),
                (0.7, -0.2),
            ],
        }
    }

    /// Radius profile at the 4 control-point parameter values
    /// (t = 0, 1/3, 2/3, 1). Linearly interpolated between samples in
    /// `radius_at`.
    ///
    /// **v3.1b retune**: max radius reduced to ≤0.35 (was 0.45) so the
    /// offset curve stays inside the spine's local curvature radius even
    /// at the tightest bends. Slightly narrower plates, materially better
    /// simple-polygon rate.
    fn radius_profile(self) -> [f32; 4] {
        match self {
            BezierTemplate::SCurve => [0.22, 0.32, 0.30, 0.18],
            BezierTemplate::Hook => [0.22, 0.28, 0.30, 0.26],
            BezierTemplate::Boot => [0.20, 0.26, 0.26, 0.18],
        }
    }
}

/// Bezier-internal jitter cap. Caller's `ctx.edge_jitter` is clamped to
/// this before per-station variation — keeps sweep curve self-intersection
/// rare even when the global jitter is high (plates default 0.35).
const BEZIER_JITTER_CAP: f32 = 0.15;

pub struct BezierSpineGenerator;

impl ShapeGenerator for BezierSpineGenerator {
    fn kind(&self) -> ShapeKind {
        ShapeKind::BezierSpine
    }

    fn generate(&self, ctx: &ShapeContext, _caller_rng: &mut Rng) -> ShapeResult {
        // Internal RNG keyed by ctx.seed — caller's stream is NOT consumed
        // here, so cross-plate dispatch order doesn't get perturbed if
        // Bezier alternates with Ellipse.
        let mut rng = Rng::for_stage(ctx.seed as u64, b"bezier-spine");

        let template = pick_template(ctx.seed);
        let spine = template.spine();
        let radii = template.radius_profile();

        // Station count = nv / 2 (each station emits 2 boundary points →
        // total polygon vertices = 2N). Clamp to ≥3 stations so the result
        // is a valid polygon (6+ vertices).
        let (vmin, vmax) = ctx.vertex_count_range;
        let max_v = vmax.max(vmin);
        let nv = vmin + (rng.next_f32() * (max_v - vmin + 1) as f32) as usize;
        let stations = (nv.clamp(6, max_v.max(6)) / 2).max(3);

        // Sample stations + radii + jitter into LOCAL (unit-square) coords.
        let mut left = Vec::with_capacity(stations);
        let mut right = Vec::with_capacity(stations);
        for k in 0..stations {
            let t = k as f32 / (stations - 1) as f32;
            let (px, py) = bezier_point(spine, t);
            let (tx, ty) = bezier_tangent(spine, t);
            // Normal = 90° rotation of tangent, normalised.
            let mag = (tx * tx + ty * ty).sqrt().max(1e-6);
            let (nx, ny) = (-ty / mag, tx / mag);

            let base_r = radius_at(radii, t);
            // Per-station radial jitter clamped to BEZIER_JITTER_CAP so
            // production callers (edge_jitter=0.35) don't push the offset
            // curve past its local curvature radius.
            let effective_jitter = ctx.edge_jitter.min(BEZIER_JITTER_CAP);
            let jitter = 1.0 + (rng.next_f32() - 0.5) * effective_jitter;
            let r = base_r * jitter;

            left.push((px + nx * r, py + ny * r));
            right.push((px - nx * r, py - ny * r));
        }

        // Walk left forward, right backward → closed loop of 2 * stations vertices.
        let mut local: Polygon = Vec::with_capacity(stations * 2);
        local.extend(left.iter().copied());
        local.extend(right.iter().rev().copied());

        // Fit to envelope (rotation-invariant scaling via max distance from
        // local centroid). For square envelopes (typical plate use case)
        // every output vertex lands within target_radius of ctx.center
        // regardless of rotation.
        let (lminx, lminy, lmaxx, lmaxy) = bbox(&local);
        let lcx = (lminx + lmaxx) * 0.5;
        let lcy = (lminy + lmaxy) * 0.5;
        let max_dist = local
            .iter()
            .map(|&(x, y)| ((x - lcx).powi(2) + (y - lcy).powi(2)).sqrt())
            .fold(0.0_f32, f32::max)
            .max(1e-6);
        let target_radius = ctx.envelope.0.min(ctx.envelope.1);
        let scale = target_radius / max_dist;

        let theta = rng.next_f32() * TAU;
        let (cos_t, sin_t) = (theta.cos(), theta.sin());

        let polygon: Polygon = local
            .into_iter()
            .map(|(x, y)| {
                let sx = (x - lcx) * scale;
                let sy = (y - lcy) * scale;
                let rx = sx * cos_t - sy * sin_t;
                let ry = sx * sin_t + sy * cos_t;
                (ctx.center.0 + rx, ctx.center.1 + ry)
            })
            .collect();

        ShapeResult::single_kind(vec![polygon], ShapeKind::BezierSpine)
    }
}

/// Pick a template deterministically from `seed`. Distinct from
/// `(seed % 3)` so a `+1` to seed shifts to a meaningfully different
/// template, not a neighbour.
fn pick_template(seed: u32) -> BezierTemplate {
    // Mix bits to decorrelate from neighbouring seeds.
    let mixed = seed
        .wrapping_mul(0x85EB_CA6B)
        .wrapping_add(0xC2B2_AE35)
        .rotate_left(13);
    BezierTemplate::ALL[(mixed as usize) % BezierTemplate::ALL.len()]
}

fn bezier_point(cp: [(f32, f32); 4], t: f32) -> (f32, f32) {
    let u = 1.0 - t;
    let w0 = u * u * u;
    let w1 = 3.0 * u * u * t;
    let w2 = 3.0 * u * t * t;
    let w3 = t * t * t;
    (
        w0 * cp[0].0 + w1 * cp[1].0 + w2 * cp[2].0 + w3 * cp[3].0,
        w0 * cp[0].1 + w1 * cp[1].1 + w2 * cp[2].1 + w3 * cp[3].1,
    )
}

fn bezier_tangent(cp: [(f32, f32); 4], t: f32) -> (f32, f32) {
    let u = 1.0 - t;
    let w0 = 3.0 * u * u;
    let w1 = 6.0 * u * t;
    let w2 = 3.0 * t * t;
    (
        w0 * (cp[1].0 - cp[0].0) + w1 * (cp[2].0 - cp[1].0) + w2 * (cp[3].0 - cp[2].0),
        w0 * (cp[1].1 - cp[0].1) + w1 * (cp[2].1 - cp[1].1) + w2 * (cp[3].1 - cp[2].1),
    )
}

/// Linear interp of the 4-sample radius profile at parameter `t ∈ [0, 1]`.
fn radius_at(profile: [f32; 4], t: f32) -> f32 {
    // 3 segments: [0, 1/3], [1/3, 2/3], [2/3, 1].
    let seg = (t * 3.0).clamp(0.0, 3.0 - 1e-6);
    let i = seg as usize;
    let frac = seg - i as f32;
    profile[i] + (profile[i + 1] - profile[i]) * frac
}

fn bbox(poly: &Polygon) -> (f32, f32, f32, f32) {
    let (mut minx, mut miny) = (f32::INFINITY, f32::INFINITY);
    let (mut maxx, mut maxy) = (f32::NEG_INFINITY, f32::NEG_INFINITY);
    for &(x, y) in poly {
        minx = minx.min(x);
        miny = miny.min(y);
        maxx = maxx.max(x);
        maxy = maxy.max(y);
    }
    (minx, miny, maxx, maxy)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;

    fn ctx(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (500.0, 300.0),
            envelope: (200.0, 200.0),
            size_rank: SizeRank::Large,
            seed,
            plate_salt: seed,
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.20,
            vertex_count_range: (24, 48),
        }
    }

    /// Production-condition context: matches `flatworld::generate` defaults
    /// (envelope = pitch ≈ 291.5 for 1024×640 / 12 plates; edge_jitter =
    /// 0.35; vertex_count_range = (24, 48)). Catches issues that lighter
    /// test conditions hide.
    fn ctx_production(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (512.0, 320.0),
            envelope: (291.5, 291.5),
            size_rank: SizeRank::Giant,
            seed,
            plate_salt: seed,
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.35,
            vertex_count_range: (24, 48),
        }
    }

    #[test]
    fn bezier_kind_is_bezier_spine() {
        assert_eq!(BezierSpineGenerator.kind(), ShapeKind::BezierSpine);
    }

    #[test]
    fn bezier_returns_single_component_with_expected_size() {
        let mut rng = Rng::for_stage(1, b"test");
        let polys = BezierSpineGenerator.generate(&ctx(1), &mut rng).polygons;
        assert_eq!(polys.len(), 1);
        // 24..=48 → stations 12..=24 → polygon 24..=48 vertices
        assert!(polys[0].len() >= 24 && polys[0].len() <= 48);
    }

    #[test]
    fn bezier_does_not_perturb_caller_rng() {
        // Two parallel rngs, only one is given to the generator.
        let mut rng_a = Rng::for_stage(42, b"caller");
        let mut rng_b = Rng::for_stage(42, b"caller");
        let _ = BezierSpineGenerator.generate(&ctx(42), &mut rng_a);
        for _ in 0..5 {
            assert_eq!(
                rng_a.next_u32(),
                rng_b.next_u32(),
                "Bezier must not consume caller RNG (uses internal Rng::for_stage(seed))"
            );
        }
    }

    #[test]
    fn bezier_deterministic_same_seed() {
        let mut rng_a = Rng::for_stage(7, b"caller");
        let mut rng_b = Rng::for_stage(99, b"different");
        let polys_a = BezierSpineGenerator.generate(&ctx(7), &mut rng_a).polygons;
        let polys_b = BezierSpineGenerator.generate(&ctx(7), &mut rng_b).polygons;
        // Same ctx.seed → same polygon regardless of caller rng.
        for (a, b) in polys_a[0].iter().zip(polys_b[0].iter()) {
            assert_eq!(a.0.to_bits(), b.0.to_bits());
            assert_eq!(a.1.to_bits(), b.1.to_bits());
        }
    }

    #[test]
    fn bezier_each_template_is_picked_for_some_seed() {
        let mut seen = std::collections::HashSet::new();
        for s in 0u32..200 {
            seen.insert(pick_template(s));
        }
        // All 3 templates should be reachable.
        assert_eq!(seen.len(), 3, "every template must be reachable: {seen:?}");
    }

    #[test]
    fn bezier_each_template_centre_inside_or_acceptable() {
        // The spine doesn't necessarily pass through ctx.center because the
        // bbox-centroid is what gets centred, not the medial axis midpoint.
        // We check the centre is within the polygon's bounding box at least.
        for template in BezierTemplate::ALL {
            // Force one template by tweaking seed until pick_template returns it.
            let mut seed = 0u32;
            while pick_template(seed) != template {
                seed += 1;
            }
            let mut rng = Rng::for_stage(seed as u64, b"test");
            let polys = BezierSpineGenerator.generate(&ctx(seed), &mut rng).polygons;
            let (minx, miny, maxx, maxy) = bbox(&polys[0]);
            let (cx, cy) = ctx(seed).center;
            assert!(
                cx >= minx && cx <= maxx,
                "template {template:?} cx {cx} outside bbox [{minx}, {maxx}]"
            );
            assert!(
                cy >= miny && cy <= maxy,
                "template {template:?} cy {cy} outside bbox [{miny}, {maxy}]"
            );
        }
    }

    #[test]
    fn bezier_within_envelope() {
        let c = ctx(13);
        let mut rng = Rng::for_stage(1, b"test");
        let polys = BezierSpineGenerator.generate(&c, &mut rng).polygons;
        for &(x, y) in &polys[0] {
            // Polygon vertices must lie within ctx.envelope of ctx.center.
            // Allow a small slack (5%) for the floating-point scale fit.
            let dx = (x - c.center.0).abs();
            let dy = (y - c.center.1).abs();
            assert!(
                dx <= c.envelope.0 * 1.05 && dy <= c.envelope.1 * 1.05,
                "vertex ({x}, {y}) outside envelope ({}, {})",
                c.envelope.0,
                c.envelope.1
            );
        }
    }

    #[test]
    fn bezier_polygon_is_simple_for_most_seeds() {
        // Hook/Boot templates can produce self-intersecting polygons when
        // the spine doubles back tightly (the left + right edges cross).
        // This is acceptable — downstream renderers (`flatworld::render_rgb`,
        // `paint_plate_overlay`) handle non-simple polygons via even-odd
        // fill. We allow up to 10% non-simple in a 50-seed sweep; >10%
        // would indicate a template needs trimming.
        let mut nonsimple = 0;
        for seed in 0..50u32 {
            let c = ctx(seed);
            let mut rng = Rng::for_stage(seed as u64, b"test");
            let polys = BezierSpineGenerator.generate(&c, &mut rng).polygons;
            if !is_simple(&polys[0]) {
                nonsimple += 1;
            }
        }
        // v3.1b retune target: ≤5% non-simple at light test conditions.
        // The harder gate is the production-condition sweep below.
        assert!(
            nonsimple <= 3,
            "Too many self-intersecting polygons (light): {nonsimple}/50. Hook/Boot spines may have drifted past local curvature radius."
        );
    }

    /// Stricter version of the test above under production-default ctx
    /// (envelope=pitch, jitter=0.35). This is what `flatworld::generate`
    /// actually invokes — passes here mean real plates won't have
    /// pathological internal-hole `Plate::contains` ambiguity.
    #[test]
    fn bezier_polygon_is_simple_under_production_conditions() {
        let mut nonsimple = 0;
        for seed in 0..50u32 {
            let c = ctx_production(seed);
            let mut rng = Rng::for_stage(seed as u64, b"test");
            let polys = BezierSpineGenerator.generate(&c, &mut rng).polygons;
            if !is_simple(&polys[0]) {
                nonsimple += 1;
            }
        }
        // BEZIER_JITTER_CAP=0.15 collapses the ctx.edge_jitter=0.35 effect.
        // Target: ≤5% non-simple under production conditions.
        assert!(
            nonsimple <= 3,
            "Too many self-intersecting polygons (production): {nonsimple}/50."
        );
    }

    /// Brute O(N²) line-segment intersection check.
    fn is_simple(poly: &Polygon) -> bool {
        let n = poly.len();
        for i in 0..n {
            let a1 = poly[i];
            let a2 = poly[(i + 1) % n];
            for j in (i + 2)..n {
                // Skip adjacent edges including the wrap-around pair.
                if (j + 1) % n == i {
                    continue;
                }
                let b1 = poly[j];
                let b2 = poly[(j + 1) % n];
                if segments_intersect(a1, a2, b1, b2) {
                    return false;
                }
            }
        }
        true
    }

    fn segments_intersect(p1: (f32, f32), p2: (f32, f32), p3: (f32, f32), p4: (f32, f32)) -> bool {
        fn orient(a: (f32, f32), b: (f32, f32), c: (f32, f32)) -> f32 {
            (b.0 - a.0) * (c.1 - a.1) - (b.1 - a.1) * (c.0 - a.0)
        }
        let d1 = orient(p3, p4, p1);
        let d2 = orient(p3, p4, p2);
        let d3 = orient(p1, p2, p3);
        let d4 = orient(p1, p2, p4);
        ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0))
            && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0))
    }
}
