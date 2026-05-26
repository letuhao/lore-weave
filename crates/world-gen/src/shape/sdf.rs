//! SDF capsule chain + smooth-min shape generator (v3.2).
//!
//! Builds a continent silhouette by blending N capsule SDFs with a polynomial
//! smooth-minimum (Quílez). Four templates produce visibly distinct topologies
//! no spline-based algorithm can match cleanly:
//!
//! - [`CapsuleTemplate::YBranch`]  — 3 arms meeting at one joint (Y-shape).
//! - [`CapsuleTemplate::ZZigzag`]  — 4 capsules in alternating zig-zag.
//! - [`CapsuleTemplate::CrabRadial`] — 5 arms radiating from a centre (crab/starfish).
//! - [`CapsuleTemplate::WormChain`] — 6 capsules in slight curving chain.
//!
//! Determinism: internal `Rng::for_stage(ctx.seed as u64, b"sdf-capsule-chain")`
//! owns all randomness (template index, rotation, per-joint jitter) so the
//! caller's RNG stream is not perturbed — consistent with [`super::spine`] /
//! [`super::polar`] / [`super::csg`] discipline.
//!
//! RNG order (FROZEN — do not reorder):
//! 1. `rng.next_u32() % 4` → template index
//! 2. `rng.next_f32() × TAU` → global rotation
//! 3. per-joint jitter: 2 `next_f32()` per joint (dx, dy)
//! 4. (passed to [`super::raster::field_to_polygon`] which may consume more
//!    on saddle tiebreaks)

use std::f32::consts::TAU;

use crate::rng::Rng;

use super::raster::field_to_polygon;
use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};

/// Capsule chain topology. 4 hand-tuned variants for v3.2.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum CapsuleTemplate {
    YBranch,
    ZZigzag,
    CrabRadial,
    WormChain,
}

impl CapsuleTemplate {
    const ALL: [CapsuleTemplate; 4] = [
        CapsuleTemplate::YBranch,
        CapsuleTemplate::ZZigzag,
        CapsuleTemplate::CrabRadial,
        CapsuleTemplate::WormChain,
    ];

    /// Stable string tag (for logs + per-template eval breakdown).
    pub fn as_str(self) -> &'static str {
        match self {
            CapsuleTemplate::YBranch => "YBranch",
            CapsuleTemplate::ZZigzag => "ZZigzag",
            CapsuleTemplate::CrabRadial => "CrabRadial",
            CapsuleTemplate::WormChain => "WormChain",
        }
    }

    /// Joints in unit-envelope space (will be scaled + rotated + translated
    /// at generate-time). All joints stay in roughly `[-1, 1]²`.
    fn joints(self) -> Vec<(f32, f32)> {
        match self {
            // Y-branch — centre + 3 arms at 90° (north), 210°, 330°.
            CapsuleTemplate::YBranch => vec![
                (0.0, 0.0),
                (0.0, 0.9),
                (-0.78, -0.45),
                (0.78, -0.45),
            ],
            // Z-zigzag — 4 joints W→E with up/down alternation.
            CapsuleTemplate::ZZigzag => vec![
                (-0.9, 0.3),
                (-0.3, -0.3),
                (0.3, 0.3),
                (0.9, -0.3),
            ],
            // Crab-radial — centre + 5 arms at 72° spacing.
            CapsuleTemplate::CrabRadial => vec![
                (0.0, 0.0),
                (0.0, 0.85),
                (0.81, 0.26),
                (0.50, -0.69),
                (-0.50, -0.69),
                (-0.81, 0.26),
            ],
            // Worm-chain — 7 joints in slight curve.
            CapsuleTemplate::WormChain => vec![
                (-1.0, 0.1),
                (-0.65, -0.1),
                (-0.3, 0.1),
                (0.0, -0.05),
                (0.3, 0.1),
                (0.65, -0.1),
                (1.0, 0.1),
            ],
        }
    }

    /// Edge list (each capsule = segment between two joint indices).
    fn edges(self) -> Vec<(usize, usize)> {
        match self {
            CapsuleTemplate::YBranch => vec![(0, 1), (0, 2), (0, 3)],
            CapsuleTemplate::ZZigzag => vec![(0, 1), (1, 2), (2, 3)],
            CapsuleTemplate::CrabRadial => vec![(0, 1), (0, 2), (0, 3), (0, 4), (0, 5)],
            CapsuleTemplate::WormChain => vec![(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)],
        }
    }

    /// Per-capsule radii in unit-envelope space.
    fn radii(self) -> Vec<f32> {
        match self {
            CapsuleTemplate::YBranch => vec![0.30, 0.25, 0.25],
            CapsuleTemplate::ZZigzag => vec![0.20, 0.20, 0.20],
            CapsuleTemplate::CrabRadial => vec![0.22, 0.20, 0.20, 0.20, 0.22],
            CapsuleTemplate::WormChain => vec![0.18, 0.18, 0.18, 0.18, 0.18, 0.18],
        }
    }

    /// Smooth-min strength `k` in unit-envelope space (scaled at generate-time).
    /// Higher k → smoother blend but more bulge at acute angles. Tuned per spec §8 risk #4.
    fn smin_k(self) -> f32 {
        match self {
            CapsuleTemplate::YBranch => 0.15,
            CapsuleTemplate::ZZigzag => 0.10,
            CapsuleTemplate::CrabRadial => 0.20,
            CapsuleTemplate::WormChain => 0.08,
        }
    }
}

