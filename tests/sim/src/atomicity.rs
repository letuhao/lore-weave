//! Inc-3 — append-batch atomicity under crash (review HIGH-1).
//!
//! The kernel's REAL crash contract is `append_events` atomicity: "either every
//! event lands or none" (`event_store.rs:128`). The precise, testable form:
//!
//! > a `append_events` call that returns `Err` MUST leave the store byte-for-
//! > byte unchanged (no partial / torn batch); a call that returns `Ok` lands
//! > the WHOLE batch.
//!
//! The sim crashes an actor mid-batch (the `torn_batch_bite` fault commits only
//! the first event then reports a crash) and asserts the store never tore.
//!
//! NOTE: at-least-once *delivery* across a crash is a different property that
//! lives in the Go publisher (outbox→Redis), covered by S8 G1 — it is NOT a
//! Rust-kernel code path, so it is deliberately NOT asserted here.

use std::sync::Arc;
use std::sync::Mutex;

use serde_json::json;
use uuid::Uuid;

use dp_kernel::EventEnvelope;
use dp_kernel::event_store::{EventStore, EventStoreError};

use crate::exec::{Sim, SimTask, sim_yield};
use crate::store::{Faults, SimEventStore};

const REALITY: u128 = 0x5151_0000_0000_00A0;
const N_AGGREGATES: usize = 5;
const BATCH: u64 = 3;
const AGG_TYPE: &str = "ev";

fn batch_for(reality: Uuid, i: usize) -> Vec<EventEnvelope> {
    let agg = format!("ag-{i}");
    (1..=BATCH)
        .map(|ver| EventEnvelope {
            event_id: Uuid::from_u128(((i as u128 + 1) << 32) | ver as u128),
            event_type: "ev.appended".into(),
            event_version: 1,
            aggregate_id: agg.clone(),
            aggregate_type: AGG_TYPE.into(),
            aggregate_version: ver,
            reality_id: reality,
            occurred_at: "2026-01-01T00:00:00Z".into(),
            recorded_at: format!("2026-01-01T00:00:{:02}Z", ver),
            payload: json!({ "v": ver }),
            metadata: None,
        })
        .collect()
}

/// One observed append call: `(aggregate, returned_ok, len_before, len_after)`.
type Call = (String, bool, usize, usize);

/// Run N actors, each appending one `BATCH`-event batch to its own aggregate
/// under the seed-chosen interleaving, recording each call's before/after store
/// length. `bite` enables the torn-batch fault.
fn run(seed: u64, bite: bool) -> Result<String, String> {
    let reality = Uuid::from_u128(REALITY);
    let store = Arc::new(SimEventStore::with_faults(Faults {
        torn_batch_bite: bite,
        ..Default::default()
    }));
    let calls = Arc::new(Mutex::new(Vec::<Call>::new()));

    let tasks: Vec<SimTask> = (0..N_AGGREGATES)
        .map(|i| {
            let (store, calls) = (store.clone(), calls.clone());
            let batch = batch_for(reality, i);
            let agg = format!("ag-{i}");
            Box::pin(async move {
                sim_yield().await;
                let before = store.stream(reality, AGG_TYPE, &agg).len();
                let ok = store
                    .append_events(reality, AGG_TYPE, &agg, 0, &batch)
                    .await
                    .is_ok();
                let after = store.stream(reality, AGG_TYPE, &agg).len();
                calls
                    .lock()
                    .expect("poisoned")
                    .push((agg, ok, before, after));
            }) as SimTask
        })
        .collect();

    Sim::run(seed, tasks);

    // ── Oracle (a): all-or-none per call ────────────────────────────────────
    let recorded = calls.lock().expect("poisoned").clone();
    for (agg, ok, before, after) in &recorded {
        if *ok {
            if *after != *before + BATCH as usize {
                return Err(format!(
                    "partial COMMIT on {agg}: append returned Ok but store went {before}->{after} \
                     (expected +{BATCH})"
                ));
            }
        } else if *after != *before {
            return Err(format!(
                "ATOMICITY VIOLATED on {agg}: append returned Err but store changed {before}->{after} \
                 — a torn batch landed (all-or-none broken)"
            ));
        }
    }

    // ── Oracle (b): every stored stream is a contiguous 1..=k prefix ─────────
    for i in 0..N_AGGREGATES {
        let agg = format!("ag-{i}");
        let versions: Vec<u64> = store
            .stream(reality, AGG_TYPE, &agg)
            .iter()
            .map(|e| e.aggregate_version)
            .collect();
        for (idx, v) in versions.iter().enumerate() {
            if *v != idx as u64 + 1 {
                return Err(format!(
                    "non-contiguous stream on {agg}: versions {versions:?} (expected 1..=k)"
                ));
            }
        }
    }

    Ok(format!(
        "all {} appends respected all-or-none; streams contiguous",
        recorded.len()
    ))
}

