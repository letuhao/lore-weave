//! The encounter's shape: who is in it, whose turn it is, and the closed set
//! of budgets a driver may spend.

use std::collections::BTreeMap;

use game_rules::combat::EncounterOutcome;
use sim_core::EntityId;

use super::actor::Actor;

#[derive(Debug, Clone, PartialEq, Default)]
pub struct CombatState {
    pub actors: BTreeMap<EntityId, Actor>,
    /// COMB_001 Q8 — the per-encounter seed every roll derives from. Held in
    /// STATE rather than drawn from the island's stream so a roll depends on
    /// its own coordinates, not on how many draws happened first (see
    /// `combat::role_rng`).
    pub session_seed: u64,
    /// Monotonic per session; part of every roll's coordinate, so the same
    /// actor striking twice does not repeat the same numbers.
    pub next_action_idx: u32,
    pub round_number: u32,
    /// Set once the encounter ends. Its presence is what stops further
    /// actions resolving — a finished fight must not keep taking damage.
    pub outcome: Option<EncounterOutcome>,
}

// F1 — the domain's rules slice is now the RESOLVED RULESET (`ruleset_core::
// Ruleset`), digest-pinned, rather than a two-field struct owned by this file.
// RLS-A12's seam was already here; until F1 it carried almost nothing, so the
// digest that pins it to an event could not have detected a rules change.
//
// `strike_damage` was DELETED rather than migrated: its own doc-comment said
// "no longer consulted for a Strike" and grep confirmed zero reads. Carrying a
// field nobody reads into the hashed struct would let it change the digest —
// a rules change that changes no rule.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct NoResource;

/// IAS-D6 — the domain's semantic resources. A closed set, like every other
/// vocabulary here: an open-ended resource name would let a caller invent a
/// budget the rules never granted.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CombatResource {
    /// The right to act this turn. Consumed by any action, refilled by
    /// `CombatPayload::EndTurn`.
    TurnSlot,
    /// COMB_001 §4 — it is THIS actor's turn by HSR action value.
    ///
    /// Distinct from `TurnSlot`, and collapsing the two would be a real bug:
    /// the slot is an anti-abuse BUDGET (one action per actor per turn,
    /// IAS-D6), while initiative decides *whose turn it is at all*. An actor
    /// can hold an unspent slot and still not be up. Without this the queue
    /// is computed, displayed, and ignored — combat resolves in submission
    /// order while claiming to be initiative-based.
    Initiative,
}
