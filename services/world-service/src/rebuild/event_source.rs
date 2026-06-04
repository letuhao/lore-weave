//! sqlx-backed [`AggregateEventSource`] over the per-reality `events` log.
//!
//! The `AggregateEventSource` trait is SYNC (the rebuilder fans workers out via
//! `spawn_blocking`), so each call bridges to async sqlx via a dedicated
//! runtime [`Handle`]. The handle MUST belong to a runtime DIFFERENT from the
//! one driving `ParallelRebuilder::run` (see `bin/rebuilder.rs`): calling
//! `block_on` from a `spawn_blocking` worker of one runtime into another is
//! sound; re-entering the SAME runtime is not.

use std::sync::Arc;

use rebuilder::{AggregateEventSource, AggregateRef};
use sqlx::{PgPool, Row};
use tokio::runtime::Handle;
use uuid::Uuid;

use dp_kernel::EventEnvelope;

/// Reads the `events` table for one aggregate, version-ordered.
pub struct SqlxEventSource {
    pool: Arc<PgPool>,
    handle: Handle,
    reality_id: Uuid,
}

impl SqlxEventSource {
    /// Bind the per-reality pool + the DB runtime handle + the reality scope.
    pub fn new(pool: Arc<PgPool>, handle: Handle, reality_id: Uuid) -> Self {
        Self {
            pool,
            handle,
            reality_id,
        }
    }
}

/// `SELECT` one aggregate's events strictly after `after_version`. Timestamps are
/// rendered to RFC3339 text (sqlx is built without a chrono/time feature) so they
/// map straight onto [`EventEnvelope`]'s `String` timestamp fields.
const EVENTS_BATCH_SQL: &str = r#"
SELECT event_id,
       event_type,
       event_version,
       aggregate_id,
       aggregate_type,
       aggregate_version,
       reality_id,
       to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS occurred_at,
       to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS recorded_at,
       payload,
       metadata
  FROM events
 WHERE reality_id = $1
   AND aggregate_type = $2
   AND aggregate_id = $3
   AND aggregate_version > $4
 ORDER BY aggregate_version ASC
 LIMIT $5
"#;

impl AggregateEventSource for SqlxEventSource {
    fn events_batch(
        &self,
        agg: &AggregateRef,
        after_version: u64,
        batch_size: u64,
    ) -> Result<Vec<EventEnvelope>, String> {
        let pool = self.pool.clone();
        let reality_id = self.reality_id;
        let agg_type = agg.aggregate_type.clone();
        let agg_id = agg.aggregate_id.clone();
        self.handle.block_on(async move {
            let rows = sqlx::query(EVENTS_BATCH_SQL)
                .bind(reality_id)
                .bind(&agg_type)
                .bind(&agg_id)
                .bind(after_version as i64)
                .bind(batch_size as i64)
                .fetch_all(&*pool)
                .await
                .map_err(|e| format!("events_batch query: {e}"))?;

            let mut out = Vec::with_capacity(rows.len());
            for row in &rows {
                out.push(decode_event(row)?);
            }
            Ok(out)
        })
    }
}

fn col_err(e: sqlx::Error) -> String {
    format!("events row decode: {e}")
}

/// Decode one `events` row (the SELECT column shape below) into an
/// [`EventEnvelope`]. Shared by the per-aggregate and global readers so they
/// decode identically.
fn decode_event(row: &sqlx::postgres::PgRow) -> Result<EventEnvelope, String> {
    Ok(EventEnvelope {
        event_id: row.try_get("event_id").map_err(col_err)?,
        event_type: row.try_get("event_type").map_err(col_err)?,
        event_version: row.try_get::<i32, _>("event_version").map_err(col_err)? as u32,
        aggregate_id: row.try_get("aggregate_id").map_err(col_err)?,
        aggregate_type: row.try_get("aggregate_type").map_err(col_err)?,
        aggregate_version: row
            .try_get::<i64, _>("aggregate_version")
            .map_err(col_err)? as u64,
        reality_id: row.try_get("reality_id").map_err(col_err)?,
        occurred_at: row.try_get("occurred_at").map_err(col_err)?,
        recorded_at: row.try_get("recorded_at").map_err(col_err)?,
        payload: row.try_get("payload").map_err(col_err)?,
        metadata: row.try_get("metadata").map_err(col_err)?,
    })
}

