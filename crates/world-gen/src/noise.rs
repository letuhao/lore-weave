//! Procedural noise — Perlin-style gradient noise + fBm + ridged-multifractal,
//! in both **2D** (legacy, used by the relief renderer's render-time detail)
//! and **3D** (sphere migration, B3 — sampled at unit-sphere `(x, y, z)` so
//! the heightmap wraps seamlessly across the antimeridian).
//!
//! Hand-rolled — no external noise crate, the same philosophy as the
//! hand-rolled [`crate::rng`]. Fully deterministic given seed + position; the
//! same `(x, y[, z], seed)` always produces the same `f32`.

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

/// Ridged-multifractal noise — `octaves` of [`gradient_noise`] folded with
/// `offset − |n|` so crests track the noise's *zero crossings* (sharp ridge
/// **lines**, not smooth bumps), squared to sharpen the crest, and
/// multifractally weighted so finer detail concentrates on the ridges. Output
/// is in roughly `[0, 1]`, high along ridgelines — the basis for mountain
/// ranges rather than radial cones.
pub fn ridged_fbm(x: f32, y: f32, seed: u32, octaves: u32) -> f32 {
    const OFFSET: f32 = 1.0;
    const GAIN: f32 = 2.0;
    let mut sum = 0.0;
    let mut norm = 0.0;
    let mut freq = 1.0;
    let mut weight = 1.0f32;
    for o in 0..octaves {
        let oseed = seed.wrapping_add(o.wrapping_mul(0x9E37_79B9));
        let mut signal = OFFSET - gradient_noise(x * freq, y * freq, oseed).abs();
        signal *= signal; // sharpen the ridge crest
        signal *= weight; // multifractal — gate this octave by the previous
        weight = (signal * GAIN).clamp(0.0, 1.0);
        let spectral = 1.0 / freq; // h = 1 spectral weighting
        sum += signal * spectral;
        norm += spectral;
        freq *= 2.0; // lacunarity 2
    }
    if norm > 0.0 { sum / norm } else { 0.0 }
}

// ===== 3D variants (sphere migration, B3) ==================================

/// Integer-lattice hash → a well-mixed `u32`, **3D**. Platform-stable; only
/// wrapping integer ops.
fn hash_3d(ix: i32, iy: i32, iz: i32, seed: u32) -> u32 {
    let mut h = seed ^ 0x9E37_79B9;
    h = h.wrapping_add((ix as u32).wrapping_mul(0x85EB_CA6B));
    h = (h ^ (h >> 13)).wrapping_mul(0xC2B2_AE35);
    h = h.wrapping_add((iy as u32).wrapping_mul(0x27D4_EB2F));
    h = (h ^ (h >> 15)).wrapping_mul(0x1656_67B1);
    h = h.wrapping_add((iz as u32).wrapping_mul(0x9E37_79B1));
    h = (h ^ (h >> 14)).wrapping_mul(0x85EB_CA77);
    h ^ (h >> 16)
}

/// 3D unit gradient vector at lattice point `(ix, iy, iz)` — hashed onto a
/// uniform-on-sphere direction (Marsaglia-style: azimuth from one hash,
/// z-coord from a second). Two hashes per call; avoids the axis-aligned
/// artefacts of a fixed-12-gradient table.
fn gradient_3d(ix: i32, iy: i32, iz: i32, seed: u32) -> [f32; 3] {
    let h1 = hash_3d(ix, iy, iz, seed);
    let h2 = hash_3d(ix, iy, iz, seed.wrapping_add(0x9E37_79B9));
    let theta = h1 as f32 * (TAU / 4_294_967_296.0);
    // z uniform in [-1, 1).
    let z = h2 as f32 * (2.0 / 4_294_967_296.0) - 1.0;
    let r = (1.0 - z * z).max(0.0).sqrt();
    [r * theta.cos(), r * theta.sin(), z]
}

