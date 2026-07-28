//! S2 multi-island suite — §9 messaging, SL-A12 handoff, §10.1 dissolution,
//! §10.5 checkpoint/restore. Every test names its kill-mutation.

use std::sync::Arc;

use sim::{input, Realm, TestDomain, TestPayload, TestPortable, TestRules, TestState};
use sim_core::{Admitted, 
    DiscardReason, DissolutionReason, EntityId, Fallback, Gen, InputId, Island, IslandId,
    IslandMessage, Lane, Outcome, Precondition, PreconditionKind, SeenWindow, Seq,
    StepStatus, Tick, Violation,
};

fn island(id: u64, seed: u64) -> Island<TestDomain> {
    Island::new(
        IslandId(id),
        seed,
        Arc::new(TestRules { max_counter: 1_000_000 }),
        SeenWindow::Unbounded,
        TestState::default(),
    )
}

fn msg(from: u64, to: u64, delivery: u128, payload: TestPayload) -> IslandMessage<TestDomain> {
    IslandMessage {
        from: IslandId(from),
        to: IslandId(to),
        causality: Seq(0),
        delivery_id: InputId(delivery),
        payload,
    }
}

/// §9 +1-tick latency: a message sent during tick-window T is NOT visible to
/// steps inside T; it applies only after the next tick boundary.
/// Kill-mutation: `Realm::send` delivering immediately.
#[test]
fn message_delivers_at_next_tick_not_before() {
    let mut realm: Realm<TestDomain> = Realm::new();
    let (a, b) = (island(1, 7), island(2, 8));
    let e = EntityId(1);
    let mut b = b;
    b.spawn_entity(e);
    realm.insert(a);
    realm.insert(b);

    realm.send(msg(1, 2, 100, TestPayload::Inc { id: e, by: 5 }));
    assert_eq!(realm.step_all(), 0, "not delivered inside the send window");
    assert!(!realm.island(IslandId(2)).unwrap().state().counters.contains_key(&e));

    realm.tick_all(1); // the boundary — mailbox flushes here
    realm.step_all();
    assert_eq!(realm.island(IslandId(2)).unwrap().state().counters[&e], 5);
}

/// I8 exactly-once IS the I2 seen-set: a router redelivery (same
/// delivery_id) discards as Duplicate. Kill-mutation: deliver() minting a
/// fresh input_id instead of using delivery_id.
#[test]
fn message_redelivery_discards_duplicate() {
    let mut isle = island(2, 8);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.deliver(Lane::Live, msg(1, 2, 100, TestPayload::Inc { id: e, by: 5 }));
    isle.deliver(Lane::Live, msg(1, 2, 100, TestPayload::Inc { id: e, by: 5 })); // redelivery
    while isle.step() != StepStatus::Idle {}

    assert_eq!(isle.state().counters[&e], 5, "applied exactly once");
    assert_eq!(isle.metrics().discarded_duplicate, 1);
    assert_eq!(isle.metrics().cross_island_delivered, 2);
}

/// §9: target missing/dissolved → recorded dead letter, NEVER an error.
/// Kill-mutation: unwrap on the islands map.
#[test]
fn message_to_missing_island_is_recorded_dead_letter() {
    let mut realm: Realm<TestDomain> = Realm::new();
    realm.insert(island(1, 7));

    realm.send(msg(1, 99, 100, TestPayload::Noop));
    realm.tick_all(1);

    assert_eq!(realm.dead_letters.len(), 1);
    assert_eq!(realm.dead_letters[0].message.to, IslandId(99));
    assert_eq!(realm.dead_letters[0].reason, "unknown-or-dissolved island");
}

