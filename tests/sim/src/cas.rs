//! Inc-4 — optimistic-concurrency (version) CAS oracle (review MED-1).
//!
//! The CAS is a REAL in-process Rust path: `append_events(expected_version)` →
//! `ConcurrencyConflict` when stale (`event_store.rs:497`). K actors race
//! single-event appends to ONE shared aggregate, each doing the classic
//! optimistic loop: read high-water → (yield: a rival may commit) → append with
//! the read version → retry on conflict. The CAS must serialize them so the
//! final stream is `1..=K`, strictly monotonic, NO duplicate version (no lost
//! update).
//!
//! Higher lifecycle semantics (no double-spawn / illegal-transition) have no
//! reusable Rust state-machine (Inc-1 verdict, README) — that is S9's model and
//! is out of scope here.

use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::json;
use uuid::Uuid;

use dp_kernel::EventEnvelope;
use dp_kernel::event_store::{EventStore, EventStoreError};

use crate::exec::{Sim, SimTask, sim_yield};
use crate::store::{Faults, SimEventStore};

const REALITY: u128 = 0x5151_0000_0000_00CA;
const K_ACTORS: u64 = 6;
const AGG_TYPE: &str = "shared";
const AGG_ID: &str = "the-one";

fn mk(reality: Uuid, actor: u64, version: u64) -> EventEnvelope {
    EventEnvelope {
        // event_id keyed by the WRITER, so a lost-update dup is visible as two
        // distinct events sharing one aggregate_version.
        event_id: Uuid::from_u128(((actor as u128 + 1) << 40) | version as u128),
        event_type: "shared.touched".into(),
        event_version: 1,
        aggregate_id: AGG_ID.into(),
        aggregate_type: AGG_TYPE.into(),
        aggregate_version: version,
        reality_id: reality,
        occurred_at: "2026-01-01T00:00:00Z".into(),
        recorded_at: "2026-01-01T00:00:00Z".into(),
        payload: json!({ "actor": actor }),
        metadata: None,
    }
}

/// Returns `(stream_versions, total_attempts)` after the race.
fn run(seed: u64, bite: bool) -> (Vec<u64>, u64) {
    let reality = Uuid::from_u128(REALITY);
    let store = Arc::new(SimEventStore::with_faults(Faults {
        cas_disabled: bite,
        ..Default::default()
    }));
    let attempts = Arc::new(AtomicU64::new(0));

    let tasks: Vec<SimTask> = (0..K_ACTORS)
        .map(|actor| {
            let (store, attempts) = (store.clone(), attempts.clone());
            Box::pin(async move {
                loop {
                    // Read the current high-water...
                    let high = store.stream(reality, AGG_TYPE, AGG_ID).len() as u64;
                    // ...then YIELD: a rival may commit here, making `high`
                    // stale — this is what exercises the CAS.
                    sim_yield().await;
                    let env = mk(reality, actor, high + 1);
                    attempts.fetch_add(1, Ordering::SeqCst);
                    match store
                        .append_events(reality, AGG_TYPE, AGG_ID, high, std::slice::from_ref(&env))
                        .await
                    {
                        Ok(_) => break,
                        Err(EventStoreError::ConcurrencyConflict { .. }) => continue,
                        // cas_disabled never conflicts; any other error is a bug.
                        Err(other) => panic!("unexpected append error: {other}"),
                    }
                }
            }) as SimTask
        })
        .collect();

    Sim::run(seed, tasks);

    let versions: Vec<u64> = store
        .stream(reality, AGG_TYPE, AGG_ID)
        .iter()
        .map(|e| e.aggregate_version)
        .collect();
    (versions, attempts.load(Ordering::SeqCst))
}

/// Check the post-race stream is consistent: exactly `1..=K`, strictly
/// monotonic, no duplicate version.
fn stream_consistent(versions: &[u64]) -> Result<(), String> {
    if versions.len() != K_ACTORS as usize {
        return Err(format!(
            "expected {K_ACTORS} committed events, got {}",
            versions.len()
        ));
    }
    for (idx, v) in versions.iter().enumerate() {
        if *v != idx as u64 + 1 {
            return Err(format!("non-1..=K / duplicate version: {versions:?}"));
        }
    }
    Ok(())
}

/// The Inc-4 oracle entry point.
pub fn check(bite: bool) -> Result<String, String> {
    if bite {
        // Without the CAS, some interleaving MUST corrupt the stream (a lost
        // update: two actors land the same version). Find one across a sweep.
        for seed in 0..128u64 {
            let (versions, _) = run(seed, true);
            if stream_consistent(&versions).is_err() {
                return Ok(format!(
                    "bite fired: CAS-disabled store corrupted the stream at seed {seed} \
                     (versions {versions:?}) — the CAS oracle HAS teeth"
                ));
            }
        }
        Err("bite did NOT fire: no seed corrupted a CAS-free store — CAS oracle is VACUOUS".into())
    } else {
        let seeds = crate::seed_sweep(128);
        let mut raced = 0u64; // seeds where a conflict actually occurred
        for seed in 0..seeds {
            let (versions, attempts) = run(seed, false);
            stream_consistent(&versions).map_err(|e| format!("CAS FAILED at seed {seed}: {e}"))?;
            if attempts > K_ACTORS {
                raced += 1;
            }
        }
        // Scenario non-vacuity: across a reasonable sweep, SOME seed must
        // produce a conflict, else the race never happened and the CAS was never
        // exercised. Only enforced for sweeps wide enough to expect a race — a
        // deliberately tiny SIM_SEEDS (< 4) may legitimately not race (review
        // LOW-4), and that is an operator choice, not a failure.
        if raced == 0 && seeds >= 4 {
            return Err(format!(
                "scenario VACUOUS: no seed in 0..{seeds} produced a CAS conflict — the \
                 read→yield→append race is not interleaving"
            ));
        }
        Ok(format!(
            "CAS OK: {K_ACTORS} racing actors always converged to a clean 1..={K_ACTORS} stream \
             across all {seeds} interleavings ({raced} of them actually raced/retried)"
        ))
    }
}
