//! L3.C — Snapshot READ runtime (`load_aggregate`).
//!
//! ## Scope (RAID cycle 12)
//!
//! Reconstructs an aggregate's current state by:
//!   1. Consulting the [`SnapshotStore`] for the latest snapshot row (if any).
//!   2. Asking the [`EventReader`] for events strictly newer than the
//!      snapshot's `aggregate_version` (or all events when no snapshot).
//!   3. Folding events through `A::apply(env)` in order.
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3-2**: sync only. No `async fn` here.
//! - **Q-L3-4**: snapshots themselves do NOT carry verification metadata
//!   columns (per `0004_aggregate_snapshots_table.up.sql` comment: "snapshots
//!   are a write-path cache, not the SSOT"). Verification metadata sits on
//!   the projection rows produced by L3.B (sibling DPS).
//! - **L2.E snapshot table** (cycle 9, `aggregate_snapshots`): the
//!   `SnapshotStore` trait wraps the SELECT-latest query against this table.
//!
//! ## Three load paths
//!
//! | Path | Snapshot row | Events since snap | Behavior |
//! |---|---|---|---|
//! | A | NONE | ANY | Fold all events from v0 (cold path) |
//! | B | EXISTS | ANY > 0 | Deserialize snapshot, fold delta events |
//! | C | EXISTS | NONE | Return snapshot directly (no fold) |
//!
//! All three are covered by tests in this module.
//!
//! ## What is NOT in cycle 12
//!
//! - **`sqlx` / `tokio-postgres` impls of `SnapshotStore` / `EventReader`**
//!   — wired in cycle 14+ when world-service uses this. Cycle 12 ships the
//!   trait shape + an in-memory test impl (matches outbox.rs design).
//! - **Streaming event reader** for huge backlogs — V2+. Cycle 12 batches.
//!   The L3.C acceptance bar (< 50ms P99 at version 10K) is met by the
//!   snapshot fast-path; the cold path is intentionally rare.
//! - **Redis tier cache** — process-local LRU only (see `snapshot_cache.rs`).
//! - **Cache invalidation wired to L2.D publisher** — cycle 14+ integration.
//!   Cycle 12 exposes `SnapshotCache::invalidate` for the wiring point.

use serde::{de::DeserializeOwned, Serialize};
use uuid::Uuid;

use crate::envelope::EventEnvelope;
use crate::snapshot_cache::{CacheEntry, CacheKey, SnapshotCache};

/// Errors emitted by the L3.C load path.
#[derive(Debug, thiserror::Error)]
pub enum LoadError {
    /// Snapshot store returned an error (DB unavailable, etc.).
    #[error("snapshot store error: {0}")]
    SnapshotStore(String),

    /// Event reader returned an error.
    #[error("event reader error: {0}")]
    EventReader(String),

    /// Snapshot row exists but its `snapshot_data` cannot be deserialized
    /// into the requested aggregate type. Indicates schema drift the
    /// loader cannot self-heal — caller should fall back to full replay
    /// (cycle 14 will offer a `force_full_replay` knob).
    #[error("snapshot deserialize failure: {0}")]
    SnapshotDeserialize(String),

    /// Aggregate `apply` raised. Per L3.B contract, projections should not
    /// fail on well-formed envelopes; an error here means schema corruption.
    #[error("aggregate apply failure at version {at_version}: {detail}")]
    AggregateApply { at_version: u64, detail: String },
}

/// Trait implemented by per-aggregate state types. The loader is generic
/// over `A: Aggregate` so it can reconstruct PC / NPC / region / etc. with
/// a single code path.
///
/// Implementors are typically `serde::{Serialize, Deserialize}` so they can
/// round-trip through a snapshot row.
pub trait Aggregate: Default + Serialize + DeserializeOwned {
    /// Apply an event to the aggregate, advancing its state.
    ///
    /// MUST be deterministic per `(state, event)` (matches L3.B
    /// `apply_event` contract). Returning `Err` halts the load with
    /// [`LoadError::AggregateApply`].
    fn apply(&mut self, env: &EventEnvelope) -> Result<(), String>;

    /// Current high-water aggregate_version after all applied events.
    /// Used by the loader to know the starting point for delta events.
    fn aggregate_version(&self) -> u64;
}