fn one_ev(reality: Uuid, agg: &str, version: u64) -> EventEnvelope {
    EventEnvelope {
        event_id: Uuid::from_u128(0xE0 ^ ((version as u128) << 8)),
        event_type: "ev.appended".into(),
        event_version: 1,
        aggregate_id: agg.into(),
        aggregate_type: AGG_TYPE.into(),
        aggregate_version: version,
        reality_id: reality,
        occurred_at: "2026-01-01T00:00:00Z".into(),
        recorded_at: "2026-01-01T00:00:00Z".into(),
        payload: json!({ "v": version }),
        metadata: None,
    }
}

/// Positively exercise the REAL store rejecting an append and proving it left
/// the store UNCHANGED — the all-or-none-ON-FAILURE half (review MED-1). The
/// interleaved `run` only ever produces successful appends on the correct
/// store, so without this the failure branch is validated by the bite ALONE.
fn real_failure_is_atomic() -> Result<String, String> {
    let reality = Uuid::from_u128(REALITY ^ 0xFFFF);
    let store = Arc::new(SimEventStore::new()); // a CORRECT store (no faults)
    let outcome: Arc<Mutex<Result<(), String>>> = Arc::new(Mutex::new(Ok(())));
    let task = {
        let (store, outcome) = (store.clone(), outcome.clone());
        Box::pin(async move {
            let agg = "ag-0";
            let r: Result<(), String> = async {
                store
                    .append_events(reality, AGG_TYPE, agg, 0, &batch_for(reality, 0))
                    .await
                    .map_err(|e| format!("setup append failed: {e}"))?;
                let before = store.stream(reality, AGG_TYPE, agg).len();
                if before != BATCH as usize {
                    return Err(format!("setup: expected {BATCH} events, got {before}"));
                }

                // (1) stale expected_version → REAL ConcurrencyConflict; store unchanged.
                let dup = [one_ev(reality, agg, 1)];
                match store.append_events(reality, AGG_TYPE, agg, 0, &dup).await {
                    Err(EventStoreError::ConcurrencyConflict { .. }) => {}
                    other => return Err(format!("expected ConcurrencyConflict, got {other:?}")),
                }
                if store.stream(reality, AGG_TYPE, agg).len() != before {
                    return Err("CAS-rejected append MUTATED the store — not all-or-none".into());
                }

                // (2) gapped first version → REAL NonMonotonicBatch; store unchanged.
                let gap = [one_ev(reality, agg, BATCH + 2)]; // CAS ok (expected=high) but version skips
                match store
                    .append_events(reality, AGG_TYPE, agg, before as u64, &gap)
                    .await
                {
                    Err(EventStoreError::NonMonotonicBatch { .. }) => {}
                    other => return Err(format!("expected NonMonotonicBatch, got {other:?}")),
                }
                if store.stream(reality, AGG_TYPE, agg).len() != before {
                    return Err("non-monotonic-rejected append MUTATED the store".into());
                }
                Ok(())
            }
            .await;
            *outcome.lock().expect("poisoned") = r;
        }) as SimTask
    };
    Sim::run(0, vec![task]);
    let r = outcome.lock().expect("poisoned").clone();
    r.map(|()| "real rejections (CAS conflict, gapped batch) left the store unchanged".to_string())
}

/// The Inc-3 oracle entry point.
pub fn check(bite: bool) -> Result<String, String> {
    if bite {
        // The torn store MUST trip the atomicity oracle.
        match run(7, true) {
            Err(why) => Ok(format!("bite fired: {why}")),
            Ok(_) => Err(
                "bite did NOT fire: torn store still satisfied all-or-none — \
                          atomicity oracle is VACUOUS"
                    .into(),
            ),
        }
    } else {
        // (a) Positively confirm a REAL append rejection is all-or-none (MED-1).
        let rej = real_failure_is_atomic()?;
        // (b) The interleaved batch sweep (successful appends + contiguity).
        let seeds = crate::seed_sweep(64);
        for seed in 0..seeds {
            run(seed, false)?;
        }
        Ok(format!(
            "atomicity OK: {rej}; and {N_AGGREGATES}-aggregate batches respected all-or-none \
             across all {seeds} interleavings"
        ))
    }
}
