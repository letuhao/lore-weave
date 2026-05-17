//! Deterministic RNG — blake3 sub-seed derivation + a ChaCha8 stream.
//!
//! Determinism is the load-bearing invariant of the whole generator. Each
//! pipeline stage gets its own RNG, seeded from `blake3(master_seed, domain)`,
//! so stages are independent yet fully reproducible.

use rand_chacha::ChaCha8Rng;
use rand_core::{RngCore, SeedableRng};

/// Derive a stable 64-bit sub-seed for a named pipeline stage.
pub fn sub_seed(master: u64, domain: &[u8]) -> u64 {
    let mut hasher = blake3::Hasher::new();
    hasher.update(&master.to_le_bytes());
    hasher.update(domain);
    let bytes = hasher.finalize();
    u64::from_le_bytes(
        bytes.as_bytes()[..8]
            .try_into()
            .expect("blake3 digest is 32 bytes, always >= 8"),
    )
}

/// A deterministic RNG for one pipeline stage.
pub struct Rng(ChaCha8Rng);

impl Rng {
    /// Build a stage RNG from the master seed + a stage domain tag.
    pub fn for_stage(master: u64, domain: &[u8]) -> Self {
        Rng(ChaCha8Rng::seed_from_u64(sub_seed(master, domain)))
    }

    /// Uniform `f32` in `[0, 1)`. 24-bit mantissa precision; fully
    /// deterministic given the (deterministic) ChaCha8 stream.
    pub fn next_f32(&mut self) -> f32 {
        // next_u32() >> 8 lands in [0, 2^24); divisor 2^24 is exact in f32.
        (self.0.next_u32() >> 8) as f32 / (1u32 << 24) as f32
    }

    /// Raw next `u32` from the deterministic stream.
    pub fn next_u32(&mut self) -> u32 {
        self.0.next_u32()
    }
}

/// Deterministic in-place Fisher-Yates shuffle.
pub fn shuffle<T>(rng: &mut Rng, v: &mut [T]) {
    let len = v.len();
    if len < 2 {
        return;
    }
    for i in (1..len).rev() {
        // modulo bias is negligible and irrelevant to determinism.
        let j = (rng.next_u32() as usize) % (i + 1);
        v.swap(i, j);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sub_seed_is_stable() {
        assert_eq!(sub_seed(42, b"mesh"), sub_seed(42, b"mesh"));
    }

    #[test]
    fn distinct_domains_distinct_seeds() {
        assert_ne!(sub_seed(42, b"mesh"), sub_seed(42, b"terrain"));
    }

    #[test]
    fn next_f32_in_unit_range() {
        let mut rng = Rng::for_stage(1, b"t");
        for _ in 0..10_000 {
            let v = rng.next_f32();
            assert!((0.0..1.0).contains(&v));
        }
    }

    #[test]
    fn stream_is_reproducible() {
        let mut a = Rng::for_stage(7, b"x");
        let mut b = Rng::for_stage(7, b"x");
        for _ in 0..1000 {
            assert_eq!(a.next_f32().to_bits(), b.next_f32().to_bits());
        }
    }
}
