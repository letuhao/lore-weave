//! The `Domain` impl: `apply`, `check`, and the island seams.
//!
//! **This file holds the ENGINE's half, never the LAWS' half.** The damage
//! chain, initiative and stat resolution live in `crates/game-rules` (IMP-A5);
//! what is here decides *when* to call them and what to record — which is why
//! `apply` is TOTAL and defensive while a law may assume its inputs.
//!
//! ## `M1` — the laws read ROLES, not fields
//!
//! Every number this file touches now arrives as *the pool bound to
//! `EngineRole::X`*, resolved once per reality in [`super::binding`]. **No
//! quantity name appears here**, and that is the whole of what `M1` bought: an
//! author may call their vital anything at all, and the defeat law is unchanged
//! — which is `Q2`'s exit criterion, stated in `ruleset-core` when nothing could
//! express it.

use game_rules::combat::{
    action_value, evaluate_outcome, next_actor, resolve_attack, EncounterOutcome,
};
use sim_core::{
    DetRng, Domain, EntityId, Precondition, PreconditionKind, QueuedInput, Violation,
};

use super::actor::Actor;
use super::binding::RealityRules;
use super::payload::{CombatEvent, CombatPayload, RefusalReason};
use super::state::{CombatResource, CombatState};

pub struct CombatDomain;

impl CombatDomain {
    /// Evaluate the COMB_001 end condition over current state.
    pub(super) fn outcome_of(state: &CombatState, rules: &RealityRules) -> Option<EncounterOutcome> {
        evaluate_outcome(
            state
                .actors
                .values()
                .map(|a| (a.side, a.vital(rules), a.fled))
                .collect::<Vec<_>>()
                .into_iter(),
        )
    }

    /// IAS-D6 — the acting entity of a payload, or `None` for engine payloads.
    /// Separated out so slot accounting cannot drift per-arm as actions are
    /// added: a new action that forgot to spend the turn would be a free one.
    pub(crate) fn actor_of(p: &CombatPayload) -> Option<EntityId> {
        match p {
            CombatPayload::Strike { attacker, .. } => Some(*attacker),
            CombatPayload::Defend { actor }
            | CombatPayload::Move { actor, .. }
            | CombatPayload::Flee { actor }
            | CombatPayload::Declared { actor, .. } => Some(*actor),
            CombatPayload::EndTurn => None,
        }
    }
}

impl Domain for CombatDomain {
    type Payload = CombatPayload;
    type State = CombatState;
    type Event = CombatEvent;
    type ResKind = CombatResource;
    /// **`M1`** — the rules an island holds are the resolved ruleset PLUS the
    /// role→ordinal binding derived from it. The binding is not a second source
    /// of truth: it is a pure function of the ruleset, computed once, and it
    /// stays out of the digest (see [`RealityRules::digest`]).
    type Rules = RealityRules;

    /// RLS-A13 — BLAKE3 over the ruleset's canonical bytes. The island derives
    /// its pin through this, so the digest an island reports and the rules it
    /// actually runs cannot disagree.
    fn rules_digest(rules: &Self::Rules) -> sim_core::RulesetDigest {
        rules.digest()
    }
    /// `Fled` leaves the encounter island (the SL-A12 handoff seam).
    type External = CombatEvent;
    type Portable = Actor;

    /// IAS-D2/A3 — the in-loop half of validation. The island routes semantic
    /// preconditions here at STEP time, which is the only moment "does this
    /// actor still have its turn?" has a definite answer: checking it at
    /// admission would be a TOCTOU race, since the loop mutates exactly the
    /// state the check reads.
    fn check(
        state: &Self::State,
        rules: &Self::Rules,
        p: &Precondition<Self>,
    ) -> Result<(), Violation> {
        match p {
            Precondition::ResourceAtLeast { id, kind: CombatResource::TurnSlot, amount } => {
                let have = state.actors.get(id).map(|a| a.action_budget(rules)).unwrap_or(0);
                if have < *amount {
                    return Err(Violation {
                        kind: PreconditionKind::ResourceAtLeast,
                        entity: Some(*id),
                    });
                }
                Ok(())
            }
            Precondition::ResourceAtLeast { id, kind: CombatResource::Initiative, .. } => {
                // Lowest AV acts. Evaluated at STEP time against live state,
                // which is the only moment the answer is definite: an actor
                // that was next when the proposal was made may have been
                // stunned, hasted or killed since (IAS-A2 — this reads state
                // the loop mutates, so it belongs inside the loop).
                let queue: Vec<(EntityId, i64)> = state
                    .actors
                    .iter()
                    .filter(|(_, a)| a.alive(rules))
                    .map(|(id, a)| (*id, a.initiative(rules)))
                    .collect();
                match next_actor(&queue) {
                    Some(up) if up == *id => Ok(()),
                    // Nobody can act (all down/fled) — refuse rather than let
                    // an arbitrary actor through on an empty queue.
                    _ => Err(Violation {
                        kind: PreconditionKind::ResourceAtLeast,
                        entity: Some(*id),
                    }),
                }
            }
            // Structural variants (EntityAlive / IslandOwns / ...) are the
            // island's own registries; it never routes them here.
            _ => Ok(()),
        }
    }

