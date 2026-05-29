//! Polar / superformula shape generator — closed curves expressed in polar
//! coordinates (`r(θ)`). Produces stars, cardioids, roses, and ovals (v3.1b).
//!
//! Algorithm: sample `N = nv` angles around `[0, TAU)`; compute `r(θ)` per
//! template; emit `(r·cosθ, r·sinθ)` in local coords; apply per-vertex
//! radial jitter; uniform-scale to envelope; rotate; translate to ctx.center.
//!
//! Templates (picked deterministically by `hash(ctx.seed) % 4`):
//! - **Pentagon** — superformula m=5, n1=n2=n3=10 → rounded pentagon.
//! - **Cardioid** — `r(θ) = 1 + cos(θ)` → heart shape.
//! - **Rose** — `r(θ) = |cos(2θ)|` → 4-petal rose (rare; weight ≤ 0.10 in
//!   v3.1b dispatch table).
//! - **Oval** — superformula m=2, n1=n2=n3=2 → near-ellipse fallback.
//!
//! Self-intersect guard: after assembly we winding-check; if non-simple,
//! retry up to 3× with `edge_jitter * 0.5`; final fallback is Oval.
//!
//! Determinism via `Rng::for_stage(ctx.seed as u64, b"polar")` (independent
//! of caller stream — same rationale as `spine.rs`).

use std::f32::consts::TAU;

use crate::flatworld::Polygon;
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum PolarTemplate {
    Pentagon,
    Cardioid,
    Rose,
    Oval,
}

impl PolarTemplate {
    const ALL: [PolarTemplate; 4] = [
        PolarTemplate::Pentagon,
        PolarTemplate::Cardioid,
        PolarTemplate::Rose,
        PolarTemplate::Oval,
    ];

    fn radius(self, theta: f32) -> f32 {
        match self {
            PolarTemplate::Pentagon => superformula(theta, 5.0, 10.0, 10.0, 10.0),
            PolarTemplate::Cardioid => 0.5 * (1.0 + theta.cos()),
            // |cos(2θ)| keeps r ≥ 0 (raw cos would produce a degenerate
            // self-touching curve at zero crossings).
            PolarTemplate::Rose => (theta * 2.0).cos().abs(),
            PolarTemplate::Oval => superformula(theta, 2.0, 2.0, 2.0, 2.0),
        }
    }
}

/// Superformula: `r(θ) = ( |cos(m·θ/4)|^n2 + |sin(m·θ/4)|^n3 )^(-1/n1)`.
/// Symmetric special case (a = b = 1).
fn superformula(theta: f32, m: f32, n1: f32, n2: f32, n3: f32) -> f32 {
    let phi = m * theta / 4.0;
    let cos_term = phi.cos().abs().powf(n2);
    let sin_term = phi.sin().abs().powf(n3);
    (cos_term + sin_term).powf(-1.0 / n1).clamp(0.0, 10.0)
}

pub struct PolarGenerator;

impl ShapeGenerator for PolarGenerator {
    fn kind(&self) -> ShapeKind {
        ShapeKind::Polar
    }

    fn generate(&self, ctx: &ShapeContext, _caller_rng: &mut Rng) -> ShapeResult {
        let mut rng = Rng::for_stage(ctx.seed as u64, b"polar");

        let initial_template = pick_template(ctx.seed);
        let (vmin, vmax) = ctx.vertex_count_range;
        let max_v = vmax.max(vmin);
        let nv = (vmin + (rng.next_f32() * (max_v - vmin + 1) as f32) as usize)
            .clamp(8, max_v.max(8));
        let theta_rot = rng.next_f32() * TAU;

        // Pre-draw jitter values so retry attempts use the same baseline RNG state
        // (deterministic re-roll with diminishing jitter).
        let base_jitter_seq: Vec<f32> = (0..nv).map(|_| rng.next_f32()).collect();

        for attempt in 0..3 {
            let template = if attempt == 2 {
                PolarTemplate::Oval // Fallback after 2 failed retries.
            } else {
                initial_template
            };
            let jitter_scale = ctx.edge_jitter * 0.5f32.powi(attempt);

            let local = build_local(template, nv, &base_jitter_seq, jitter_scale);
            if is_simple_polygon(&local) {
                return ShapeResult::single_kind(
                    vec![fit_to_envelope(&local, ctx, theta_rot)],
                    ShapeKind::Polar,
                );
            }
        }
        // Hard fallback: zero-jitter Oval — guaranteed simple. Still
        // ShapeKind::Polar because Oval IS a Polar template.
        let local = build_local(PolarTemplate::Oval, nv, &base_jitter_seq, 0.0);
        ShapeResult::single_kind(
            vec![fit_to_envelope(&local, ctx, theta_rot)],
            ShapeKind::Polar,
        )
    }
}

