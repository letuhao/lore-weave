//! L4.A — Postgres impl of [`crate::event_store::EventStore`].
//!
//! ## Q-L4A-1 — WRAPPED `PgPool`
//!
//! The `sqlx::PgPool` is held in a private (`pub(crate)`) field on
//! [`PgEventStore`]; callers see ONLY the `EventStore` trait surface. A
//! future Redis-streams / NATS-JetStream backend swap would touch this file
//! and its tests, but no caller code.
//!
//! ## Wired tables
//!
//! - `events`               (cycle 8 / migration 0002) — append + read.
//! - `aggregate_snapshots`  (cycle 9 / migration 0004) — snapshot read/write.
//!
//! Column names in this impl are KEPT IN SYNC with the migration SQL — if
//! the migration changes, the queries below must change too.
//!
//! ## Test gate
//!
//! Postgres integration tests live in `tests/integration_event_store.rs`
//! and are gated behind the `LOREWEAVE_TEST_PG_URL` env var. CI provides
//! the URL via the cycle-1 docker-compose Postgres; dev machines that don't
//! set it simply skip the integration test (the unit suite still runs the
//! `InMemoryEventStore` against the shared conformance harness).

use std::sync::Arc;

use async_trait::async_trait;
use sqlx::postgres::PgPool;
use sqlx::Row;
use uuid::Uuid;

use crate::envelope::EventEnvelope;
use crate::event_store::{EventStore, EventStoreError, EventStoreResult};
use crate::load_aggregate::SnapshotRecord;

/// W1.4 — gate the append path on the reality's lifecycle status.
///
/// The relocation copy/flip (Inc-4) and the closure drain (W1.3) both rely on
/// the source reality being quiesced. An append that lands AFTER the freeze
/// flip would be silently lost (relocation copies a snapshot; the drain
/// declares the outbox empty). This guard rejects appends to a frozen reality.
#[async_trait]
pub trait AppendGuard: Send + Sync {
    /// Return `Ok(())` if `reality_id` accepts new appends, or
    /// [`EventStoreError::RealityFrozen`] if it is frozen/terminal.
    async fn ensure_appendable(&self, reality_id: Uuid) -> EventStoreResult<()>;
}

/// Lifecycle statuses that ACCEPT appends. Everything else (migrating,
/// pending_close, frozen, archived, archived_verified, soft_deleted, dropped)
/// is frozen for appends. Kept as canonical lowercase strings (the
/// `reality_registry.status` CHECK enum) so dp-kernel stays decoupled from
/// `meta-rs`.
pub fn status_accepts_append(status: &str) -> bool {
    matches!(status, "provisioning" | "seeding" | "active")
}

/// Production [`AppendGuard`] — reads `reality_registry.status` from the META
/// DB **uncached** on every append (freeze-settle option (b), plan review #1).
///
/// Why uncached: the transition that freezes a reality is driven by an EXTERNAL
/// actor (the relocation / closure orchestrator), not the reality's own command
/// processor, so a per-reality status CACHE would not be synchronously
/// invalidated by the flip — leaving a TTL window where an append still sees
/// "active" and lands after the flip. An uncached read narrows that window to a
/// single statement.
///
/// SCOPE (review #3 — do NOT overclaim): this rejects every append that BEGINS
/// after the flip commits. It does NOT make a freeze atomic with the append —
/// the status read and the `events` INSERT are in DIFFERENT databases (meta vs
/// per-reality), so an append already in-flight at the flip (read `active`, then
/// flip, then commit) can still land post-flip. Closing that residual in-flight
/// window is the ORCHESTRATOR's job: the closure drain (W1.3) re-polls the outbox
/// to 0 after a settle so a straggler's same-TX outbox row is caught; the
/// relocation copy (Inc-4) must likewise settle/re-checksum after the flip. See
/// D-W1-INFLIGHT-FREEZE-WINDOW. The cost is one indexed PK lookup on the meta DB
/// per append (hot-path overhead unmeasured — D-W1-FREEZE-HOTPATH-COST).
/// Fail-closed: a missing reality row → frozen.
#[derive(Clone)]
pub struct MetaFreezeGuard {
    meta_pool: Arc<PgPool>,
}

impl MetaFreezeGuard {
    /// Construct over the META DB pool (where `reality_registry` lives) — NOT
    /// the per-reality pool the event store writes to.
    pub fn new(meta_pool: Arc<PgPool>) -> Self {
        Self { meta_pool }
    }
}