/// Signed distance from point `p` to capsule defined by endpoints `a, b` and
/// radius `r`. Standard capsule SDF.
fn sdf_capsule(p: (f32, f32), a: (f32, f32), b: (f32, f32), r: f32) -> f32 {
    let ba = (b.0 - a.0, b.1 - a.1);
    let pa = (p.0 - a.0, p.1 - a.1);
    let dot_ba = ba.0 * ba.0 + ba.1 * ba.1;
    if dot_ba < 1e-12 {
        // Degenerate capsule (a == b) — reduces to a disk SDF.
        return (pa.0 * pa.0 + pa.1 * pa.1).sqrt() - r;
    }
    let t = ((pa.0 * ba.0 + pa.1 * ba.1) / dot_ba).clamp(0.0, 1.0);
    let proj = (a.0 + t * ba.0, a.1 + t * ba.1);
    ((p.0 - proj.0).powi(2) + (p.1 - proj.1).powi(2)).sqrt() - r
}

/// Polynomial smooth minimum (Quílez):
/// <https://iquilezles.org/articles/smin/>
fn smin_poly(d1: f32, d2: f32, k: f32) -> f32 {
    if k.abs() < 1e-9 {
        return d1.min(d2);
    }
    let h = (0.5 + 0.5 * (d2 - d1) / k).clamp(0.0, 1.0);
    d2 * (1.0 - h) + d1 * h - k * h * (1.0 - h)
}

pub struct SdfCapsuleChainGenerator;

impl ShapeGenerator for SdfCapsuleChainGenerator {
    fn kind(&self) -> ShapeKind {
        ShapeKind::SdfCapsuleChain
    }

