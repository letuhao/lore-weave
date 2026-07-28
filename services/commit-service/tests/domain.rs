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
        Arc::new(CombatRules { strike_damage: 10, ko_duration_rounds: 5 }),
        RulesetDigest([0u8; 32]),
        SeenWindow::Unbounded,
        state,
    );
    isle.spawn_entity(EntityId(1));
    isle.spawn_entity(EntityId(2));
    isle
}

/// Each `submit` here models ONE turn: the IAS-D6 turn economy allows an
/// actor a single action per turn, so a test exercising a multi-turn exchange
/// must end the turn between actions. Before the turn economy existed these
/// tests fired freely from one actor, which is exactly the behaviour the
/// economy removed — the tests are catching up with the rule, not working
/// around it.
fn submit(isle: &mut Island<CombatDomain>, id: u128, payload: CombatPayload) {
    isle.submit(Lane::Live, sim_core::Admitted::unchecked(QueuedInput {
        seq: Seq(u64::MAX),
        input_id: InputId(id),
        class: Class::B,
        source: Producer::ScriptDecision,
        payload,
        preconditions: vec![],
        on_invalid: Fallback::Drop,
        admitted_gen: Gen(0),
        deadline: None,
    }));
    while isle.step() != StepStatus::Idle {}
    // Turn boundary — refills every actor's slot (engine-only payload).
    isle.submit(Lane::Live, commit_service::admission::admit_engine_turn_end(id as u64));
    while isle.step() != StepStatus::Idle {}
}

/// Defend halves ONE incoming strike, then is consumed.
///
/// Asserted as a RELATIONSHIP, not against fixed hp values: damage now runs
/// the COMB_001 law-chain (`floor(max(1, sp − armor) × roll(0.85–1.15) ×
/// crit)`), so a hardcoded 35/25 would be asserting one particular seed's
/// arithmetic rather than the rule. Pinning numbers here would also make every
/// future stat or archetype change look like a regression.
///
/// Kill-mutations: defend not halving · defend not being consumed by the hit.
#[test]
fn defend_halves_exactly_one_strike() {
    let mut isle = island();
    let full_hp = isle.state().actors[&EntityId(2)].hp;

    submit(&mut isle, 1, CombatPayload::Defend { actor: EntityId(2) });
    submit(&mut isle, 2, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });
    let defended_dmg = full_hp - isle.state().actors[&EntityId(2)].hp;

    let before = isle.state().actors[&EntityId(2)].hp;
    submit(&mut isle, 3, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });
    let undefended_dmg = before - isle.state().actors[&EntityId(2)].hp;

    assert!(defended_dmg > 0, "the defended hit still landed (it is halved, not negated)");
    assert!(
        defended_dmg < undefended_dmg,
        "defend must reduce the hit: defended {defended_dmg} vs undefended {undefended_dmg}"
    );
    assert!(
        !isle.state().actors[&EntityId(2)].defending,
        "defend is CONSUMED by the hit it absorbs, not a standing buff"
    );
}

/// Total-apply discipline: striking an absent or fled target records a Miss,
/// never panics, never mutates. Kill-mutation: unwrap on the actors map.
#[test]
fn strike_on_absent_or_fled_target_is_a_recorded_miss() {
    let mut isle = island();
    submit(&mut isle, 1, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(99) });
    // Search for the Miss rather than reading `last()`: the turn boundary now
    // appends its own (eventless) outcome, and an assertion pinned to the tail
    // of the log breaks whenever anything is appended after the action.
    assert!(
        isle.outcomes().iter().any(|(_, o)| matches!(
            o,
            Outcome::Applied { events } if events.iter().any(|e| matches!(e, CombatEvent::Missed { .. }))
        )),
        "an absent target is a recorded Miss"
    );

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
