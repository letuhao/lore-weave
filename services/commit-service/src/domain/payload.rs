//! What a driver may ask for, and what the domain records having happened.
//!
//! Split out of `domain.rs` by `S2` (IMP-D3's 400-line ceiling). The vocabulary
//! and the events are one concern: both are the domain's CONTRACT with the
//! outside, and both are closed sets for the same reason.

use sim_core::EntityId;

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
    /// **`M2` — a DECLARED verb, named by its ordinal and nothing else.**
    ///
    /// There is no verb name in this variant and no arm per verb anywhere that
    /// reads it. That is `CMD-6`: *"binding a declared name to an engine
    /// operation is table-driven, not a `match` arm."* The name is resolved to
    /// an ordinal ONCE, on the submission path (`VerbTable::ordinal_of`), and
    /// the engine carries the ordinal from there.
    ///
    /// The four variants above are the legacy combat vocabulary `D-14` slates
    /// for rewrite; they keep their arms because none of them is expressible as
    /// a `Delta`, which is the only effect door the substrate has built.
    Declared { verb: u16, actor: EntityId },
}

/// Why a declared verb was refused — **a closed ENGINE set, carried as an
/// ordinal into a committed fact.**
///
/// `CMD-5`: the outcome is *"a committed fact either way — applied, or refused
/// with a reason."* A refusal that is not committed is indistinguishable, from
/// the log, from an action that never arrived; and a refusal whose reason is a
/// free string is one no consumer can branch on and no operator can count.
///
/// **The set is the engine's, and an author never adds to it**, for the reason
/// every closed set in this tier is closed: each member is a decision some
/// engine rule reached, so minting one would be minting a rule.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
#[repr(u8)]
pub enum RefusalReason {
    /// The ordinal names no verb in this reality's table. Reachable across an
    /// epoch switch: a submission stamped under the old rules can pop under new
    /// ones that declare fewer verbs.
    UnknownVerb = 0,
    /// The verb's declared threshold does not hold (`D-29` — a THRESHOLD, never
    /// a predicate grammar).
    RequirementUnmet = 1,
    /// The actor cannot pay the declared spend.
    CannotAfford = 2,
    /// The submitter is not in this encounter.
    ActorAbsent = 3,
    /// Down, fled, or out of turn budget — the actor holds a place in the
    /// encounter without holding a turn.
    NotActing = 4,
}

impl RefusalReason {
    /// Every member, so a consumer-side mirror can be checked against the enum
    /// rather than against a second list. `closed-set-gate` exists because Rust
    /// makes you HANDLE every variant but cannot make an array CONTAIN every
    /// variant.
    pub const ALL: [RefusalReason; 5] = [
        RefusalReason::UnknownVerb,
        RefusalReason::RequirementUnmet,
        RefusalReason::CannotAfford,
        RefusalReason::ActorAbsent,
        RefusalReason::NotActing,
    ];
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
        /// The declared per-hit ceiling bound, so `damage` is `MAX_HIT` rather
        /// than what the chain computed (XST-D2).
        ///
        /// Carried for exactly the reason `crit` is carried, one step further
        /// along the same axis: a crit says the numbers are swingy, this says
        /// the numbers are WRONG. Before this existed the chain saturated in
        /// `i64` and every oversized hit returned the same clipped number in
        /// silence — a degrade path absorbing a bug and reporting success, for
        /// the third time in this codebase. A ceiling that binds is now a fact
        /// in the committed log (CS-D5/EVT-L5: nothing silent).
        capped: bool,
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
    /// **`M2` — a declared verb resolved.** Carries the verb's ordinal, its
    /// declared CUE ordinal (`CMD-4` — that something must be SHOWN, on a
    /// channel of its own), and the quantity it moved.
    ///
    /// No verb NAME and no quantity name: a consumer that wants either resolves
    /// it against the reality's tables, which is the only place they are
    /// meaningful (`QTY-A14` — an ordinal is meaningless without its digest).
    Acted {
        #[serde(with = "entity_str")]
        actor: EntityId,
        verb: u16,
        cue: u16,
        quantity: u16,
        delta: i64,
        left: i64,
    },
    /// **`M2` / `CMD-5` — the refusal, as a committed fact.**
    ///
    /// A substrate that only commits its happy path has proved half of `CMD-5`.
    /// The reason is an ordinal from a closed engine set, so a consumer can
    /// branch on it and an operator can count it.
    Refused {
        #[serde(with = "entity_str")]
        actor: EntityId,
        verb: u16,
        reason: RefusalReason,
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

/// The wire tag of one `CombatEvent`, by an EXHAUSTIVE match.
///
/// This function exists to be un-skippable rather than to be called: adding a
/// ninth variant to [`CombatEvent`] fails to compile **here**, which forces the
/// author to the contract. The alternative — a hand-written list beside the
/// enum — is what `closed-set-gate` exists to catch, because Rust makes you
/// HANDLE every variant but cannot make an array CONTAIN every variant.
#[cfg(test)]
fn wire_tag(e: &CombatEvent) -> &'static str {
    match e {
        CombatEvent::Struck { .. } => "struck",
        CombatEvent::Missed { .. } => "missed",
        CombatEvent::Defended { .. } => "defended",
        CombatEvent::Moved { .. } => "moved",
        CombatEvent::Fled { .. } => "fled",
        CombatEvent::Downed { .. } => "downed",
        CombatEvent::StatusExpired { .. } => "status_expired",
        CombatEvent::Acted { .. } => "acted",
        CombatEvent::Refused { .. } => "refused",
        CombatEvent::EncounterEnded { .. } => "encounter_ended",
    }
}

#[cfg(test)]
mod mirror_tests {
    use super::*;
    use sim_core::EntityId;