    fn apply(
        state: &mut Self::State,
        rules: &Self::Rules,
        input: &QueuedInput<Self>,
        _rng: &mut DetRng,
    ) -> Vec<Self::Event> {
        // IAS-D6 — spend the turn slot BEFORE resolving. `apply` is only
        // reached once the island's `check_all` has already confirmed the
        // slot is there, so this is the consumption half of a check/consume
        // pair that both run inside the loop, under the single writer. There
        // is no window between them for a second action to slip through —
        // which is exactly what an admission-time check could not promise.
        // HSR queue advance: the acting actor's AV is subtracted from
        // EVERYONE, then the actor resets to its own base (COMB_001 §4 "reset
        // on act"). Adding the base to the actor instead — the obvious
        // shortcut — produces the wrong RATIO: with speeds 200 vs 100 the
        // faster actor should act twice per slow turn, and the additive form
        // makes them alternate. Speed then stops being a meaningful stat.
        //
        // Done BEFORE resolution so a KO'd actor still leaves the queue in a
        // consistent state.
        if let Some(actor) = Self::actor_of(&input.payload)
            && state.actors.get(&actor).is_some_and(|a| a.action_budget(rules) >= 1)
            && state.outcome.is_none()
        {
            let spent = state.actors.get(&actor).map(|a| a.initiative(rules)).unwrap_or(0);
            let ids: Vec<EntityId> = state.actors.keys().copied().collect();
            for id in ids {
                let (current, status) = {
                    let a = &state.actors[&id];
                    (a.initiative(rules), a.status)
                };
                let next = if id == actor {
                    action_value(&rules.rules().combat, rules.archetype().speed, status, false)
                } else {
                    current.saturating_sub(spent)
                };
                if let Some(a) = state.actors.get_mut(&id) {
                    a.set_initiative(rules, next);
                }
            }
        }

        // A resolved encounter takes no further actions. Without this a
        // late-arriving proposal could damage corpses after Victory, and the
        // outcome event would already have been committed and fanned out.
        //
        // **A DECLARED verb is refused rather than dropped** (`CMD-5`). The
        // legacy arms still return silence, and that is the pre-existing
        // behaviour `D-14` will rewrite; a declared verb has a reason ordinal
        // and a committed fact, so there is no excuse for it to vanish.
        if state.outcome.is_some() && !matches!(input.payload, CombatPayload::EndTurn) {
            return super::substrate::refuse_declared(&input.payload, RefusalReason::EncounterResolved);
        }

        if let Some(actor) = Self::actor_of(&input.payload) {
            // Defence in depth: the kernel applies a `Substitute` with NO
            // preconditions (they "must be TOTAL/defensive in apply"), so
            // `apply` cannot assume `check_all` ran for this payload. An
            // out-of-budget actor therefore does nothing here, whatever
            // route the payload arrived by.
            let budget = match state.actors.get(&actor) {
                Some(a) => a.action_budget(rules),
                // The submitter is not in this encounter. This is what made
                // `RefusalReason::ActorAbsent` DEAD CODE: the substrate had an
                // arm for it that nothing could reach, because `apply` returned
                // silence here first.
                None => return super::substrate::refuse_declared(&input.payload, RefusalReason::ActorAbsent),
            };
            if budget < 1 {
                // Out of turn budget — `NotActing`'s doc already names this case
                // and nothing could produce it.
                return super::substrate::refuse_declared(&input.payload, RefusalReason::NotActing);
            }
            if let Some(a) = state.actors.get_mut(&actor) {
                a.set_action_budget(rules, budget - 1);
            }
        }
        match &input.payload {
            CombatPayload::Strike { attacker, target } => {
                // The attacker's and defender's blocks are the REALITY's
                // archetype, read once. Before `M1` each actor stored its own
                // copy; they differed only in `CombatStats::max_hp`, which no
                // law reads — so the per-actor copy was 64 bytes of duplicated
                // ruleset and the "read both blocks before mutating" dance
                // protected a value that could not change.
                let stats = *rules.archetype();
                if state.actors.get(attacker).is_none() {
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                }
                let Some(def_actor) = state.actors.get(target) else {
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                };
                if !def_actor.alive(rules) {
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                }
                let defending = def_actor.defending;

                // COMB_001 §4 — the locked 4-step chain, on streams derived
                // from this action's own coordinates (Q8).
                let action_idx = state.next_action_idx;
                state.next_action_idx = state.next_action_idx.wrapping_add(1);
                let out = resolve_attack(
                    &rules.rules().combat,
                    &stats,
                    &stats,
                    defending,
                    state.session_seed,
                    *attacker,
                    action_idx,
                );

                if !out.hit {
                    // A miss is an EVENT, never a silent nothing (COMB_001 §4:
                    // "miss → damage 0 + MissEvent"). A player who saw nothing
                    // happen cannot tell a miss from a dropped action.
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                }

                let left = {
                    let t = state.actors.get_mut(target).expect("checked above");
                    t.defending = false; // consumed by this hit
                    let left = (t.vital(rules) - out.damage).max(0);
                    // The CLAMP is the caller's, deliberately: the hub carries a
                    // value and has no ceiling to clamp against (see
                    // `actor_hub::Actor::set_quantity`).
                    t.set_vital(rules, left);
                    left
                };
                let mut events = vec![CombatEvent::Struck {
                    attacker: *attacker,
                    target: *target,
                    damage: out.damage,
                    hp_left: left,
                    crit: out.crit,
                    capped: out.capped,
                }];
                let ko = {
                    let t = state.actors.get_mut(target).expect("checked above");
                    if left == 0 && t.knocked_out.is_none() {
                        // KO, not death: revivable for `ko_duration_rounds`
                        // (COMB_001 AC-8). WA_006 mortality only applies once
                        // the encounter itself resolves to Defeat.
                        t.knocked_out = Some(rules.rules().combat.ko_duration_rounds);
                        true
                    } else {
                        false
                    }
                };
                if ko {
                    events.push(CombatEvent::Downed { target: *target });
                }
                if let Some(o) = Self::outcome_of(state, rules) {
                    state.outcome = Some(o);
                    events.push(CombatEvent::EncounterEnded { outcome: o });
                }
                events
            }
            CombatPayload::Defend { actor } => {
                let can = state.actors.get(actor).is_some_and(|a| a.alive(rules));
                match state.actors.get_mut(actor) {
                    Some(a) if can => {
                        a.defending = true;
                        vec![CombatEvent::Defended { actor: *actor }]
                    }
                    _ => vec![],
                }
            }
            CombatPayload::Move { actor, stance } => {
                let can = state.actors.get(actor).is_some_and(|a| a.alive(rules));
                match state.actors.get_mut(actor) {
                    Some(a) if can => {
                        a.stance = Some(*stance);
                        vec![CombatEvent::Moved { actor: *actor, stance: *stance }]
                    }
                    _ => vec![],
                }
            }
            CombatPayload::Flee { actor } => {
                let can = state.actors.get(actor).is_some_and(|a| a.alive(rules));
                match state.actors.get_mut(actor) {
                    Some(a) if can => {
                        a.fled = true;
                        vec![CombatEvent::Fled { actor: *actor }]
                    }
                    _ => vec![],
                }
            }
            // ─── `M2` — THE DECLARED VERB. One arm for ALL of them, forever. ───
            //
            // `CMD-6`: *"the substrate never branches on the verb's name."* There
            // is no name in the payload and no `match` on one; the ordinal
            // indexes a table the REALITY declared. The resolution itself lives
            // in `substrate.rs` — this arm exists only to route to it, and it is
            // the LAST arm this file will ever gain for a verb.
            CombatPayload::Declared { verb, actor } => {
                super::substrate::resolve_declared(state, rules, *verb, *actor)
            }
            // Engine-only turn boundary — refills every actor's slot. Emits no
            // event: it is bookkeeping, not a thing that happened in the
            // fiction, and narrating it would put "the turn ended" into a
            // player's combat log once per round forever.
            // The ROUND boundary. COMB_001 §4 puts status expiry here and
            // says why explicitly: PL_006 V1 has NO auto-expire mechanism at
            // all, so three documents were assuming one that did not exist and
            // a 3-round debuff would have been permanent. In-combat expiry is
            // COMB-owned and round-scoped.
            CombatPayload::EndTurn => super::round::end_turn(state, rules),
        }
    }

    fn externals(events: &[Self::Event]) -> Vec<Self::External> {
        events
            .iter()
            .filter(|e| matches!(e, CombatEvent::Fled { .. }))
            .cloned()
            .collect()
    }

    fn extract(state: &mut Self::State, id: EntityId) -> Self::Portable {
        state.actors.remove(&id).unwrap_or_else(|| Actor::absent(id))
    }

    fn install(state: &mut Self::State, id: EntityId, portable: Self::Portable) {
        state.actors.insert(id, portable);
    }
}