    fn generate(&self, ctx: &ShapeContext, _caller_rng: &mut Rng) -> ShapeResult {
        // Internal RNG — keeps caller stream invariant.
        let mut rng = Rng::for_stage(ctx.seed as u64, b"sdf-capsule-chain");

        // 1. Template index.
        let template = CapsuleTemplate::ALL[(rng.next_u32() % 4) as usize];
        // 2. Global rotation.
        let rotation = rng.next_f32() * TAU;
        let cos_r = rotation.cos();
        let sin_r = rotation.sin();

        // Per-rank scale of unit-space joints.
        let (rmin, rmax) = ctx.size_rank.radius_band();
        let scale = ctx.envelope.0 * (rmin + rmax) * 0.5;

        let joints_unit = template.joints();
        let radii_unit = template.radii();
        let edges = template.edges();

        // 3. Per-joint micro-jitter + transform to world space.
        let joints_world: Vec<(f32, f32)> = joints_unit
            .iter()
            .map(|&(jx, jy)| {
                let dx = (rng.next_f32() - 0.5) * 0.1;
                let dy = (rng.next_f32() - 0.5) * 0.1;
                let jx_j = jx + dx;
                let jy_j = jy + dy;
                let rx = jx_j * cos_r - jy_j * sin_r;
                let ry = jx_j * sin_r + jy_j * cos_r;
                (ctx.center.0 + rx * scale, ctx.center.1 + ry * scale)
            })
            .collect();
        let radii_world: Vec<f32> = radii_unit.iter().map(|r| r * scale).collect();
        let smin_k_world = template.smin_k() * scale;

        // Build capsule list owned by the closure.
        type Capsule = ((f32, f32), (f32, f32), f32);
        let capsules: Vec<Capsule> = edges
            .iter()
            .enumerate()
            .map(|(i, &(a, b))| (joints_world[a], joints_world[b], radii_world[i]))
            .collect();

        let field = move |p: (f32, f32)| -> f32 {
            // Start from a large value; smooth-min progressively merges capsules.
            capsules.iter().fold(1.0e6_f32, |acc, &(a, b, r)| {
                smin_poly(acc, sdf_capsule(p, a, b, r), smin_k_world)
            })
        };

        // BBox margin = scale + capsule radii max — must be wide enough that
        // capsule contours (up to ~1.15 × scale from centre at template-max
        // joint + radius) fit inside. Use envelope × 1.5 as conservative margin.
        let bbox_half = ctx.envelope.0.max(scale * 1.3);
        let bbox = (
            ctx.center.0 - bbox_half,
            ctx.center.1 - bbox_half,
            ctx.center.0 + bbox_half,
            ctx.center.1 + bbox_half,
        );
        // Vertex-count range — same band as Ellipse / Bezier / Polar. Use
        // the shape-preserving fit (re-DP + edge subdivision) instead of
        // arc-length resampling so concave corners on Y / Crab / Z templates
        // survive the count-clamp step.
        let range = (ctx.vertex_count_range.0.max(3), ctx.vertex_count_range.1.max(ctx.vertex_count_range.0));
        let poly = field_to_polygon(
            field, bbox, 0.0, 256, 2, 0.005, &mut rng, ctx.center, Some(range),
        );
        ShapeResult::single_kind(vec![poly], ShapeKind::SdfCapsuleChain)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;

    fn test_ctx(seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (100.0, 100.0),
            envelope: (50.0, 50.0),
            size_rank: SizeRank::Medium,
            seed,
            plate_salt: 0x0BAD_F00D,
            parent_path: vec![],
            world_theme: None,
            edge_jitter: 0.0,
            vertex_count_range: (24, 96),
        }
    }

    // -- SDF math primitives --------------------------------------------------

    #[test]
    fn capsule_sdf_zero_at_endpoint_minus_radius() {
        // sdf_capsule at endpoint a is -r (we're on the surface boundary
        // if r==0, inside by r otherwise).
        let d = sdf_capsule((0.0, 0.0), (0.0, 0.0), (10.0, 0.0), 1.0);
        assert!((d - (-1.0)).abs() < 1e-5, "expected -1.0, got {d}");
    }

    #[test]
    fn capsule_sdf_radius_at_perpendicular_distance() {
        // Point at (5, 5) — perpendicular distance from segment ((0,0)-(10,0))
        // is 5. With r=1, SDF should be 5 - 1 = 4.
        let d = sdf_capsule((5.0, 5.0), (0.0, 0.0), (10.0, 0.0), 1.0);
        assert!((d - 4.0).abs() < 1e-5, "expected 4.0, got {d}");
    }