#[async_trait]
impl AppendGuard for MetaFreezeGuard {
    async fn ensure_appendable(&self, reality_id: Uuid) -> EventStoreResult<()> {
        let status: Option<String> = sqlx::query_scalar(
            "SELECT status FROM reality_registry WHERE reality_id = $1",
        )
        .bind(reality_id)
        .fetch_optional(&*self.meta_pool)
        .await
        .map_err(|e| EventStoreError::Transport(e.to_string()))?;
        match status {
            Some(s) if status_accepts_append(&s) => Ok(()),
            // A known-but-frozen reality, OR an unknown reality (fail-closed:
            // we cannot confirm it is appendable, so we refuse).
            Some(s) => Err(EventStoreError::RealityFrozen { reality_id, status: s }),
            None => Err(EventStoreError::RealityFrozen {
                reality_id,
                status: "unknown".to_string(),
            }),
        }
    }
}

/// Postgres-backed event store. Holds a wrapped [`PgPool`] (Q-L4A-1) so
/// callers never see `sqlx` types in the public API.
///
/// Clone-cheap: internally `Arc<PgPool>`. Construct once at service startup
/// and clone freely.
#[derive(Clone)]
pub struct PgEventStore {
    pub(crate) pool: Arc<PgPool>,
    /// Optional W1.4 write-freeze guard. `None` = no freeze check (the default
    /// for the in-memory/integration tests, which have no meta DB). Production
    /// wires a [`MetaFreezeGuard`] over the meta pool.
    freeze_guard: Option<Arc<dyn AppendGuard>>,
}

impl PgEventStore {
    /// Construct from a pre-built `PgPool`. The pool is wrapped in an `Arc`
    /// so this struct can be cloned freely. No freeze guard (back-compat).
    pub fn new(pool: PgPool) -> Self {
        Self { pool: Arc::new(pool), freeze_guard: None }
    }

    /// Construct from an already-shared pool. No freeze guard.
    pub fn from_arc(pool: Arc<PgPool>) -> Self {
        Self { pool, freeze_guard: None }
    }

    /// Attach a W1.4 [`AppendGuard`] (builder-style). Production wires a
    /// [`MetaFreezeGuard`] so appends to a frozen reality are rejected.
    pub fn with_freeze_guard(mut self, guard: Arc<dyn AppendGuard>) -> Self {
        self.freeze_guard = Some(guard);
        self
    }
}

