//! Deterministic RNG — SplitMix64, hand-rolled so the kernel has ZERO
//! dependencies. Not cryptographic, deliberately: this is a replay-exact
//! simulation source, and auditability beats statistical perfection here.

/// Seeded deterministic RNG. Same seed + same call sequence → same outputs,
/// on every platform (pure u64 arithmetic, no floats).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DetRng {
    state: u64,
}

impl DetRng {
    pub fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    /// SplitMix64 step (Steele/Lea/Flood 2014 constants).
    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform-ish value in `0..n`. Modulo bias is accepted for S1a (documented;
    /// n is tiny relative to 2^64 in every current use). `n` must be non-zero.
    pub fn range_u64(&mut self, n: u64) -> u64 {
        assert!(n > 0, "range_u64(0)");
        self.next_u64() % n
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_seed_same_stream() {
        let mut a = DetRng::new(42);
        let mut b = DetRng::new(42);
        for _ in 0..1000 {
            assert_eq!(a.next_u64(), b.next_u64());
        }
    }

    #[test]
    fn different_seed_different_stream() {
        let mut a = DetRng::new(1);
        let mut b = DetRng::new(2);
        // First outputs differing is enough — this is a sanity check, not a
        // statistical suite.
        assert_ne!(a.next_u64(), b.next_u64());
    }
}