/// The snapshot row shape returned by the L2.E `aggregate_snapshots` table.
/// Fields match the migration column names 1:1 — keep these in sync if the
/// migration is ever extended.
#[derive(Debug, Clone, PartialEq)]
pub struct SnapshotRecord {
    pub aggregate_version: u64,
    pub snapshot_data: serde_json::Value,
    /// `registry_version` at snapshot time (per migration comment: lets the
    /// loader detect schema drift and decide on fallback). Not used by
    /// cycle-12 load path; logged + carried through for cycle-13+.
    pub registry_version: Option<i32>,
}

/// Abstract snapshot store. Concrete impls wrap `sqlx::PgPool` /
/// `tokio_postgres::Client`; in-memory impls back tests.
pub trait SnapshotStore {
    /// Returns the highest-version snapshot row for the aggregate (per
    /// `aggregate_snapshots` PK ordering — DESC scan on `aggregate_version`).
    /// `Ok(None)` when no row exists (cold path A).
    fn latest_snapshot(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
    ) -> Result<Option<SnapshotRecord>, String>;
}

/// Abstract event reader. Returns events for `(reality_id, aggregate_type,
/// aggregate_id)` strictly newer than `after_version`. Pass `0` to fetch
/// all events from the beginning.
pub trait EventReader {
    fn events_since(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        after_version: u64,
    ) -> Result<Vec<EventEnvelope>, String>;
}

/// Load the latest reconstructed state for an aggregate. Implements the
/// 3-path algorithm documented at module top.
///
/// `cache` is mutable so the loader can both READ (fast path) and WRITE
/// (warm the cache on cold misses). Pass `None` to bypass the cache (e.g.
/// for the integrity checker which MUST hit the source-of-truth).
pub fn load_aggregate<A, S, E>(
    reality_id: Uuid,
    aggregate_type: &str,
    aggregate_id: &str,
    snapshots: &S,
    events: &E,
    cache: Option<&mut SnapshotCache>,
) -> Result<A, LoadError>
where
    A: Aggregate,
    S: SnapshotStore,
    E: EventReader,
{
    let key = CacheKey::new(reality_id, aggregate_type, aggregate_id);

    // ── Fast path: cache hit ──────────────────────────────────────────────
    //
    // The cached entry holds the aggregate state as JSON + its version.
    // We MUST still check the event reader for events newer than the cached
    // version — otherwise stale state is returned. The fast path matters
    // when the answer is "no new events" (read-heavy workload).
    if let Some(c) = &cache {
        // Borrow immutably first to peek without bumping LRU; if hit, we
        // re-grab mutably below to bump.
        let _ = c; // silence unused-mut lint when no entry exists
    }
    if let Some(cache_ref) = cache {
        if let Some(entry) = cache_ref.get(&key) {
            let mut state: A = serde_json::from_value(entry.snapshot_data.clone())
                .map_err(|e| LoadError::SnapshotDeserialize(e.to_string()))?;
            let delta = events
                .events_since(reality_id, aggregate_type, aggregate_id, entry.aggregate_version)
                .map_err(LoadError::EventReader)?;
            for env in &delta {
                state
                    .apply(env)
                    .map_err(|d| LoadError::AggregateApply {
                        at_version: env.aggregate_version,
                        detail: d,
                    })?;
            }
            // Refresh cache only if we actually folded events (avoid pointless
            // re-serialization of unchanged state).
            if !delta.is_empty() {
                let snapshot_data = serde_json::to_value(&state)
                    .map_err(|e| LoadError::SnapshotDeserialize(e.to_string()))?;
                cache_ref.insert(
                    key.clone(),
                    CacheEntry {
                        snapshot_data,
                        aggregate_version: state.aggregate_version(),
                    },
                );
            }
            return Ok(state);
        }
        // ── Cache miss: fall through to snapshot store ────────────────
        let state = load_uncached::<A, S, E>(reality_id, aggregate_type, aggregate_id, snapshots, events)?;
        let snapshot_data = serde_json::to_value(&state)
            .map_err(|e| LoadError::SnapshotDeserialize(e.to_string()))?;
        cache_ref.insert(
            key,
            CacheEntry {
                snapshot_data,
                aggregate_version: state.aggregate_version(),
            },
        );
        return Ok(state);
    }

    // No cache → straight to the source.
    load_uncached::<A, S, E>(reality_id, aggregate_type, aggregate_id, snapshots, events)
}