#[async_trait]
impl EventStore for PgEventStore {
    async fn append_events(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        expected_version: u64,
        batch: &[EventEnvelope],
    ) -> EventStoreResult<u64> {
        // ── W1.4 write-freeze: reject appends to a quiescing reality ──────
        // Checked FIRST (before the empty-batch read-path too) so a frozen
        // reality cannot be appended to OR probed via the no-op idiom. Uncached
        // authoritative read ⇒ no settle-window race (see MetaFreezeGuard).
        if let Some(guard) = &self.freeze_guard {
            guard.ensure_appendable(reality_id).await?;
        }

        // ── Validate batch shape BEFORE any DB call ───────────────────────
        if batch.is_empty() {
            // Empty batch is allowed — returns current high-water mark
            // without mutating. Useful for the "no-op append" idiom.
            let current = self
                .current_high_water(reality_id, aggregate_type, aggregate_id)
                .await?;
            return Ok(current);
        }
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
        for ev in batch {
            if ev.reality_id != reality_id
                || ev.aggregate_type != aggregate_type
                || ev.aggregate_id != aggregate_id
            {
                return Err(EventStoreError::NonMonotonicBatch {
                    detail: format!(
                        "envelope belongs to a different aggregate: \
                         expected ({reality_id}, {aggregate_type}, {aggregate_id}); \
                         got ({}, {}, {})",
                        ev.reality_id, ev.aggregate_type, ev.aggregate_id
                    ),
                });
            }
        }

        // ── Transaction: concurrency-check then bulk INSERT ──────────────
        let mut tx = self
            .pool
            .begin()
            .await
            .map_err(|e| EventStoreError::Transport(e.to_string()))?;

        let high_water: Option<i64> = sqlx::query_scalar(
            r#"
            SELECT MAX(aggregate_version)
            FROM events
            WHERE reality_id = $1
              AND aggregate_type = $2
              AND aggregate_id = $3
            "#,
        )
        .bind(reality_id)
        .bind(aggregate_type)
        .bind(aggregate_id)
        .fetch_one(&mut *tx)
        .await
        .map_err(|e| EventStoreError::Transport(e.to_string()))?;
        let current = high_water.unwrap_or(0) as u64;

        if current != expected_version {
            return Err(EventStoreError::ConcurrencyConflict {
                aggregate_type: aggregate_type.into(),
                aggregate_id: aggregate_id.into(),
                expected: expected_version,
                actual: current,
            });
        }
        if batch.first().expect("non-empty").aggregate_version != current + 1 {
            return Err(EventStoreError::NonMonotonicBatch {
                detail: format!(
                    "first batch version {} != current_high + 1 ({})",
                    batch[0].aggregate_version,
                    current + 1
                ),
            });
        }

        // Insert all events in the batch. One INSERT-per-row keeps the
        // implementation straightforward; cycle 18 perf tuning may switch
        // to UNNEST + multi-row for bulk-load throughput.
        for ev in batch {
            sqlx::query(
                r#"
                INSERT INTO events (
                    event_id,
                    reality_id,
                    aggregate_type,
                    aggregate_id,
                    aggregate_version,
                    event_type,
                    event_version,
                    payload,
                    metadata,
                    occurred_at,
                    recorded_at,
                    content_sha256
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    $10::timestamptz, $11::timestamptz,
                    -- W3.4 stored checksum over the event's JSONB CONTENT (payload
                    -- AND metadata). PG is the single canonicalizer, so the hash is
                    -- taken over the SAME normalized jsonb the row stores, reusing
                    -- the $8 payload + $9 metadata binds. The Go emit path emits the
                    -- identical expression ⇒ byte-identical hashes for equal content
                    -- with no cross-lang JSON lib. Plain column (not generated) so a
                    -- later UPDATE to payload/metadata can't mask byte-rot.
                    encode(sha256(convert_to(
                        jsonb_build_object('p', $8::jsonb, 'm', $9::jsonb)::text, 'UTF8')), 'hex')
                )
                "#,
            )
            .bind(ev.event_id)
            .bind(ev.reality_id)
            .bind(&ev.aggregate_type)
            .bind(&ev.aggregate_id)
            .bind(ev.aggregate_version as i64)
            .bind(&ev.event_type)
            .bind(ev.event_version as i32)
            .bind(&ev.payload)
            .bind(ev.metadata.as_ref())
            .bind(&ev.occurred_at)
            .bind(&ev.recorded_at)
            .execute(&mut *tx)
            .await
            .map_err(|e| EventStoreError::Transport(e.to_string()))?;
        }

        tx.commit()
            .await
            .map_err(|e| EventStoreError::Transport(e.to_string()))?;

