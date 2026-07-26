//! First measurement bin — the GDA-Q1 / SL-Q11 numbers (ms/step, events/sec,
//! single island, TestDomain). std::Instant only measures the harness, never
//! enters kernel state. Run `--release` for the real number.

use std::sync::Arc;
use std::time::Instant;

use sim::{input, TestDomain, TestPayload, TestRules, TestState};
use sim_core::{EntityId, Fallback, Island, IslandId, Lane, RulesetDigest, SeenWindow, StepStatus};

fn main() {
    const N: u128 = 200_000;

    let mut isle: Island<TestDomain> = Island::new(
        IslandId(1),
        42,
        Arc::new(TestRules { max_counter: i64::MAX }),
        RulesetDigest([0u8; 32]),
        SeenWindow::TtlTicks(300), // cell-island shape: TTL window live
        TestState::default(),
    );
    let e = EntityId(1);
    isle.spawn_entity(e);

    let t_admit = Instant::now();
    for i in 0..N {
        isle.submit(
            Lane::Live,
            input(i, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop),
        );
    }
    let admit = t_admit.elapsed();

    let t_step = Instant::now();
    let mut processed = 0u64;
    while isle.step() != StepStatus::Idle {
        processed += 1;
    }
    let step = t_step.elapsed();

    let ns_per_step = step.as_nanos() as f64 / processed as f64;
    println!("sim-bench S1a — single island, TestDomain::Inc, N={N}");
    println!("  admit: {:?} total ({:.0} ns/item)", admit, admit.as_nanos() as f64 / N as f64);
    println!("  step:  {:?} total ({ns_per_step:.0} ns/step)", step);
    println!("  throughput: {:.0} steps/sec", 1e9 / ns_per_step);
    println!("  (write these into docs/plans/2026-07-26-sim-core-s1a.md §measurements)");
}
