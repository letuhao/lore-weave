//! The `Domain` impl: `apply`, `check`, and the island seams.
//!
//! **This file holds the ENGINE's half, never the LAWS' half.** The damage
//! chain, initiative and stat resolution live in `crates/game-rules` (IMP-A5);
//! what is here decides *when* to call them and what to record — which is why
//! `apply` is TOTAL and defensive while a law may assume its inputs.

use game_rules::combat::{
    action_value, evaluate_outcome, next_actor, resolve_attack, AvStatus, EncounterOutcome,
};
use ruleset_core::Ruleset;
use sim_core::{
    DetRng, Domain, EntityId, Precondition, PreconditionKind, QueuedInput, Violation,
};

use super::actor::Actor;
use super::payload::{CombatEvent, CombatPayload};
use super::state::{CombatResource, CombatState};

pub struct CombatDomain;

impl CombatDomain {
    /// Evaluate the COMB_001 end condition over current state.
    fn outcome_of(state: &CombatState) -> Option<EncounterOutcome> {
        evaluate_outcome(
            state
                .actors
                .values()
                .map(|a| (a.side, a.hp, a.fled))
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
            | CombatPayload::Flee { actor } => Some(*actor),
            CombatPayload::EndTurn => None,
        }
    }

}

impl Domain for CombatDomain {
    type Payload = CombatPayload;
    type State = CombatState;
    type Event = CombatEvent;
    type ResKind = CombatResource;
    type Rules = Ruleset;

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
        _rules: &Self::Rules,
        p: &Precondition<Self>,
    ) -> Result<(), Violation> {
        match p {
            Precondition::ResourceAtLeast { id, kind: CombatResource::TurnSlot, amount } => {
                let have = state.actors.get(id).map(|a| a.turn_slots).unwrap_or(0);
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
                    .filter(|(_, a)| a.alive())
                    .map(|(id, a)| (*id, a.av))
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
            && state.actors.get(&actor).is_some_and(|a| a.turn_slots >= 1)
            && state.outcome.is_none()
        {
            let spent = state.actors.get(&actor).map(|a| a.av).unwrap_or(0);
            for (id, a) in state.actors.iter_mut() {
                a.av = a.av.saturating_sub(spent);
                if *id == actor {
                    a.av = action_value(&rules.combat, a.stats.speed, a.status, false);
                }
            }
        }

        // A resolved encounter takes no further actions. Without this a
        // late-arriving proposal could damage corpses after Victory, and the
        // outcome event would already have been committed and fanned out.
        if state.outcome.is_some() && !matches!(input.payload, CombatPayload::EndTurn) {
            return Vec::new();
        }

        if let Some(actor) = Self::actor_of(&input.payload) {
            match state.actors.get_mut(&actor) {
                // Defence in depth: the kernel applies a `Substitute` with NO
                // preconditions (they "must be TOTAL/defensive in apply"), so
                // `apply` cannot assume `check_all` ran for this payload. An
                // out-of-budget actor therefore does nothing here, whatever
                // route the payload arrived by.
                Some(a) if a.turn_slots < 1 => return Vec::new(),
                Some(a) => a.turn_slots -= 1,
                None => return Vec::new(),
            }
        }
        match &input.payload {
            CombatPayload::Strike { attacker, target } => {
                // Read both stat blocks BEFORE mutating: the borrow checker
                // is right to object, and copying the blocks is also the
                // honest model — an attack resolves against the defender as
                // it stood when the blow landed.
                let Some(atk) = state.actors.get(attacker).map(|a| a.stats) else {
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                };
                let Some(def_actor) = state.actors.get(target) else {
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                };
                if !def_actor.alive() {
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                }
                let (def, defending) = (def_actor.stats, def_actor.defending);

                // COMB_001 §4 — the locked 4-step chain, on streams derived
                // from this action's own coordinates (Q8).
                let action_idx = state.next_action_idx;
                state.next_action_idx = state.next_action_idx.wrapping_add(1);
                let out = resolve_attack(
                    &rules.combat,
                    &atk,
                    &def,
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

                let t = state.actors.get_mut(target).expect("checked above");
                t.defending = false; // consumed by this hit
                t.hp = (t.hp - out.damage).max(0);
                let mut events = vec![CombatEvent::Struck {
                    attacker: *attacker,
                    target: *target,
                    damage: out.damage,
                    hp_left: t.hp,
                    crit: out.crit,
                    capped: out.capped,
                }];
                if t.hp == 0 && t.knocked_out.is_none() {
                    // KO, not death: revivable for `ko_duration_rounds`
                    // (COMB_001 AC-8). WA_006 mortality only applies once the
                    // encounter itself resolves to Defeat.
                    t.knocked_out = Some(rules.combat.ko_duration_rounds);
                    events.push(CombatEvent::Downed { target: *target });
                }
                if let Some(o) = Self::outcome_of(state) {
                    state.outcome = Some(o);
                    events.push(CombatEvent::EncounterEnded { outcome: o });
                }
                events
            }
            CombatPayload::Defend { actor } => match state.actors.get_mut(actor) {
                Some(a) if a.alive() => {
                    a.defending = true;
                    vec![CombatEvent::Defended { actor: *actor }]
                }
                _ => vec![],
            },
            CombatPayload::Move { actor, stance } => match state.actors.get_mut(actor) {
                Some(a) if a.alive() => {
                    a.stance = Some(*stance);
                    vec![CombatEvent::Moved { actor: *actor, stance: *stance }]
                }
                _ => vec![],
            },
            CombatPayload::Flee { actor } => match state.actors.get_mut(actor) {
                Some(a) if a.alive() => {
                    a.fled = true;
                    vec![CombatEvent::Fled { actor: *actor }]
                }
                _ => vec![],
            },
            // Engine-only turn boundary — refills every actor's slot. Emits no
            // event: it is bookkeeping, not a thing that happened in the
            // fiction, and narrating it would put "the turn ended" into a
            // player's combat log once per round forever.
            // The ROUND boundary. COMB_001 §4 puts status expiry here and
            // says why explicitly: PL_006 V1 has NO auto-expire mechanism at
            // all, so three documents were assuming one that did not exist and
            // a 3-round debuff would have been permanent. In-combat expiry is
            // COMB-owned and round-scoped.
            CombatPayload::EndTurn => {
                let mut events = Vec::new();
                state.round_number = state.round_number.saturating_add(1);

                for (id, a) in state.actors.iter_mut() {
                    a.turn_slots = 1;
                    // AV resets each round from the actor's own speed and
                    // whatever status it currently carries.
                    a.av = action_value(&rules.combat, a.stats.speed, a.status, false);

                    // Round-scoped statuses expire together, and the expiry is
                    // EMITTED — a debuff that vanishes silently is
                    // indistinguishable from one that never applied.
                    if a.status != AvStatus::default() {
                        a.status = AvStatus::default();
                        events.push(CombatEvent::StatusExpired { actor: *id });
                    }

                    if let Some(left) = a.knocked_out {
                        match left.checked_sub(1) {
                            Some(0) | None => {
                                // The revival window closed. The actor stays
                                // at 0 HP; permanence is WA_006's call at
                                // encounter end, not the engine's here.
                                a.knocked_out = Some(0);
                            }
                            Some(n) => a.knocked_out = Some(n),
                        }
                    }
                }
                if state.outcome.is_none()
                    && let Some(o) = Self::outcome_of(state)
                {
                    state.outcome = Some(o);
                    events.push(CombatEvent::EncounterEnded { outcome: o });
                }
                events
            }
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
        state.actors.remove(&id).unwrap_or_else(Actor::absent)
    }

    fn install(state: &mut Self::State, id: EntityId, portable: Self::Portable) {
        state.actors.insert(id, portable);
    }
}
