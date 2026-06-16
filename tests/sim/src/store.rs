//! `SimEventStore` — the sim's own [`EventStore`] impl (review MED-2).
//!
//! The sim owns this rather than borrowing the kernel's `InMemoryEventStore`
//! (which is explicitly "not part of the public API", `event_store.rs:~442`, and
//! exposes no fault hooks). It re-implements the SAME trait semantics — most
//! importantly the optimistic-concurrency `expected_version` CAS
//! (`event_store.rs:497`) that Oracle 3 (version-CAS) exercises — and adds the
//! crash/fault injection points Oracles 2 and 3 need.
//!
//! It also records a GLOBAL append log: the order events actually landed across
//! all aggregates. That order is the observable interleaving trace the Inc-1
//! non-vacuity gate reads.

use std::collections::HashMap;
use std::sync::Mutex;

use async_trait::async_trait;
use uuid::Uuid;

use dp_kernel::envelope::EventEnvelope;
use dp_kernel::event_store::{EventStore, EventStoreError, EventStoreResult};
use dp_kernel::load_aggregate::SnapshotRecord;

/// `(reality_id, aggregate_type, aggregate_id)` — the per-stream key.
type Key = (Uuid, String, String);

/// Fault-injection knobs. Default = all faults OFF (a faithful, correct store).
/// Inc-3 (atomicity) and Inc-4 (CAS) flip individual knobs to drive their bites.
#[derive(Default, Clone)]
pub struct Faults {
    /// BITE (Inc-3): when set, an append of an N-event batch commits only the
    /// FIRST event then reports a crash — a torn batch that violates the
    /// all-or-none contract. The correct store (this `false`) never tears.
    pub torn_batch_bite: bool,
    /// BITE (Inc-4): when set, `append_events` SKIPS the optimistic-concurrency
    /// version check (and the first-version monotonic check) and appends the
    /// batch blindly — modelling a store that forgot the `WHERE version =
    /// expected` clause. Two racing actors then both land the same version
    /// (lost update). The correct store (this `false`) enforces the CAS.
    pub cas_disabled: bool,
}

struct State {
    streams: HashMap<Key, Vec<EventEnvelope>>,
    snapshots: HashMap<Key, Vec<SnapshotRecord>>,
    /// Global append order — the OBSERVABLE interleaving trace. One entry per
    /// landed event, in real append order: `(key, aggregate_version)`.
    global_log: Vec<(Key, u64)>,
}

/// In-memory, fault-injectable [`EventStore`] for the simulator.
pub struct SimEventStore {
    state: Mutex<State>,
    faults: Faults,
}

impl Default for SimEventStore {
    fn default() -> Self {
        Self::new()
    }
}

impl SimEventStore {
    /// A correct store (no faults).
    pub fn new() -> Self {
        Self::with_faults(Faults::default())
    }

    /// A store with the given fault config (Inc-3+/bites).
    pub fn with_faults(faults: Faults) -> Self {
        Self {
            state: Mutex::new(State {
                streams: HashMap::new(),
                snapshots: HashMap::new(),
                global_log: Vec::new(),
            }),
            faults,
        }
    }

    /// The observable interleaving trace: each landed event as
    /// `"<agg_id>:<version>"`, in global append order.
    pub fn global_trace(&self) -> Vec<String> {
        let st = self.state.lock().expect("poisoned");
        st.global_log
            .iter()
            .map(|((_, _, agg), ver)| format!("{agg}:{ver}"))
            .collect()
    }

    /// Total events landed across all streams.
    pub fn total_events(&self) -> usize {
        self.state.lock().expect("poisoned").global_log.len()
    }

    /// All events for one aggregate, in stored order (for replay/convergence).
    pub fn stream(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
    ) -> Vec<EventEnvelope> {
        let key: Key = (reality_id, aggregate_type.into(), aggregate_id.into());
        self.state
            .lock()
            .expect("poisoned")
            .streams
            .get(&key)
            .cloned()
            .unwrap_or_default()
    }
}

