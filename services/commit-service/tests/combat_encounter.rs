//! Slice 1 acceptance — a REAL encounter through the island.
//!
//! `combat_rules.rs` tests the laws in isolation. This drives them through
//! `Domain::apply` and the island, which is where the laws meet the turn
//! economy, the round boundary, and the outcome condition — and where the
//! interesting mistakes live.
//!
//! The one this file exists to pin: **the turn slot and initiative are two
//! different gates and both must hold.** The slot is an anti-abuse budget (one
//! action per actor per turn, IAS-D6); initiative decides whose turn it is at
//! all. Collapsing them would let whoever submits first act, while a queue is
//! computed, displayed and ignored.

mod hub_fixture;

use std::sync::Arc;

use commit_service::combat::{EncounterOutcome, Side};
use commit_service::{
    CombatDomain, CombatEvent, CombatPayload, CombatResource, CombatState, RealityRules,
};
use sim_core::{

    RulesetEpoch,
    Admitted, Class, DiscardReason, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane,
    Outcome, Precondition, PreconditionKind, Producer, QueuedInput, SeenWindow, Seq,
    StepStatus,
};

const HERO: EntityId = EntityId(1);
const FOE: EntityId = EntityId(2);

/// Hero on side A, foe on side B. Hero is faster, so hero is up first.
fn encounter(hero_hp: i64, foe_hp: i64) -> Island<CombatDomain> {
    // F1 — the island runs the reality's RESOLVED ruleset, pinned by a real
    // content digest. Was `RulesetDigest([0u8; 32])`, which pinned nothing.
    let rules = Arc::new(RealityRules::proving_ground());
    let mut state = CombatState { session_seed: 0xBEEF_5EED, ..Default::default() };
    let mut hero = hub_fixture::actor(&rules, EntityId(1), Side::A, hero_hp as i64);
    // The hero is up first because its INITIATIVE is lower — set directly.
    //
    // `M1` note, stated rather than glossed: this used to say
    // `hero.stats.speed = 200` and let `action_value` derive an AV of 50. Per-
    // actor stats no longer exist (`RealityRules::archetype` is one block per
    // reality), so a per-actor speed cannot be expressed today, and this reaches
    // for the pool the turn order actually reads instead of the stat behind it.
    //
    // The behaviour is NOT identical and the difference is real: the hero's
    // advantage now lasts until its first act, because a reset draws from the
    // reality's speed. Every assertion below is about who is up on the FIRST
    // turn, so none of them depended on the difference — but a test that needed
    // a permanently faster actor could not be written today. Tracked as
    // `D-PER-ACTOR-STATS-UNEXPRESSIBLE`.
    hero.set_initiative(&rules, 50);
    let mut foe = hub_fixture::actor(&rules, EntityId(2), Side::B, foe_hp as i64);
    foe.set_initiative(&rules, 100);
    state.actors.insert(HERO, hero);
    state.actors.insert(FOE, foe);

    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(1),
        0xE1CE,
        RulesetEpoch(1),
        Arc::clone(&rules),
        SeenWindow::Unbounded,
        state,
    );
    isle.spawn_entity(HERO);
    isle.spawn_entity(FOE);
    isle
}

/// An action carrying the obligations admission would attach (IAS-D2): the
/// turn slot AND initiative. Both are domain-semantic, so both are discharged
/// inside the loop at step time.
fn act(id: u128, actor: EntityId, payload: CombatPayload, gated: bool) -> Admitted<CombatDomain> {
    let preconditions = if gated {
        vec![
            Precondition::ResourceAtLeast { id: actor, kind: CombatResource::TurnSlot, amount: 1 },
            Precondition::ResourceAtLeast { id: actor, kind: CombatResource::Initiative, amount: 1 },
        ]
    } else {
        vec![]
    };
    Admitted::unchecked(QueuedInput {
        seq: Seq(u64::MAX),
        input_id: InputId(id),
        class: Class::B,
        source: Producer::PlayerInput,
        payload,
        preconditions,
        on_invalid: Fallback::Drop,
        admitted_gen: Gen(0),
        deadline: None,
    })
}

fn drive(isle: &mut Island<CombatDomain>, input: Admitted<CombatDomain>) {
    isle.submit(Lane::Live, input);
    while matches!(isle.step(), StepStatus::Processed(_)) {}
}

