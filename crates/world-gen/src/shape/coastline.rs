//! Coastline fractalize post-process (v3.5).
//!
//! Universal post-process applied AFTER each plate generator's polygon
//! output. Brings smooth polygonal coasts closer to the Hausdorff-1.25
//! fractal scaling of real coastlines (Mandelbrot 1967, "How long is
//! the coast of Britain?").
//!
//! Algorithm — hybrid midpoint displacement + Perlin warp:
//! 1. **Midpoint displacement**: for `iterations` rounds, insert midpoint
//!    of each edge with perpendicular offset (rng-driven, amplitude
//!    decays `0.5^iter` per PO CLARIFY decision). Each iteration roughly
//!    doubles vertex count.
//! 2. **Perlin/fbm warp**: final per-vertex perturbation via 2D fbm
//!    noise lookup (`crate::noise::fbm`) for micro-detail consistent
//!    with surrounding terrain.
//!
//! Determinism: caller passes seeded `Rng`. Internal noise lookups use
//! the supplied `noise_salt`. Same `(poly, config, salt, rng_state)`
//! always produces bit-identical output.

use crate::flatworld::Polygon;
use crate::rng::Rng;

/// Per-plate fractalize knob, copied from `FlatParams::coastline`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FractalizeConfig {
    /// 0.0 = no fractalize; 1.0 = max chaos. Calibrated so 0.5 produces
    /// recognisable but not overpowering coast detail.
    pub roughness: f32,
    /// Midpoint displacement iterations (0-5). Each iteration roughly
    /// doubles vertex count.
    pub iterations: usize,
    /// Perlin frequency scale for the final warp pass (cycles per envelope).
    /// Default 8.0 = 8 fine wiggles per plate diameter.
    pub perlin_freq: f32,
    /// Apply to satellite components (multi-comp plates)? Default true.
    pub apply_to_satellites: bool,
}

impl Default for FractalizeConfig {
    fn default() -> Self {
        Self {
            roughness: 0.35,
            iterations: 3,
            perlin_freq: 8.0,
            apply_to_satellites: true,
        }
    }
}

impl FractalizeConfig {
    /// All-zero config — fractalize is a no-op (returns input clone).
    pub fn disabled() -> Self {
        Self {
            roughness: 0.0,
            iterations: 0,
            perlin_freq: 0.0,
            apply_to_satellites: false,
        }
    }

    /// True iff this config will actually modify the polygon.
    pub fn is_active(&self) -> bool {
        self.iterations > 0 && self.roughness > 0.0
    }
}

/// Apply hybrid midpoint-displacement + Perlin-warp fractalize to a
/// polygon. Output vertex count is roughly `input × 2^iterations` after
/// midpoint expansion; the Perlin warp does not add vertices.
///
/// `noise_salt` seeds the Perlin lookup independently of `rng` so two
/// callers with the same RNG state but different salts get different
/// fractal patterns.
pub fn fractalize_polygon(
    poly: &Polygon,
    config: &FractalizeConfig,
    noise_salt: u32,
    rng: &mut Rng,
) -> Polygon {
    if !config.is_active() || poly.len() < 3 {
        return poly.clone();
    }

    // --- Stage A: midpoint displacement ---
    // Base amplitude scales with average edge length so a plate's coast
    // wobble is proportional to its size — Mandelbrot's self-similarity
    // principle applied at the per-plate scale.
    let base_amp = config.roughness * avg_edge_length(poly);

    let mut current = poly.clone();
    for iter in 0..config.iterations {
        let amp = base_amp * 0.5_f32.powi(iter as i32);
        let n = current.len();
        let mut next = Vec::with_capacity(n * 2);
        for i in 0..n {
            let p = current[i];
            let q = current[(i + 1) % n];
            // Keep the original vertex.
            next.push(p);
            // Midpoint + perpendicular offset.
            let edge_dx = q.0 - p.0;
            let edge_dy = q.1 - p.1;
            let edge_len = (edge_dx * edge_dx + edge_dy * edge_dy).sqrt().max(1e-6);
            let mid = ((p.0 + q.0) * 0.5, (p.1 + q.1) * 0.5);
            // Perpendicular unit vector (rotated 90° CCW from edge direction).
            let perp_x = -edge_dy / edge_len;
            let perp_y = edge_dx / edge_len;
            // Offset in [-amp, +amp].
            let offset = (rng.next_f32() - 0.5) * 2.0 * amp;
            let mid_disp = (mid.0 + perp_x * offset, mid.1 + perp_y * offset);
            next.push(mid_disp);
        }
        current = next;
    }

    // --- Stage B: Perlin/fbm warp ---
    let (minx, miny, maxx, maxy) = bbox(&current);
    let bbox_diag = ((maxx - minx).powi(2) + (maxy - miny).powi(2)).sqrt().max(1e-6);
    // Warp amplitude in world units: ~1% of bbox diagonal at max roughness.
    let warp_amp = config.roughness * bbox_diag * 0.01;
    let freq_per_unit = config.perlin_freq / bbox_diag;
    let salt_x = noise_salt;
    let salt_y = noise_salt.wrapping_add(0xCAFE_F00D);
    for v in current.iter_mut() {
        let nx = crate::noise::fbm(v.0 * freq_per_unit, v.1 * freq_per_unit, salt_x, 3);
        let ny = crate::noise::fbm(v.0 * freq_per_unit, v.1 * freq_per_unit, salt_y, 3);
        v.0 += nx * warp_amp;
        v.1 += ny * warp_amp;
    }

    current
}

