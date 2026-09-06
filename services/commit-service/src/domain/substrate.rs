//! **`M2` — the command substrate: how a DECLARED verb resolves.**
//!
//! > **Verbs are declared by FEATURES. The command substrate is the HUB that
//! > resolves them — and it knows nothing about what any of them MEAN.**
//!
//! Split out of `law.rs` at `IMP-D3`'s ceiling, and the seam is the one this
//! milestone is about rather than a line-count dodge: everything left in
//! `law.rs` is the LEGACY combat vocabulary that `D-14` slates for rewrite —
//! four hardcoded arms, one per verb — and everything here is the substrate,
//! which is **one function for every verb that will ever exist**.
//!
//! ## What this file may never contain
//!
//! A `match` on a verb NAME (`CMD-6`), or an arm per verb (`CMD-3`'s closure
//! rule). If either appears, the acceptance test
//! `adding_a_verb_touches_zero_files.rs` is false and the substrate has become
//! the thing it replaced.

use sim_core::EntityId;

use super::actor::Actor;
use super::binding::RealityRules;
use super::payload::{CombatEvent, CombatPayload, RefusalReason};
use super::state::CombatState;

/// Resolve one declared verb. **Every path commits a FACT** (`CMD-5`): a
/// refusal that is not committed is indistinguishable, from the log, from an
/// action that never arrived.
pub(super) fn resolve_declared(
    state: &mut CombatState,
    rules: &RealityRules,
    verb: u16,
    actor: EntityId,
) -> Vec<CombatEvent> {

let Some(decl) = rules.rules().verbs.get(verb).copied() else {
    return vec![CombatEvent::Refused {
        actor: actor,
        verb,
        reason: RefusalReason::UnknownVerb,
    }];
};
let refuse = |reason| {
    vec![CombatEvent::Refused { actor: actor, verb, reason }]
};

let Some(a) = state.actors.get(&actor) else {
    return refuse(RefusalReason::ActorAbsent);
};
if !a.alive(rules) {
    return refuse(RefusalReason::NotActing);
}

// LEGALITY — a declared THRESHOLD, evaluated, never scored
// (`D-29`). The engine owns the comparison; the author supplied
// the number.
if let Some(req) = decl.requires {
    let Some(have) = quantity_of(a, rules, req.quantity) else {
        return refuse(RefusalReason::RequirementUnmet);
    };
    if have < i64::from(req.at_least) {
        return refuse(RefusalReason::RequirementUnmet);
    }
}

// COST — taken BEFORE the effect, and NOT rolled back if the
// effect is refused (`O-CI-4`). A verb whose cost was paid and
// whose effect failed is a fact about a real attempt, not a
// transaction to undo.
if let Some(spend) = decl.spend {
    let Some(have) = quantity_of(a, rules, spend.quantity) else {
        return refuse(RefusalReason::CannotAfford);
    };
    // Affordability is judged against the pool's declared FLOOR, not against
    // zero. `ResourceDecl::min` is signed and its doc says a pool may model
    // debt; a hardcoded zero would make such a pool unspendable while the
    // reality says otherwise.
    let (floor, _) = rules.pool_bounds(spend.quantity).unwrap_or((0, i32::MAX));
    if have + i64::from(spend.amount) < i64::from(floor) {
        return refuse(RefusalReason::CannotAfford);
    }
    let next = have + i64::from(spend.amount);
    let Some(m) = state.actors.get_mut(&actor) else {
        return refuse(RefusalReason::ActorAbsent);
    };
    write_quantity(m, rules, spend.quantity, next);
}

// EFFECT — the ONE built door: a signed write to a declared
// quantity. `TargetRole::Other` cannot reach here; the build
// refuses it while the offer registry is unbuilt.
// ABSENT is refused, not read as zero. `unwrap_or(0)` here is what let a
// verb naming a pool-less quantity commit an `Acted` fact with a fabricated
// `left` while writing nothing — a committed LIE, which is worse than the
// silence it replaced. The boot refusal
// (`BindingError::VerbNamesUndeclaredPool`) makes this unreachable for a
// declared verb; it stays because a check whose only defence is another
// check's correctness is one edit from being wrong again.
let Some(before) =
    state.actors.get(&actor).and_then(|a| quantity_of(a, rules, decl.effect.quantity))
else {
    return refuse(RefusalReason::ActorAbsent);
};
// **CLAMPED against the pool's own declared bounds**, which is what
// `EffectRow::amount`'s doc always claimed and the code did not do: it was
// `.max(0)`, a hardcoded floor that ignored `ResourceDecl::min` and had no
// ceiling at all. A cold-start reviewer drove a pool of ceiling 100 to 15100
// with three submissions.
//
// The CALLER clamps, not the hub — see `actor_hub::Actor::set_quantity`: a
// ceiling is `QTY-A8`'s, bound to a derived stat a realm can raise, and the
// hub cannot see it. This is the caller.
let (min, ceiling) = rules
    .pool_bounds(decl.effect.quantity)
    .expect("a declared verb's effect names a declared pool -- refused at boot otherwise");
let left =
    (before + i64::from(decl.effect.amount)).clamp(i64::from(min), i64::from(ceiling));
if let Some(m) = state.actors.get_mut(&actor) {
    write_quantity(m, rules, decl.effect.quantity, left);
}

let mut events = vec![CombatEvent::Acted {
    actor: actor,
    verb,
    // `CMD-4` — the cue travels with the fact, on a channel of
    // its own. The engine carries it and never reads it.
    cue: decl.cue,
    quantity: decl.effect.quantity,
    delta: i64::from(decl.effect.amount),
    left,
}];
if let Some(o) = super::law::CombatDomain::outcome_of(state, rules) {
    state.outcome = Some(o);
    events.push(CombatEvent::EncounterEnded { outcome: o });
}
events
}

