//! S1a bite-tests + the SC-A1 permutation property. Every test names the
//! mutation that must make it fail (non-vacuity discipline).

use std::sync::Arc;

use sim::{input, Qi, TestDomain, TestPayload, TestRules, TestState};
use sim_core::{
    DiscardReason, EntityId, Fallback, Island, IslandId, Lane, Outcome, Precondition,
    RulesetDigest, SeenWindow, StepStatus, Tick,
};

fn island(seed: u64, window: SeenWindow) -> Island<TestDomain> {
    Island::new(
        IslandId(1),
        seed,
        Arc::new(TestRules { max_counter: 100 }),
        RulesetDigest([0u8; 32]),
        window,
        TestState::default(),
    )
}

fn drain(isle: &mut Island<TestDomain>) {
    while isle.step() != StepStatus::Idle {}
}

/// Kill-mutation: remove the seen-set insert in `step()`.
#[test]
fn duplicate_is_discarded_not_reapplied() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, input(42, TestPayload::Inc { id: e, by: 5 }, vec![], Fallback::Drop));
    isle.submit(Lane::Live, input(42, TestPayload::Inc { id: e, by: 5 }, vec![], Fallback::Drop));
    drain(&mut isle);

    assert_eq!(isle.state().counters[&e], 5, "applied exactly once");
    assert!(matches!(
        isle.outcomes()[1].1,
        Outcome::Discarded { reason: DiscardReason::Duplicate }
    ));
}

/// Kill-mutation: validate preconditions at admission instead of step time.
#[test]
fn precondition_revalidated_at_step_not_admission() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    let g = isle.spawn_entity(e);

    // Valid at admission…
    isle.submit(
        Lane::Live,
        input(
            1,
            TestPayload::Inc { id: e, by: 5 },
            vec![Precondition::EntityAlive { id: e, generation: g }],
            Fallback::Drop,
        ),
    );
    // …but the world moves before the step (gen bump = lifecycle change).
    isle.bump_entity_gen(e);
    drain(&mut isle);

    assert!(!isle.state().counters.contains_key(&e), "stale input must not apply");
    assert!(matches!(
        isle.outcomes()[0].1,
        Outcome::Discarded { reason: DiscardReason::PreconditionFailed(_) }
    ));
}

/// Kill-mutation: route Substitute through the failed payload.
#[test]
fn substitute_applies_declared_alternative() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    let g = isle.spawn_entity(e);
    isle.bump_entity_gen(e); // make the guard stale immediately

    isle.submit(
        Lane::Live,
        input(
            1,
            TestPayload::Inc { id: e, by: 50 },
            vec![Precondition::EntityAlive { id: e, generation: g }],
            Fallback::Substitute(TestPayload::Inc { id: e, by: 1 }),
        ),
    );
    drain(&mut isle);

    assert_eq!(isle.state().counters[&e], 1, "substitute, not original, applied");
}

/// Kill-mutation: leave the buffered input in the seen set (it would
/// self-collide as Duplicate on re-offer).
#[test]
fn buffer_reparks_and_succeeds_after_world_catches_up() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    isle.spawn_entity(e);

    // Eligible only at tick 5; buffered until then.
    isle.submit(
        Lane::Live,
        input(
            1,
            TestPayload::Inc { id: e, by: 3 },
            vec![Precondition::ActorEligible { id: e, turn: Tick(5) }],
            Fallback::Buffer,
        ),
    );
    drain(&mut isle);
    assert!(matches!(isle.outcomes()[0].1, Outcome::Buffered));
    assert!(!isle.state().counters.contains_key(&e));

    isle.tick(5); // re-offers the buffered item; clock now eligible
    drain(&mut isle);

    assert_eq!(isle.state().counters[&e], 3, "buffered input applied once eligible");
}

/// Kill-mutation: pop Background before Live.
#[test]
fn live_lane_drains_strictly_first() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Background, input(1, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop));
    isle.submit(Lane::Live, input(2, TestPayload::Inc { id: e, by: 10 }, vec![], Fallback::Drop));

    isle.step(); // must be the Live item
    assert_eq!(isle.state().counters[&e], 10);
}

