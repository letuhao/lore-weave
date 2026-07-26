//! CombatDomain bite-tests + the panic canary.

use std::sync::Arc;

use commit_service::{Actor, CombatDomain, CombatEvent, CombatPayload, CombatRules, CombatState};
use sim_core::{
    Class, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane, Outcome, Producer,
    QueuedInput, RulesetDigest, SeenWindow, Seq, StepStatus,
};

fn island() -> Island<CombatDomain> {
    let mut state = CombatState::default();
    state.actors.insert(EntityId(1), Actor::new(100));
    state.actors.insert(EntityId(2), Actor::new(40));
    let mut isle = Island::new(
        IslandId(1),
        7,
        Arc::new(CombatRules { strike_damage: 10 }),
        RulesetDigest([0u8; 32]),
        SeenWindow::Unbounded,
        state,
    );
    isle.spawn_entity(EntityId(1));
    isle.spawn_entity(EntityId(2));
    isle
}

fn submit(isle: &mut Island<CombatDomain>, id: u128, payload: CombatPayload) {
    isle.submit(Lane::Live, QueuedInput {
        seq: Seq(u64::MAX),
        input_id: InputId(id),
        class: Class::B,
        source: Producer::ScriptDecision,
        payload,
        preconditions: vec![],
        on_invalid: Fallback::Drop,
        admitted_gen: Gen(0),
        deadline: None,
    });
    while isle.step() != StepStatus::Idle {}
}

/// Kill-mutation: defend not halving / not resetting after one strike.
#[test]
fn defend_halves_exactly_one_strike() {
    let mut isle = island();
    submit(&mut isle, 1, CombatPayload::Defend { actor: EntityId(2) });
    submit(&mut isle, 2, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });
    assert_eq!(isle.state().actors[&EntityId(2)].hp, 35, "halved (5, not 10)");
    submit(&mut isle, 3, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });
    assert_eq!(isle.state().actors[&EntityId(2)].hp, 25, "defend consumed — full 10");
}

/// Total-apply discipline: striking an absent or fled target records a Miss,
/// never panics, never mutates. Kill-mutation: unwrap on the actors map.
#[test]
fn strike_on_absent_or_fled_target_is_a_recorded_miss() {
    let mut isle = island();
    submit(&mut isle, 1, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(99) });
    assert!(matches!(
        isle.outcomes().last().unwrap().1,
        Outcome::Applied { ref events } if matches!(events[0], CombatEvent::Missed { .. })
    ));

    submit(&mut isle, 2, CombatPayload::Flee { actor: EntityId(2) });
    submit(&mut isle, 3, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });
    let hp = isle.state().actors[&EntityId(2)].hp;
    assert_eq!(hp, 40, "a fled actor is untouchable");
}

/// Downed fires exactly at 0 hp, hp floors at 0. Kill-mutation: hp going
/// negative or Downed on every hit.
#[test]
fn downed_fires_once_at_zero() {
    let mut isle = island();
    for i in 0..5 {
        submit(&mut isle, 10 + i, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });
    }
    assert_eq!(isle.state().actors[&EntityId(2)].hp, 0);
    let downs = isle
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Applied { events } if events.iter().any(|e| matches!(e, CombatEvent::Downed { .. }))))
        .count();
    assert_eq!(downs, 1, "exactly one Downed, at the 0-crossing");
}

/// Fled leaves the island as an external (the SL-A12 handoff seam).
/// Kill-mutation: externals() returning everything or nothing.
#[test]
fn flee_emits_external() {
    let mut isle = island();
    submit(&mut isle, 1, CombatPayload::Flee { actor: EntityId(2) });
    let ext = isle.drain_proposals();
    assert_eq!(ext.len(), 1);
    assert!(matches!(ext[0], CombatEvent::Fled { actor } if actor == EntityId(2)));
}

/// The docs-14 §10.4 canary, HERE because THIS crate is the one that ships
/// under a custom profile: if commit-service is ever built/tested with
/// panic="abort", this dies visibly instead of containment silently dying
/// in production. (`release-commit` inherits release but sets unwind.)
#[test]
fn panic_canary_this_profile_unwinds() {
    assert!(
        std::panic::catch_unwind(|| panic!("canary")).is_err(),
        "profile must unwind — SC-A8 containment depends on it"
    );
}