/// SL-A12 — the full handoff: depart strips registry + state BEFORE any
/// message exists (exactly-one-island is structural); arrive restores both.
/// Kill-mutations: depart leaves the registry entry · extract/install not
/// inverses (counter or qi dropped).
#[test]
fn handoff_moves_entity_exactly_once() {
    let mut a = island(1, 7);
    let mut b = island(2, 8);
    let e = EntityId(1);
    a.spawn_entity(e);
    a.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Inc { id: e, by: 42 }, vec![], Fallback::Drop)));
    while a.step() != StepStatus::Idle {}

    let (gen_at_depart, portable) = a.depart(e).expect("owned → departs");
    assert_eq!(gen_at_depart, Gen(0));
    assert_eq!(portable, TestPortable { counter: 42, qi: 0 });
    assert!(a.entity_gen(e).is_none(), "source no longer owns it");
    assert!(!a.state().counters.contains_key(&e), "state extracted, not copied");

    // An in-flight input on the SOURCE now fails structurally (S1a machinery).
    a.submit(Lane::Live, Admitted::unchecked(input(
        2,
        TestPayload::Inc { id: e, by: 1 },
        vec![Precondition::IslandOwns { id: e }],
        Fallback::Drop,
    )));
    while a.step() != StepStatus::Idle {}
    assert!(matches!(
        a.outcomes().last().unwrap().1,
        Outcome::Discarded {
            reason: DiscardReason::PreconditionFailed(Violation {
                kind: PreconditionKind::IslandOwns,
                ..
            })
        }
    ));

    b.arrive(e, portable);
    assert_eq!(b.state().counters[&e], 42, "state survived the handoff intact");
    b.submit(Lane::Live, Admitted::unchecked(input(
        3,
        TestPayload::Inc { id: e, by: 8 },
        vec![Precondition::IslandOwns { id: e }],
        Fallback::Drop,
    )));
    while b.step() != StepStatus::Idle {}
    assert_eq!(b.state().counters[&e], 50, "target owns and applies");
}

/// Arriving over an already-owned entity bumps its generation — old-epoch
/// refs go stale instead of silently merging. Kill-mutation: arrive
/// overwriting with Gen(0).
#[test]
fn arrive_over_existing_entity_bumps_generation() {
    let mut isle = island(1, 7);
    let e = EntityId(1);
    let g0 = isle.spawn_entity(e);

    let g1 = isle.arrive(e, TestPortable { counter: 9, qi: 0 });
    assert!(g1 > g0, "re-arrival is a new epoch");

    // A ref pinned to the OLD generation now fails EntityAlive.
    isle.submit(Lane::Live, Admitted::unchecked(input(
        1,
        TestPayload::Inc { id: e, by: 1 },
        vec![Precondition::EntityAlive { id: e, generation: g0 }],
        Fallback::Drop,
    )));
    while isle.step() != StepStatus::Idle {}
    assert!(matches!(
        isle.outcomes().last().unwrap().1,
        Outcome::Discarded {
            reason: DiscardReason::PreconditionFailed(Violation {
                kind: PreconditionKind::EntityAlive,
                ..
            })
        }
    ));
}

/// §10.1 transfer-class: Migrating carries current-gen pending work —
/// queued, scheduled AND buffered — and the successor applies it.
/// Kill-mutations: drop the schedule/buffered drains · transfer without
/// re-admitting (stale Seq stamps).
#[test]
fn dissolve_migrating_transfers_all_pending_work() {
    let mut isle = island(1, 7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop)));
    // A buffered item (ineligible until tick 40).
    isle.submit(Lane::Live, Admitted::unchecked(input(
        4,
        TestPayload::Inc { id: e, by: 8 },
        vec![Precondition::ActorEligible { id: e, turn: Tick(40) }],
        Fallback::Buffer,
    )));
    while isle.step() != StepStatus::Idle {} // applies #1, parks #4
    assert_eq!(isle.buffered_len(), 1);
    // Still-pending work at dissolve time: one queued, one scheduled, one buffered.
    isle.submit(Lane::Background, Admitted::unchecked(input(2, TestPayload::Inc { id: e, by: 2 }, vec![], Fallback::Drop)));
    isle.schedule_at(Tick(50), Lane::Live, input(3, TestPayload::Inc { id: e, by: 4 }, vec![], Fallback::Drop));
    assert!(!isle.is_quiescent());

    let d = isle.dissolve(DissolutionReason::Migrating);
    assert_eq!(d.transferable.len(), 3, "queued #2 + scheduled #3 + buffered #4; #1 already applied");
    assert_eq!(d.discarded_pending, 0);
    assert_eq!(d.checkpoint.state.counters[&e], 1, "only #1 applied pre-dissolve");

    // Successor: rebuild from the dissolution checkpoint, re-admit the work.
    let mut succ = Island::restore(d.checkpoint, Arc::new(TestRules { max_counter: 1_000_000 })).expect("TestDomain pins UNPINNED, so any TestRules matches");
    for (lane, item) in d.transferable {
        succ.submit(lane, Admitted::unchecked(item));
    }
    succ.tick(50); // makes the ActorEligible item eligible
    while succ.step() != StepStatus::Idle {}
    assert_eq!(succ.state().counters[&e], 1 + 2 + 4 + 8, "every pending item landed");
}