/// Perlin-style 3D gradient noise. Output is roughly in `[-0.6, 0.6]` and
/// exactly `0` at every integer lattice point. Smootherstep fade — adjacent
/// lattice cubes join without visible creases.
pub fn gradient_noise_3d(x: f32, y: f32, z: f32, seed: u32) -> f32 {
    let x0 = x.floor();
    let y0 = y.floor();
    let z0 = z.floor();
    let (ix, iy, iz) = (x0 as i32, y0 as i32, z0 as i32);
    let (fx, fy, fz) = (x - x0, y - y0, z - z0);

    // Eight cube-corner gradients.
    let g000 = gradient_3d(ix, iy, iz, seed);
    let g100 = gradient_3d(ix + 1, iy, iz, seed);
    let g010 = gradient_3d(ix, iy + 1, iz, seed);
    let g110 = gradient_3d(ix + 1, iy + 1, iz, seed);
    let g001 = gradient_3d(ix, iy, iz + 1, seed);
    let g101 = gradient_3d(ix + 1, iy, iz + 1, seed);
    let g011 = gradient_3d(ix, iy + 1, iz + 1, seed);
    let g111 = gradient_3d(ix + 1, iy + 1, iz + 1, seed);

    // Dot products with each corner's offset.
    let n000 = g000[0] * fx + g000[1] * fy + g000[2] * fz;
    let n100 = g100[0] * (fx - 1.0) + g100[1] * fy + g100[2] * fz;
    let n010 = g010[0] * fx + g010[1] * (fy - 1.0) + g010[2] * fz;
    let n110 = g110[0] * (fx - 1.0) + g110[1] * (fy - 1.0) + g110[2] * fz;
    let n001 = g001[0] * fx + g001[1] * fy + g001[2] * (fz - 1.0);
    let n101 = g101[0] * (fx - 1.0) + g101[1] * fy + g101[2] * (fz - 1.0);
    let n011 = g011[0] * fx + g011[1] * (fy - 1.0) + g011[2] * (fz - 1.0);
    let n111 = g111[0] * (fx - 1.0) + g111[1] * (fy - 1.0) + g111[2] * (fz - 1.0);

    // Trilinear blend with smootherstep fades.
    let u = fade(fx);
    let v = fade(fy);
    let w = fade(fz);
    let nx00 = lerp(n000, n100, u);
    let nx10 = lerp(n010, n110, u);
    let nx01 = lerp(n001, n101, u);
    let nx11 = lerp(n011, n111, u);
    let nxy0 = lerp(nx00, nx10, v);
    let nxy1 = lerp(nx01, nx11, v);
    lerp(nxy0, nxy1, w)
}

/// Fractal Brownian motion in 3D — `octaves` of [`gradient_noise_3d`], each
/// at double frequency / half amplitude, normalized to roughly `[-0.6, 0.6]`.
pub fn fbm_3d(x: f32, y: f32, z: f32, seed: u32, octaves: u32) -> f32 {
    let mut sum = 0.0;
    let mut amp = 1.0;
    let mut freq = 1.0;
    let mut norm = 0.0;
    for o in 0..octaves {
        let oseed = seed.wrapping_add(o.wrapping_mul(0x9E37_79B9));
        sum += amp * gradient_noise_3d(x * freq, y * freq, z * freq, oseed);
        norm += amp;
        amp *= 0.5;
        freq *= 2.0;
    }
    if norm > 0.0 { sum / norm } else { 0.0 }
}

