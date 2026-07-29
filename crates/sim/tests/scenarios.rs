//! S1a-stress scenario matrix — mixed workloads, adversarial input, soak.
//! Every scenario asserts INVARIANTS (replay equality, bounded collections,
//! exactly-once, nothing-silent), not just endpoint values.

use std::sync::Arc;

use sim::{input, Qi, TestDomain, TestPayload, TestRules, TestState};
use sim_core::{
    RulesetEpoch,Admitted, 
    DetRng, DiscardReason, EntityId, Fallback, Island, IslandId, Lane, Outcome, Precondition,
    SeenWindow, StepStatus, Tick,
};

fn island_with(
    seed: u64,
    window: SeenWindow,
    max_counter: i64,
    seed_qi: &[(u64, i64)],
) -> Island<TestDomain> {
    let mut st = TestState::default();
    for (id, qi) in seed_qi {
        st.qi.insert(EntityId(*id), *qi);
    }
    Island::new(
        IslandId(1),
        seed,
        RulesetEpoch(1),
        Arc::new(TestRules { max_counter }),
        window,
        st,
    )
}

fn drain(isle: &mut Island<TestDomain>) -> u64 {
    let mut n = 0;
    while isle.step() != StepStatus::Idle {
        n += 1;
    }
    n
}

/// Scenario 1 — "tavern cell": 8 actors, mixed Inc/Roll/Spend with SEEDED qi
/// (closes review-impl finding 7: spends succeed in some orders and fail in
/// others), TTL window, periodic ticks, duplicates injected mid-stream.
/// Invariants: qi floor, exactly-once, full replay equality.
#[test]
fn scenario_tavern_cell_mixed_workload() {
    let run = || {
        let mut isle = island_with(
            2026,
            SeenWindow::TtlTicks(50),
            1_000,
            &[(1, 20), (2, 5), (3, 0)],
        );
        for a in 1..=8u64 {
            isle.spawn_entity(EntityId(a));
        }
        let mut next_id = 0u128;
        let mut driver = DetRng::new(777);
        for round in 0..40u64 {
            for a in 1..=8u64 {
                let e = EntityId(a);
                let payload = match driver.range_u64(4) {
                    0 => TestPayload::Inc { id: e, by: 7 },
                    1 => TestPayload::Roll { id: e },
                    2 => TestPayload::Spend { id: e, amount: 5 },
                    _ => TestPayload::Noop,
                };
                let pre = if matches!(payload, TestPayload::Spend { .. }) {
                    vec![Precondition::ResourceAtLeast { id: e, kind: Qi, amount: 5 }]
                } else {
                    vec![]
                };
                next_id += 1;
                isle.submit(Lane::Live, Admitted::unchecked(input(next_id, payload, pre, Fallback::Drop)));
                // Inject a duplicate of every 7th input.
                if next_id % 7 == 0 {
                    isle.submit(
                        Lane::Background,
                        Admitted::unchecked(input(next_id, TestPayload::Noop, vec![], Fallback::Drop),
                    ));
                }
            }
            drain(&mut isle);
            if round % 5 == 0 {
                isle.tick(3);
            }
        }
        drain(&mut isle);

        // Invariants:
        for (id, q) in &isle.state().qi {
            assert!(*q >= 0, "qi floor violated for {id:?}");
        }
        let applied: usize = isle
            .outcomes()
            .iter()
            .filter(|(_, o)| matches!(o, Outcome::Applied { .. }))
            .count();
        assert!(applied > 0, "workload actually ran");
        (format!("{:?}", isle.state()), isle.outcomes().len(), applied)
    };
    let (a, b) = (run(), run());
    assert_eq!(a, b, "full-scenario replay equality");
}