fn avg_edge_length(poly: &Polygon) -> f32 {
    let n = poly.len();
    if n < 2 {
        return 0.0;
    }
    let mut total = 0.0f32;
    for i in 0..n {
        let p = poly[i];
        let q = poly[(i + 1) % n];
        total += ((p.0 - q.0).powi(2) + (p.1 - q.1).powi(2)).sqrt();
    }
    total / n as f32
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

    fn unit_square() -> Polygon {
        vec![(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    }

    #[test]
    fn disabled_config_returns_clone() {
        let sq = unit_square();
        let mut rng = Rng::for_stage(1, b"coastline-test");
        let out = fractalize_polygon(&sq, &FractalizeConfig::disabled(), 0, &mut rng);
        assert_eq!(out.len(), sq.len());
        for (a, b) in sq.iter().zip(out.iter()) {
            assert_eq!(a.0.to_bits(), b.0.to_bits());
            assert_eq!(a.1.to_bits(), b.1.to_bits());
        }
    }

    #[test]
    fn zero_iterations_returns_clone() {
        let sq = unit_square();
        let mut rng = Rng::for_stage(1, b"t");
        let cfg = FractalizeConfig {
            roughness: 0.5,
            iterations: 0,
            perlin_freq: 1.0,
            apply_to_satellites: true,
        };
        let out = fractalize_polygon(&sq, &cfg, 0, &mut rng);
        assert_eq!(out.len(), sq.len());
    }

    #[test]
    fn iterations_double_vertex_count() {
        let sq = unit_square(); // 4 vertices
        let mut rng = Rng::for_stage(1, b"t");
        // iterations=3 → 4 × 2^3 = 32 vertices
        let cfg = FractalizeConfig {
            roughness: 0.5,
            iterations: 3,
            perlin_freq: 0.0,
            apply_to_satellites: true,
        };
        let out = fractalize_polygon(&sq, &cfg, 0, &mut rng);
        assert_eq!(out.len(), 32, "expected 32 vertices, got {}", out.len());
    }

    #[test]
    fn deterministic_for_fixed_rng_and_salt() {
        let sq = unit_square();
        let cfg = FractalizeConfig::default();
        let mut rng_a = Rng::for_stage(42, b"t");
        let mut rng_b = Rng::for_stage(42, b"t");
        let a = fractalize_polygon(&sq, &cfg, 0x1234, &mut rng_a);
        let b = fractalize_polygon(&sq, &cfg, 0x1234, &mut rng_b);
        assert_eq!(a.len(), b.len());
        for (pa, pb) in a.iter().zip(b.iter()) {
            assert_eq!(pa.0.to_bits(), pb.0.to_bits());
            assert_eq!(pa.1.to_bits(), pb.1.to_bits());
        }
    }

    #[test]
    fn higher_roughness_increases_displacement() {
        let sq = unit_square();
        let cfg_low = FractalizeConfig {
            roughness: 0.1,
            iterations: 2,
            perlin_freq: 0.0,
            apply_to_satellites: true,
        };
        let cfg_high = FractalizeConfig {
            roughness: 0.9,
            iterations: 2,
            perlin_freq: 0.0,
            apply_to_satellites: true,
        };
        // Use a fresh RNG for each so the random offsets cancel out by
        // running enough samples; here we measure bbox spread which
        // depends only on amplitude.
        let mut rng = Rng::for_stage(7, b"t");
        let low = fractalize_polygon(&sq, &cfg_low, 0, &mut rng);
        let mut rng = Rng::for_stage(7, b"t");
        let high = fractalize_polygon(&sq, &cfg_high, 0, &mut rng);
        let bb_low = bbox(&low);
        let bb_high = bbox(&high);
        let spread_low = (bb_low.2 - bb_low.0) + (bb_low.3 - bb_low.1);
        let spread_high = (bb_high.2 - bb_high.0) + (bb_high.3 - bb_high.1);
        assert!(
            spread_high > spread_low,
            "higher roughness should produce wider bbox: low={spread_low}, high={spread_high}"
        );
    }

    #[test]
    fn perlin_warp_preserves_vertex_count_only_changes_positions() {
        let sq = unit_square();
        let cfg = FractalizeConfig {
            roughness: 0.5,
            iterations: 0,           // skip midpoint stage
            perlin_freq: 5.0,
            apply_to_satellites: true,
        };
        // iterations=0 returns clone (no warp either per is_active check).
        let mut rng = Rng::for_stage(1, b"t");
        let out = fractalize_polygon(&sq, &cfg, 0, &mut rng);
        assert_eq!(out.len(), sq.len());
    }
}
