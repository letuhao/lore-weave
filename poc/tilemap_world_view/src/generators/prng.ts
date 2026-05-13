/**
 * Mulberry32 — deterministic 32-bit PRNG.
 *
 * Required by SPIKE_03 §4 (replay-determinism per EVT-A9): same seed → byte-identical
 * tilemap output. Tested in `tests/generators.test.ts`.
 *
 * Port target: when migrating to Rust at `services/world-service/src/tilemap/`,
 * replace with `rand_chacha::ChaCha8Rng` (already used in CSC_001 §5.2 for the same
 * purpose — keep one PRNG choice across the codebase if possible).
 *
 * For PoC v1, JS Mulberry32 is sufficient: 2^32 period, 32-bit state, no dependencies.
 */
export function mulberry32(seed: number): () => number {
  let s = seed | 0;
  return function (): number {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Hash-based deterministic value at integer (x, y) given seed.
 *
 * Used by value-noise grid lookup — ensures hash result depends only on (x, y, seed)
 * NOT on the order in which the noise function is called. Pure function; safe to call
 * concurrently or in any order.
 */
export function hash2D(x: number, y: number, seed: number): number {
  let h = (Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263)) ^ (seed | 0);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h = h ^ (h >>> 16);
  return ((h >>> 0) % 1_000_000) / 1_000_000;
}
