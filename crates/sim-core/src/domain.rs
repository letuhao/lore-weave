//! The `Domain` trait — the seam between scheduling (sim-core) and rules
//! (the game). Spec §4.0, plus the RLS-A12 `Rules` parameter.

use crate::rng::DetRng;
use crate::types::{EntityId, Precondition, QueuedInput, RulesetDigest, Violation};

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
    /// S2 handoff payload (SL-A12 `EntityDeparted` → `EntityArrived`): the
    /// domain-owned slice of one entity's state, extracted on departure and
    /// installed on arrival. The kernel moves it; it never looks inside.
    type Portable: Clone + core::fmt::Debug;

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

    /// The content digest of `rules` (RLS-A13).
    ///
    /// **The island DERIVES its digest through this; it can no longer be
    /// passed in.** `Island::new` used to take `rules: Arc<D::Rules>` and
    /// `digest: RulesetDigest` as two independent parameters with nothing
    /// tying them together — so an island could claim a digest that did not
    /// describe the rules it was running, which is *precisely* the divergence
    /// the digest exists to detect, made possible inside the mechanism meant
    /// to prevent it. A pair that must agree should not be two arguments.
    ///
    /// The kernel keeps its zero-runtime-dependency invariant: this is a
    /// function the DOMAIN supplies. `CombatDomain` answers with
    /// `ruleset_core::Ruleset::digest()`; a harness domain whose rules are a
    /// struct invented by a test answers `RulesetDigest::UNPINNED`, which is
    /// the honest answer and now lives in one impl instead of at every
    /// construction site.
    fn rules_digest(rules: &Self::Rules) -> RulesetDigest;

    /// Which of these events leave the island (need external authorization).
    fn externals(events: &[Self::Event]) -> Vec<Self::External>;

    /// S2 handoff: remove `id`'s domain state and return it as a portable
    /// payload. TOTAL — an entity with no domain rows yet still departs (the
    /// portable encodes the empty case). Only called by `Island::depart`,
    /// which gates on registry ownership first.
    fn extract(state: &mut Self::State, id: EntityId) -> Self::Portable;

    /// S2 handoff: install a departed entity's state on the arrival island.
    /// Deterministic; must be the inverse of `extract`.
    fn install(state: &mut Self::State, id: EntityId, portable: Self::Portable);
}
