//! CombatDomain bite-tests + the panic canary.

mod hub_fixture;

use std::sync::Arc;

use commit_service::combat::Side;
use commit_service::{Actor, CombatDomain, CombatEvent, CombatPayload, CombatState, RealityRules};
use sim_core::{

    RulesetEpoch,
    Class, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane, Outcome, Producer,
    QueuedInput, SeenWindow, Seq, StepStatus,
};


fn island() -> Island<CombatDomain> {
    // F1 — the island runs the reality's RESOLVED ruleset, pinned by a real
    // content digest. Was `RulesetDigest([0u8; 32])`, which pinned nothing.
    let rules = Arc::new(RealityRules::proving_ground());
    let mut state = CombatState::default();
    state.actors.insert(EntityId(1), hub_fixture::actor(&rules, EntityId(1), Side::A, 100));
    state.actors.insert(EntityId(2), hub_fixture::actor(&rules, EntityId(2), Side::B, 40));
    let mut isle = Island::new(
        IslandId(1),
        7,
        RulesetEpoch(1),
        Arc::clone(&rules),
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
    let full_hp = isle.state().actors[&EntityId(2)].vital(isle.rules());

    submit(&mut isle, 1, CombatPayload::Defend { actor: EntityId(2) });
    submit(&mut isle, 2, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });
    let defended_dmg = full_hp - isle.state().actors[&EntityId(2)].vital(isle.rules());

    let before = isle.state().actors[&EntityId(2)].vital(isle.rules());
    submit(&mut isle, 3, CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) });
    let undefended_dmg = before - isle.state().actors[&EntityId(2)].vital(isle.rules());

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
    let hp = isle.state().actors[&EntityId(2)].vital(isle.rules());
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
    assert_eq!(isle.state().actors[&EntityId(2)].vital(isle.rules()), 0);
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

/// RLS-A13 — an island's digest must describe the rules it is actually running.
///
/// **Found by the second `/review-impl` pass.** `Island::new` used to take
/// `rules` and `digest` as two independent parameters with nothing tying them,
/// so an island could report a digest for a ruleset it was not running — the
/// exact divergence the digest exists to DETECT, made constructible inside the
/// mechanism meant to prevent it. F1 shipped a correct digest that could still
/// be attached to the wrong rules.
///
/// The fix is structural: the digest is DERIVED via `Domain::rules_digest` and
/// the parameter is gone. **Passing a mismatched digest is now a compile error,
/// not a test failure** — there is no argument to pass. This test pins the
/// derivation itself, which is the part a future edit could still get wrong.
#[test]
fn an_island_reports_the_digest_of_the_rules_it_runs() {
    // A second reality: the preset with ONE balance number changed. Built from
    // the preset rather than from `engine_default` because an island's rules
    // must bind every engine role (`M1`), and the engine default binds none.
    let base = RealityRules::proving_ground();
    let mut a_rules = base.rules().clone();
    a_rules.combat.max_hit -= 1; // any reality with non-default rules
    let a = RealityRules::resolve(a_rules).expect("still binds every role");

    let isle_default: Island<CombatDomain> = Island::new(
        IslandId(1),
        7,
        RulesetEpoch(1),
        Arc::new(RealityRules::proving_ground()),
        SeenWindow::Unbounded,
        CombatState::default(),
    );
    let isle_a: Island<CombatDomain> = Island::new(
        IslandId(2),
        7,
        RulesetEpoch(1),
        Arc::new(a.clone()),
        SeenWindow::Unbounded,
        CombatState::default(),
    );

    assert_eq!(isle_default.digest, base.digest());
    assert_eq!(isle_a.digest, a.digest());
    assert_ne!(
        isle_default.digest, isle_a.digest,
        "two islands on different rules must be distinguishable by their pin — \
         this is what makes replay able to notice the rules moved"
    );
}

/// RLS-A13 on the RESTORE path: an island may not resume under rules its
/// checkpoint's digest does not describe.
///
/// `Island::new` closed the forgery at construction (there is no digest
/// argument). `restore` is the one place the two can still disagree, because
/// the checkpoint carries a HISTORICAL digest while the caller supplies rules
/// NOW — and the case is not exotic: `engine_default()` is compiled INTO the
/// binary, so a rolling deploy that changes one constant is exactly this.
///
/// Resuming anyway is silent replay divergence: the island keeps stepping,
/// its events keep claiming the old pin, and nothing looks wrong until an
/// oracle disagrees months later, by which time the evidence is overwritten.
/// RLS-D12 already specifies the answer for an engine that cannot honour a
/// stored ruleset — quarantine, never silently reinterpret.
///
/// This test can only be written with a domain whose rules_digest actually
/// varies; `TestDomain` pins `UNPINNED` and can never mismatch, so the kernel's
/// own suite could not have caught a regression here.
#[test]
fn restoring_under_different_rules_is_refused() {
    let rules_a = Arc::new(RealityRules::proving_ground());
    let mut b_rules = rules_a.rules().clone();
    b_rules.combat.max_hit -= 1; // one balance number, the smallest real rules change
    let b = RealityRules::resolve(b_rules).expect("still binds every role");

    let isle: Island<CombatDomain> = Island::new(
        IslandId(9),
        7,
        RulesetEpoch(1),
        Arc::clone(&rules_a),
        SeenWindow::Unbounded,
        CombatState::default(),
    );
    let cp = isle.checkpoint().expect("a healthy island checkpoints");

    // Same rules — resumes.
    let ok = Island::<CombatDomain>::restore(cp.clone(), Arc::clone(&rules_a));
    assert!(ok.is_ok(), "an island must resume under the rules it was pinned to");

    // Different rules — refused, and the error names BOTH digests so an
    // operator can resolve the right ruleset instead of guessing.
    let err = Island::<CombatDomain>::restore(cp, Arc::new(b.clone()))
        .err()
        .expect("resuming under rules the checkpoint does not describe must be REFUSED");
    assert_eq!(err.checkpoint, rules_a.digest());
    assert_eq!(err.supplied, b.digest());
    assert!(format!("{err}").contains(&rules_a.digest().to_hex()));
}
