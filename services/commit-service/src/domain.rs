//! `CombatDomain` — the production combat domain's SEED (not `sim`'s
//! TestDomain, which stays a chaos harness). Minimal but total semantics for
//! the POC-2 vertical slice: strike / defend / move(stance) / flee, mirroring
//! `contracts/agent/vocabularies/combat_v1.json` one-to-one.
//!
//! Rules discipline: every `apply` is TOTAL and defensive — a cross-island
//! message or substitute arrives with no preconditions (sim-core contract),
//! so an absent/fled/downed target is a recorded miss, never a panic.

use std::collections::BTreeMap;

use sim_core::{PreconditionKind, DetRng, Domain, EntityId, Precondition, QueuedInput, Violation};

use crate::combat::{
    action_value, evaluate_outcome, next_actor, resolve_attack, AvStatus, CombatStats,
    EncounterOutcome, Side,
};
use crate::stats::StatSnapshot;

pub struct CombatDomain;

/// TG-A4 positioning intents (closed set — the model picks a stance, the
/// engine owns space; POC records the stance, the tactical grid is COMB_002).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Stance {
    Kite,
    Flank,
    Cover,
    Hold,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CombatPayload {
    Strike { attacker: EntityId, target: EntityId },
    Defend { actor: EntityId },
    Move { actor: EntityId, stance: Stance },
    Flee { actor: EntityId },
    /// IAS-D6 — engine-only turn boundary: refills every actor's turn slot.
    ///
    /// Submitted by the HOST, never reachable from the tool vocabulary, so no
    /// driver (player, LLM or script) can mint itself another action by
    /// asking for one. It is a payload rather than a host-side mutation
    /// because the domain is deliberately time-blind (`apply` sees no clock),
    /// and refilling through the normal input path keeps the refill inside
    /// the replayable, deterministic stream instead of beside it.
    EndTurn,
}

/// A domain fact. **Serialized into the committed payload as STRUCTURED JSON**
/// — never `format!("{:?}")`. A `Debug` rendering is not a contract: it has no
/// stability guarantee and changes the moment a field is added, so a consumer
/// parsing one is parsing a bug. Entity ids serialize as DECIMAL STRINGS
/// (CWC-A2) because the browser reads this payload directly.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum CombatEvent {
    Struck {
        #[serde(with = "entity_str")]
        attacker: EntityId,
        #[serde(with = "entity_str")]
        target: EntityId,
        damage: i64,
        hp_left: i64,
        /// Surfaced because a crit is the difference between "unlucky" and
        /// "the numbers are wrong" from the player's side. Hiding it makes
        /// legitimate variance look like a bug report.
        crit: bool,
    },
    /// Total-apply discipline: target absent/fled/down — recorded, not applied.
    Missed {
        #[serde(with = "entity_str")]
        attacker: EntityId,
        #[serde(with = "entity_str")]
        target: EntityId,
    },
    Defended {
        #[serde(with = "entity_str")]
        actor: EntityId,
    },
    Moved {
        #[serde(with = "entity_str")]
        actor: EntityId,
        stance: Stance,
    },
    Fled {
        #[serde(with = "entity_str")]
        actor: EntityId,
    },
    Downed {
        #[serde(with = "entity_str")]
        target: EntityId,
    },
    /// A round-scoped status lapsed at the round boundary. Emitted rather
    /// than applied silently: the client cannot render "slowed" wearing off
    /// if it never hears about it.
    StatusExpired {
        #[serde(with = "entity_str")]
        actor: EntityId,
    },
    /// The encounter resolved. Terminal — nothing further applies.
    EncounterEnded {
        outcome: crate::combat::EncounterOutcome,
    },
}

/// CWC-A2 at the event-body boundary: `EntityId` is a u64 server-side and must
/// cross the wire as a decimal string, exactly like the envelope ids.
mod entity_str {
    use serde::{Deserialize, Deserializer, Serializer};
    use sim_core::EntityId;

    pub fn serialize<S: Serializer>(id: &EntityId, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&id.0.to_string())
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<EntityId, D::Error> {
        let s = String::deserialize(d)?;
        s.parse::<u64>().map(EntityId).map_err(serde::de::Error::custom)
    }
}

