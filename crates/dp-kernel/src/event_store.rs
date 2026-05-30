//! L4.A — `EventStore` trait. The keystone abstraction every service uses to
//! append events + read streams + read/write snapshots.
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L4A-1** — WRAPPED `PgPool` (not exposed). The trait defines the
//!   contract; [`crate::event_store_pg::PgEventStore`] is the Postgres impl
//!   and holds the pool as a `pub(crate)` field. Callers see ONLY the trait
//!   surface, so a future Redis-streams / NATS-JetStream backend swap touches
//!   only the impl boundary.
//!
//! ## Trait shape
//!
//! ```ignore
//! #[async_trait]
//! pub trait EventStore {
//!     async fn append_events(&self, reality_id, batch: &[EventEnvelope]) -> Result<u64, EventStoreError>;
//!     async fn read_stream(&self, reality_id, agg_type, agg_id, after_version) -> Result<Vec<EventEnvelope>, EventStoreError>;
//!     async fn snapshot_write(&self, reality_id, agg_type, agg_id, version, data) -> Result<(), EventStoreError>;
//!     async fn snapshot_read(&self, reality_id, agg_type, agg_id) -> Result<Option<SnapshotRecord>, EventStoreError>;
//! }
//! ```
//!
//! `append_events` returns the new high-water `aggregate_version` after the
//! batch is committed, so callers can pin their cache invalidation key
//! without re-reading. The CONFLICT detection (concurrency) is the store
//! impl's responsibility — see [`EventStoreError::ConcurrencyConflict`].
//!
//! ## Shared test suite
//!
//! [`shared_test_suite::run_event_store_tests`] is a generic harness every
//! EventStore impl must pass. In-memory test impl
//! ([`shared_test_suite::InMemoryEventStore`]) exists to validate the suite
//! itself; the Postgres impl runs the same harness against
//! `docker-compose.yml`-provisioned Postgres (gated behind
//! `LOREWEAVE_TEST_PG_URL`).
//!
//! ## What is NOT in L4.A
//!
//! - **Streaming readers** for huge backlogs — V2+; cycle 17 batches.
//! - **Subscription / change-data-capture** — L2.D publisher already handles
//!   the outbox tail; `EventStore::subscribe` would duplicate.
//! - **Multi-aggregate atomic append** — V1 batch is single-aggregate;
//!   cross-aggregate atomicity is L6/L7 saga work.

use async_trait::async_trait;
use thiserror::Error;
use uuid::Uuid;

use crate::envelope::EventEnvelope;
use crate::load_aggregate::SnapshotRecord;

/// Canonical EventStore error enum. Matches the L4.A.13 contract from the
/// layer plan (`ErrConcurrencyConflict`, `ErrAggregateNotFound`, …) with
/// thiserror-friendly naming.
#[derive(Debug, Error)]
pub enum EventStoreError {
    /// The append batch's `aggregate_version` does not match the current
    /// high-water mark. Caller must reload + retry.
    #[error("concurrency conflict on {aggregate_type}/{aggregate_id}: expected version {expected}, store at {actual}")]
    ConcurrencyConflict {
        aggregate_type: String,
        aggregate_id: String,
        expected: u64,
        actual: u64,
    },

    /// `read_stream` for an aggregate that has zero events.
    #[error("aggregate not found: {aggregate_type}/{aggregate_id}")]
    AggregateNotFound {
        aggregate_type: String,
        aggregate_id: String,
    },

    /// `snapshot_read` for an aggregate with no snapshot row. Distinct from
    /// `AggregateNotFound` so the loader can fall through to full replay.
    #[error("snapshot missing for {aggregate_type}/{aggregate_id}")]
    SnapshotMissing {
        aggregate_type: String,
        aggregate_id: String,
    },