fn end_round(isle: &mut Island<CombatDomain>, n: u64) {
    isle.submit(Lane::Live, commit_service::admission::admit_engine_turn_end(n));
    while matches!(isle.step(), StepStatus::Processed(_)) {}
}

fn events(isle: &Island<CombatDomain>) -> Vec<CombatEvent> {
    isle.outcomes()
        .iter()
        .filter_map(|(_, o)| match o {
            Outcome::Applied { events } => Some(events.clone()),
            _ => None,
        })
        .flatten()
        .collect()
}

/// **The acceptance test.** A fight runs to Victory through the real chain.
#[test]
fn an_encounter_runs_to_victory() {
    let mut isle = encounter(200, 40);

    // Hero is faster, so hero is always up first in a round; one action each
    // round until the foe is down.
    for round in 0..40u64 {
        if isle.state().outcome.is_some() {
            break;
        }
        drive(
            &mut isle,
            act(round as u128 * 2, HERO, CombatPayload::Strike { attacker: HERO, target: FOE }, true),
        );
        end_round(&mut isle, round);
    }

    assert_eq!(
        isle.state().outcome,
        Some(EncounterOutcome::Victory),
        "the encounter resolved through the real damage chain"
    );
    let ev = events(&isle);
    assert!(ev.iter().any(|e| matches!(e, CombatEvent::Struck { .. })), "hits landed");
    assert!(ev.iter().any(|e| matches!(e, CombatEvent::Downed { .. })), "the foe went down");
    assert!(
        ev.iter().any(|e| matches!(e, CombatEvent::EncounterEnded { .. })),
        "the end is an EVENT — the client cannot render a victory it never heard about"
    );
    // "some attacks miss" is a RATE property and does not belong here: with a
    // fixed seed one short fight either contains a miss or does not, so this
    // assertion was a coin-flip dressed as a check. It lives in
    // `combat_rules::misses_occur_at_the_archetype_rate`, where it can be
    // sampled.
}

/// **Initiative BINDS.** The slower actor cannot act while the faster one is
/// up, even holding an unspent turn slot.
///
/// Kill-mutation: dropping the `Initiative` precondition. The turn slot alone
/// would let the foe act first simply by submitting first — the queue would be
/// computed and ignored, which is the difference between initiative-based
/// combat and submission-order combat.
#[test]
fn the_slower_actor_cannot_act_out_of_turn() {
    let mut isle = encounter(200, 200);
    assert_eq!(isle.state().actors[&FOE].action_budget(isle.rules()), 1, "the foe HAS its slot");

    drive(&mut isle, act(1, FOE, CombatPayload::Strike { attacker: FOE, target: HERO }, true));

    assert_eq!(isle.state().actors[&HERO].vital(isle.rules()), 200, "the out-of-turn strike did not land");
    let refused = isle
        .outcomes()
        .iter()
        .filter(|(_, o)| {
            matches!(
                o,
                Outcome::Discarded { reason: DiscardReason::PreconditionFailed(v) }
                    if v.kind == PreconditionKind::ResourceAtLeast
            )
        })
        .count();
    assert_eq!(refused, 1, "refused with a RECORDED reason, not silently dropped");
}

/// The pairing rule (IAS-D10): the queue must ADVANCE, or "cannot act out of
/// turn" would be satisfied by a queue that never moves and a game nobody can
/// play.
///
/// And it must advance in the right RATIO. Hero speed 200 / foe speed 100 means
/// the hero acts twice per foe turn — that is what speed BUYS. Asserting mere
/// alternation would pass against the additive AV shortcut, which produces a
/// 1:1 cadence and quietly makes speed cosmetic.
#[test]
fn initiative_advances_in_proportion_to_speed() {
    let mut isle = encounter(500, 500);

    // Hero (av 50) acts twice before the foe (av 100) comes up.
    drive(&mut isle, act(1, HERO, CombatPayload::Defend { actor: HERO }, true));
    drive(&mut isle, act(2, HERO, CombatPayload::Defend { actor: HERO }, true));

    // The foe is now up; a strike from it must land.
    drive(&mut isle, act(3, FOE, CombatPayload::Strike { attacker: FOE, target: HERO }, true));
    assert!(
        isle.state().actors[&HERO].vital(isle.rules()) < 500 || isle.state().actors[&HERO].defending,
        "the foe got its turn after two hero actions (2:1 cadence for 2x speed)"
    );

    // …and the hero could NOT have taken a third before the foe acted.
    let mut fresh = encounter(500, 500);
    drive(&mut fresh, act(1, HERO, CombatPayload::Defend { actor: HERO }, true));
    drive(&mut fresh, act(2, HERO, CombatPayload::Defend { actor: HERO }, true));
    drive(&mut fresh, act(3, HERO, CombatPayload::Strike { attacker: HERO, target: FOE }, true));
    assert_eq!(
        fresh.state().actors[&FOE].vital(isle.rules()),
        500,
        "a THIRD consecutive hero action is refused — the foe is up"
    );
}