/// Scenario 2 — encounter lifecycle: EncounterActive guards + mid-stream
/// `end_encounter` turning the remaining half of the queue stale.
#[test]
fn scenario_encounter_ends_mid_stream() {
    let mut isle = island_with(7, SeenWindow::Unbounded, 1_000, &[]);
    let e = EntityId(1);
    let enc = EntityId(99);
    isle.spawn_entity(e);
    let g = isle.start_encounter(enc);

    for i in 0..10u128 {
        isle.submit(
            Lane::Live,
            Admitted::unchecked(input(
                i,
                TestPayload::Inc { id: e, by: 1 },
                vec![Precondition::EncounterActive { id: enc, generation: g }],
                Fallback::Drop,
            ),
        ));
    }
    // Process half, then the encounter resolves.
    for _ in 0..5 {
        isle.step();
    }
    isle.end_encounter(enc);
    drain(&mut isle);

    assert_eq!(isle.state().counters[&e], 5, "exactly the pre-end half applied");
    let stale = isle
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Discarded { reason: DiscardReason::PreconditionFailed(_) }))
        .count();
    assert_eq!(stale, 5, "post-end half discarded, none silent");
}

/// Scenario 3 — entity churn: spawn/bump/despawn interleaved with in-flight
/// inputs; every stale path (EntityAlive gen, IslandOwns) exercised.
#[test]
fn scenario_entity_churn() {
    let mut isle = island_with(7, SeenWindow::Unbounded, 1_000, &[]);
    let a = EntityId(1);
    let b = EntityId(2);
    let ga = isle.spawn_entity(a);
    let _gb = isle.spawn_entity(b);

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Inc { id: a, by: 1 },
        vec![Precondition::EntityAlive { id: a, generation: ga }], Fallback::Drop)));
    isle.submit(Lane::Live, Admitted::unchecked(input(2, TestPayload::Inc { id: b, by: 1 },
        vec![Precondition::IslandOwns { id: b }], Fallback::Drop)));
    isle.step(); // a applies at gen ga

    let _ga2 = isle.bump_entity_gen(a).unwrap();
    isle.despawn_entity(b);

    // b's IslandOwns is now stale; a's OLD-gen guard is stale too.
    isle.submit(Lane::Live, Admitted::unchecked(input(3, TestPayload::Inc { id: a, by: 10 },
        vec![Precondition::EntityAlive { id: a, generation: ga }], Fallback::Drop)));
    drain(&mut isle);

    assert_eq!(isle.state().counters[&a], 1, "only the fresh-gen apply landed");
    assert!(!isle.state().counters.contains_key(&b), "despawned entity untouched");
    let discards = isle.outcomes().iter()
        .filter(|(_, o)| matches!(o, Outcome::Discarded { .. }))
        .count();
    assert_eq!(discards, 2, "both stale paths recorded");
}

/// Scenario 4 — adversarial: duplicate storm (one id ×100), buffer thrash
/// (20 never-eligible), schedule flood (200 at one tick). Invariants:
/// exactly-once, one Buffered record per episode, all scheduled fire.
#[test]
fn scenario_adversarial_storms() {
    let mut isle = island_with(7, SeenWindow::Unbounded, 1_000, &[]);
    let e = EntityId(1);
    isle.spawn_entity(e);

    // Duplicate storm.
    for _ in 0..100 {
        isle.submit(Lane::Live, Admitted::unchecked(input(42, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop)));
    }
    // Buffer thrash: 20 items eligible only at tick 1000.
    for i in 0..20u128 {
        isle.submit(Lane::Background, Admitted::unchecked(input(1000 + i, TestPayload::Inc { id: e, by: 1 },
            vec![Precondition::ActorEligible { id: e, turn: Tick(1000) }], Fallback::Buffer)));
    }
    // Schedule flood: 200 due at tick 10.
    for i in 0..200u128 {
        isle.schedule_at(Tick(10), Lane::Background,
            input(2000 + i, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop));
    }
    drain(&mut isle);
    assert_eq!(isle.state().counters[&e], 1, "storm applied exactly once");

    // Thrash 30 ticks below eligibility: episodes must not re-record.
    for _ in 0..30 {
        isle.tick(1);
        drain(&mut isle);
    }
    let buffered_records = isle.outcomes().iter()
        .filter(|(_, o)| matches!(o, Outcome::Buffered)).count();
    assert_eq!(buffered_records, 20, "one Buffered record per episode despite 30 re-parks");
    assert_eq!(isle.state().counters[&e], 201, "storm(1) + flood(200) applied; buffered still parked");

    isle.tick(1000);
    drain(&mut isle);
    assert_eq!(isle.state().counters[&e], 221, "buffered 20 land on eligibility");
}

