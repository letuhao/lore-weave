//! S1b chaos suite — panic containment, O(1) invalidation cascade, deadline
//! expiry. Every test names its kill-mutation.

use std::sync::Arc;

use sim::{input, input_deadline, TestDomain, TestPayload, TestRules, TestState};
use sim_core::{
    RulesetEpoch,Admitted, 
    DiscardReason, EntityId, Fallback, Island, IslandId, Lane, Outcome, Precondition,
    SeenWindow, StepStatus, Tick,
};

fn island(seed: u64) -> Island<TestDomain> {
    Island::new(
        IslandId(1),
        seed,
        RulesetEpoch(1),
        Arc::new(TestRules { max_counter: 1_000_000 }),
        SeenWindow::Unbounded,
        TestState::default(),
    )
}

/// Canary for the docs-14/15 trap: if anyone sets `panic = "abort"` on the
/// test profile, this test DIES instead of passing — visible, not silent.
#[test]
fn panic_unwinds_in_test_profile() {
    let caught = std::panic::catch_unwind(|| panic!("canary"));
    assert!(caught.is_err(), "test profile must unwind (panic != abort)");
}

/// SC-A8/A9. Kill-mutations: remove the poison flag (island resumes over
/// half-mutated state) · skip the quarantine push · record nothing.
#[test]
fn panic_is_contained_quarantined_and_poisons() {
    let mut isle = island(7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Inc { id: e, by: 5 }, vec![], Fallback::Drop)));
    isle.submit(Lane::Live, Admitted::unchecked(input(2, TestPayload::Panic, vec![], Fallback::Drop)));
    isle.submit(Lane::Live, Admitted::unchecked(input(3, TestPayload::Inc { id: e, by: 100 }, vec![], Fallback::Drop)));

    assert!(matches!(isle.step(), StepStatus::Processed(_))); // Inc applies
    assert!(matches!(isle.step(), StepStatus::Processed(_))); // Panic contained
    assert!(isle.is_poisoned(), "island poisons on first quarantine");
    assert_eq!(isle.step(), StepStatus::Poisoned, "no further work");
    assert_eq!(isle.state().counters[&e], 5, "post-pill input NEVER ran");

    assert_eq!(isle.quarantined().len(), 1, "the pill is quarantined");
    assert_eq!(isle.metrics().quarantined, 1);
    assert_eq!(
        isle.metrics().accounted(),
        isle.metrics().steps_processed,
        "a quarantined step is an ACCOUNTED step (review-impl S2 finding 5)"
    );
    assert!(matches!(
        isle.outcomes().last().unwrap().1,
        Outcome::Discarded { reason: DiscardReason::Quarantined }
    ), "the incident is recorded, never silent");
}

/// Spec §10.4: chaos-harness mode — containment OFF lets the panic surface
/// as a test failure. Kill-mutation: ignore the containment flag.
#[test]
fn containment_off_propagates_panic() {
    let mut isle = island(7);
    isle.set_containment(false);
    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Panic, vec![], Fallback::Drop)));
    let boom = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        isle.step();
    }));
    assert!(boom.is_err(), "passthrough mode must surface the panic");
}

/// Spec §7 — the O(1) cascade. Kill-mutations: stamp at pop instead of
/// admission · burn superseded ids in `seen` · walk the queue on bump.
#[test]
fn island_gen_bump_supersedes_all_pending_o1() {
    let mut isle = island(7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    for i in 0..1000u128 {
        isle.submit(Lane::Live, Admitted::unchecked(input(i, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop)));
    }
    isle.bump_island_gen(); // dissolution-class event: everything pending dies

    while isle.step() != StepStatus::Idle {}
    assert!(!isle.state().counters.contains_key(&e), "nothing applied");
    assert_eq!(isle.metrics().discarded_superseded, 1000, "all superseded");

    // The ids were NOT burned: a re-submission processes normally.
    isle.submit(Lane::Live, Admitted::unchecked(input(500, TestPayload::Inc { id: e, by: 7 }, vec![], Fallback::Drop)));
    while isle.step() != StepStatus::Idle {}
    assert_eq!(isle.state().counters[&e], 7, "re-submit after cascade applies");
}

/// A BUFFERED item is pending work too — dissolution must cancel it.
/// Kill-mutation: re-stamp admitted_gen on repark.
#[test]
fn buffered_item_superseded_by_bump() {
    let mut isle = island(7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Inc { id: e, by: 3 },
        vec![Precondition::ActorEligible { id: e, turn: Tick(50) }], Fallback::Buffer)));
    while isle.step() != StepStatus::Idle {}
    assert_eq!(isle.buffered_len(), 1);

    isle.bump_island_gen();
    isle.tick(100); // re-offers the parked item — now both eligible AND stale
    while isle.step() != StepStatus::Idle {}

    assert!(!isle.state().counters.contains_key(&e), "parked work died with the epoch");
    assert_eq!(isle.metrics().discarded_superseded, 1);
}

/// SL-A4 expiry, Drop path. Kill-mutation: check the deadline at admission.
#[test]
fn deadline_expiry_records_expired() {
    let mut isle = island(7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input_deadline(1, TestPayload::Inc { id: e, by: 5 }, Tick(3), Fallback::Drop)));
    isle.tick(10); // deadline passes while queued
    while isle.step() != StepStatus::Idle {}

    assert!(!isle.state().counters.contains_key(&e));
    assert!(matches!(
        isle.outcomes().last().unwrap().1,
        Outcome::Discarded { reason: DiscardReason::Expired }
    ));
    assert_eq!(isle.metrics().discarded_expired, 1);
}