fn pick_template(seed: u32) -> PolarTemplate {
    let mixed = seed
        .wrapping_mul(0x27D4_EB2F)
        .wrapping_add(0x1656_67B1)
        .rotate_left(11);
    PolarTemplate::ALL[(mixed as usize) % PolarTemplate::ALL.len()]
}

fn build_local(
    template: PolarTemplate,
    nv: usize,
    jitter_seq: &[f32],
    jitter_scale: f32,
) -> Polygon {
    (0..nv)
        .map(|k| {
            let theta = TAU * (k as f32) / (nv as f32);
            let base_r = template.radius(theta);
            // ±jitter_scale/2 multiplicative jitter; keep r ≥ tiny positive.
            let jitter = 1.0 + (jitter_seq[k] - 0.5) * jitter_scale;
            let r = (base_r * jitter).max(1e-4);
            (r * theta.cos(), r * theta.sin())
        })
        .collect()
}

fn fit_to_envelope(local: &Polygon, ctx: &ShapeContext, theta_rot: f32) -> Polygon {
    // Rotation-invariant max-radius scaling — see spine.rs.
    let (mut minx, mut miny) = (f32::INFINITY, f32::INFINITY);
    let (mut maxx, mut maxy) = (f32::NEG_INFINITY, f32::NEG_INFINITY);
    for &(x, y) in local {
        minx = minx.min(x);
        miny = miny.min(y);
        maxx = maxx.max(x);
        maxy = maxy.max(y);
    }
    let lcx = (minx + maxx) * 0.5;
    let lcy = (miny + maxy) * 0.5;
    let max_dist = local
        .iter()
        .map(|&(x, y)| ((x - lcx).powi(2) + (y - lcy).powi(2)).sqrt())
        .fold(0.0_f32, f32::max)
        .max(1e-6);
    let target_radius = ctx.envelope.0.min(ctx.envelope.1);
    let scale = target_radius / max_dist;

    let cos_t = theta_rot.cos();
    let sin_t = theta_rot.sin();

    local
        .iter()
        .map(|&(x, y)| {
            let sx = (x - lcx) * scale;
            let sy = (y - lcy) * scale;
            let rx = sx * cos_t - sy * sin_t;
            let ry = sx * sin_t + sy * cos_t;
            (ctx.center.0 + rx, ctx.center.1 + ry)
        })
        .collect()
}