#[async_trait]
impl EventStore for SimEventStore {
    async fn append_events(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        expected_version: u64,
        batch: &[EventEnvelope],
    ) -> EventStoreResult<u64> {
        // Batch-level monotonic check BEFORE any mutation — a bad batch must
        // never partially land (mirrors InMemoryEventStore).
        for w in batch.windows(2) {
            if w[1].aggregate_version <= w[0].aggregate_version {
                return Err(EventStoreError::NonMonotonicBatch {
                    detail: format!(
                        "version {} <= previous {}",
                        w[1].aggregate_version, w[0].aggregate_version
                    ),
                });
            }
        }

        let key: Key = (reality_id, aggregate_type.into(), aggregate_id.into());
        let mut st = self.state.lock().expect("poisoned");
        let current_high = st
            .streams
            .get(&key)
            .and_then(|s| s.last())
            .map(|e| e.aggregate_version)
            .unwrap_or(0);

        // Optimistic-concurrency CAS — the real kernel contract (Oracle 3).
        // The `cas_disabled` bite skips it (and the first-version monotonic
        // check) to model a store that lost its `WHERE version = expected`.
        if !self.faults.cas_disabled {
            if current_high != expected_version {
                return Err(EventStoreError::ConcurrencyConflict {
                    aggregate_type: aggregate_type.into(),
                    aggregate_id: aggregate_id.into(),
                    expected: expected_version,
                    actual: current_high,
                });
            }
            if let Some(first) = batch.first() {
                if first.aggregate_version != current_high + 1 {
                    return Err(EventStoreError::NonMonotonicBatch {
                        detail: format!(
                            "first batch version {} != current_high + 1 ({})",
                            first.aggregate_version,
                            current_high + 1
                        ),
                    });
                }
            }
        }

        // Commit. All-or-none is the contract (Oracle 2). The `torn_batch_bite`
        // fault deliberately commits a PARTIAL batch to prove the atomicity
        // oracle has teeth; the correct path commits the whole batch.
        let commit_n = if self.faults.torn_batch_bite && batch.len() > 1 {
            1
        } else {
            batch.len()
        };
        for e in batch.iter().take(commit_n) {
            st.global_log.push((key.clone(), e.aggregate_version));
            st.streams.entry(key.clone()).or_default().push(e.clone());
        }
        if self.faults.torn_batch_bite && batch.len() > 1 {
            return Err(EventStoreError::Transport(
                "simulated crash mid-batch (torn)".into(),
            ));
        }

        let high = st
            .streams
            .get(&key)
            .and_then(|s| s.last())
            .map(|e| e.aggregate_version)
            .unwrap_or(0);
        Ok(high)
    }

    async fn read_stream(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        after_version: u64,
    ) -> EventStoreResult<Vec<EventEnvelope>> {
        let key: Key = (reality_id, aggregate_type.into(), aggregate_id.into());
        let st = self.state.lock().expect("poisoned");
        Ok(st
            .streams
            .get(&key)
            .map(|v| {
                v.iter()
                    .filter(|e| e.aggregate_version > after_version)
                    .cloned()
                    .collect()
            })
            .unwrap_or_default())
    }

    async fn snapshot_write(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        aggregate_version: u64,
        snapshot_data: serde_json::Value,
        registry_version: Option<i32>,
    ) -> EventStoreResult<()> {
        let key: Key = (reality_id, aggregate_type.into(), aggregate_id.into());
        let mut st = self.state.lock().expect("poisoned");
        st.snapshots.entry(key).or_default().push(SnapshotRecord {
            aggregate_version,
            snapshot_data,
            registry_version,
        });
        Ok(())
    }

    async fn snapshot_read(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
    ) -> EventStoreResult<Option<SnapshotRecord>> {
        let key: Key = (reality_id, aggregate_type.into(), aggregate_id.into());
        let st = self.state.lock().expect("poisoned");
        Ok(st
            .snapshots
            .get(&key)
            .and_then(|v| v.iter().max_by_key(|r| r.aggregate_version).cloned()))
    }
}
