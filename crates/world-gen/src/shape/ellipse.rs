//! Ellipse shape generator — the v3.0 anisotropic ellipsoid + multi-octave
//! fbm warp extracted into a [`super::ShapeGenerator`] impl.
//!
//! **Bit-identical contract:** the body of [`EllipseGenerator::generate`] is
//! a verbatim port of the per-plate vertex closure that lived in
//! `flatworld::generate` (v3.0 commit `f022cf82`, lines 488–565). RNG calls
//! happen in the same order and the math is the same, so a `FlatWorld`
//! produced via this generator hashes byte-identical to the v3.0 baseline
//! at the same seed. The byte-identical snapshot test in
//! `flatworld::tests::v3_0_byte_identical_seeds_*` pins this.
//!
//! ## RNG consumption contract
//!
//! Per call to [`EllipseGenerator::generate`], `rng` is consumed exactly:
//! `4 + 2 * nv` `next_f32` calls — 4 setup draws (radius, aspect,
//! theta_rot, nv, phase — wait, that's 5 setup draws; see below) and 2
//! per-vertex draws (wobble + residual). Counted precisely:
//!
//! | Step | `next_f32` calls |
//! |------|-----------------:|
//! | radius (`lerp(rmin, rmax, t)`)     | 1 |
//! | aspect (`lerp(amin, amax, t)`)     | 1 |
//! | theta_rot (`* TAU`)                | 1 |
//! | nv (sample int from float)         | 1 |
//! | phase (`* TAU`)                    | 1 |
//! | per-vertex wobble (× nv)           | nv |
//! | per-vertex residual (× nv)         | nv |
//! | **Total**                          | **`5 + 2 * nv`** |
//!
//! `ellipse_rng_consumes_known_count` test pins this exact count.

use std::f32::consts::TAU;

use crate::flatworld::Polygon;
use crate::noise::lerp;
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};

// ── V1 Phase A polygon-realism constants (preserved verbatim from v3.0) ─────
//
// EDGE_NOISE_AMP=0.30 keeps r in roughly [0.7·radius, 1.3·radius] (fbm range
// ~±0.71 × 0.30 = ±0.21 on the (1 + …) scale) — visibly more organic than the
// old smooth octagons, small enough to keep the climate eval composite stable
// (~±1pt). EDGE_NOISE_FREQ=1.5 + 3 octaves gives ~4-6 main lobes per plate
// perimeter at octave 1 (continent-scale capes/bays).
//
// JITTER_RESIDUAL_SCALE: per-vertex random shrink kept at 0.10 (the spec's
// "small residual jitter for character"); a `shrink_bias` compensator inside
// `generate` keeps E[r] unchanged so the land:ocean ratio (and climate eval)
// stays stable.
const EDGE_NOISE_AMP: f32 = 0.30;
const EDGE_NOISE_FREQ: f32 = 1.5;
const EDGE_NOISE_OCTAVES: u32 = 3;
const JITTER_RESIDUAL_SCALE: f32 = 0.10;

/// The v3.0 anisotropic ellipsoid + fbm warp algorithm, dressed as a
/// [`ShapeGenerator`].
pub struct EllipseGenerator;

impl ShapeGenerator for EllipseGenerator {
    fn kind(&self) -> ShapeKind {
        ShapeKind::Ellipse
    }