/// Ridged-multifractal noise in 3D — same `OFFSET − |n|` ridge-line trick as
/// the 2D variant. Output is roughly in `[0, 1]`, high along ridge lines on
/// the sphere — the basis for mountain ranges that fold around the globe
/// without antimeridian artefacts.
pub fn ridged_fbm_3d(x: f32, y: f32, z: f32, seed: u32, octaves: u32) -> f32 {
    const OFFSET: f32 = 1.0;
    const GAIN: f32 = 2.0;
    let mut sum = 0.0;
    let mut norm = 0.0;
    let mut freq = 1.0;
    let mut weight = 1.0f32;
    for o in 0..octaves {
        let oseed = seed.wrapping_add(o.wrapping_mul(0x9E37_79B9));
        let mut signal = OFFSET - gradient_noise_3d(x * freq, y * freq, z * freq, oseed).abs();
        signal *= signal;
        signal *= weight;
        weight = (signal * GAIN).clamp(0.0, 1.0);
        let spectral = 1.0 / freq;
        sum += signal * spectral;
        norm += spectral;
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

    #[test]
    fn ridged_fbm_is_deterministic_and_bounded() {
        for i in 0..2000 {
            let (x, y) = (i as f32 * 0.013, i as f32 * 0.017);
            let v = ridged_fbm(x, y, 11, 5);
            assert_eq!(v.to_bits(), ridged_fbm(x, y, 11, 5).to_bits());
            assert!(
                (0.0..=1.0).contains(&v),
                "ridged_fbm out of [0,1] at ({x},{y}): {v}"
            );
        }
    }

    #[test]
    fn ridged_fbm_varies_across_space() {
        let first = ridged_fbm(0.2, 0.6, 4, 5);
        let differs = (1..300).any(|i| {
            let p = i as f32 * 0.04;
            (ridged_fbm(p, p * 0.7, 4, 5) - first).abs() > 1e-4
        });
        assert!(differs, "ridged_fbm produced a constant field");
    }

    // ===== 3D tests (sphere migration, B3) ==============================

    #[test]
    fn gradient_noise_3d_is_zero_at_lattice_points() {
        for ix in -2..=2 {
            for iy in -2..=2 {
                for iz in -2..=2 {
                    let n = gradient_noise_3d(ix as f32, iy as f32, iz as f32, 42);
                    assert!(
                        n.abs() < 1e-5,
                        "3D noise at lattice ({ix},{iy},{iz}) = {n}, want ~0"
                    );
                }
            }
        }
    }

    #[test]
    fn gradient_noise_3d_is_bounded() {
        let mut max = 0.0f32;
        for i in 0..3000 {
            let n = gradient_noise_3d(
                i as f32 * 0.137,
                i as f32 * 0.071,
                i as f32 * 0.053,
                7,
            );
            max = max.max(n.abs());
        }
        // 3D gradient noise is bounded by ~0.6; ceiling at 1.0, floor proves
        // the field is not degenerate.
        assert!(max < 1.0, "3D gradient noise exceeded 1.0: {max}");
        assert!(max > 0.15, "3D gradient noise suspiciously flat: {max}");
    }

    #[test]
    fn gradient_3d_is_a_unit_vector() {
        for ix in -2..=2 {
            for iy in -2..=2 {
                for iz in -2..=2 {
                    let g = gradient_3d(ix, iy, iz, 17);
                    let len2 = g[0] * g[0] + g[1] * g[1] + g[2] * g[2];
                    assert!(
                        (len2 - 1.0).abs() < 1e-3,
                        "3D gradient at ({ix},{iy},{iz}) is not unit: {len2}"
                    );
                }
            }
        }
    }

    #[test]
    fn fbm_3d_is_deterministic() {
        for i in 0..500 {
            let (x, y, z) = (i as f32 * 0.019, i as f32 * 0.023, i as f32 * 0.029);
            assert_eq!(
                fbm_3d(x, y, z, 99, 5).to_bits(),
                fbm_3d(x, y, z, 99, 5).to_bits(),
                "fbm_3d not reproducible at ({x},{y},{z})"
            );
        }
    }

    #[test]
    fn fbm_3d_varies_across_sphere() {
        // Sample a sweep of unit-sphere points; non-constant output.
        let first = fbm_3d(1.0, 0.0, 0.0, 1, 5);
        let differs = (1..120).any(|i| {
            let theta = i as f32 * 0.05;
            let p = [theta.cos(), theta.sin(), 0.0];
            (fbm_3d(p[0], p[1], p[2], 1, 5) - first).abs() > 1e-4
        });
        assert!(differs, "fbm_3d produced a constant field");
    }

    #[test]
    fn ridged_fbm_3d_is_bounded_and_deterministic() {
        for i in 0..1000 {
            let (x, y, z) = (i as f32 * 0.013, i as f32 * 0.017, i as f32 * 0.021);
            let v = ridged_fbm_3d(x, y, z, 11, 5);
            assert_eq!(v.to_bits(), ridged_fbm_3d(x, y, z, 11, 5).to_bits());
            assert!(
                (0.0..=1.0).contains(&v),
                "ridged_fbm_3d out of [0,1] at ({x},{y},{z}): {v}"
            );
        }
    }
}