/// Read any declared quantity of an actor by ORDINAL.
///
/// The generic form the role accessors specialise. A declared verb may name any
/// quantity the reality declares, not only the three an engine law reads — so
/// the substrate needs the general read, and having it is what makes a verb's
/// effect independent of which roles happen to be bound.
fn quantity_of(a: &Actor, rules: &RealityRules, ordinal: u16) -> Option<i64> {
    let q = actor_hub::QuantityOrdinal::new(ordinal)?;
    a.quantity_by_ordinal(rules, q)
}

/// The write half. Refusals are the hub's and are already recorded there; a
/// caller here treats an absent quantity as nothing to do, because `apply` is
/// TOTAL and a cross-island substitute arrives with no preconditions.
fn write_quantity(a: &mut Actor, rules: &RealityRules, ordinal: u16, v: i64) {
    if let Some(q) = actor_hub::QuantityOrdinal::new(ordinal) {
        a.set_quantity_by_ordinal(rules, q, v);
    }
}

/// A refusal fact for a DECLARED verb, or silence for anything else.
///
/// **The three silent paths a cold-start reviewer measured, closed.** `apply`
/// returned an empty event vector for an out-of-budget actor, an absent actor
/// and a resolved encounter, so the spine committed `turn.resolved` carrying an
/// empty `events` array — a turn that resolved into nothing, which is precisely
/// the *"indistinguishable from an action that never arrived"* `CMD-5` forbids.
///
/// **The legacy arms are deliberately still silent**, and saying so is more
/// honest than quietly changing them: they are the combat vocabulary `D-14`
/// slates for rewrite, they have no reason ordinal, and giving them one would be
/// designing the rewrite from here. A declared verb has both, so it has no
/// excuse.
pub(super) fn refuse_declared(p: &CombatPayload, reason: RefusalReason) -> Vec<CombatEvent> {
    match p {
        CombatPayload::Declared { verb, actor } => {
            vec![CombatEvent::Refused { actor: *actor, verb: *verb, reason }]
        }
        _ => Vec::new(),
    }
}
