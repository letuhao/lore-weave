//! Render-time procedural noise — Perlin-style 2-D gradient noise + fBm.
//!
//! Used only by [`crate::relief`] to add detail and domain-warp the heightmap
//! at render time. The renderer is not part of `WorldMap` / `content_hash`,
//! but this noise is still fully deterministic given its `seed`, so a rendered
//! PNG reproduces byte-for-byte. Hand-rolled — no external noise crate, the
//! same philosophy as the hand-rolled [`crate::rng`].

use std::f32::consts::TAU;

/// Linear interpolation — `t = 0 → a`, `t = 1 → b`.
pub(crate) fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// Smootherstep fade `6t⁵ − 15t⁴ + 10t³`. Zero 1st *and* 2nd derivatives at
/// `t ∈ {0,1}`, so adjacent gradient-noise cells join without visible creases.
fn fade(t: f32) -> f32 {
    t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
}

/// Integer-lattice hash → a well-mixed `u32`. Platform-stable: only wrapping
/// integer ops, no floats.
fn hash(ix: i32, iy: i32, seed: u32) -> u32 {
    let mut h = seed ^ 0x9E37_79B9;
    h = h.wrapping_add((ix as u32).wrapping_mul(0x85EB_CA6B));
    h = (h ^ (h >> 13)).wrapping_mul(0xC2B2_AE35);
    h = h.wrapping_add((iy as u32).wrapping_mul(0x27D4_EB2F));
    h = (h ^ (h >> 15)).wrapping_mul(0x1656_67B1);
    h ^ (h >> 16)
}

/// Unit gradient vector at integer lattice point `(ix, iy)` — the hash mapped
/// onto an angle. Arbitrary-angle gradients avoid the axis-aligned artefacts
/// of a small fixed gradient set.
fn gradient(ix: i32, iy: i32, seed: u32) -> (f32, f32) {
    let angle = hash(ix, iy, seed) as f32 * (TAU / 4_294_967_296.0);
    (angle.cos(), angle.sin())
}

/// Perlin-style 2-D gradient noise. Output is in roughly `[-0.71, 0.71]` and
/// is exactly `0` at every integer lattice point.
pub fn gradient_noise(x: f32, y: f32, seed: u32) -> f32 {
    let x0 = x.floor();
    let y0 = y.floor();
    let (ix, iy) = (x0 as i32, y0 as i32);
    let (fx, fy) = (x - x0, y - y0);

    let g00 = gradient(ix, iy, seed);
    let g10 = gradient(ix + 1, iy, seed);
    let g01 = gradient(ix, iy + 1, seed);
    let g11 = gradient(ix + 1, iy + 1, seed);

    // dot of each corner's gradient with the offset from that corner.
    let n00 = g00.0 * fx + g00.1 * fy;
    let n10 = g10.0 * (fx - 1.0) + g10.1 * fy;
    let n01 = g01.0 * fx + g01.1 * (fy - 1.0);
    let n11 = g11.0 * (fx - 1.0) + g11.1 * (fy - 1.0);

    let (u, v) = (fade(fx), fade(fy));
    lerp(lerp(n00, n10, u), lerp(n01, n11, u), v)
}

/// Fractal Brownian motion — sum `octaves` of [`gradient_noise`], each at
/// double the frequency (lacunarity 2) and half the amplitude (gain 0.5),
/// normalized back to roughly `[-0.71, 0.71]`.
pub fn fbm(x: f32, y: f32, seed: u32, octaves: u32) -> f32 {
    let mut sum = 0.0;
    let mut amp = 1.0;
    let mut freq = 1.0;
    let mut norm = 0.0;
    for o in 0..octaves {
        // a distinct per-octave seed so the octaves are decorrelated.
        let oseed = seed.wrapping_add(o.wrapping_mul(0x9E37_79B9));
        sum += amp * gradient_noise(x * freq, y * freq, oseed);
        norm += amp;
        amp *= 0.5;
        freq *= 2.0;
    }
    if norm > 0.0 { sum / norm } else { 0.0 }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gradient_noise_is_zero_at_lattice_points() {
        // every corner offset is the zero vector at an integer point ⇒ noise 0.
        for ix in -3..=3 {
            for iy in -3..=3 {
                let n = gradient_noise(ix as f32, iy as f32, 42);
                assert!(n.abs() < 1e-5, "noise at lattice ({ix},{iy}) = {n}, want ~0");
            }
        }
    }

    #[test]
    fn gradient_noise_is_bounded() {
        let mut max = 0.0f32;
        for i in 0..5000 {
            let n = gradient_noise(i as f32 * 0.137, i as f32 * 0.071, 7);
            max = max.max(n.abs());
        }
        // 2-D gradient noise is bounded by ~0.71; assert a generous ceiling
        // and a floor proving the field is not degenerate.
        assert!(max < 1.0, "gradient noise exceeded 1.0: {max}");
        assert!(max > 0.2, "gradient noise suspiciously flat: {max}");
    }

    #[test]
    fn fbm_is_deterministic() {
        for i in 0..1000 {
            let (x, y) = (i as f32 * 0.019, i as f32 * 0.023);
            assert_eq!(
                fbm(x, y, 99, 5).to_bits(),
                fbm(x, y, 99, 5).to_bits(),
                "fbm not reproducible at ({x},{y})"
            );
        }
    }

    #[test]
    fn fbm_varies_across_space() {
        let first = fbm(0.31, 0.74, 1, 5);
        let differs = (1..200).any(|i| {
            let p = i as f32 * 0.05;
            (fbm(p, p * 1.3, 1, 5) - first).abs() > 1e-4
        });
        assert!(differs, "fbm produced a constant field");
    }

    #[test]
    fn fbm_is_bounded() {
        for i in 0..5000 {
            let (x, y) = (i as f32 * 0.041, i as f32 * 0.067);
            let v = fbm(x, y, 3, 5);
            assert!(v.abs() < 1.0, "fbm out of range at ({x},{y}): {v}");
        }
    }

    #[test]
    fn distinct_seeds_decorrelate() {
        // two seeds must not produce an identical field.
        let same = (0..500)
            .filter(|&i| {
                let p = i as f32 * 0.03;
                fbm(p, p, 1, 4).to_bits() == fbm(p, p, 2, 4).to_bits()
            })
            .count();
        assert!(same < 10, "seeds 1 and 2 produced near-identical fields");
    }
}
