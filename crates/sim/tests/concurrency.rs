//! CNC-D5 — the concurrency conformance test.
//!
//! The audit (doc 23) concluded that the game tier is shared-nothing by
//! construction: a repo-wide grep finds no `static mut`, no `Mutex`, no
//! `RwLock`, no atomics anywhere in the island path. That is an argument from
//! *absence*, and absence is exactly the kind of claim that quietly stops
//! being true — one convenient `Arc<Mutex<_>>` at a time, in a commit whose
//! tests all pass.
//!
//! So this file replaces the argument with a measurement. It asserts the
//! property that shared-nothing actually buys:
//!
//! > **Running N islands concurrently on N threads produces byte-identical
//! > outcomes to running the same N islands sequentially on one thread.**
//!
//! If a future change introduces shared mutable state, cross-island
//! interference, or any dependence on thread scheduling, these tests go red —
//! and they go red *deterministically*, not one run in a thousand, because the
//! kernel has no ambient clock and no ambient randomness (`DetRng`, injected
//! `Tick`, `BTreeMap` everywhere). Most systems cannot write this test; this
//! one can, and the cost of not writing it is finding out in production.
//!
//! What this does NOT claim: nothing here exercises Postgres, Redis, or the
//! epoch fence. It is scoped to the kernel — which is the layer where a
//! concurrency regression would be silent, because the DB layer fails loudly
//! (`WrongChannelWriter`) while a data race just returns a different answer.

use std::sync::Arc;
use std::thread;

use sim_core::{
    Admitted, Class, DiscardReason, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane,
    Outcome, Producer, QueuedInput, SeenWindow, Seq, StepStatus,
};

use sim::{TestDomain, TestPayload, TestRules, TestState};

/// `TestRules` has no Default (it is the RLS-A12 rules slice, deliberately
/// explicit); a fixed ceiling keeps the fleet reproducible.
const MAX_COUNTER: i64 = 1_000_000;

const ISLANDS: u64 = 8;
const INPUTS_PER_ISLAND: u64 = 200;

/// One island's whole observable result, flattened to a comparable string.
/// Comparing the *rendered* outcome log rather than a hash keeps a failure
/// readable: an assertion that two hashes differ tells you nothing about how.
type Digest = Vec<String>;

fn island_for(id: u64) -> Island<TestDomain> {
    Island::new(
        IslandId(id),
        // Seed derived from the island id: distinct streams per island, but
        // reproducible across runs and across thread counts.
        0xC0FFEE_u64.wrapping_mul(id + 1),
        Arc::new(TestRules { max_counter: MAX_COUNTER }),
        SeenWindow::Unbounded,
        TestState::default(),
    )
}

/// A deterministic input mix per island: a few duplicates and a superseded
/// item, so the digest covers the interesting outcome variants rather than a
/// uniform stream of successes.
fn inputs_for(island: u64) -> Vec<QueuedInput<TestDomain>> {
    (0..INPUTS_PER_ISLAND)
        .map(|i| {
            // Every 17th input repeats an earlier id — exercises the I2 dedup
            // path, whose state is per-island and would be the first thing a
            // shared-state bug corrupted.
            let input_id = if i % 17 == 0 && i > 0 { i - 1 } else { i };
            QueuedInput {
                seq: Seq(u64::MAX),
                input_id: InputId((island as u128) << 64 | input_id as u128),
                class: Class::B,
                source: Producer::PlayerInput,
                // `Roll` exercises DetRng — the strongest determinism probe available:
                // any ambient randomness would diverge across threads immediately.
                payload: if i % 5 == 0 {
                    TestPayload::Roll { id: EntityId(1) }
                } else {
                    TestPayload::Inc { id: EntityId(1), by: ((island + i) % 7) as i64 + 1 }
                },
                preconditions: vec![],
                on_invalid: Fallback::Drop,
                admitted_gen: Gen(0),
                deadline: None,
            }
        })
        .collect()
}

