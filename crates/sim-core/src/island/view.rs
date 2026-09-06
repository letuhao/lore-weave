//! The island's READ surface — everything the host and the tests observe, and
//! nothing that steps.
//!
//! Split out of `island/mod.rs` at `IMP-D3`'s ceiling when `M1` added
//! [`Island::rules`]. **The row in `scripts/file-ceiling-gate.py` has been paid
//! in a split three times and this is the fourth**; absorbing 16 lines into the
//! allowlist instead would have been the first time the ceiling bought nothing.
//!
//! The seam is real: everything here is `&self` and total, everything left
//! behind mutates the loop. A CHILD module rather than a sibling, so it still
//! reaches the parent's private fields — a sibling would have forced them
//! `pub(crate)` and widened the kernel's mutable surface across the whole crate
//! to satisfy a line count, which is the argument `island/epoch.rs` already made.

use super::{Island, IslandMetrics};
use crate::domain::Domain;
use crate::types::{Outcome, Seq, Tick};

impl<D: Domain> Island<D> {

    pub fn now(&self) -> Tick {
        self.tick
    }

    pub fn state(&self) -> &D::State {
        &self.state
    }

    /// The rules this island is running — read-only, and the ONLY way out.
    ///
    /// Added by `M1`, when a domain's state accessors started needing the rules
    /// to answer at all: a quantity is addressed by a role, and the role→ordinal
    /// binding lives in `D::Rules`. Before that, `state()` was self-describing
    /// because every number was a struct field with a name on it — which is the
    /// arrangement `M1` removed.
    ///
    /// **`&` and not `Arc`, deliberately.** A caller that could clone the `Arc`
    /// could outlive an epoch switch holding the old rules and read state under
    /// them, which is the exact staleness `submit_epoch_switch` is ordered to
    /// prevent.
    pub fn rules(&self) -> &D::Rules {
        &self.rules
    }

    pub fn outcomes(&self) -> &[(Seq, Outcome<D>)] {
        &self.outcomes
    }

    pub fn ingress_len(&self) -> usize {
        self.ingress.len()
    }

    pub fn seen_len(&self) -> usize {
        self.seen.len()
    }

    pub fn buffered_len(&self) -> usize {
        self.buffered.len()
    }

    /// The kernel's observability surface — deterministic counters + peak
    /// gauges. The HOST emits these as real telemetry (DP-R8); tests assert
    /// they agree with the outcome log (a drift = a silent outcome path).
    pub fn metrics(&self) -> &IslandMetrics {
        &self.metrics
    }

    /// Drain effects that must LEAVE the island (SC-A4). sim-core never
    /// writes anything external itself (AGT-A6 / DP-A6).
    pub fn drain_proposals(&mut self) -> Vec<D::External> {
        std::mem::take(&mut self.externals)
    }
}