/// Shared helper for the no-cache path (also used by the cache-miss branch).
/// Implements the 3-path algorithm without any cache concerns.
fn load_uncached<A, S, E>(
    reality_id: Uuid,
    aggregate_type: &str,
    aggregate_id: &str,
    snapshots: &S,
    events: &E,
) -> Result<A, LoadError>
where
    A: Aggregate,
    S: SnapshotStore,
    E: EventReader,
{
    let snap = snapshots
        .latest_snapshot(reality_id, aggregate_type, aggregate_id)
        .map_err(LoadError::SnapshotStore)?;

    let (mut state, after_version) = match snap {
        // Path B / C: snapshot exists. Deserialize then fold delta.
        Some(record) => {
            let state: A = serde_json::from_value(record.snapshot_data.clone())
                .map_err(|e| LoadError::SnapshotDeserialize(e.to_string()))?;
            (state, record.aggregate_version)
        }
        // Path A: no snapshot — fold from v0.
        None => (A::default(), 0u64),
    };

    let delta = events
        .events_since(reality_id, aggregate_type, aggregate_id, after_version)
        .map_err(LoadError::EventReader)?;

    for env in &delta {
        state
            .apply(env)
            .map_err(|d| LoadError::AggregateApply {
                at_version: env.aggregate_version,
                detail: d,
            })?;
    }
    Ok(state)
}

