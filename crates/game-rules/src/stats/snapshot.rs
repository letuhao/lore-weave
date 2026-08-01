//! `StatSnapshot` — resolved once at encounter start (DF07 §8.1/8.2).

use super::block::StatBlock;

/// DF07 §8.2 — the 5-tuple of input versions a snapshot was resolved under.
///
/// Its job is to make staleness *detectable*: if any input version moves, the
/// snapshot is invalid and must be re-resolved rather than repaired.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct StatEpoch {
    pub manifest_version: u64,
    pub progression_turn: u64,
    pub equipment_version: u64,
    pub status_version: u64,
    pub archetype_version: u64,
}

/// DF07 §8.1 — resolved once at encounter start and read by every law-chain
/// step thereafter.
///
/// **Why a snapshot rather than a live read:** a progression tick or manifest
/// reload mid-encounter would retroactively change how *earlier rounds should
/// have resolved*, breaking replay of the encounter as a unit. Striking trains
/// swordsmanship, and PROG_001 trains on Action — so this is the normal case,
/// not an exotic one.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StatSnapshot {
    pub stats: StatBlock,
    pub epoch: StatEpoch,
}

impl Default for StatSnapshot {
    /// A snapshot that has never been resolved: a ZEROED block at epoch zero.
    ///
    /// Hand-written because `StatBlock` no longer has `Default` (see its doc).
    /// Zeroed is the honest value here — `is_stale` against any real epoch
    /// returns true, so an unresolved snapshot is one that must be re-resolved
    /// before it is read, which is exactly what it is.
    fn default() -> Self {
        Self { stats: StatBlock::zeroed(), epoch: StatEpoch::default() }
    }
}

impl StatSnapshot {
    /// True when any input version has moved since resolution. The caller
    /// re-resolves; nothing is ever patched in place (DF7-A2).
    pub fn is_stale(&self, current: &StatEpoch) -> bool {
        &self.epoch != current
    }
}