    /// Generate the ellipsoid polygon. **Bit-identical** to v3.0 inline code
    /// at the same `(ctx, rng)`.
    ///
    /// Always returns a `Vec` of length 1 (the primary ring). Multi-component
    /// plates are reserved for v3.3.
    fn generate(&self, ctx: &ShapeContext, rng: &mut Rng) -> ShapeResult {
        // For depth-0 plates, envelope.0 == envelope.1 == pitch. The v3.0
        // code used `pitch` directly; we recover it from envelope.0.
        let pitch = ctx.envelope.0;

        let (rmin, rmax) = ctx.size_rank.radius_band();
        let radius = pitch * lerp(rmin, rmax, rng.next_f32());

        let (amin, amax) = ctx.size_rank.aspect_band();
        let mut aspect = lerp(amin, amax, rng.next_f32());
        // **v4.3b**: honour the LLM-decided aspect_ratio override when the
        // dispatcher threaded `ParamOverride::Ellipse { aspect_ratio:
        // Some(_) }` into `ctx.params`. Clamped to `[0.5, 3.0]` so a
        // hallucinated extreme value doesn't break the polygon shape.
        // RNG draw above STAYS — preserves byte-identical determinism
        // when override is absent.
        if let Some(crate::shape::ParamOverride::Ellipse {
            aspect_ratio: Some(r),
        }) = &ctx.params
        {
            aspect = r.clamp(0.5, 3.0);
        }
        let rx = radius * aspect.sqrt();
        let ry = radius / aspect.sqrt();

        let theta_rot = rng.next_f32() * TAU;

        let (min_v, max_v_in) = ctx.vertex_count_range;
        let max_v = max_v_in.max(min_v);
        let nv = min_v + (rng.next_f32() * (max_v - min_v + 1) as f32) as usize;
        let nv = nv.clamp(3, max_v.max(3));

        let phase = rng.next_f32() * TAU;
        let cos_t = theta_rot.cos();
        let sin_t = theta_rot.sin();

        // Calibrated so E[shrink × bias] = 1 − edge_jitter/2 (preserves
        // mean polygon area despite the residual scale being < 1.0).
        let target_mean = 1.0 - ctx.edge_jitter * 0.5;
        let residual_mean = 1.0 - ctx.edge_jitter * JITTER_RESIDUAL_SCALE * 0.5;
        let shrink_bias = target_mean / residual_mean.max(1e-3);

        let primary: Polygon = (0..nv)
            .map(|k| {
                let base = phase + TAU * (k as f32) / nv as f32;
                let wobble = (rng.next_f32() - 0.5) * (TAU / nv as f32) * 0.6;
                let ang = base + wobble;
                let nx = ang.cos() * EDGE_NOISE_FREQ;
                let ny = ang.sin() * EDGE_NOISE_FREQ;
                let noise = crate::noise::fbm(nx, ny, ctx.plate_salt, EDGE_NOISE_OCTAVES);
                // Small per-vertex random shrink: ~3% range at default
                // edge_jitter=0.35 → enough to give honest character,
                // not so much that high-vertex polygons look fuzzy.
                let residual = 1.0 - ctx.edge_jitter * JITTER_RESIDUAL_SCALE * rng.next_f32();
                let radial_factor = shrink_bias * residual * (1.0 + EDGE_NOISE_AMP * noise);
                let lx = rx * radial_factor * ang.cos();
                let ly = ry * radial_factor * ang.sin();
                (
                    ctx.center.0 + lx * cos_t - ly * sin_t,
                    ctx.center.1 + lx * sin_t + ly * cos_t,
                )
            })
            .collect();

        ShapeResult::single_kind(vec![primary], ShapeKind::Ellipse)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;

    fn ctx_for(size_rank: SizeRank, seed: u32) -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (500.0, 300.0),
            envelope: (200.0, 200.0),
            size_rank,
            seed,
            plate_salt: seed.wrapping_mul(0x9E37_79B9),
            parent_path: Vec::new(),
            world_theme: None,
            edge_jitter: 0.35,
            vertex_count_range: (24, 48),
            params: None,
        }
    }

    #[test]
    fn ellipse_kind_is_ellipse() {
        assert_eq!(EllipseGenerator.kind(), ShapeKind::Ellipse);
    }

    #[test]
    fn ellipse_returns_single_component() {
        let ctx = ctx_for(SizeRank::Medium, 1);
        let mut rng = Rng::for_stage(1, b"ellipse-test");
        let polys = EllipseGenerator.generate(&ctx, &mut rng).polygons;
        assert_eq!(polys.len(), 1, "v3.1 invariant: single component");
        assert!(polys[0].len() >= 24, "vertex count within configured range");
    }

    #[test]
    fn ellipse_centre_inside_polygon() {
        let ctx = ctx_for(SizeRank::Large, 7);
        let mut rng = Rng::for_stage(7, b"ellipse-test");
        let polys = EllipseGenerator.generate(&ctx, &mut rng).polygons;
        let poly = &polys[0];
        // Ray-cast point-in-polygon at ctx.center.
        let (cx, cy) = ctx.center;
        let n = poly.len();
        let mut inside = false;
        let mut j = n - 1;
        for i in 0..n {
            let (xi, yi) = poly[i];
            let (xj, yj) = poly[j];
            if (yi > cy) != (yj > cy) {
                let t = (cy - yi) / (yj - yi);
                if cx < xi + t * (xj - xi) {
                    inside = !inside;
                }
            }
            j = i;
        }
        assert!(inside, "ellipse centre must be inside its own polygon");
    }

    #[test]
    fn ellipse_deterministic_same_seed() {
        let ctx = ctx_for(SizeRank::Medium, 42);
        let mut rng_a = Rng::for_stage(42, b"ellipse-test");
        let mut rng_b = Rng::for_stage(42, b"ellipse-test");
        let polys_a = EllipseGenerator.generate(&ctx, &mut rng_a).polygons;
        let polys_b = EllipseGenerator.generate(&ctx, &mut rng_b).polygons;
        assert_eq!(polys_a.len(), polys_b.len());
        for (a, b) in polys_a[0].iter().zip(polys_b[0].iter()) {
            assert_eq!(a.0.to_bits(), b.0.to_bits());
            assert_eq!(a.1.to_bits(), b.1.to_bits());
        }
    }

    /// Pin the RNG-call-count contract: `5 + 2 * nv` `next_f32` calls per
    /// `generate`. If a future edit changes this count, every downstream
    /// plate's velocity/zones/etc. shifts — byte-identical breaks. This
    /// test catches that BEFORE the snapshot test does.
    #[test]
    fn ellipse_rng_consumes_known_count() {
        // Force nv: vertex_count_range (24, 24) → nv = 24 deterministically.
        let mut ctx = ctx_for(SizeRank::Medium, 1);
        ctx.vertex_count_range = (24, 24);

        let mut rng_real = Rng::for_stage(1, b"count-test");
        let _polys = EllipseGenerator.generate(&ctx, &mut rng_real);

        let mut rng_replay = Rng::for_stage(1, b"count-test");
        // Replay exactly 5 + 2*24 = 53 next_f32 calls and confirm we land
        // on the SAME state as rng_real (i.e. their next-after-this calls match).
        for _ in 0..(5 + 2 * 24) {
            let _ = rng_replay.next_f32();
        }
        // The two RNGs should now be identical: same next u32 reveals it.
        let real_next = rng_real.next_u32();
        let replay_next = rng_replay.next_u32();
        assert_eq!(
            real_next, replay_next,
            "EllipseGenerator must consume exactly 5 + 2*nv next_f32 calls"
        );
    }

    #[test]
    fn ellipse_size_rank_drives_radius_band() {
        // Giant should produce visibly larger polygon than Micro at the
        // same envelope. (Approx area via bounding box.)
        let mut rng_g = Rng::for_stage(1, b"size-g");
        let polys_g = EllipseGenerator.generate(&ctx_for(SizeRank::Giant, 1), &mut rng_g).polygons;
        let mut rng_m = Rng::for_stage(1, b"size-m");
        let polys_m = EllipseGenerator.generate(&ctx_for(SizeRank::Micro, 1), &mut rng_m).polygons;

        fn bbox_area(poly: &Polygon) -> f32 {
            let (mut minx, mut miny) = (f32::INFINITY, f32::INFINITY);
            let (mut maxx, mut maxy) = (f32::NEG_INFINITY, f32::NEG_INFINITY);
            for &(x, y) in poly {
                minx = minx.min(x);
                miny = miny.min(y);
                maxx = maxx.max(x);
                maxy = maxy.max(y);
            }
            (maxx - minx) * (maxy - miny)
        }
        let a_g = bbox_area(&polys_g[0]);
        let a_m = bbox_area(&polys_m[0]);
        assert!(
            a_g > 4.0 * a_m,
            "Giant bbox area ({a_g}) should be ≥4× Micro ({a_m})"
        );
    }
}
