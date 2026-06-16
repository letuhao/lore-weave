//! G3 (structural perf-shape gate) — criterion micro-bench over the REAL
//! projection hot path a higher-layer rebuild change would regress:
//!
//!   1. `ProjectionRunner::apply_one` — the inner loop the production rebuilder
//!      runs per event (`crates/rebuilder/src/lib.rs:315`,
//!      `services/world-service/src/rebuild/global.rs:86`). Benched over the
//!      FULL 11-projection set returned by `all_projections()` (F4) — NOT a
//!      subset — so a regression in ANY registered arm's `handles`/`apply_event`
//!      is visible, not just the relationship/canon arms.
//!   2. `build_stmt` — the rebuild writer's per-update SQL construction, via the
//!      `build_stmt_sql_for_bench` shim over the REAL private fn (F3) — a copy in
//!      the bench would let a regression hide behind drift, so we call through.
//!
//! This is the per-PR structural gate (`scripts/perf/rust-bench-gate.sh`): a
//! same-runner A/B vs the base ref, with a `--bite` non-vacuity proof. It does
//! NOT gate wall-clock µs (cross-machine variance → flaky); criterion's
//! same-run statistical comparison is machine-relative by construction.
//!
//! ## Bite (LW_PERF_BITE) — F6 sizing
//! With `LW_PERF_BITE=1` each benched closure does a SMALL extra synthetic cost
//! (default 500-iter spin, overridable via `LW_PERF_BITE_ITERS`) sized to a
//! REALISTIC regression the gate must catch — empirically ≈+50% on the
//! ~0.53 µs `apply_one/npc.said` baseline (measured 2026-06-15), NOT a 10×
//! blow-up that would only prove the gate isn't completely dead (4000 iters gave
//! +195%, a 3× blow-up). criterion's own detection floor is its statistical
//! threshold (~2–5% at p<0.05); the ~50% bite sits comfortably above CI-runner
//! noise while staying in true-regression territory (an N+1 doubling work).
//! `rust-bench-gate.sh --bite` runs clean→bitten on the same runner and asserts
//! criterion flags the regression (else the gate is vacuous → exit 1).

use std::hint::black_box;

use criterion::{Criterion, criterion_group, criterion_main};
use dp_kernel::{EventEnvelope, Projection, ProjectionRunner, ProjectionUpdate};
use world_service::rebuild::{all_projections, writer::build_stmt_sql_for_bench};

/// Deserialize just the `envelope` out of a golden fixture (the rest —
/// `expected_updates`, `_spec` — is ignored). Reusing the C2 golden fixtures
/// keeps the benched events identical to the ones the conformance battery pins.
#[derive(serde::Deserialize)]
struct FxEnvelope {
    envelope: EventEnvelope,
}

fn env_of(bytes: &str) -> EventEnvelope {
    serde_json::from_str::<FxEnvelope>(bytes)
        .expect("golden fixture envelope must parse")
        .envelope
}

/// A spread of events that, between them, exercise every one of the 11
/// registered projections' `apply_event` paths (so the apply_one bench is
/// representative of a real mixed-event rebuild, not one hot arm).
fn representative_events() -> Vec<(&'static str, EventEnvelope)> {
    // include_str! is relative to THIS file (services/world-service/benches/):
    // ../../../crates → repo-root/crates.
    macro_rules! fx {
        ($name:literal, $file:literal) => {
            (
                $name,
                env_of(include_str!(concat!(
                    "../../../crates/projection-golden/fixtures/",
                    $file
                ))),
            )
        };
    }
    vec![
        fx!("npc.said", "npc.said.json"),
        fx!("npc.relationship_changed", "npc.relationship_changed.json"),
        fx!("npc.memory_embedded", "npc.memory_embedded.json"),
        fx!("npc.created", "npc.created.json"),
        fx!("pc.moved", "pc.moved.json"),
        fx!("pc.relationship_changed", "pc.relationship_changed.json"),
        fx!("pc.item_acquired", "pc.item_acquired.json"),
        fx!("pc.spawned", "pc.spawned.json"),
        fx!("canon.entry.created", "canon.entry.created.json"),
        fx!("region.created", "region.created.json"),
        fx!("session.started", "session.started.json"),
        fx!("world.kv_set", "world.kv_set.json"),
    ]
}

/// Build a runner holding the FULL production projection set (F4).
fn full_runner() -> ProjectionRunner<'static> {
    // `all_projections()` leaks one `&'static` of each stateless projection
    // struct (the production pattern). Called once per bench process.
    let projs: Vec<&'static dyn Projection> = all_projections()
        .into_iter()
        .map(|p| p as &dyn Projection)
        .collect();
    let mut runner = ProjectionRunner::new();
    for p in projs {
        runner = runner.with_projection(p);
    }
    runner
}

/// F6 bite: a small, tunable synthetic cost. Default 500 iters lands at ≈+50% on
/// these micro-benches (a realistic regression, not a 10× blow-up);
/// `LW_PERF_BITE_ITERS` lets the gate recalibrate the magnitude without a recompile.
#[inline(never)]
fn bite_work() {
    let iters: u64 = std::env::var("LW_PERF_BITE_ITERS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(500);
    let mut acc = 0u64;
    let mut sink = Vec::with_capacity(64);
    for i in 0..iters {
        acc = acc.wrapping_add(i.wrapping_mul(2_654_435_761));
        if i % 64 == 0 {
            sink.push(acc as u8);
        }
    }
    black_box(acc);
    black_box(sink);
}

fn bite_on() -> bool {
    std::env::var("LW_PERF_BITE")
        .map(|v| v == "1")
        .unwrap_or(false)
}

fn bench_apply_one(c: &mut Criterion) {
    let bite = bite_on();
    let runner = full_runner();
    let events = representative_events();

    let mut group = c.benchmark_group("apply_one");
    group.sample_size(50);
    for (name, env) in &events {
        group.bench_function(*name, |b| {
            b.iter(|| {
                let out = runner.apply_one(black_box(env));
                if bite {
                    bite_work();
                }
                black_box(out);
            });
        });
    }
    group.finish();
}

fn bench_build_stmt(c: &mut Criterion) {
    let bite = bite_on();
    let runner = full_runner();
    let events = representative_events();

    // Materialize a representative (table, update) work-list by running the
    // events through the real projections, keeping only updates the real
    // builder accepts (some variants — e.g. Tombstone — may not be buildable
    // for every table; filtering keeps the bench measuring the real build path).
    let work: Vec<(String, ProjectionUpdate)> = events
        .iter()
        .flat_map(|(_, env)| {
            runner
                .apply_one(env)
                .into_iter()
                .map(|u| (u.table().to_string(), u))
        })
        .filter(|(t, u)| build_stmt_sql_for_bench(t, u).is_ok())
        .collect();
    assert!(
        !work.is_empty(),
        "build_stmt bench must have at least one buildable update"
    );

    let mut group = c.benchmark_group("build_stmt");
    group.sample_size(50);
    group.bench_function("representative_updates", |b| {
        b.iter(|| {
            for (t, u) in &work {
                let sql = build_stmt_sql_for_bench(black_box(t), black_box(u))
                    .expect("prefiltered to Ok");
                black_box(sql);
            }
            if bite {
                bite_work();
            }
        });
    });
    group.finish();
}

criterion_group!(benches, bench_apply_one, bench_build_stmt);
criterion_main!(benches);