    /// `FATAL-1`. The `CombatEvent` tags must be exactly
    /// `turn.schema.json#/$defs/DomainEvent`'s closed enum.
    ///
    /// **There was no such assertion**, while a comment on the TypeScript
    /// consumer claimed the set was *"asserted in the tests rather than
    /// trusted"*. It was not: the tests asserted `OutcomeKind` and
    /// `DiscardReason`. Under that comment the two sides reached **8 against
    /// 6** — `status_expired` and `encounter_ended` had no consumer arm, so
    /// `renderEvent` returned `undefined` for facts the log really contains.
    ///
    /// Kill-mutation: delete a variant's arm from the schema enum, or add a
    /// ninth variant — the first reds here, the second stops compiling in
    /// [`wire_tag`].
    #[test]
    fn combat_event_tags_match_the_schema_enum() {
        let schema: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../contracts/game-wire/turn.schema.json"
        ))
        .expect("schema parses");
        let allowed: Vec<String> = schema["$defs"]["DomainEventType"]["enum"]
            .as_array()
            .expect("DomainEventType is a closed enum in the schema")
            .iter()
            .map(|v| v.as_str().unwrap().to_string())
            .collect();

        let e = EntityId(1);
        // One value per variant. Constructed rather than listed, so the tag
        // comes from `wire_tag`'s exhaustive match and not from a second list
        // that could drift from the first.
        let all = [
            CombatEvent::Struck {
                attacker: e,
                target: e,
                damage: 1,
                hp_left: 1,
                crit: false,
                capped: false,
            },
            CombatEvent::Missed { attacker: e, target: e },
            CombatEvent::Defended { actor: e },
            CombatEvent::Moved { actor: e, stance: Stance::Hold },
            CombatEvent::Fled { actor: e },
            CombatEvent::Downed { target: e },
            CombatEvent::StatusExpired { actor: e },
            CombatEvent::Acted { actor: e, verb: 0, cue: 1, quantity: 0, delta: -3, left: 97 },
            CombatEvent::Refused { actor: e, verb: 0, reason: RefusalReason::CannotAfford },
            CombatEvent::EncounterEnded { outcome: game_rules::combat::EncounterOutcome::Victory },
        ];

        assert_eq!(all.len(), allowed.len(), "schema and Rust enum must have the same arity");
        for ev in &all {
            let tag = wire_tag(ev);
            assert!(allowed.contains(&tag.to_string()), "{tag} is not in the schema enum");
            // The tag the match names and the tag serde emits must agree —
            // otherwise the exhaustive match guards a string nobody sends.
            let json = serde_json::to_value(ev).unwrap();
            assert_eq!(json["type"].as_str().unwrap(), tag, "serde tag disagrees with wire_tag");
        }
    }

    /// **`M2`** — the same mirror for `RefusalReason`, and it is the reason
    /// `ALL` exists: Rust makes you HANDLE every variant but cannot make an
    /// array CONTAIN every variant, so the list and the enum are checked against
    /// the CONTRACT rather than against each other.
    ///
    /// That is `FATAL-1`'s root cause, stated: the two languages were joined to
    /// one another with no contract between them, under a comment claiming the
    /// set was *"asserted in the tests"*, and they reached 8 against 6.
    #[test]
    fn refusal_reasons_match_the_schema_enum() {
        let schema: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../contracts/game-wire/turn.schema.json"
        ))
        .unwrap();
        let allowed: Vec<String> = schema["$defs"]["RefusalReason"]["enum"]
            .as_array()
            .expect("RefusalReason is a closed enum in the schema")
            .iter()
            .map(|v| v.as_str().unwrap().to_string())
            .collect();
        assert_eq!(RefusalReason::ALL.len(), allowed.len(), "same arity");
        for r in RefusalReason::ALL {
            let wire = serde_json::to_value(r).unwrap();
            assert!(
                allowed.contains(&wire.as_str().unwrap().to_string()),
                "{wire:?} is not in the schema enum"
            );
        }
    }

    /// The `EncounterOutcome` strings must also be inside the contract, since
    /// `encounter_ended` carries one and the consumer switches on it.
    #[test]
    fn encounter_outcomes_match_the_schema_enum() {
        let schema: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../contracts/game-wire/turn.schema.json"
        ))
        .unwrap();
        let allowed: Vec<String> = schema["$defs"]["EncounterOutcome"]["enum"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap().to_string())
            .collect();
        use game_rules::combat::EncounterOutcome::*;
        assert_eq!(allowed.len(), 3);
        for o in [Victory, Defeat, Disengaged] {
            let wire = serde_json::to_value(o).unwrap();
            assert!(allowed.contains(&wire.as_str().unwrap().to_string()), "{wire:?} missing");
        }
    }
}