        Ok(batch.last().expect("non-empty").aggregate_version)
    }

    async fn read_stream(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
        after_version: u64,
    ) -> EventStoreResult<Vec<EventEnvelope>> {
        let rows = sqlx::query(
            r#"
            SELECT
                event_id,
                event_type,
                event_version,
                aggregate_id,
                aggregate_type,
                aggregate_version,
                reality_id,
                payload,
                metadata,
                to_char(occurred_at AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS occurred_at_str,
                to_char(recorded_at AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS recorded_at_str
            FROM events
            WHERE reality_id = $1
              AND aggregate_type = $2
              AND aggregate_id = $3
              AND aggregate_version > $4
            ORDER BY aggregate_version ASC
            "#,
        )
        .bind(reality_id)
        .bind(aggregate_type)
        .bind(aggregate_id)
        .bind(after_version as i64)
        .fetch_all(&*self.pool)
        .await
        .map_err(|e| EventStoreError::Transport(e.to_string()))?;

        let mut out = Vec::with_capacity(rows.len());
        for r in rows {
            out.push(EventEnvelope {
                event_id: r
                    .try_get("event_id")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
                event_type: r
                    .try_get("event_type")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
                event_version: {
                    let v: i32 = r
                        .try_get("event_version")
                        .map_err(|e| EventStoreError::Transport(e.to_string()))?;
                    v as u32
                },
                aggregate_id: r
                    .try_get("aggregate_id")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
                aggregate_type: r
                    .try_get("aggregate_type")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
                aggregate_version: {
                    let v: i64 = r
                        .try_get("aggregate_version")
                        .map_err(|e| EventStoreError::Transport(e.to_string()))?;
                    v as u64
                },
                reality_id: r
                    .try_get("reality_id")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
                occurred_at: r
                    .try_get::<String, _>("occurred_at_str")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
                recorded_at: r
                    .try_get::<String, _>("recorded_at_str")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
                payload: r
                    .try_get("payload")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
                metadata: r
                    .try_get::<Option<serde_json::Value>, _>("metadata")
                    .map_err(|e| EventStoreError::Transport(e.to_string()))?,
            });
        }
        Ok(out)
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
        // The aggregate_snapshots PK includes aggregate_version, so multiple
        // snapshots per aggregate coexist (per migration comment: snapshot
        // worker prunes older rows). We INSERT ... ON CONFLICT DO NOTHING so
        // re-writing the same (reality_id, type, id, version) tuple is a
        // no-op rather than an error.
        sqlx::query(
            r#"
            INSERT INTO aggregate_snapshots (
                reality_id,
                aggregate_type,
                aggregate_id,
                aggregate_version,
                snapshot_data,
                registry_version
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (reality_id, aggregate_type, aggregate_id, aggregate_version)
            DO NOTHING
            "#,
        )
        .bind(reality_id)
        .bind(aggregate_type)
        .bind(aggregate_id)
        .bind(aggregate_version as i64)
        .bind(&snapshot_data)
        .bind(registry_version)
        .execute(&*self.pool)
        .await
        .map_err(|e| EventStoreError::Transport(e.to_string()))?;
        Ok(())
    }

    async fn snapshot_read(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
    ) -> EventStoreResult<Option<SnapshotRecord>> {
        let row = sqlx::query(
            r#"
            SELECT
                aggregate_version,
                snapshot_data,
                registry_version
            FROM aggregate_snapshots
            WHERE reality_id = $1
              AND aggregate_type = $2
              AND aggregate_id = $3
            ORDER BY aggregate_version DESC
            LIMIT 1
            "#,
        )
        .bind(reality_id)
        .bind(aggregate_type)
        .bind(aggregate_id)
        .fetch_optional(&*self.pool)
        .await
        .map_err(|e| EventStoreError::Transport(e.to_string()))?;

        Ok(row.map(|r| SnapshotRecord {
            aggregate_version: r.get::<i64, _>("aggregate_version") as u64,
            snapshot_data: r.get::<serde_json::Value, _>("snapshot_data"),
            registry_version: r.get::<Option<i32>, _>("registry_version"),
        }))
    }
}

impl PgEventStore {
    async fn current_high_water(
        &self,
        reality_id: Uuid,
        aggregate_type: &str,
        aggregate_id: &str,
    ) -> EventStoreResult<u64> {
        let v: Option<i64> = sqlx::query_scalar(
            r#"
            SELECT MAX(aggregate_version)
            FROM events
            WHERE reality_id = $1
              AND aggregate_type = $2
              AND aggregate_id = $3
            "#,
        )
        .bind(reality_id)
        .bind(aggregate_type)
        .bind(aggregate_id)
        .fetch_one(&*self.pool)
        .await
        .map_err(|e| EventStoreError::Transport(e.to_string()))?;
        Ok(v.unwrap_or(0) as u64)
    }
}

// Unit tests in this file are minimal — the real conformance gate is the
// integration test at tests/integration_event_store.rs which spins up the
// docker-compose Postgres + applies migrations + runs `run_event_store_tests`.
//
// Here we just check the trivial constructor + Q-L4A-1 invariant (the pool
// field is NOT public).
#[cfg(test)]
mod tests {
    use super::*;

    // Compile-only assertion: `PgEventStore.pool` is NOT pub.
    // If someone made it pub, this test would still compile, but the
    // `pub(crate)` declaration above is the contract; we can't easily
    // negative-test pub-ness without a separate crate that tries to access it.
    // The check is therefore at the file level — see `pub(crate) pool`.
    //
    // Q-L4A-1 invariant verified by inspection.

    #[test]
    fn ev_store_is_clone_and_send_sync() {
        fn assert_send_sync<T: Send + Sync>() {}
        assert_send_sync::<PgEventStore>();
    }

    // W1.4 — the freeze set is the load-bearing predicate; pin it so a future
    // status-enum change can't silently make a frozen state appendable.
    #[test]
    fn only_provisioning_seeding_active_accept_appends() {
        for s in ["provisioning", "seeding", "active"] {
            assert!(status_accepts_append(s), "{s} must accept appends");
        }
        for s in [
            "migrating",
            "pending_close",
            "frozen",
            "archived",
            "archived_verified",
            "soft_deleted",
            "dropped",
            "unknown",
        ] {
            assert!(!status_accepts_append(s), "{s} must be frozen for appends");
        }
    }
}
