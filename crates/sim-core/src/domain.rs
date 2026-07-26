//! The `Domain` trait — the seam between scheduling (sim-core) and rules
//! (the game). Spec §4.0, plus the RLS-A12 `Rules` parameter.

use crate::rng::DetRng;
use crate::types::{Precondition, QueuedInput, Violation};

/// sim-core owns *scheduling*; the domain owns *rules*.
///
/// - `apply` MUST be deterministic and total — no I/O, no ambient clock;
///   randomness only via the seeded [`DetRng`]. It is only reachable through
///   the island's precondition check (structural: the island owns `State`).
/// - `Rules` (RLS-A12): the resolved, immutable per-reality ruleset slice this
///   domain reads. Passed by reference — never stored in `State`, so it never
///   enters checkpoints, migration payloads or crash rebuilds.
/// - `External` — S1a note: spec §4.0 names a bare `External` type it never
///   defines; promoted to an associated type here (plan deviation 2). These
///   are the effects that LEAVE the island and need commit-service
///   authorization (SC-A4): loot→inventory, xp→progression, cross-island.
pub trait Domain: Sized {
    type Payload: Clone + core::fmt::Debug;
    type State;
    type Event: Clone + core::fmt::Debug;
    type ResKind: Copy + Eq + core::fmt::Debug;
    type Rules;
    type External;

    /// Evaluate a SEMANTIC precondition (`ResourceAtLeast`, and the domain's
    /// own). The island never routes structural variants here.
    fn check(
        state: &Self::State,
        rules: &Self::Rules,
        p: &Precondition<Self>,
    ) -> Result<(), Violation>;

    /// Apply a VALIDATED input. Deterministic, total, pure.
    fn apply(
        state: &mut Self::State,
        rules: &Self::Rules,
        input: &QueuedInput<Self>,
        rng: &mut DetRng,
    ) -> Vec<Self::Event>;

    /// Which of these events leave the island (need external authorization).
    fn externals(events: &[Self::Event]) -> Vec<Self::External>;
}