/// O(N²) simple-polygon check via edge-pair intersection. Fine for nv ≤ 100.
fn is_simple_polygon(poly: &Polygon) -> bool {
    let n = poly.len();
    if n < 4 {
        return true;
    }
    for i in 0..n {
        let a1 = poly[i];
        let a2 = poly[(i + 1) % n];
        for j in (i + 2)..n {
            if (j + 1) % n == i {
                continue;
            }
            if segments_intersect(a1, a2, poly[j], poly[(j + 1) % n]) {
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;

    fn ctx(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (500.0, 300.0),
            envelope: (180.0, 180.0),
            size_rank: SizeRank::Medium,
            seed,
            plate_salt: seed,
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.15,
            vertex_count_range: (32, 48),
            params: None,
        }
    }

    /// Production-condition ctx (envelope=pitch, jitter=0.35) — matches
    /// `flatworld::generate` defaults.
    fn ctx_production(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (512.0, 320.0),
            envelope: (291.5, 291.5),
            size_rank: SizeRank::Medium,
            seed,
            plate_salt: seed,
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.35,
            vertex_count_range: (24, 48),
            params: None,
        }
    }

    #[test]
    fn polar_kind_is_polar() {
        assert_eq!(PolarGenerator.kind(), ShapeKind::Polar);
    }

    #[test]
    fn polar_does_not_perturb_caller_rng() {
        let mut rng_a = Rng::for_stage(1, b"caller");
        let mut rng_b = Rng::for_stage(1, b"caller");
        let _ = PolarGenerator.generate(&ctx(1), &mut rng_a);
        for _ in 0..5 {
            assert_eq!(rng_a.next_u32(), rng_b.next_u32());
        }
    }

    #[test]
    fn polar_deterministic_same_seed() {
        let mut rng_a = Rng::for_stage(1, b"a");
        let mut rng_b = Rng::for_stage(99, b"different");
        let a = PolarGenerator.generate(&ctx(7), &mut rng_a).polygons;
        let b = PolarGenerator.generate(&ctx(7), &mut rng_b).polygons;
        for (p, q) in a[0].iter().zip(b[0].iter()) {
            assert_eq!(p.0.to_bits(), q.0.to_bits());
            assert_eq!(p.1.to_bits(), q.1.to_bits());
        }
    }

    #[test]
    fn polar_each_template_reachable() {
        let mut seen = std::collections::HashSet::new();
        for s in 0u32..400 {
            seen.insert(pick_template(s));
        }
        assert_eq!(seen.len(), 4, "every PolarTemplate must be reachable");
    }

    #[test]
    fn polar_all_templates_produce_simple_polygon_at_low_jitter() {
        // Test each template by forcing it through pick_template + seed sweep.
        for target in PolarTemplate::ALL {
            let mut seed = 0u32;
            while pick_template(seed) != target {
                seed += 1;
            }
            let c = ctx(seed);
            let mut rng = Rng::for_stage(seed as u64, b"caller");
            let polys = PolarGenerator.generate(&c, &mut rng).polygons;
            assert_eq!(polys.len(), 1);
            assert!(
                is_simple_polygon(&polys[0]),
                "{target:?} (seed {seed}) produced non-simple polygon"
            );
        }
    }

    #[test]
    fn polar_within_envelope() {
        for seed in 0..20u32 {
            let c = ctx(seed);
            let mut rng = Rng::for_stage(seed as u64, b"caller");
            let polys = PolarGenerator.generate(&c, &mut rng).polygons;
            for &(x, y) in &polys[0] {
                let dx = (x - c.center.0).abs();
                let dy = (y - c.center.1).abs();
                assert!(
                    dx <= c.envelope.0 * 1.05 && dy <= c.envelope.1 * 1.05,
                    "seed {seed}: vertex outside envelope"
                );
            }
        }
    }

    #[test]
    fn polar_simple_polygon_under_production_conditions() {
        // Polar self-intersect guard should keep all output simple under
        // production jitter (0.35) — retry-with-half-jitter + Oval fallback.
        for seed in 0..50u32 {
            let c = ctx_production(seed);
            let mut rng = Rng::for_stage(seed as u64, b"caller");
            let polys = PolarGenerator.generate(&c, &mut rng).polygons;
            assert!(
                is_simple_polygon(&polys[0]),
                "seed {seed}: Polar produced self-intersecting polygon under production jitter"
            );
        }
    }

    #[test]
    fn cardioid_has_dimple_at_pi() {
        // Cardioid r(π) ≈ 0, r(0) ≈ 1 — distinctive shape.
        let r0 = PolarTemplate::Cardioid.radius(0.0);
        let r_pi = PolarTemplate::Cardioid.radius(std::f32::consts::PI);
        assert!(r0 > 0.9 && r_pi < 0.1);
    }

    #[test]
    fn pentagon_has_5_radial_extrema() {
        // Superformula m=5 → 5 maxima in [0, 2π).
        let samples: Vec<f32> = (0..360)
            .map(|d| {
                let theta = (d as f32) * std::f32::consts::PI / 180.0;
                PolarTemplate::Pentagon.radius(theta)
            })
            .collect();
        let mut maxima = 0;
        for i in 0..360 {
            let prev = samples[(i + 359) % 360];
            let curr = samples[i];
            let next = samples[(i + 1) % 360];
            if curr > prev && curr > next {
                maxima += 1;
            }
        }
        // Allow 5 ± 0 (clean superformula).
        assert_eq!(maxima, 5, "Pentagon should have 5 maxima, got {maxima}");
    }
}