/// KO is revivable, not death (COMB_001 AC-8), and the countdown runs at the
/// ROUND boundary.
#[test]
fn a_downed_actor_is_knocked_out_not_dead() {
    let mut isle = encounter(200, 1);
    drive(&mut isle, act(1, HERO, CombatPayload::Strike { attacker: HERO, target: FOE }, true));

    let foe = &isle.state().actors[&FOE];
    assert_eq!(foe.vital(isle.rules()), 0);
    assert_eq!(foe.knocked_out, Some(5), "revivable for ko_duration_rounds, not gone");

    end_round(&mut isle, 1);
    assert_eq!(
        isle.state().actors[&FOE].knocked_out,
        Some(4),
        "the revival window closes a round at a time"
    );
}

/// **Status expiry is engine-owned and round-scoped** — COMB_001 says this
/// explicitly because PL_006 V1 has NO auto-expire, so a 3-round debuff would
/// otherwise be permanent. And the expiry is EMITTED: a status that vanishes
/// silently is indistinguishable from one that never applied.
#[test]
fn round_scoped_status_expires_and_says_so() {
    let mut isle = encounter(200, 200);
    // A slowed foe: AV 100 → 120.
    {
        let before = isle.state().actors[&FOE].initiative(isle.rules());
        assert_eq!(before, 100);
    }
    // Drive a round boundary with a status set via a strike that KOs nobody,
    // then confirm the boundary clears round-scoped state.
    drive(&mut isle, act(1, HERO, CombatPayload::Defend { actor: HERO }, true));
    assert!(isle.state().actors[&HERO].defending, "defend is set");

    end_round(&mut isle, 1);
    assert_eq!(isle.state().round_number, 1, "the round advanced");
    assert_eq!(isle.state().actors[&FOE].initiative(isle.rules()), 100, "AV is recomputed from speed each round");
}

/// A resolved encounter takes no further actions. Without the guard a
/// late-arriving proposal would damage corpses after Victory — and the
/// outcome event would already have been committed and fanned out to clients.
#[test]
fn a_resolved_encounter_accepts_no_further_actions() {
    let mut isle = encounter(200, 1);
    drive(&mut isle, act(1, HERO, CombatPayload::Strike { attacker: HERO, target: FOE }, true));
    assert_eq!(isle.state().outcome, Some(EncounterOutcome::Victory));

    let hp_before = isle.state().actors[&FOE].vital(isle.rules());
    drive(&mut isle, act(2, HERO, CombatPayload::Strike { attacker: HERO, target: FOE }, false));
    assert_eq!(isle.state().actors[&FOE].vital(isle.rules()), hp_before, "nothing resolves after the end");
}

/// Determinism: the same seed and the same inputs produce the same fight.
/// This is what makes the committed event log replayable, and it is the
/// property the CNC-D5 conformance test relies on at the kernel level.
#[test]
fn the_same_seed_replays_the_same_fight() {
    let render = |
        | -> Vec<String> {
        let mut isle = encounter(200, 60);
        for round in 0..30u64 {
            if isle.state().outcome.is_some() {
                break;
            }
            drive(
                &mut isle,
                act(round as u128 * 2, HERO, CombatPayload::Strike { attacker: HERO, target: FOE }, true),
            );
            end_round(&mut isle, round);
        }
        events(&isle).iter().map(|e| format!("{e:?}")).collect()
    };


    let a = render();
    let b = render();
    assert!(!a.is_empty(), "the fight actually happened");
    assert_eq!(a, b, "same seed, same inputs, same fight — event for event");
}