// PartialEq only: `StatBlock` carries f64 (accuracy/dodge/crit), and floats
// have no total equality. Deriving Eq here would be a lie the compiler
// happens to catch.
#[derive(Debug, Clone, PartialEq)]
pub struct Actor {
    pub hp: i64,
    pub max_hp: i64,
    pub defending: bool,
    pub stance: Option<Stance>,
    pub fled: bool,
    /// COMB_001 Q5 — two sides in V1. Win/lose is evaluated per side, so an
    /// actor with no side could never be counted and the encounter could
    /// never end.
    pub side: Side,
    /// DF07 §8.1 — the block RESOLVED AT ENCOUNTER START, not read live.
    ///
    /// A progression tick or manifest reload mid-encounter would otherwise
    /// retroactively change how earlier rounds *should* have resolved,
    /// breaking replay of the encounter as a unit. And that is the normal
    /// case, not an exotic one: striking trains swordsmanship, and PROG_001
    /// trains on Action.
    pub snapshot: StatSnapshot,
    /// The combat-facing projection of `snapshot.stats` (DF07 §8.1 table).
    pub stats: CombatStats,
    /// HSR action value. LOWEST acts; reset on act (COMB_001 §4).
    pub av: i64,
    pub status: AvStatus,
    /// COMB_001: KO is REVIVABLE for a bounded number of rounds — it is not
    /// death. `Some(n)` counts rounds remaining before it becomes permanent.
    pub knocked_out: Option<u8>,
    /// IAS-D6 — the turn economy, as a RESOURCE rather than a timestamp.
    ///
    /// One slot per actor per turn; an action consumes it and `EndTurn`
    /// refills it. A resource works where a cooldown timestamp cannot: the
    /// domain never sees the clock, so "has it been long enough?" is not a
    /// question it can answer, while "do you still have your action?" is.
    ///
    /// This is the layer-3 defence of doc 22 §5 and the one that actually
    /// stops action spam. Layers 1-2 (transport rate limit, in-flight cap)
    /// shape traffic; only this one enforces the RULES of play, which is why
    /// it binds NPCs exactly as it binds players (IAS-A9).
    pub turn_slots: i64,
}

impl Actor {
    /// Slice-1 constructor: a melee archetype at `max_hp`, on side B.
    /// Kept so existing callers/tests compile unchanged; `with_side` is the
    /// one to use when the side matters.
    pub fn new(max_hp: i64) -> Self {
        Self::with_side(max_hp, Side::B)
    }

    pub fn with_side(max_hp: i64, side: Side) -> Self {
        let stats = CombatStats::archetype_melee(max_hp);
        Self {
            hp: max_hp,
            max_hp,
            defending: false,
            stance: None,
            fled: false,
            side,
            snapshot: StatSnapshot::default(),
            stats,
            av: action_value(stats.speed, AvStatus::default(), false),
            status: AvStatus::default(),
            knocked_out: None,
            turn_slots: 1,
        }
    }

    /// Able to act. A knocked-out actor is NOT alive for this purpose even
    /// though its KO is revivable — it holds a place in the encounter without
    /// holding a turn.
    pub fn alive(&self) -> bool {
        self.hp > 0 && !self.fled && self.knocked_out.is_none()
    }
}

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

/// RLS-A12 rules slice — resolved per reality, immutable, never in State.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CombatRules {
    /// Retained for compatibility with existing callers/tests. The real
    /// damage now comes from the COMB_001 law-chain over `StatBlock`; this is
    /// no longer consulted for a Strike.
    pub strike_damage: i64,
    /// COMB_001 AC-8 — how many rounds a KO stays revivable before it is
    /// permanent.
    pub ko_duration_rounds: u8,
}

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
    type Rules = CombatRules;
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
                    a.av = action_value(a.stats.speed, a.status, false);
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
                }];
                if t.hp == 0 && t.knocked_out.is_none() {
                    // KO, not death: revivable for `ko_duration_rounds`
                    // (COMB_001 AC-8). WA_006 mortality only applies once the
                    // encounter itself resolves to Defeat.
                    t.knocked_out = Some(rules.ko_duration_rounds);
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
                    a.av = action_value(a.stats.speed, a.status, false);

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
        state.actors.remove(&id).unwrap_or_else(|| Actor::new(0))
    }

    fn install(state: &mut Self::State, id: EntityId, portable: Self::Portable) {
        state.actors.insert(id, portable);
    }
}
