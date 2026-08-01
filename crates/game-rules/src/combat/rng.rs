//! Per-roll derived streams (COMB_001 Q8).
//!
//! Moved verbatim from `commit-service/src/combat.rs` by `S2`; the module doc
//! that explains WHY the RNG is derived per-roll rather than drawn from a
//! stream now lives on [`super`], because it governs the whole chain.

use sim_core::{DetRng, EntityId};

/// Which roll a derived stream is for (COMB_001 Q8). Closed set — an
//  open-ended role string would let two call sites collide on one stream and
//  correlate rolls that must be independent.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SeedRole {
    Damage,
    Crit,
    Hit,
    Position,
    Loot,
}

impl SeedRole {
    /// Distinct, stable discriminants. Values are pinned rather than derived
    /// from declaration order: reordering the enum must not change any
    /// historical roll.
    fn tag(self) -> u64 {
        match self {
            SeedRole::Damage => 0x01,
            SeedRole::Crit => 0x02,
            SeedRole::Hit => 0x03,
            SeedRole::Position => 0x04,
            SeedRole::Loot => 0x05,
        }
    }
}

/// Derive the stream for one (actor, action, role) coordinate.
///
/// SplitMix64 finalisation, the same family `DetRng` itself uses — so this
/// introduces no new randomness primitive and no dependency. Mixing each
/// coordinate through the finaliser before combining avoids the trivial
/// correlations a plain XOR of small integers would leave.
pub fn role_rng(session_seed: u64, actor: EntityId, action_idx: u32, role: SeedRole) -> DetRng {
    let mut z = session_seed;
    for part in [actor.0, action_idx as u64, role.tag()] {
        z = z.wrapping_add(part).wrapping_add(0x9E37_79B9_7F4A_7C15);
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^= z >> 31;
    }
    DetRng::new(z)
}

/// Draw a per-mille value in `0..1000`.
///
/// Integer, not a float fraction — DF7-A4 keeps floats out of the stat path,
/// and the same reasoning applies to the rolls that consume it. Float
/// arithmetic is reproducible within a build but not reliably across targets
/// (fused multiply-add, x87 80-bit intermediates), and this project REPLAYS
/// committed encounters. A roll that differs in the last bit on another
/// machine makes a replayed fight diverge.
pub(super) fn roll_pm(rng: &mut DetRng) -> i64 {
    rng.range_u64(1000) as i64
}