/// §10.1 discard-class: Resolved counts pending as discarded, transfers none.
/// Kill-mutation: transferring regardless of reason.
#[test]
fn dissolve_resolved_discards_pending() {
    let mut isle = island(1, 7);
    let e = EntityId(1);
    isle.spawn_entity(e);
    for i in 0..5u128 {
        isle.submit(Lane::Live, Admitted::unchecked(input(i, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop)));
    }

    let d = isle.dissolve(DissolutionReason::Resolved);
    assert!(d.transferable.is_empty());
    assert_eq!(d.discarded_pending, 5);
    assert!(!d.checkpoint.state.counters.contains_key(&e), "none applied");
}

/// Even under a transfer-class reason, items superseded by an earlier
/// island-gen bump DIE at dissolution — a migration must not resurrect
/// work a dissolution-class event already cancelled. Kill-mutation:
/// dropping the admitted_gen filter in dissolve().
#[test]
fn dissolve_migrating_drops_stale_generation_items() {
    let mut isle = island(1, 7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop)));
    isle.bump_island_gen(); // cancels #1
    isle.submit(Lane::Live, Admitted::unchecked(input(2, TestPayload::Inc { id: e, by: 2 }, vec![], Fallback::Drop)));

    let d = isle.dissolve(DissolutionReason::Migrating);
    assert_eq!(d.transferable.len(), 1, "only the current-gen item travels");
    assert_eq!(d.transferable[0].1.input_id, InputId(2));
    assert_eq!(d.discarded_pending, 1);
}

/// SC-A9 — the poison pill rides `quarantined`, NEVER `transferable`:
/// re-queuing it anywhere is the infinite crash loop. Kill-mutation:
/// draining quarantine into the pending vec.
#[test]
fn dissolve_returns_quarantine_separately_never_transferable() {
    let mut isle = island(1, 7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Panic, vec![], Fallback::Drop)));
    isle.submit(Lane::Live, Admitted::unchecked(input(2, TestPayload::Inc { id: e, by: 3 }, vec![], Fallback::Drop)));
    while !matches!(isle.step(), StepStatus::Poisoned | StepStatus::Idle) {}
    assert!(isle.is_poisoned());

    let d = isle.dissolve(DissolutionReason::Unresponsive);
    assert!(d.was_poisoned);
    assert_eq!(d.quarantined.len(), 1);
    assert_eq!(d.quarantined[0].input_id, InputId(1));
    assert!(
        d.transferable.iter().all(|(_, i)| i.input_id != InputId(1)),
        "the pill must never travel as pending work"
    );
}

/// §10.5 — restore is STEPPING-IDENTICAL: same post-checkpoint stream →
/// byte-identical outcomes and state, including rng-dependent rolls.
/// Kill-mutations: omit rng from the checkpoint · omit seen (redelivery
/// applies twice) · reset island_gen.
#[test]
fn checkpoint_restore_is_stepping_identical() {
    let stream1 = |isle: &mut Island<TestDomain>| {
        let e = EntityId(1);
        for i in 0..10u128 {
            isle.submit(Lane::Live, Admitted::unchecked(input(i, TestPayload::Roll { id: e }, vec![], Fallback::Drop)));
        }
        while isle.step() != StepStatus::Idle {}
    };
    let stream2 = |isle: &mut Island<TestDomain>| {
        let e = EntityId(1);
        // A pre-checkpoint duplicate (redelivery) + fresh rolls + an inc.
        isle.submit(Lane::Live, Admitted::unchecked(input(3, TestPayload::Roll { id: e }, vec![], Fallback::Drop)));
        for i in 20..30u128 {
            isle.submit(Lane::Live, Admitted::unchecked(input(i, TestPayload::Roll { id: e }, vec![], Fallback::Drop)));
        }
        isle.submit(Lane::Live, Admitted::unchecked(input(30, TestPayload::Inc { id: e, by: 7 }, vec![], Fallback::Drop)));
        while isle.step() != StepStatus::Idle {}
    };

    // Original: stream1 → checkpoint → stream2.
    let mut original = island(1, 99);
    original.spawn_entity(EntityId(1));
    stream1(&mut original);
    let cp = original.checkpoint().expect("healthy island checkpoints");
    let outcomes_before = original.outcomes().len();
    stream2(&mut original);
    let tail_a: Vec<String> =
        original.outcomes()[outcomes_before..].iter().map(|o| format!("{o:?}")).collect();

    // Restored: rebuild from checkpoint → same stream2.
    let mut restored = Island::restore(cp, Arc::new(TestRules { max_counter: 1_000_000 })).expect("TestDomain pins UNPINNED, so any TestRules matches");
    stream2(&mut restored);
    let tail_b: Vec<String> = restored.outcomes().iter().map(|o| format!("{o:?}")).collect();

    assert_eq!(tail_a, tail_b, "identical outcomes incl. rng rolls + the dedup discard");
    assert_eq!(
        format!("{:?}", original.state()),
        format!("{:?}", restored.state()),
        "identical final state"
    );
    assert_eq!(restored.metrics().discarded_duplicate, 1, "seen-set survived the restore");
}

