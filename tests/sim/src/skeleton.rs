//! Inc-1 skeleton — the harness self-non-vacuity gate.
//!
//! Before any oracle rides on the simulator, the simulator must prove ITSELF
//! sound on two counts:
//!   1. **Reproducible** — same seed ⇒ byte-identical observable trace.
//!   2. **Non-vacuous** — the yield-based scheduling produces TRUE interleaving
//!      (two actors' events genuinely interleaved, not just whole-actor blocks
//!      in a seed-varied order). A sim that can only ever produce one
//!      interleaving proves nothing about concurrency.
//!
//! These run as `#[test]`s (`tests/skeleton.rs`) and as the `sim skeleton`
//! subcommand (so the conformance runner can shell it, Inc-6).

use std::sync::Arc;

use uuid::Uuid;

use dp_kernel::envelope::EventEnvelope;
use dp_kernel::event_store::EventStore;

use crate::exec::{Sim, SimTask, sim_yield};
use crate::store::SimEventStore;

/// Deterministic envelope for the skeleton (payload is irrelevant here).
fn mk_env(reality: Uuid, agg_type: &str, agg_id: &str, version: u64) -> EventEnvelope {
    EventEnvelope {
        event_id: Uuid::from_u128(((agg_id.len() as u128) << 64) ^ version as u128),
        event_type: "SkelAppended".into(),
        event_version: 1,
        aggregate_id: agg_id.into(),
        aggregate_type: agg_type.into(),
        aggregate_version: version,
        reality_id: reality,
        occurred_at: "2026-01-01T00:00:00Z".into(),
        recorded_at: "2026-01-01T00:00:00Z".into(),
        payload: serde_json::json!({ "v": version }),
        metadata: None,
    }
}

/// Build `n_actors` actors, each appending `ops` events to its OWN aggregate.
/// Distinct aggregates ⇒ no CAS conflict, so every append lands; the only
/// variable is the GLOBAL interleaving order, which is exactly what we test.
/// Each op is preceded by a [`sim_yield`] so the scheduler can interleave.
fn build_actors(
    store: Arc<SimEventStore>,
    reality: Uuid,
    n_actors: usize,
    ops: u64,
) -> Vec<SimTask> {
    (0..n_actors)
        .map(|a| {
            let store = store.clone();
            let agg = format!("agg-{a}");
            let fut = async move {
                for v in 1..=ops {
                    sim_yield().await;
                    let env = mk_env(reality, "skel", &agg, v);
                    store
                        .append_events(reality, "skel", &agg, v - 1, &[env])
                        .await
                        .expect("skeleton append must succeed (own aggregate, correct version)");
                }
            };
            Box::pin(fut) as SimTask
        })
        .collect()
}

/// Run the skeleton scenario under `seed` and return the observable trace.
pub fn trace_for(seed: u64) -> Vec<String> {
    let store = Arc::new(SimEventStore::new());
    let reality = Uuid::from_u128(0x5151_0000_0000_0001);
    let tasks = build_actors(store.clone(), reality, 4, 3);
    Sim::run(seed, tasks);
    store.global_trace()
}

/// True if the global trace shows genuine interleaving — some aggregate is
/// "re-entered" after a *different* aggregate ran in between (i.e. its events
/// are not one contiguous block). Without working yield points this is
/// impossible: a non-yielding actor runs all its ops on first poll.
pub fn has_interleaving(trace: &[String]) -> bool {
    use std::collections::HashSet;
    let mut closed: HashSet<&str> = HashSet::new();
    let mut prev: Option<&str> = None;
    for entry in trace {
        let agg = entry.split(':').next().unwrap_or(entry);
        if Some(agg) != prev {
            if let Some(p) = prev {
                closed.insert(p);
            }
            if closed.contains(agg) {
                return true; // re-entered after leaving ⇒ interleaved
            }
        }
        prev = Some(agg);
    }
    false
}

/// The Inc-1 gate, callable from the bin. `Ok(summary)` on pass, `Err` on a
/// soundness violation.
pub fn self_check() -> Result<String, String> {
    // 1. Reproducibility.
    let (a, b) = (trace_for(7), trace_for(7));
    if a != b {
        return Err("reproducibility FAILED: same seed produced two different traces".into());
    }
    // Sanity: every event landed (4 actors × 3 ops).
    if a.len() != 12 {
        return Err(format!("expected 12 landed events, got {}", a.len()));
    }

    // 2. Non-vacuity: at least one seed in a small sweep must truly interleave.
    let sweep = 64u64;
    let interleaved = (0..sweep)
        .filter(|s| has_interleaving(&trace_for(*s)))
        .count();
    if interleaved == 0 {
        return Err(format!(
            "non-vacuity FAILED: no seed in 0..{sweep} interleaved two actors — the yield \
             points are not taking effect, the sim is single-path (vacuous)"
        ));
    }

    Ok(format!(
        "skeleton OK: reproducible (seed 7 → 12 events, stable); non-vacuous \
         ({interleaved}/{sweep} seeds produced true interleaving)"
    ))
}