/// Kill-mutation: fire scheduled inputs on submit instead of at their tick.
#[test]
fn scheduled_input_fires_at_its_tick_not_before() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.schedule_at(Tick(10), Lane::Background, input(1, TestPayload::Inc { id: e, by: 4 }, vec![], Fallback::Drop));

    isle.tick(9);
    drain(&mut isle);
    assert!(!isle.state().counters.contains_key(&e), "not before tick 10");

    isle.tick(1);
    drain(&mut isle);
    assert_eq!(isle.state().counters[&e], 4);
}

/// Kill-mutation: guard Spend at admission (or drop the guard entirely —
/// qi would go negative via saturation masking the bug elsewhere).
#[test]
fn resource_precondition_delegates_to_domain() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    isle.spawn_entity(e);
    // qi starts at 0 — spend must be rejected.
    isle.submit(
        Lane::Live,
        input(
            1,
            TestPayload::Spend { id: e, amount: 10 },
            vec![Precondition::ResourceAtLeast { id: e, kind: Qi, amount: 10 }],
            Fallback::Drop,
        ),
    );
    drain(&mut isle);
    assert!(matches!(
        isle.outcomes()[0].1,
        Outcome::Discarded { reason: DiscardReason::PreconditionFailed(_) }
    ));
}

/// Replay determinism. Kill-mutation: swap DetRng for entropy, or a
/// HashMap anywhere in replay-observable state.
#[test]
fn identical_ingress_replays_byte_identical() {
    let run = || {
        let mut isle = island(999, SeenWindow::Unbounded);
        let e = EntityId(1);
        isle.spawn_entity(e);
        for i in 0..50u128 {
            let payload = match i % 3 {
                0 => TestPayload::Inc { id: e, by: 7 },
                1 => TestPayload::Roll { id: e },
                _ => TestPayload::Noop,
            };
            isle.submit(Lane::Live, input(i, payload, vec![], Fallback::Drop));
        }
        drain(&mut isle);
        (format!("{:?}", isle.outcomes()), format!("{:?}", isle.state()))
    };
    assert_eq!(run(), run());
}

/// SC-A1 — order-independent SAFETY (the correctness claim itself, scoped to
/// S1a semantics): across K seeded permutations of one input set, outcomes
/// may differ but validity may not. Kill-mutations: apply bypassing check;
/// double-apply on duplicate; counter clamp removal.
#[test]
fn permutation_property_all_orders_valid() {
    let e = EntityId(1);

    // Input set: 8 unique inputs + 4 duplicates + a stale-gen guard + spends.
    let build_inputs = || {
        let mut v = Vec::new();
        for i in 0..8u128 {
            v.push(input(i, TestPayload::Inc { id: e, by: 30 }, vec![], Fallback::Drop));
        }
        for i in 0..4u128 {
            v.push(input(i, TestPayload::Inc { id: e, by: 30 }, vec![], Fallback::Drop)); // dup ids
        }
        v.push(input(
            100,
            TestPayload::Spend { id: e, amount: 5 },
            vec![Precondition::ResourceAtLeast { id: e, kind: Qi, amount: 5 }],
            Fallback::Drop,
        ));
        v
    };

    for perm_seed in 0..20u64 {
        // Seeded Fisher-Yates via DetRng — the harness itself stays deterministic.
        let mut rng = sim_core::DetRng::new(perm_seed);
        let mut inputs = build_inputs();
        for i in (1..inputs.len()).rev() {
            let j = rng.range_u64((i + 1) as u64) as usize;
            inputs.swap(i, j);
        }

        let mut isle = island(7, SeenWindow::Unbounded);
        isle.spawn_entity(e);
        for inp in inputs {
            isle.submit(Lane::Live, inp);
        }
        drain(&mut isle);

        // Validity invariants — MUST hold in every order:
        let c = isle.state().counters.get(&e).copied().unwrap_or(0);
        assert!(c <= 100, "clamp violated in perm {perm_seed}: {c}");
        assert_eq!(
            c, 100,
            "8 unique ×30 clamped to 100 regardless of order; dups must not add (perm {perm_seed})"
        );
        let dup_discards = isle
            .outcomes()
            .iter()
            .filter(|(_, o)| matches!(o, Outcome::Discarded { reason: DiscardReason::Duplicate }))
            .count();
        assert_eq!(dup_discards, 4, "exactly the 4 duplicate ids discard (perm {perm_seed})");
        let qi = isle.state().qi.get(&e).copied().unwrap_or(0);
        assert!(qi >= 0, "resource never negative (perm {perm_seed})");
        // Every item got a recorded fate — nothing silent.
        assert_eq!(isle.outcomes().len(), 13, "13 items, 13 outcomes (perm {perm_seed})");
    }
}