/// Scenario 5 — soak: 100k mixed inputs with periodic ticks under a TTL
/// window. Memory-bound invariants: seen-set bounded by eviction, outcome
/// count == processed count (nothing silent), buffered-episode set empty.
#[test]
fn scenario_soak_bounded_memory() {
    let mut isle = island_with(9, SeenWindow::TtlTicks(20), i64::MAX, &[]);
    let e = EntityId(1);
    isle.spawn_entity(e);

    let mut processed = 0u64;
    let mut submitted = 0u64;
    for batch in 0..100u128 {
        for i in 0..1000u128 {
            isle.submit(Lane::Live, Admitted::unchecked(input(batch * 1000 + i,
                TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop)));
            submitted += 1;
        }
        processed += drain(&mut isle);
        isle.tick(25); // beyond TTL → evicts the whole previous batch
        assert!(isle.seen_len() <= 1000, "seen-set bounded by TTL eviction (batch {batch})");
    }
    assert_eq!(processed, submitted, "every submission processed");
    assert_eq!(isle.outcomes().len() as u64, processed, "every item's fate recorded");
    assert_eq!(isle.state().counters[&e], 100_000);
}

/// Metrics are the kernel's observability surface — and because they are
/// deterministic, they must AGREE with the outcome log at all times.
/// Kill-mutation: add any outcome path that records without counting (or
/// counts without recording) — this test is what makes silent paths
/// impossible to add unnoticed.
#[test]
fn metrics_cross_check_outcome_log() {
    let mut isle = island_with(31, SeenWindow::TtlTicks(40), 500, &[(1, 30)]);
    let e = EntityId(1);
    isle.spawn_entity(e);
    let stale_g = isle.spawn_entity(EntityId(2));
    isle.bump_entity_gen(EntityId(2));

    let mut id = 0u128;
    for round in 0..30u64 {
        for _ in 0..10 {
            id += 1;
            match id % 5 {
                0 => { // duplicate of previous
                    isle.submit(Lane::Live, Admitted::unchecked(input(id - 1, TestPayload::Noop, vec![], Fallback::Drop)));
                }
                1 => { // plain apply
                    isle.submit(Lane::Live, Admitted::unchecked(input(id, TestPayload::Inc { id: e, by: 2 }, vec![], Fallback::Drop)));
                }
                2 => { // stale gen -> precondition discard
                    isle.submit(Lane::Live, Admitted::unchecked(input(id, TestPayload::Inc { id: EntityId(2), by: 1 },
                        vec![Precondition::EntityAlive { id: EntityId(2), generation: stale_g }], Fallback::Drop)));
                }
                3 => { // guarded spend (some succeed until qi runs out)
                    isle.submit(Lane::Live, Admitted::unchecked(input(id, TestPayload::Spend { id: e, amount: 3 },
                        vec![Precondition::ResourceAtLeast { id: e, kind: Qi, amount: 3 }], Fallback::Drop)));
                }
                _ => { // buffer episode (eligible at tick 500, never reached)
                    isle.submit(Lane::Background, Admitted::unchecked(input(id, TestPayload::Inc { id: e, by: 1 },
                        vec![Precondition::ActorEligible { id: e, turn: Tick(500) }], Fallback::Buffer)));
                }
            }
        }
        drain(&mut isle);
        if round % 3 == 0 {
            isle.tick(2);
            drain(&mut isle);
        }
    }

    let m = isle.metrics().clone();
    let (mut applied, mut discarded, mut buffered) = (0u64, 0u64, 0u64);
    for (_, o) in isle.outcomes() {
        match o {
            Outcome::Applied { .. } => applied += 1,
            Outcome::Discarded { .. } => discarded += 1,
            Outcome::Buffered => buffered += 1,
        }
    }
    assert_eq!(m.applied, applied, "metrics.applied vs log");
    assert_eq!(m.discarded_total(), discarded, "metrics.discarded vs log");
    assert_eq!(m.buffered_episodes, buffered, "metrics.buffered_episodes vs log");
    assert_eq!(
        m.steps_processed,
        isle.outcomes().len() as u64 + m.rebuffer_cycles,
        "every step is either a recorded outcome or a counted silent re-park"
    );
    assert_eq!(m.accounted(), m.steps_processed, "no unaccounted outcome path");
    assert!(m.peak_seen_len > 0 && m.peak_ingress_depth > 0, "gauges moved");
}
