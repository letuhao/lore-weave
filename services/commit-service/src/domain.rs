//! `CombatDomain` — the production combat domain's SEED (not `sim`'s
//! TestDomain, which stays a chaos harness). Minimal but total semantics for
//! the POC-2 vertical slice: strike / defend / move(stance) / flee, mirroring
//! `contracts/agent/vocabularies/combat_v1.json` one-to-one.
//!
//! Rules discipline: every `apply` is TOTAL and defensive — a cross-island
//! message or substitute arrives with no preconditions (sim-core contract),
//! so an absent/fled/downed target is a recorded miss, never a panic.

use std::collections::BTreeMap;

use sim_core::{DetRng, Domain, EntityId, Precondition, QueuedInput, Violation};

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
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CombatEvent {
    Struck { attacker: EntityId, target: EntityId, damage: i64, hp_left: i64 },
    /// Total-apply discipline: target absent/fled/down — recorded, not applied.
    Missed { attacker: EntityId, target: EntityId },
    Defended { actor: EntityId },
    Moved { actor: EntityId, stance: Stance },
    Fled { actor: EntityId },
    Downed { target: EntityId },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Actor {
    pub hp: i64,
    pub max_hp: i64,
    pub defending: bool,
    pub stance: Option<Stance>,
    pub fled: bool,
}

impl Actor {
    pub fn new(max_hp: i64) -> Self {
        Self { hp: max_hp, max_hp, defending: false, stance: None, fled: false }
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

impl Domain for CombatDomain {
    type Payload = CombatPayload;
    type State = CombatState;
    type Event = CombatEvent;
    type ResKind = NoResource;
    type Rules = CombatRules;
    /// `Fled` leaves the encounter island (the SL-A12 handoff seam).
    type External = CombatEvent;
    type Portable = Actor;

    fn check(
        _state: &Self::State,
        _rules: &Self::Rules,
        _p: &Precondition<Self>,
    ) -> Result<(), Violation> {
        // POC domain has no semantic resources; structural preconditions
        // (EntityAlive/IslandOwns/...) are the island's job.
        Ok(())
    }

    fn apply(
        state: &mut Self::State,
        rules: &Self::Rules,
        input: &QueuedInput<Self>,
        _rng: &mut DetRng,
    ) -> Vec<Self::Event> {
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