/// SL-A4 expiry, Substitute path — the AGT-A2 "deadline fires → fallback
/// commits (Defend)" pattern. Kill-mutation: route expiry to plain Drop.
#[test]
fn deadline_expiry_substitute_commits_fallback() {
    let mut isle = island(7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input_deadline(
        1,
        TestPayload::Inc { id: e, by: 100 },
        Tick(3),
        Fallback::Substitute(TestPayload::Inc { id: e, by: 1 }), // "Defend"
    )));
    isle.tick(10);
    while isle.step() != StepStatus::Idle {}

    assert_eq!(isle.state().counters[&e], 1, "fallback committed, not the stale intent");
    assert_eq!(isle.metrics().substituted, 1);
}

/// Review-impl S2 finding 1 (HIGH), half A: expiry is a FINAL outcome and
/// burns the input_id — a redelivery of an expired `Substitute` input must
/// NOT re-commit the fallback. Kill-mutation: the original bug (deadline
/// check before the seen-set insert).
#[test]
fn expired_substitute_redelivery_commits_fallback_once() {
    let mut isle = island(7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    let expired_sub = || input_deadline(
        1,
        TestPayload::Inc { id: e, by: 100 },
        Tick(3),
        Fallback::Substitute(TestPayload::Inc { id: e, by: 1 }),
    );
    isle.tick(10); // deadline already passed at first delivery
    isle.submit(Lane::Live, Admitted::unchecked(expired_sub()));
    isle.submit(Lane::Live, Admitted::unchecked(expired_sub())); // router/bus redelivery
    while isle.step() != StepStatus::Idle {}

    assert_eq!(isle.state().counters[&e], 1, "fallback committed EXACTLY once");
    assert_eq!(isle.metrics().substituted, 1);
    assert_eq!(isle.metrics().discarded_duplicate, 1, "the redelivery deduped");
}

/// Review-impl S2 finding 1, half B: a duplicate of an ALREADY-APPLIED input
/// reports Duplicate even when its deadline has since passed — reporting
/// Expired would tell the client "never landed" and invite a re-issue under
/// a fresh id (double apply). Kill-mutation: same as above.
#[test]
fn duplicate_of_applied_input_reports_duplicate_not_expired() {
    let mut isle = island(7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input_deadline(1, TestPayload::Inc { id: e, by: 5 }, Tick(30), Fallback::Drop)));
    while isle.step() != StepStatus::Idle {}
    assert_eq!(isle.state().counters[&e], 5, "applied in time");

    isle.tick(50); // deadline passes AFTER the apply
    isle.submit(Lane::Live, Admitted::unchecked(input_deadline(1, TestPayload::Inc { id: e, by: 5 }, Tick(30), Fallback::Drop)));
    while isle.step() != StepStatus::Idle {}

    assert!(matches!(
        isle.outcomes().last().unwrap().1,
        Outcome::Discarded { reason: DiscardReason::Duplicate }
    ), "the truth is Duplicate (it landed), never Expired");
    assert_eq!(isle.state().counters[&e], 5);
}

/// Review-impl S2 finding 6: a poisoned island is NEVER resumed — tick()
/// must not fire timers into the ingress. Kill-mutation: tick() without the
/// poison guard.
#[test]
fn poisoned_island_tick_does_no_work() {
    let mut isle = island(7);
    let e = EntityId(1);
    isle.spawn_entity(e);
    isle.schedule_at(Tick(5), Lane::Live, input(2, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop));

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Panic, vec![], Fallback::Drop)));
    while !matches!(isle.step(), StepStatus::Poisoned | StepStatus::Idle) {}
    assert!(isle.is_poisoned());

    let before = isle.now();
    isle.tick(10);
    assert_eq!(isle.now(), before, "clock frozen");
    assert_eq!(isle.ingress_len(), 0, "no timer fired into the ingress");
}

/// Replay determinism SURVIVES the chaos features: same stream incl. a bump
/// + expiries + (contained) pill → byte-identical outcomes and state.
#[test]
fn chaos_replay_still_deterministic() {
    let run = || {
        let mut isle = island(99);
        let e = EntityId(1);
        isle.spawn_entity(e);
        for i in 0..20u128 {
            isle.submit(Lane::Live, Admitted::unchecked(input(i, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop)));
        }
        isle.bump_island_gen();
        for i in 20..40u128 {
            isle.submit(Lane::Live, Admitted::unchecked(input(i, TestPayload::Roll { id: e }, vec![], Fallback::Drop)));
        }
        isle.submit(Lane::Live, Admitted::unchecked(input_deadline(99, TestPayload::Inc { id: e, by: 9 }, Tick(0), Fallback::Drop)));
        isle.tick(5);
        while isle.step() != StepStatus::Idle {}
        (format!("{:?}", isle.outcomes()), format!("{:?}", isle.state()), isle.metrics().clone())
    };
    let (a, b) = (run(), run());
    assert_eq!(a.0, b.0);
    assert_eq!(a.1, b.1);
    assert_eq!(a.2, b.2, "metrics replay-identical too");
}