// ───────────────────────────────────────────────────────────────────────────
// Tests — covers all 3 paths + cache hit-rate + edge cases.
// ───────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde::{Deserialize, Serialize};
    use serde_json::json;
    use std::cell::RefCell;
    use std::collections::HashMap;

    // ── Test aggregate: Counter ────────────────────────────────────────────
    #[derive(Default, Serialize, Deserialize, Debug, Clone, PartialEq)]
    struct Counter {
        value: i64,
        version: u64,
    }

    impl Aggregate for Counter {
        fn apply(&mut self, env: &EventEnvelope) -> Result<(), String> {
            match env.event_type.as_str() {
                "counter.incremented" => {
                    let delta = env
                        .payload
                        .get("delta")
                        .and_then(|v| v.as_i64())
                        .ok_or_else(|| "missing 'delta'".to_string())?;
                    self.value += delta;
                }
                "counter.reset" => self.value = 0,
                _ => return Err(format!("unknown event {}", env.event_type)),
            }
            self.version = env.aggregate_version;
            Ok(())
        }
        fn aggregate_version(&self) -> u64 {
            self.version
        }
    }

    // ── In-memory snapshot store + event reader ────────────────────────────
    type SnapKey = (Uuid, String, String);

    struct InMemSnapshots {
        rows: HashMap<SnapKey, SnapshotRecord>,
    }
    impl SnapshotStore for InMemSnapshots {
        fn latest_snapshot(
            &self,
            reality_id: Uuid,
            aggregate_type: &str,
            aggregate_id: &str,
        ) -> Result<Option<SnapshotRecord>, String> {
            Ok(self
                .rows
                .get(&(reality_id, aggregate_type.into(), aggregate_id.into()))
                .cloned())
        }
    }

    struct InMemEvents {
        events: RefCell<HashMap<SnapKey, Vec<EventEnvelope>>>,
        // Optional override: simulate DB failure.
        fail: RefCell<Option<String>>,
    }
    impl InMemEvents {
        fn new() -> Self {
            Self {
                events: RefCell::new(HashMap::new()),
                fail: RefCell::new(None),
            }
        }
        fn push(&self, key: SnapKey, env: EventEnvelope) {
            self.events.borrow_mut().entry(key).or_default().push(env);
        }
    }
    impl EventReader for InMemEvents {
        fn events_since(
            &self,
            reality_id: Uuid,
            aggregate_type: &str,
            aggregate_id: &str,
            after_version: u64,
        ) -> Result<Vec<EventEnvelope>, String> {
            if let Some(err) = self.fail.borrow().clone() {
                return Err(err);
            }
            let key = (reality_id, aggregate_type.into(), aggregate_id.into());
            let all = self.events.borrow();
            let v = all.get(&key).cloned().unwrap_or_default();
            Ok(v.into_iter().filter(|e| e.aggregate_version > after_version).collect())
        }
    }

    fn env(version: u64, delta: i64) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(version as u128),
            event_type: "counter.incremented".into(),
            event_version: 1,
            aggregate_id: "c-1".into(),
            aggregate_type: "counter".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: "2026-05-29T00:00:00Z".into(),
            payload: json!({ "delta": delta }),
            metadata: None,
        }
    }

    fn reality() -> Uuid {
        Uuid::from_u128(0xDEAD)
    }
    fn key() -> SnapKey {
        (reality(), "counter".into(), "c-1".into())
    }

    // ── PATH A: no snapshot, full replay ──────────────────────────────────
    #[test]
    fn path_a_no_snapshot_full_replay() {
        let snaps = InMemSnapshots { rows: HashMap::new() };
        let events = InMemEvents::new();
        events.push(key(), env(1, 5));
        events.push(key(), env(2, 3));
        events.push(key(), env(3, -1));

        let state: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, None).unwrap();
        assert_eq!(state.value, 7);
        assert_eq!(state.version, 3);
    }

    // ── PATH B: snapshot exists + delta events ─────────────────────────────
    #[test]
    fn path_b_snapshot_plus_delta() {
        let mut snaps = InMemSnapshots { rows: HashMap::new() };
        let counter_at_v5 = Counter { value: 100, version: 5 };
        snaps.rows.insert(
            key(),
            SnapshotRecord {
                aggregate_version: 5,
                snapshot_data: serde_json::to_value(&counter_at_v5).unwrap(),
                registry_version: Some(1),
            },
        );
        let events = InMemEvents::new();
        // Older events should be ignored by `events_since(after=5)`.
        events.push(key(), env(1, 999));
        events.push(key(), env(5, 999));
        // Delta:
        events.push(key(), env(6, 10));
        events.push(key(), env(7, -3));

        let state: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, None).unwrap();
        assert_eq!(state.value, 100 + 10 - 3, "snapshot + delta = 107");
        assert_eq!(state.version, 7);
    }

    // ── PATH C: snapshot exists, no events since ───────────────────────────
    #[test]
    fn path_c_snapshot_direct_no_events() {
        let mut snaps = InMemSnapshots { rows: HashMap::new() };
        let counter_at_v9 = Counter { value: 50, version: 9 };
        snaps.rows.insert(
            key(),
            SnapshotRecord {
                aggregate_version: 9,
                snapshot_data: serde_json::to_value(&counter_at_v9).unwrap(),
                registry_version: None,
            },
        );
        let events = InMemEvents::new();
        // Only old events, all <= snapshot.version → filtered out.
        events.push(key(), env(1, 1));
        events.push(key(), env(9, 1));

        let state: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, None).unwrap();
        assert_eq!(state.value, 50, "snapshot returned as-is");
        assert_eq!(state.version, 9);
    }

    // ── Edge case: snapshot_version = 0 should never be written, but if it
    // is (broken writer), the loader still degrades cleanly: it loads the
    // snapshot AND folds events with version >= 1 (after_version=0 filter).
    #[test]
    fn snapshot_version_zero_edge_case() {
        let mut snaps = InMemSnapshots { rows: HashMap::new() };
        let counter_at_v0 = Counter { value: 0, version: 0 };
        snaps.rows.insert(
            key(),
            SnapshotRecord {
                aggregate_version: 0,
                snapshot_data: serde_json::to_value(&counter_at_v0).unwrap(),
                registry_version: None,
            },
        );
        let events = InMemEvents::new();
        events.push(key(), env(1, 11));
        events.push(key(), env(2, 22));

        let state: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, None).unwrap();
        assert_eq!(state.value, 33);
        assert_eq!(state.version, 2);
    }

    // ── Snapshot store error propagates ────────────────────────────────────
    #[test]
    fn snapshot_store_error_propagates() {
        struct FailingSnapshots;
        impl SnapshotStore for FailingSnapshots {
            fn latest_snapshot(
                &self,
                _r: Uuid,
                _at: &str,
                _ai: &str,
            ) -> Result<Option<SnapshotRecord>, String> {
                Err("connection refused".into())
            }
        }
        let events = InMemEvents::new();
        let res: Result<Counter, _> =
            load_aggregate(reality(), "counter", "c-1", &FailingSnapshots, &events, None);
        assert!(matches!(res, Err(LoadError::SnapshotStore(_))));
    }

    // ── Event reader error propagates ──────────────────────────────────────
    #[test]
    fn event_reader_error_propagates() {
        let snaps = InMemSnapshots { rows: HashMap::new() };
        let events = InMemEvents::new();
        *events.fail.borrow_mut() = Some("DB down".into());
        let res: Result<Counter, _> =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, None);
        assert!(matches!(res, Err(LoadError::EventReader(_))));
    }

    // ── Apply failure surfaces with at_version ─────────────────────────────
    #[test]
    fn apply_failure_surfaces_with_version() {
        let snaps = InMemSnapshots { rows: HashMap::new() };
        let events = InMemEvents::new();
        let mut bad = env(1, 0);
        bad.event_type = "unknown".into(); // Counter::apply rejects unknown
        events.push(key(), bad);
        let res: Result<Counter, _> =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, None);
        match res {
            Err(LoadError::AggregateApply { at_version, .. }) => assert_eq!(at_version, 1),
            other => panic!("expected AggregateApply error, got {other:?}"),
        }
    }

    // ── CACHE HIT-RATE TEST: L3.C acceptance ───────────────────────────────
    #[test]
    fn cache_hit_rate_meets_acceptance() {
        let snaps = InMemSnapshots { rows: HashMap::new() };
        let events = InMemEvents::new();
        events.push(key(), env(1, 5));
        let mut cache = SnapshotCache::new(8);

        // First load: cold miss → loads from store, warms cache.
        let s1: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, Some(&mut cache)).unwrap();
        assert_eq!(s1.value, 5);
        assert_eq!(cache.misses(), 1);
        assert_eq!(cache.hits(), 0);

        // Subsequent N loads: cache HITs. No new events → cache state returned as-is.
        for _ in 0..9 {
            let sn: Counter =
                load_aggregate(reality(), "counter", "c-1", &snaps, &events, Some(&mut cache)).unwrap();
            assert_eq!(sn.value, 5);
        }
        assert_eq!(cache.hits(), 9);
        assert_eq!(cache.misses(), 1);
        // L3.C acceptance bar: >= 80% hit rate in steady-state.
        assert!(cache.hit_rate() >= 0.8, "hit_rate={} should meet >= 0.8 bar", cache.hit_rate());
    }

    // ── CACHE COHERENCE: new events folded into cached state ───────────────
    #[test]
    fn cache_hit_path_folds_new_events() {
        let snaps = InMemSnapshots { rows: HashMap::new() };
        let events = InMemEvents::new();
        events.push(key(), env(1, 5));
        let mut cache = SnapshotCache::new(8);

        // Cold load.
        let s1: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, Some(&mut cache)).unwrap();
        assert_eq!(s1.value, 5);

        // New event arrives.
        events.push(key(), env(2, 7));

        // Cache HIT path must still fetch delta and fold (otherwise stale).
        let s2: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, Some(&mut cache)).unwrap();
        assert_eq!(s2.value, 12, "cache hit must fold delta events, not return stale state");
        assert_eq!(s2.version, 2);
    }

    // ── CACHE INVALIDATION: explicit drop forces re-load ───────────────────
    #[test]
    fn cache_invalidate_forces_reload() {
        let snaps = InMemSnapshots { rows: HashMap::new() };
        let events = InMemEvents::new();
        events.push(key(), env(1, 5));
        let mut cache = SnapshotCache::new(8);

        let _: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, Some(&mut cache)).unwrap();
        assert_eq!(cache.misses(), 1);

        cache.invalidate(&CacheKey::new(reality(), "counter", "c-1"));
        assert_eq!(cache.len(), 0);

        let _: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, Some(&mut cache)).unwrap();
        assert_eq!(cache.misses(), 2, "invalidation forced re-load");
    }

    // ── Multi-aggregate isolation in the cache ─────────────────────────────
    #[test]
    fn cache_does_not_leak_across_aggregates() {
        let snaps = InMemSnapshots { rows: HashMap::new() };
        let events = InMemEvents::new();
        let k1: SnapKey = (reality(), "counter".into(), "c-1".into());
        let k2: SnapKey = (reality(), "counter".into(), "c-2".into());

        events.push(k1.clone(), env(1, 10));
        let mut e2 = env(1, 20);
        e2.aggregate_id = "c-2".into();
        events.push(k2.clone(), e2);

        let mut cache = SnapshotCache::new(8);

        let s1: Counter =
            load_aggregate(reality(), "counter", "c-1", &snaps, &events, Some(&mut cache)).unwrap();
        let s2: Counter =
            load_aggregate(reality(), "counter", "c-2", &snaps, &events, Some(&mut cache)).unwrap();

        assert_eq!(s1.value, 10);
        assert_eq!(s2.value, 20);
        assert_eq!(cache.len(), 2);
    }
}