    /// The append batch contains an event whose `aggregate_version` ordering
    /// is non-monotonic relative to the rest of the batch or the store
    /// high-water. Distinct from `ConcurrencyConflict` (which is between
    /// caller-expected vs store-actual); this is an INTRA-batch error.
    #[error("non-monotonic batch: {detail}")]
    NonMonotonicBatch { detail: String },

    /// Envelope failed the L2.I schema check or basic structural validation.
    /// Wrapped from [`crate::EventError::SchemaViolation`] /
    /// [`crate::EventError::UnknownSchema`].
    #[error("schema violation: {0}")]
    SchemaViolation(String),

    /// The underlying transport (sqlx, Redis client, NATS, …) raised an
    /// error. Stringified to keep the trait dependency-free.
    #[error("transport error: {0}")]
    Transport(String),

    /// Catch-all for impl-specific failures. Prefer one of the typed
    /// variants when possible.
    #[error("event store error: {0}")]
    Other(String),
}

/// Result alias to cut visual noise at every signature.
pub type EventStoreResult<T> = Result<T, EventStoreError>;

/// The EventStore trait. Async; one impl per backend.
///
/// Concrete impls MUST be `Send + Sync` so a single store handle can be
/// shared across a tokio runtime's worker threads. The `async_trait` macro
/// adds the Send bound transparently.
#[async_trait]
pub trait EventStore: Send + Sync {
    /// Atomically append a batch of events for a single aggregate within a
    /// reality. Returns the new high-water `aggregate_version` after the
    /// batch lands.
    ///
    /// **Invariants:**
    ///   * All events in `batch` MUST share the same `(reality_id,
    ///     aggregate_type, aggregate_id)`.
    ///   * `batch` MUST be strictly monotonic in `aggregate_version`.
    ///   * `expected_version` MUST equal the store's current high-water (0
    ///     if the aggregate is brand new). Otherwise return
    ///     [`EventStoreError::ConcurrencyConflict`].
    ///   * Append is ATOMIC — either every event lands or none.
    async fn append_events(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        expected_version: u64,
        batch: &[EventEnvelope],
    ) -> EventStoreResult<u64>;

    /// Read all events for `(reality_id, aggregate_type, aggregate_id)`
    /// strictly newer than `after_version`. Pass `0` to fetch the full
    /// stream. Empty Vec is a valid response (no new events since the
    /// supplied high-water mark) — NOT an error.
    async fn read_stream(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        after_version: u64,
    ) -> EventStoreResult<Vec<EventEnvelope>>;

    /// Write (upsert) the latest snapshot row for an aggregate. Older
    /// snapshots are NOT replaced — the loader always SELECTs by max version.
    /// V2+ will add a snapshot-pruner; cycle 17 retains all snapshots.
    async fn snapshot_write(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        aggregate_version: u64,
        snapshot_data: serde_json::Value,
        registry_version: Option<i32>,
    ) -> EventStoreResult<()>;

    /// Read the latest (highest-version) snapshot row for an aggregate.
    /// `Ok(None)` when no snapshot exists — the loader falls through to
    /// full replay.
    async fn snapshot_read(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
    ) -> EventStoreResult<Option<SnapshotRecord>>;
}

// ───────────────────────────────────────────────────────────────────────────
// Shared test suite — every EventStore impl must pass.
// ───────────────────────────────────────────────────────────────────────────

pub mod shared_test_suite {
    //! Generic conformance tests every [`super::EventStore`] impl must pass.
    //!
    //! Reusable across the in-memory test impl AND the
    //! [`crate::event_store_pg::PgEventStore`] integration tests so the two
    //! cannot drift on contract semantics.
    //!
    //! Each test takes an `&S: EventStore` and a fresh `reality_id`. The
    //! caller is responsible for arranging that any state in `S` is isolated
    //! by `reality_id` so the suite can run concurrently on the same store.

    use super::*;
    use serde_json::json;
    use std::sync::Mutex;
    use uuid::Uuid;

