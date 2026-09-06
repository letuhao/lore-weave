//! The ROUND boundary — what happens between turns.
//!
//! Split out of `law.rs` at `IMP-D3`'s ceiling. The seam is a real one and the
//! file itself says so: `EndTurn` is *"bookkeeping, not a thing that happened in
//! the fiction"*. Everything left in `law.rs` resolves a submitted ACTION;
//! everything here runs on the clock's own beat and belongs to nobody's
//! submission — which is also why `EndTurn` is host-only and unreachable from
//! any tool vocabulary (`IAS-D6`).

use game_rules::combat::{action_value, AvStatus};
use sim_core::EntityId;

use super::binding::RealityRules;
use super::payload::CombatEvent;
use super::state::CombatState;

/// `COMB_001 §4` — advance the round: refill every budget, reset initiative,
/// expire round-scoped statuses, and count down a revival window.
pub(super) fn end_turn(state: &mut CombatState, rules: &RealityRules) -> Vec<CombatEvent> {

let mut events = Vec::new();
state.round_number = state.round_number.saturating_add(1);

let ids: Vec<EntityId> = state.actors.keys().copied().collect();
for id in ids {
    // The refill value is the reality's declared `base`, not a
    // hardcoded 1: a reality that grants two actions a turn
    // says so in content.
    let refill = rules.hub().action_budget_base() as i64;
    let status = state.actors[&id].status;
    // AV resets each round from the reality's speed and
    // whatever status the actor currently carries.
    let av =
        action_value(&rules.rules().combat, rules.archetype().speed, status, false);
    let Some(a) = state.actors.get_mut(&id) else { continue };
    a.set_action_budget(rules, refill);
    a.set_initiative(rules, av);

    // Round-scoped statuses expire together, and the expiry is
    // EMITTED — a debuff that vanishes silently is
    // indistinguishable from one that never applied.
    if a.status != AvStatus::default() {
        a.status = AvStatus::default();
        events.push(CombatEvent::StatusExpired { actor: id });
    }

    if let Some(left) = a.knocked_out {
        match left.checked_sub(1) {
            Some(0) | None => {
                // The revival window closed. The actor stays
                // at 0 vital; permanence is WA_006's call at
                // encounter end, not the engine's here.
                a.knocked_out = Some(0);
            }
            Some(n) => a.knocked_out = Some(n),
        }
    }
}
if state.outcome.is_none()
    && let Some(o) = super::law::CombatDomain::outcome_of(state, rules)
{
    state.outcome = Some(o);
    events.push(CombatEvent::EncounterEnded { outcome: o });
}
events
}
