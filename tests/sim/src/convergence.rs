//! Inc-2 — projection-convergence oracle (review HIGH-2).
//!
//! Property: the runtime delivers each aggregate's events in `aggregate_version`
//! order, but DIFFERENT aggregates interleave arbitrarily. Because the real
//! projections are per-aggregate keyed, the FINAL projection state must be
//! independent of the cross-aggregate interleaving:
//!
//! ```text
//!   apply(any legal interleaving)  ==  apply(canonical replay order)
//! ```
//!
//! This is the H1 *convergence* property — NOT S5's Go-vs-Rust differential
//! (both sides here run the SAME real Rust `crates/projections/pc`, by design).
//! It catches a projection that accidentally depends on GLOBAL (cross-aggregate)
//! ordering — a real bug class the bite demonstrates.

use std::sync::Arc;
use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::json;
use uuid::Uuid;

use dp_kernel::event_store::EventStore;
use dp_kernel::{EventEnvelope, Projection, ProjectionUpdate, VerificationMeta};

use crate::exec::{Sim, SimTask, sim_yield};
use crate::store::SimEventStore;
use crate::table::TableStore;

const REALITY: u128 = 0x5151_0000_0000_00C0;
const N_AGGREGATES: usize = 5;

/// Build the fixed event script for aggregate `i`: spawn, then two moves.
fn script(reality: Uuid, i: usize) -> Vec<EventEnvelope> {
    let agg = format!("pc-{i}");
    let mk = |ver: u64, etype: &str, payload: serde_json::Value| EventEnvelope {
        event_id: Uuid::from_u128(((i as u128 + 1) << 32) | ver as u128),
        event_type: etype.into(),
        event_version: 1,
        aggregate_id: agg.clone(),
        aggregate_type: "pc".into(),
        aggregate_version: ver,
        reality_id: reality,
        occurred_at: "2026-01-01T00:00:00Z".into(),
        // Deterministic (NOT now()) → byte-comparable projection state.
        recorded_at: format!("2026-01-01T00:00:{:02}Z", ver),
        payload,
        metadata: None,
    };
    vec![
        mk(
            1,
            "pc.spawned",
            json!({ "user_id": format!("u{i}"), "name": format!("PC{i}"), "spawn_region_id": "r0" }),
        ),
        mk(2, "pc.moved", json!({ "to_region_id": "r1" })),
        mk(3, "pc.moved", json!({ "to_region_id": "r2" })),
    ]
}

/// Apply one envelope through a projection into the shared table-store.
fn project_into(proj: &dyn Projection, env: &EventEnvelope, store: &Mutex<TableStore>) {
    for u in proj.apply_event(env) {
        store.lock().expect("poisoned").apply(&u);
    }
}

/// LIVE run: actors project each aggregate's events into a shared table-store
/// at the moment of delivery — so the table-store observes the seed-chosen
/// GLOBAL interleaving. The `SimEventStore.append_events` call is here only as a
/// per-aggregate ORDERING GUARD (`expected_version` rejects out-of-order
/// delivery); the projection is built from the envelope directly, NOT read back
/// from the store (reading it back would always yield canonical order, hiding
/// the interleaving this oracle exists to test). Review LOW-2.
fn run_live(seed: u64, proj: Arc<dyn Projection + Send + Sync>) -> String {
    let reality = Uuid::from_u128(REALITY);
    let es = Arc::new(SimEventStore::new());
    let table = Arc::new(Mutex::new(TableStore::new()));

    let tasks: Vec<SimTask> = (0..N_AGGREGATES)
        .map(|i| {
            let (es, table, proj) = (es.clone(), table.clone(), proj.clone());
            let evs = script(reality, i);
            Box::pin(async move {
                for (idx, env) in evs.iter().enumerate() {
                    sim_yield().await;
                    es.append_events(
                        env.reality_id,
                        "pc",
                        &env.aggregate_id,
                        idx as u64,
                        std::slice::from_ref(env),
                    )
                    .await
                    .expect("live append must succeed");
                    project_into(&*proj, env, &table);
                }
            }) as SimTask
        })
        .collect();

    Sim::run(seed, tasks);
    table.lock().expect("poisoned").snapshot()
}

/// REPLAY run: aggregate-by-aggregate, each in canonical version order.
fn run_replay(proj: &dyn Projection) -> String {
    let reality = Uuid::from_u128(REALITY);
    let mut table = TableStore::new();
    for i in 0..N_AGGREGATES {
        for env in script(reality, i) {
            for u in proj.apply_event(&env) {
                table.apply(&u);
            }
        }
    }
    table.snapshot()
}

/// The Inc-2 oracle. Returns `Ok(summary)` if every seed converges; `Err` with
/// the diverging seed otherwise.
pub fn check(bite: bool) -> Result<String, String> {
    if bite {
        // BITE: a projection whose output depends on GLOBAL apply order (writes
        // a numbered shared-log row keyed by a per-instance counter, NOT by
        // aggregate). Live (interleaved) and replay (grouped) orders then yield
        // different shared-log contents → the oracle MUST report divergence.
        // Search a sweep (review LOW-1) rather than trusting one hard-coded seed
        // to interleave.
        let replay = run_replay(&GlobalSeqProjection::new());
        for seed in 0..crate::seed_sweep(64) {
            let live = run_live(seed, Arc::new(GlobalSeqProjection::new()));
            if live != replay {
                return Ok(format!(
                    "bite fired: global-order-dependent projection DIVERGED at seed {seed} \
                     (live != replay) — convergence oracle HAS teeth"
                ));
            }
        }
        return Err(
            "bite did NOT fire: a global-order-dependent projection converged across the sweep \
             — the convergence oracle would be VACUOUS"
                .into(),
        );
    }

    // Real projection must converge across the whole sweep.
    let replay = run_replay(&projections_pc::PcProjection);
    let seeds = crate::seed_sweep(64);
    for seed in 0..seeds {
        let live = run_live(seed, Arc::new(projections_pc::PcProjection));
        if live != replay {
            return Err(format!(
                "convergence FAILED at seed {seed}: real PcProjection diverged between \
                 interleaved-apply and canonical replay\n--- live ---\n{live}\n--- replay ---\n{replay}"
            ));
        }
    }
    Ok(format!(
        "convergence OK: real PcProjection over {N_AGGREGATES} aggregates converged to canonical \
         replay across all {seeds} interleavings"
    ))
}

// ── Bite projection: depends on GLOBAL apply order (a real bug class) ─────────

/// Records every event into a single shared `global_seq_log` table, keyed by a
/// per-instance monotonically-increasing apply counter (NOT by aggregate). Its
/// final state therefore reflects the GLOBAL apply order — which differs between
/// an interleaved live run and a grouped replay.
struct GlobalSeqProjection {
    seq: AtomicU64,
}

impl GlobalSeqProjection {
    fn new() -> Self {
        Self {
            seq: AtomicU64::new(0),
        }
    }
}

impl Projection for GlobalSeqProjection {
    fn name(&self) -> &str {
        "global_seq_bite"
    }
    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        let n = self.seq.fetch_add(1, Ordering::SeqCst);
        vec![ProjectionUpdate::Update {
            table: "global_seq_log".into(),
            pk: json!({ "seq": n }),
            fields: json!({ "agg": env.aggregate_id, "ver": env.aggregate_version }),
            meta: VerificationMeta::from_envelope(env),
        }]
    }
}