    /// Build a deterministic envelope for the test suite.
    pub fn envelope(
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        aggregate_version: u64,
        event_type: &str,
    ) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(aggregate_version as u128),
            event_type: event_type.into(),
            event_version: 1,
            aggregate_id: aggregate_id.into(),
            aggregate_type: aggregate_type.into(),
            aggregate_version,
            reality_id,
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", aggregate_version % 60),
            payload: json!({ "v": aggregate_version }),
            metadata: None,
        }
    }

    /// Run the full conformance suite. Returns Ok(()) on success, panics on
    /// the first failure — easy to plug into `#[tokio::test]`.
    pub async fn run_event_store_tests<S: EventStore>(store: &S, reality_id: Uuid) {
        test_append_and_read_single_event(store, reality_id).await;
        test_append_batch_monotonic(store, reality_id).await;
        test_append_rejects_non_monotonic_batch(store, reality_id).await;
        test_concurrency_conflict_on_stale_expected(store, reality_id).await;
        test_read_empty_stream(store, reality_id).await;
        test_read_after_version_filter(store, reality_id).await;
        test_snapshot_write_then_read(store, reality_id).await;
        test_snapshot_read_missing(store, reality_id).await;
        test_snapshot_overwrite_keeps_highest_version(store, reality_id).await;
        test_reality_isolation(store, reality_id).await;
    }

    async fn test_append_and_read_single_event<S: EventStore>(store: &S, reality: Uuid) {
        let agg_id = "agg-1";
        let env = envelope(reality, "test_agg", agg_id, 1, "test.created");
        let new_v = store
            .append_events(reality, "test_agg", agg_id, 0, std::slice::from_ref(&env))
            .await
            .expect("append");
        assert_eq!(new_v, 1, "high water after one event is 1");

        let read = store
            .read_stream(reality, "test_agg", agg_id, 0)
            .await
            .expect("read");
        assert_eq!(read.len(), 1);
        assert_eq!(read[0], env);
    }

    async fn test_append_batch_monotonic<S: EventStore>(store: &S, reality: Uuid) {
        let agg_id = "agg-batch";
        let batch: Vec<EventEnvelope> = (1..=5)
            .map(|v| envelope(reality, "test_agg", agg_id, v, "test.ticked"))
            .collect();
        let new_v = store
            .append_events(reality, "test_agg", agg_id, 0, &batch)
            .await
            .expect("append batch");
        assert_eq!(new_v, 5);
        let read = store
            .read_stream(reality, "test_agg", agg_id, 0)
            .await
            .expect("read");
        assert_eq!(read.len(), 5);
        for (i, e) in read.iter().enumerate() {
            assert_eq!(e.aggregate_version, (i + 1) as u64);
        }
    }

    async fn test_append_rejects_non_monotonic_batch<S: EventStore>(store: &S, reality: Uuid) {
        let agg_id = "agg-bad-batch";
        // Versions [1, 3, 2] — non-monotonic.
        let batch = vec![
            envelope(reality, "test_agg", agg_id, 1, "test.x"),
            envelope(reality, "test_agg", agg_id, 3, "test.x"),
            envelope(reality, "test_agg", agg_id, 2, "test.x"),
        ];
        let err = store
            .append_events(reality, "test_agg", agg_id, 0, &batch)
            .await
            .expect_err("non-monotonic batch must reject");
        assert!(
            matches!(err, EventStoreError::NonMonotonicBatch { .. }),
            "got {:?}",
            err
        );
        // Aggregate must remain empty (atomic rollback).
        let read = store
            .read_stream(reality, "test_agg", agg_id, 0)
            .await
            .expect("read");
        assert!(read.is_empty(), "rejected batch must not partially land");
    }

    async fn test_concurrency_conflict_on_stale_expected<S: EventStore>(
        store: &S,
        reality: Uuid,
    ) {
        let agg_id = "agg-conflict";
        store
            .append_events(
                reality,
                "test_agg",
                agg_id,
                0,
                &[envelope(reality, "test_agg", agg_id, 1, "test.x")],
            )
            .await
            .expect("first append");

        // Second caller expects version 0 but store is at 1 → conflict.
        let err = store
            .append_events(
                reality,
                "test_agg",
                agg_id,
                0,
                &[envelope(reality, "test_agg", agg_id, 1, "test.x")],
            )
            .await
            .expect_err("must conflict");
        assert!(
            matches!(err, EventStoreError::ConcurrencyConflict { actual: 1, expected: 0, .. }),
            "got {:?}",
            err
        );
    }

    async fn test_read_empty_stream<S: EventStore>(store: &S, reality: Uuid) {
        let read = store
            .read_stream(reality, "test_agg", "nonexistent", 0)
            .await
            .expect("read");
        assert!(read.is_empty(), "missing stream is empty Vec, not Err");
    }

    async fn test_read_after_version_filter<S: EventStore>(store: &S, reality: Uuid) {
        let agg_id = "agg-filter";
        let batch: Vec<EventEnvelope> = (1..=5)
            .map(|v| envelope(reality, "test_agg", agg_id, v, "test.x"))
            .collect();
        store
            .append_events(reality, "test_agg", agg_id, 0, &batch)
            .await
            .unwrap();
        let after_3 = store
            .read_stream(reality, "test_agg", agg_id, 3)
            .await
            .unwrap();
        assert_eq!(after_3.len(), 2, "events 4, 5 returned");
        assert!(after_3.iter().all(|e| e.aggregate_version > 3));
    }

    async fn test_snapshot_write_then_read<S: EventStore>(store: &S, reality: Uuid) {
        let agg_id = "snap-1";
        store
            .snapshot_write(
                reality,
                "test_agg",
                agg_id,
                7,
                json!({ "count": 100 }),
                Some(2),
            )
            .await
            .expect("snap write");
        let got = store
            .snapshot_read(reality, "test_agg", agg_id)
            .await
            .expect("snap read");
        let rec = got.expect("snapshot present");
        assert_eq!(rec.aggregate_version, 7);
        assert_eq!(rec.snapshot_data, json!({ "count": 100 }));
        assert_eq!(rec.registry_version, Some(2));
    }

    async fn test_snapshot_read_missing<S: EventStore>(store: &S, reality: Uuid) {
        let got = store
            .snapshot_read(reality, "test_agg", "no-such-snap")
            .await
            .expect("snap read");
        assert!(got.is_none());
    }

    async fn test_snapshot_overwrite_keeps_highest_version<S: EventStore>(
        store: &S,
        reality: Uuid,
    ) {
        let agg_id = "snap-multi";
        store
            .snapshot_write(reality, "test_agg", agg_id, 3, json!({ "v": 3 }), None)
            .await
            .unwrap();
        store
            .snapshot_write(reality, "test_agg", agg_id, 10, json!({ "v": 10 }), None)
            .await
            .unwrap();
        // The contract says snapshot_read returns the HIGHEST version row.
        // Writing a lower-version one after must not regress the read result.
        store
            .snapshot_write(reality, "test_agg", agg_id, 5, json!({ "v": 5 }), None)
            .await
            .unwrap();
        let got = store
            .snapshot_read(reality, "test_agg", agg_id)
            .await
            .unwrap()
            .expect("snap present");
        assert_eq!(got.aggregate_version, 10, "snapshot_read returns highest version");
    }

    async fn test_reality_isolation<S: EventStore>(store: &S, reality_a: Uuid) {
        // Aggregate in a different reality must not leak into reality_a reads.
        // Re-run-safe: derive a fresh, distinct reality from reality_a rather
        // than a fixed constant. A hardcoded reality_b accumulates rows in a
        // PERSISTENT store (PgEventStore) and breaks idempotency on the 2nd+
        // run (expected_version 0 conflicts with the prior run's v1). XOR with
        // a nonzero mask guarantees reality_b != reality_a.
        let reality_b = Uuid::from_u128(reality_a.as_u128() ^ 0xB000_0000_0000);
        let agg_id = "isolated-agg";
        store
            .append_events(
                reality_b,
                "test_agg",
                agg_id,
                0,
                &[envelope(reality_b, "test_agg", agg_id, 1, "test.x")],
            )
            .await
            .unwrap();
        let from_a = store
            .read_stream(reality_a, "test_agg", agg_id, 0)
            .await
            .unwrap();
        assert!(
            from_a.is_empty(),
            "events in reality_b must not be visible to reality_a"
        );
    }

    // ────────────────────────────────────────────────────────────────────
    // InMemoryEventStore — proves the test suite is itself sound.
    // Not exported as part of the public API; tests rely on it via
    // `use crate::event_store::shared_test_suite::InMemoryEventStore;`.
    // ────────────────────────────────────────────────────────────────────

    type Key = (Uuid, String, String);

    /// Minimal in-memory `EventStore` so the shared test suite + the
    /// `dp-kernel` unit tests can exercise the trait without a Postgres.
    pub struct InMemoryEventStore {
        events: Mutex<std::collections::HashMap<Key, Vec<EventEnvelope>>>,
        snapshots: Mutex<std::collections::HashMap<Key, Vec<SnapshotRecord>>>,
    }

    impl Default for InMemoryEventStore {
        fn default() -> Self {
            Self {
                events: Mutex::new(std::collections::HashMap::new()),
                snapshots: Mutex::new(std::collections::HashMap::new()),
            }
        }
    }

    impl InMemoryEventStore {
        pub fn new() -> Self {
            Self::default()
        }
    }

    #[async_trait]
    impl EventStore for InMemoryEventStore {
        async fn append_events(
            &self,
            reality_id: Uuid,
            aggregate_type: &str,
            aggregate_id: &str,
            expected_version: u64,
            batch: &[EventEnvelope],
        ) -> EventStoreResult<u64> {
            // Non-monotonic check is BATCH-LEVEL — must come before any state
            // mutation so a bad batch can't partially land.
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
            let mut guard = self.events.lock().expect("poisoned");
            let stream = guard.entry(key).or_default();
            let current_high = stream.last().map(|e| e.aggregate_version).unwrap_or(0);
            if current_high != expected_version {
                return Err(EventStoreError::ConcurrencyConflict {
                    aggregate_type: aggregate_type.into(),
                    aggregate_id: aggregate_id.into(),
                    expected: expected_version,
                    actual: current_high,
                });
            }
            // First event in the batch must be exactly current_high + 1.
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
            stream.extend(batch.iter().cloned());
            Ok(stream.last().map(|e| e.aggregate_version).unwrap_or(0))
        }

        async fn read_stream(
            &self,
            reality_id: Uuid,
            aggregate_type: &str,
            aggregate_id: &str,
            after_version: u64,
        ) -> EventStoreResult<Vec<EventEnvelope>> {
            let key: Key = (reality_id, aggregate_type.into(), aggregate_id.into());
            let guard = self.events.lock().expect("poisoned");
            Ok(guard
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
            let mut guard = self.snapshots.lock().expect("poisoned");
            guard.entry(key).or_default().push(SnapshotRecord {
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
            let guard = self.snapshots.lock().expect("poisoned");
            Ok(guard
                .get(&key)
                .and_then(|v| v.iter().max_by_key(|r| r.aggregate_version).cloned()))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::shared_test_suite::*;
    use uuid::Uuid;

    #[tokio::test]
    async fn in_memory_passes_shared_suite() {
        let store = InMemoryEventStore::new();
        let reality = Uuid::from_u128(0xA000_0000_0001);
        run_event_store_tests(&store, reality).await;
    }
}
