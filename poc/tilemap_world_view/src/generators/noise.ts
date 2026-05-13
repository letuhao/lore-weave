import { hash2D } from './prng';

/**
 * 2D value noise with smoothstep interpolation.
 *
 * Returns a function `(x, y) → 0..1` that produces smooth pseudo-random noise.
 * Determined entirely by seed; same (seed, x, y) → identical output.
 *
 * Algorithm: lattice-grid value noise (cheap, deterministic, no gradients).
 * Quality is below Perlin/Simplex but sufficient for biome distribution at zone scale.
 *
 * V2: upgrade to Simplex 2D for higher visual quality. PoC v1 prioritizes simplicity
 * over visual fidelity since terrain is rendered as colored squares anyway.
 */
export function valueNoise2D(seed: number): (x: number, y: number) => number {
  const smoothstep = (t: number): number => t * t * (3 - 2 * t);

  return function (x: number, y: number): number {
    const x0 = Math.floor(x);
    const x1 = x0 + 1;
    const y0 = Math.floor(y);
    const y1 = y0 + 1;
    const fx = smoothstep(x - x0);
    const fy = smoothstep(y - y0);

    const v00 = hash2D(x0, y0, seed);
    const v10 = hash2D(x1, y0, seed);
    const v01 = hash2D(x0, y1, seed);
    const v11 = hash2D(x1, y1, seed);

    const v0 = v00 * (1 - fx) + v10 * fx;
    const v1 = v01 * (1 - fx) + v11 * fx;
    return v0 * (1 - fy) + v1 * fy;
  };
}

/**
 * Fractal Brownian Motion — sum N octaves of value noise at increasing frequency.
 *
 * Result is in 0..1. Higher octaves = more high-frequency detail.
 * persistence < 1 means each octave contributes less; standard 0.5.
 * lacunarity = frequency multiplier per octave; standard 2.
 */
export function fbm2D(
  noiseFn: (x: number, y: number) => number,
  x: number,
  y: number,
  octaves: number = 4,
  persistence: number = 0.5,
  lacunarity: number = 2,
): number {
  let value = 0;
  let amplitude = 1;
  let frequency = 1;
  let maxAmplitude = 0;
  for (let i = 0; i < octaves; i++) {
    value += noiseFn(x * frequency, y * frequency) * amplitude;
    maxAmplitude += amplitude;
    amplitude *= persistence;
    frequency *= lacunarity;
  }
  return value / maxAmplitude;
}