/// Post-restore Seq stamps CONTINUE from the checkpoint — they never collide
/// with pre-checkpoint stamps in host logs. Kill-mutation: restore starting
/// next_seq at 0.
#[test]
fn restore_continues_seq_stamps() {
    let mut isle = island(1, 7);
    let e = EntityId(1);
    isle.spawn_entity(e);
    for i in 0..5u128 {
        isle.submit(Lane::Live, Admitted::unchecked(input(i, TestPayload::Noop, vec![], Fallback::Drop)));
    }
    while isle.step() != StepStatus::Idle {}

    let cp = isle.checkpoint().expect("healthy island checkpoints");
    let mut restored = Island::restore(cp, Arc::new(TestRules { max_counter: 1_000_000 })).expect("TestDomain pins UNPINNED, so any TestRules matches");
    let seq = restored.submit(Lane::Live, Admitted::unchecked(input(9, TestPayload::Noop, vec![], Fallback::Drop)));
    assert_eq!(seq, Seq(5), "continues after the 5 pre-checkpoint stamps");
}

/// Two islands + cross traffic through the Realm, run twice → byte-identical
/// everything. Multi-island determinism is a property of the WHOLE transport,
/// not just one island. Kill-mutation: HashMap in the Realm (iteration order
/// enters step order) · mailbox delivered out of send order.
#[test]
fn multi_island_replay_determinism() {
    let run = || {
        let mut realm: Realm<TestDomain> = Realm::new();
        let mut a = island(1, 41);
        let mut b = island(2, 42);
        let (ea, eb) = (EntityId(10), EntityId(20));
        a.spawn_entity(ea);
        b.spawn_entity(eb);
        realm.insert(a);
        realm.insert(b);

        for round in 0..20u128 {
            realm.send(msg(1, 2, 1000 + round, TestPayload::Roll { id: eb }));
            realm.send(msg(2, 1, 2000 + round, TestPayload::Inc { id: ea, by: 1 }));
            if round % 5 == 4 {
                realm.send(msg(1, 99, 3000 + round, TestPayload::Noop)); // dead letter
            }
            realm.tick_all(1);
            realm.step_all();
        }
        // Handoff mid-run: ea moves from island 1 to island 2.
        let p = realm.island_mut(IslandId(1)).unwrap().depart(ea).unwrap().1;
        realm.island_mut(IslandId(2)).unwrap().arrive(ea, p);
        realm.send(msg(1, 2, 5000, TestPayload::Inc { id: ea, by: 100 }));
        realm.tick_all(1);
        realm.step_all();

        let a = realm.island(IslandId(1)).unwrap();
        let b = realm.island(IslandId(2)).unwrap();
        (
            format!("{:?}{:?}", a.outcomes(), b.outcomes()),
            format!("{:?}{:?}", a.state(), b.state()),
            realm.dead_letters.len(),
        )
    };
    let (r1, r2) = (run(), run());
    assert_eq!(r1.0, r2.0, "outcomes replay-identical across both islands");
    assert_eq!(r1.1, r2.1, "states replay-identical");
    assert_eq!(r1.2, 4, "dead letters deterministic too");
}

/// The Realm survives an island dissolving mid-run: later messages to it
/// dead-letter instead of erroring, and its entities live on elsewhere.
/// This is the §10 lifecycle end-to-end. Kill-mutation: Realm::remove not
/// existing (dissolve needs ownership).
#[test]
fn realm_dissolution_end_to_end() {
    let mut realm: Realm<TestDomain> = Realm::new();
    let mut a = island(1, 7);
    let e = EntityId(1);
    a.spawn_entity(e);
    realm.insert(a);
    realm.insert(island(2, 8));

    realm.send(msg(2, 1, 1, TestPayload::Inc { id: e, by: 5 }));
    realm.tick_all(1);
    realm.step_all();

    // Encounter resolves: island 1 dissolves; survivor hands off to island 2.
    let isle = realm.remove(IslandId(1)).unwrap();
    let mut d = isle.dissolve(DissolutionReason::Resolved);
    // Releasing a survivor from a dissolution checkpoint is exactly the
    // host's extract path.
    let portable = <TestDomain as sim_core::Domain>::extract(&mut d.checkpoint.state, e);
    realm.island_mut(IslandId(2)).unwrap().arrive(e, portable);

    // Straggler message to the dissolved island → dead letter, not a crash.
    realm.send(msg(2, 1, 2, TestPayload::Inc { id: e, by: 1 }));
    realm.tick_all(1);
    realm.step_all();

    assert_eq!(realm.dead_letters.len(), 1);
    assert_eq!(realm.island(IslandId(2)).unwrap().state().counters[&e], 5, "entity survived the dissolution");
}