/// Drive one island to completion and render its outcome log.
fn run_island(id: u64) -> Digest {
    let mut isle = island_for(id);
    isle.spawn_entity(EntityId(1));
    for input in inputs_for(id) {
        isle.submit(Lane::Live, Admitted::unchecked(input));
    }
    while matches!(isle.step(), StepStatus::Processed(_)) {}

    isle.outcomes()
        .iter()
        .map(|(seq, o)| match o {
            Outcome::Applied { events } => format!("{}:applied:{:?}", seq.0, events),
            Outcome::Discarded { reason } => format!("{}:discarded:{}", seq.0, name(reason)),
            Outcome::Buffered => format!("{}:buffered", seq.0),
        })
        .collect()
}

fn name(r: &DiscardReason) -> &'static str {
    match r {
        DiscardReason::Duplicate => "duplicate",
        DiscardReason::PreconditionFailed(_) => "precondition",
        DiscardReason::Superseded => "superseded",
        DiscardReason::Expired => "expired",
        DiscardReason::Quarantined => "quarantined",
    }
}

/// **The conformance property.** Sequential and concurrent execution of the
/// same islands must agree exactly.
///
/// Kill-mutations this would catch: an island reaching shared mutable state ·
/// a `static` counter feeding into `Seq` or `input_id` · rules held by a
/// shared `RefCell`/`Mutex` whose interleaving changes results · any use of an
/// ambient clock or `rand::random()` inside the kernel.
#[test]
fn n_threads_produce_identical_outcomes_to_one_thread() {
    let sequential: Vec<Digest> = (0..ISLANDS).map(run_island).collect();

    let concurrent: Vec<Digest> = {
        let handles: Vec<_> = (0..ISLANDS).map(|id| thread::spawn(move || run_island(id))).collect();
        handles.into_iter().map(|h| h.join().expect("island thread panicked")).collect()
    };

    assert_eq!(
        sequential.len(),
        concurrent.len(),
        "same number of islands either way"
    );
    for (id, (seq_digest, con_digest)) in sequential.iter().zip(&concurrent).enumerate() {
        assert_eq!(
            seq_digest, con_digest,
            "island {id} produced different outcomes when run concurrently — \
             something in the island path is no longer shared-nothing"
        );
    }
}

/// Repeated concurrent runs must also agree with EACH OTHER. A single
/// sequential-vs-concurrent comparison can pass by luck if a race happens to
/// resolve the same way once; running the fleet several times and demanding
/// unanimity is what turns "probably fine" into a real signal.
#[test]
fn repeated_concurrent_runs_are_identical_to_each_other() {
    let runs: Vec<Vec<Digest>> = (0..5)
        .map(|_| {
            let handles: Vec<_> =
                (0..ISLANDS).map(|id| thread::spawn(move || run_island(id))).collect();
            handles.into_iter().map(|h| h.join().expect("island thread panicked")).collect()
        })
        .collect();

    for (n, run) in runs.iter().enumerate().skip(1) {
        assert_eq!(
            &runs[0], run,
            "concurrent run {n} disagreed with run 0 — the kernel is scheduling-dependent"
        );
    }
}

/// Islands must not observe one another. Running island A alone must give the
/// same answer as running it in a fleet of eight — otherwise "one island = one
/// unit of parallelism" (SL-A9) is not true, and the C2 scaling numbers in
/// doc 21 measure something other than what they claim.
#[test]
fn an_island_result_does_not_depend_on_its_neighbours() {
    let alone = run_island(3);

    let in_a_crowd = {
        let handles: Vec<_> = (0..ISLANDS).map(|id| thread::spawn(move || run_island(id))).collect();
        let all: Vec<Digest> =
            handles.into_iter().map(|h| h.join().expect("island thread panicked")).collect();
        all[3].clone()
    };

    assert_eq!(alone, in_a_crowd, "island 3 was influenced by its neighbours");
}

/// The test fleet must actually exercise the paths it claims to. Without this,
/// a refactor that made every input a no-op would leave the three tests above
/// passing on empty logs — comparing nothing to nothing, unanimously.
#[test]
fn the_fleet_produces_a_non_trivial_outcome_mix() {
    let d = run_island(1);
    assert_eq!(d.len(), INPUTS_PER_ISLAND as usize, "every input got an outcome");
    assert!(d.iter().any(|l| l.contains("applied")), "some inputs applied");
    assert!(
        d.iter().any(|l| l.contains("duplicate")),
        "the dedup path was exercised — otherwise the comparison misses per-island state"
    );
}
