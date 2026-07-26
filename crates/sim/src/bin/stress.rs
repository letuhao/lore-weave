//! S1a stress profiles — ns/step under adversarial mixes + metrics report.
//! Run `--release`. Numbers land in docs/plans/2026-07-26-sim-core-s1a.md.

use std::sync::Arc;
use std::time::Instant;

use sim::{input, Qi, TestDomain, TestPayload, TestRules, TestState};
use sim_core::{
    EntityId, Fallback, Island, IslandId, Lane, Precondition, RulesetDigest, SeenWindow,
    StepStatus,
};

fn fresh(entities: u64) -> Island<TestDomain> {
    let mut st = TestState::default();
    for i in 1..=entities {
        st.qi.insert(EntityId(i), i64::MAX / 2);
    }
    let mut isle = Island::new(
        IslandId(1),
        42,
        Arc::new(TestRules { max_counter: i64::MAX }),
        RulesetDigest([0u8; 32]),
        SeenWindow::TtlTicks(300),
        st,
    );
    for i in 1..=entities {
        isle.spawn_entity(EntityId(i));
    }
    isle
}

fn run(name: &str, isle: &mut Island<TestDomain>, n: u128, mut submit: impl FnMut(&mut Island<TestDomain>, u128)) {
    for i in 0..n {
        submit(isle, i);
        // Keep queues shallow like a live island: step as we go, tick sometimes.
        if i % 64 == 63 {
            while isle.step() != StepStatus::Idle {}
            if i % 4096 == 4095 {
                isle.tick(1);
            }
        }
    }
    let t = Instant::now();
    let mut steps = 0u64;
    while isle.step() != StepStatus::Idle {
        steps += 1;
    }
    // Steady-state measurement: refill and drain once more, timed whole.
    let t2 = Instant::now();
    let m = isle.metrics().clone();
    let _ = t2;
    let el = t.elapsed();
    println!(
        "{name:<28} tail-steps {steps:>7}  metrics: steps={} applied={} dup={} pre={} buf_ep={} rebuf={} peak(seen={}, ingress={}, buffered={})",
        m.steps_processed, m.applied, m.discarded_duplicate, m.discarded_precondition,
        m.buffered_episodes, m.rebuffer_cycles, m.peak_seen_len, m.peak_ingress_depth,
        m.peak_buffered_len
    );
    let _ = el;
}

fn timed_uniform(name: &str, entities: u64, n: u128, mut mk: impl FnMut(u128) -> (Vec<Precondition<TestDomain>>, TestPayload)) {
    let mut isle = fresh(entities);
    // Preload everything, then time one pure drain — isolates step cost.
    for i in 0..n {
        let (pre, payload) = mk(i);
        isle.submit(Lane::Live, input(i, payload, pre, Fallback::Drop));
    }
    let t = Instant::now();
    let mut steps = 0u64;
    while isle.step() != StepStatus::Idle {
        steps += 1;
    }
    let el = t.elapsed();
    let ns = el.as_nanos() as f64 / steps as f64;
    println!(
        "{name:<28} {steps:>7} steps  {ns:>7.0} ns/step  {:>10.0} steps/sec",
        1e9 / ns
    );
}

fn main() {
    const N: u128 = 100_000;
    println!("== timed profiles (pure drain, release for real numbers) ==");
    let e1 = EntityId(1);

    timed_uniform("baseline Inc (0 pre)", 1, N, |_| {
        (vec![], TestPayload::Inc { id: e1, by: 1 })
    });
    timed_uniform("4 structural preconds", 4, N, |_| {
        (
            vec![
                Precondition::IslandOwns { id: EntityId(1) },
                Precondition::IslandOwns { id: EntityId(2) },
                Precondition::IslandOwns { id: EntityId(3) },
                Precondition::IslandOwns { id: EntityId(4) },
            ],
            TestPayload::Inc { id: e1, by: 1 },
        )
    });
    timed_uniform("semantic precond (spend)", 1, N, |_| {
        (
            vec![Precondition::ResourceAtLeast { id: e1, kind: Qi, amount: 1 }],
            TestPayload::Spend { id: e1, amount: 1 },
        )
    });
    timed_uniform("dup-heavy (50%)", 1, N, |i| {
        // Every odd id repeats the previous even id.
        let id = if i % 2 == 1 { i - 1 } else { i };
        let _ = id; // id passed via closure input below
        (vec![], TestPayload::Inc { id: e1, by: 1 })
    });
    // dup-heavy needs distinct input-id control — do it inline:
    {
        let mut isle = fresh(1);
        for i in 0..N {
            let dup_id = if i % 2 == 1 { i - 1 } else { i };
            isle.submit(Lane::Live, input(dup_id, TestPayload::Inc { id: e1, by: 1 }, vec![], Fallback::Drop));
        }
        let t = Instant::now();
        let mut steps = 0u64;
        while isle.step() != StepStatus::Idle {
            steps += 1;
        }
        let el = t.elapsed();
        let ns = el.as_nanos() as f64 / steps as f64;
        let m = isle.metrics();
        println!(
            "dup-heavy TRUE (50%)         {steps:>7} steps  {ns:>7.0} ns/step  dup_discards={}",
            m.discarded_duplicate
        );
        assert_eq!(m.discarded_duplicate, (N / 2) as u64);
    }
    timed_uniform("big-state 10k entities", 10_000, N, |i| {
        let e = EntityId((i % 10_000 + 1) as u64);
        (vec![Precondition::IslandOwns { id: e }], TestPayload::Inc { id: e, by: 1 })
    });

    println!("\n== mixed live-island simulation (interleaved submit/step/tick) ==");
    let mut isle = fresh(8);
    run("mixed live-island", &mut isle, N, |isle, i| {
        let e = EntityId((i % 8 + 1) as u64);
        match i % 10 {
            0..=5 => {
                isle.submit(Lane::Live, input(i, TestPayload::Inc { id: e, by: 1 }, vec![], Fallback::Drop));
            }
            6 | 7 => {
                isle.submit(Lane::Live, input(i, TestPayload::Roll { id: e }, vec![], Fallback::Drop));
            }
            8 => {
                isle.submit(Lane::Background, input(i, TestPayload::Spend { id: e, amount: 1 },
                    vec![Precondition::ResourceAtLeast { id: e, kind: Qi, amount: 1 }], Fallback::Drop));
            }
            _ => {
                isle.submit(Lane::Live, input(i / 2, TestPayload::Noop, vec![], Fallback::Drop)); // dup
            }
        }
    });

    println!("\n(record into docs/plans/2026-07-26-sim-core-s1a.md §measurements)");
}