/// Review finding 1 regression: a buffered BACKGROUND item must re-offer on
/// its OWN lane — never jump to Live. Kill-mutation: hardcode Lane::Live in
/// the Buffer arm of `resolve_fallback` (the original S1a bug).
#[test]
fn buffered_background_item_does_not_preempt_live() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    isle.spawn_entity(e);

    // Background item that buffers (eligible only at tick 5).
    isle.submit(
        Lane::Background,
        input(
            1,
            TestPayload::Inc { id: e, by: 100 },
            vec![Precondition::ActorEligible { id: e, turn: Tick(5) }],
            Fallback::Buffer,
        ),
    );
    drain(&mut isle);
    assert!(matches!(isle.outcomes()[0].1, Outcome::Buffered));

    // Clock catches up; buffered item re-offers on BACKGROUND. A Live item
    // submitted now must still drain first.
    isle.tick(5);
    isle.submit(Lane::Live, input(2, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop));

    isle.step(); // must be the LIVE item, not the re-offered Background one
    assert_eq!(
        isle.state().counters[&e], 1,
        "Live drains before a re-offered Background item"
    );
    drain(&mut isle);
    assert_eq!(isle.state().counters[&e], 100, "clamped total after both apply");
}

/// review-impl finding 1: a re-buffer cycle records `Buffered` ONCE per
/// episode. Kill-mutation: remove the `currently_buffered` guard.
#[test]
fn rebuffering_records_once_not_per_tick() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(
        Lane::Live,
        input(
            1,
            TestPayload::Inc { id: e, by: 3 },
            vec![Precondition::ActorEligible { id: e, turn: Tick(100) }],
            Fallback::Buffer,
        ),
    );
    drain(&mut isle);
    // 10 ticks of still-ineligible re-offers…
    for _ in 0..10 {
        isle.tick(1);
        drain(&mut isle);
    }
    let buffered_records = isle
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Buffered))
        .count();
    assert_eq!(buffered_records, 1, "one episode, one Buffered record");

    isle.tick(90); // now eligible
    drain(&mut isle);
    assert_eq!(isle.state().counters[&e], 3);
}

/// review-impl finding 2: `Notify`'s outcome records the ACTUAL violation,
/// never the caller-declared reason. Kill-mutation: record the declared
/// reason (the original bug — a client could falsify the audit log).
#[test]
fn notify_records_actual_violation_not_declared_reason() {
    let mut isle = island(7, SeenWindow::Unbounded);
    let e = EntityId(1);
    let g = isle.spawn_entity(e);
    isle.bump_entity_gen(e); // real failure: stale EntityAlive

    isle.submit(
        Lane::Live,
        input(
            1,
            TestPayload::Inc { id: e, by: 5 },
            vec![Precondition::EntityAlive { id: e, generation: g }],
            // Client DECLARES a misleading reason:
            Fallback::Notify(e, DiscardReason::Expired),
        ),
    );
    drain(&mut isle);

    match &isle.outcomes()[0].1 {
        Outcome::Discarded { reason: DiscardReason::PreconditionFailed(v) } => {
            assert_eq!(v.kind, sim_core::PreconditionKind::EntityAlive);
        }
        other => panic!("audit log must carry the truth, got {other:?}"),
    }
}
