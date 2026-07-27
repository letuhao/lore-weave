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

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Actor {
    pub hp: i64,
    pub max_hp: i64,
    pub defending: bool,
    pub stance: Option<Stance>,
    pub fled: bool,
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
    pub fn new(max_hp: i64) -> Self {
        Self { hp: max_hp, max_hp, defending: false, stance: None, fled: false, turn_slots: 1 }
    }

    pub fn alive(&self) -> bool {
        self.hp > 0 && !self.fled
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct CombatState {
    pub actors: BTreeMap<EntityId, Actor>,
}

/// RLS-A12 rules slice — resolved per reality, immutable, never in State.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CombatRules {
    pub strike_damage: i64,
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
}


impl CombatDomain {
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
                let Some(t) = state.actors.get_mut(target) else {
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                };
                if !t.alive() {
                    return vec![CombatEvent::Missed { attacker: *attacker, target: *target }];
                }
                // Defend halves ONE incoming strike, then resets.
                let damage = if t.defending { rules.strike_damage / 2 } else { rules.strike_damage };
                t.defending = false;
                t.hp = (t.hp - damage).max(0);
                let mut events = vec![CombatEvent::Struck {
                    attacker: *attacker,
                    target: *target,
                    damage,
                    hp_left: t.hp,
                }];
                if t.hp == 0 {
                    events.push(CombatEvent::Downed { target: *target });
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
            CombatPayload::EndTurn => {
                for a in state.actors.values_mut() {
                    a.turn_slots = 1;
                }
                vec![]
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