/// Review-impl S2 finding 2: re-spawning over a live id bumps the
/// generation — inserting Gen(0) again would RESURRECT old-epoch refs.
/// Kill-mutation: spawn_entity unconditionally inserting Gen(0).
#[test]
fn respawn_bumps_generation_no_resurrection() {
    let mut isle = island(1, 7);
    let e = EntityId(1);
    let g0 = isle.spawn_entity(e);
    let g1 = isle.spawn_entity(e); // host double-spawn
    assert!(g1 > g0, "re-spawn is a new epoch, not a reset");

    isle.submit(Lane::Live, Admitted::unchecked(input(
        1,
        TestPayload::Inc { id: e, by: 1 },
        vec![Precondition::EntityAlive { id: e, generation: g0 }],
        Fallback::Drop,
    )));
    while isle.step() != StepStatus::Idle {}
    assert!(matches!(
        isle.outcomes().last().unwrap().1,
        Outcome::Discarded {
            reason: DiscardReason::PreconditionFailed(Violation {
                kind: PreconditionKind::EntityAlive,
                ..
            })
        }
    ), "old-epoch ref stays dead");
}

/// Review-impl S2 finding 3: a poisoned island NEVER transfers pending work,
/// even if the host picks a transfer-class reason — §10.1 says a dead
/// island's pending is LOST. Kill-mutation: dropping the poison guard in
/// dissolve().
#[test]
fn poisoned_dissolve_migrating_transfers_nothing() {
    let mut isle = island(1, 7);
    let e = EntityId(1);
    isle.spawn_entity(e);

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Panic, vec![], Fallback::Drop)));
    isle.submit(Lane::Live, Admitted::unchecked(input(2, TestPayload::Inc { id: e, by: 3 }, vec![], Fallback::Drop)));
    while !matches!(isle.step(), StepStatus::Poisoned | StepStatus::Idle) {}
    assert!(isle.is_poisoned());

    let d = isle.dissolve(DissolutionReason::Migrating);
    assert!(d.transferable.is_empty(), "corrupted context launders nothing");
    assert_eq!(d.discarded_pending, 1, "the pending Inc is counted lost");
    assert_eq!(d.quarantined.len(), 1, "the pill stays quarantined");
}

/// Review-impl S2 finding 4: a message routed to a POISONED island is
/// dead-lettered with a recorded reason — delivering it would maroon it in
/// a queue that never steps again. Kill-mutation: Realm delivering without
/// the is_poisoned check.
#[test]
fn realm_dead_letters_message_to_poisoned_island() {
    let mut realm: Realm<TestDomain> = Realm::new();
    let mut a = island(1, 7);
    a.spawn_entity(EntityId(1));
    a.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Panic, vec![], Fallback::Drop)));
    while !matches!(a.step(), StepStatus::Poisoned | StepStatus::Idle) {}
    realm.insert(a);

    realm.send(msg(2, 1, 100, TestPayload::Noop));
    realm.tick_all(1);

    assert_eq!(realm.dead_letters.len(), 1);
    assert_eq!(realm.dead_letters[0].reason, "poisoned island");
}

/// A POISONED island refuses `checkpoint()` — its state may be half-mutated
/// (SC-A8); snapshotting it would smuggle corruption past the poison flag.
/// Kill-mutation: checkpoint() ignoring the poison flag.
#[test]
fn poisoned_island_refuses_checkpoint() {
    let mut isle = island(1, 7);
    isle.spawn_entity(EntityId(1));
    assert!(isle.checkpoint().is_some(), "healthy → Some");

    isle.submit(Lane::Live, Admitted::unchecked(input(1, TestPayload::Panic, vec![], Fallback::Drop)));
    while !matches!(isle.step(), StepStatus::Poisoned | StepStatus::Idle) {}
    assert!(isle.is_poisoned());
    assert!(isle.checkpoint().is_none(), "poisoned → never a checkpoint");
}