    #[test]
    fn capsule_sdf_degenerate_endpoint_returns_disk_sdf() {
        // a == b: SDF should be |p - a| - r.
        let d = sdf_capsule((3.0, 4.0), (0.0, 0.0), (0.0, 0.0), 1.0);
        assert!((d - 4.0).abs() < 1e-5, "expected 4.0 (disk), got {d}");
    }

    #[test]
    fn smin_poly_at_extremes_matches_min() {
        // smin_poly with k=0 reduces to min.
        let d = smin_poly(0.0, 10.0, 0.0);
        assert!(d.abs() < 1e-5, "expected ~0.0, got {d}");
        // Equal values: smin is slightly less than common value (subtract k/4 ≈ peak smoothing).
        let d2 = smin_poly(0.0, 0.0, 0.1);
        assert!(d2 < 0.0 && d2 > -0.05, "expected slightly negative, got {d2}");
    }

    // -- Generator integration ------------------------------------------------

    fn assert_polygon_contains(poly: &[(f32, f32)], point: (f32, f32)) -> bool {
        // Ray casting — count crossings.
        let mut inside = false;
        let n = poly.len();
        for i in 0..n {
            let (xi, yi) = poly[i];
            let (xj, yj) = poly[(i + 1) % n];
            let cond = ((yi > point.1) != (yj > point.1))
                && (point.0
                    < (xj - xi) * (point.1 - yi) / (yj - yi + f32::EPSILON) + xi);
            if cond {
                inside = !inside;
            }
        }
        inside
    }

    #[test]
    fn all_four_templates_produce_centre_containing_polygon() {
        // Force each template by re-seeding to hit each index. We cycle a
        // seed range until all 4 templates appear at least once; assert
        // each one's output contains ctx.center.
        let mut seen = [false; 4];
        let mut tested = [false; 4];
        for seed in 0..200u32 {
            let mut probe_rng = Rng::for_stage(seed as u64, b"sdf-capsule-chain");
            let tmpl_idx = (probe_rng.next_u32() % 4) as usize;
            if seen[tmpl_idx] {
                continue;
            }
            seen[tmpl_idx] = true;
            let gen_ = SdfCapsuleChainGenerator;
            let result = gen_.generate(&test_ctx(seed), &mut Rng::for_stage(0, b"caller"));
            assert_eq!(result.polygons.len(), 1, "single-component invariant");
            let poly = &result.polygons[0];
            assert!(
                assert_polygon_contains(poly, (100.0, 100.0)),
                "template {tmpl_idx} (seed {seed}) does not contain ctx.center"
            );
            tested[tmpl_idx] = true;
            if tested.iter().all(|x| *x) {
                break;
            }
        }
        for (i, t) in tested.iter().enumerate() {
            assert!(*t, "template index {i} was never tested");
        }
    }

    #[test]
    fn sdf_generator_deterministic_same_ctx() {
        let gen_ = SdfCapsuleChainGenerator;
        let mut rng_a = Rng::for_stage(0, b"caller");
        let mut rng_b = Rng::for_stage(0, b"caller");
        let ra = gen_.generate(&test_ctx(42), &mut rng_a);
        let rb = gen_.generate(&test_ctx(42), &mut rng_b);
        assert_eq!(ra.polygons[0].len(), rb.polygons[0].len());
        for (a, b) in ra.polygons[0].iter().zip(rb.polygons[0].iter()) {
            assert_eq!(a.0.to_bits(), b.0.to_bits());
            assert_eq!(a.1.to_bits(), b.1.to_bits());
        }
        assert_eq!(ra.effective_kind, ShapeKind::SdfCapsuleChain);
    }

    #[test]
    fn sdf_generator_does_not_perturb_caller_rng() {
        let gen_ = SdfCapsuleChainGenerator;
        let mut caller_a = Rng::for_stage(7, b"caller");
        let mut caller_b = Rng::for_stage(7, b"caller");
        let _ = gen_.generate(&test_ctx(99), &mut caller_a);
        // caller_a should still match caller_b on the next draw.
        assert_eq!(caller_a.next_u32(), caller_b.next_u32());
    }
}
