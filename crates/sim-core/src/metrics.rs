//! Island metrics — the kernel's observability surface (added at S1a-stress:
//! "without them, we cannot test").
//!
//! DESIGN RULE: **metrics are data; emission is the host's job.** The kernel
//! stays zero-dep and I/O-free — it maintains deterministic counters (pure
//! functions of the processed stream, so replay-safe by construction) and the
//! HOST (commit-service, S3) turns them into real telemetry per DP-R8.
//! Because they are deterministic, tests assert on them AND cross-check them
//! against the outcome log — the two must always agree.

/// Cumulative counters + peak gauges for one island. All `u64`, all updated
/// inline on the paths they observe (a handful of adds — bench-verified
/// negligible against the 176 ns/step baseline).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct IslandMetrics {
    // ─── step outcomes (must sum-match the outcome log) ───
    pub steps_processed: u64,
    pub applied: u64,
    pub discarded_duplicate: u64,
    pub discarded_precondition: u64,
    pub discarded_superseded: u64,
    pub discarded_expired: u64,
    pub substituted: u64,
    /// Buffered EPISODES (recorded once per episode, matching the outcome log).
    pub buffered_episodes: u64,
    /// Every re-park cycle, including the silent ones — the counter the
    /// outcome log deliberately does NOT show (review-impl finding 1).
    pub rebuffer_cycles: u64,

    // ─── S1b: containment + cascade ───
    /// Inputs whose `apply` panicked (island poisons after the first, so ≤1
    /// by construction in V1).
    pub quarantined: u64,
    /// Island-generation bumps — each is an O(1) invalidation cascade.
    pub island_gen_bumps: u64,

    // ─── time + scheduling ───
    pub ticks: u64,
    pub scheduled_fired: u64,
    pub seen_evictions: u64,

    // ─── peak gauges (memory-bound assertions in soak tests) ───
    pub peak_ingress_depth: u64,
    pub peak_seen_len: u64,
    pub peak_buffered_len: u64,
    pub peak_outcomes_len: u64,
}

impl IslandMetrics {
    /// Total discards across all reasons.
    pub fn discarded_total(&self) -> u64 {
        self.discarded_duplicate
            + self.discarded_precondition
            + self.discarded_superseded
            + self.discarded_expired
    }

    /// Self-check: every processed step ended as exactly one of
    /// applied / discarded / buffered-episode / silent-rebuffer.
    /// Tests assert this; a drift here means a silent outcome path exists.
    pub fn accounted(&self) -> u64 {
        self.applied + self.discarded_total() + self.buffered_episodes + self.rebuffer_cycles
    }

    /// S1b: `Quarantined` outcomes count under `discarded_total` via their
    /// own counter — kept separate because a quarantine is an INCIDENT, not
    /// a routine discard.
    pub fn discarded_and_quarantined(&self) -> u64 {
        self.discarded_total() + self.quarantined
    }

    pub(crate) fn gauge_peak(peak: &mut u64, current: usize) {
        if current as u64 > *peak {
            *peak = current as u64;
        }
    }
}