/// The `events` SELECT column list (timestamps rendered to RFC3339 text, matching
/// [`EventEnvelope`]'s `String` fields). Shared so the per-aggregate and global
/// queries return the identical row shape `decode_event` expects.
const EVENT_COLUMNS: &str = r#"event_id, event_type, event_version, aggregate_id, aggregate_type, aggregate_version, reality_id, to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS occurred_at, to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS recorded_at, payload, metadata"#;

/// A position in a reality's GLOBAL event order `(recorded_at, event_id)`.
#[derive(Debug, Clone)]
pub struct GlobalCursor {
    /// RFC3339 micros, matching [`EventEnvelope::recorded_at`].
    pub recorded_at: String,
    pub event_id: Uuid,
}

/// Reads a reality's events in GLOBAL `(recorded_at, event_id)` order — the input
/// to the multi-aggregate global-order rebuild path (so e.g. `session.started`
/// is replayed before the `npc.said` that increments its session-memory row,
/// which the per-aggregate reader cannot guarantee).
pub struct GlobalEventSource {
    pool: Arc<PgPool>,
    handle: Handle,
    reality_id: Uuid,
}

impl GlobalEventSource {
    pub fn new(pool: Arc<PgPool>, handle: Handle, reality_id: Uuid) -> Self {
        Self {
            pool,
            handle,
            reality_id,
        }
    }

    /// Fetch up to `batch_size` events strictly after `cursor` (None = from the
    /// start), in global order. The caller pages until an empty Vec is returned.
    pub fn events_after(
        &self,
        cursor: Option<&GlobalCursor>,
        batch_size: u64,
    ) -> Result<Vec<EventEnvelope>, String> {
        let pool = self.pool.clone();
        let reality_id = self.reality_id;
        let cursor = cursor.cloned();
        self.handle.block_on(async move {
            let rows = if let Some(c) = cursor {
                let sql = format!(
                    "SELECT {EVENT_COLUMNS} FROM events \
                     WHERE reality_id = $1 \
                       AND (recorded_at, event_id) > ($2::timestamptz, $3::uuid) \
                     ORDER BY recorded_at, event_id LIMIT $4"
                );
                sqlx::query(&sql)
                    .bind(reality_id)
                    .bind(&c.recorded_at)
                    .bind(c.event_id)
                    .bind(batch_size as i64)
                    .fetch_all(&*pool)
                    .await
            } else {
                let sql = format!(
                    "SELECT {EVENT_COLUMNS} FROM events WHERE reality_id = $1 \
                     ORDER BY recorded_at, event_id LIMIT $2"
                );
                sqlx::query(&sql)
                    .bind(reality_id)
                    .bind(batch_size as i64)
                    .fetch_all(&*pool)
                    .await
            }
            .map_err(|e| format!("events_after query: {e}"))?;

            let mut out = Vec::with_capacity(rows.len());
            for row in &rows {
                out.push(decode_event(row)?);
            }
            Ok(out)
        })
    }
}

/// Enumerate every `(aggregate_type, aggregate_id)` pair that has at least one
/// event for `reality_id`. Async (called from the bin's setup phase, before the
/// orchestration runtime starts). The full set is replayed so the target
/// projection is rebuilt regardless of which aggregate type populates it.
pub async fn enumerate_aggregates(
    pool: &PgPool,
    reality_id: Uuid,
) -> Result<Vec<AggregateRef>, String> {
    let rows = sqlx::query(
        "SELECT DISTINCT aggregate_type, aggregate_id FROM events WHERE reality_id = $1",
    )
    .bind(reality_id)
    .fetch_all(pool)
    .await
    .map_err(|e| format!("enumerate_aggregates: {e}"))?;

    let mut out = Vec::with_capacity(rows.len());
    for row in rows {
        out.push(AggregateRef {
            reality_id,
            aggregate_type: row.try_get("aggregate_type").map_err(col_err)?,
            aggregate_id: row.try_get("aggregate_id").map_err(col_err)?,
        });
    }
    Ok(out)
}
