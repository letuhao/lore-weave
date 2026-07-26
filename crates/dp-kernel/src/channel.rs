//! DP-Ch11/Ch12/Ch13 — channel-ordered, epoch-fenced event append (S3a).
//!
//! One island = one DP-A16 channel. This module is the SDK write path for
//! channel-scoped events: allocation of `channel_event_id` and the writer
//! fence happen in ONE atomic CAS against `channel_writer_state`, so a
//! stale-epoch writer fails **at the DB layer** — DP-A16's forgery guard,
//! delivered (migration `0014_channel_ordering`).
//!
//! ## Lease issuance is CP-less for now; the FENCE is real (plan D3)
//! [`acquire_writer_lease`] bumps `current_epoch` directly — the control
//! plane will own issuance later, over the SAME table with the SAME fence.
//! The moment a newer lease exists, every append under the old epoch returns
//! [`ChannelError::WrongChannelWriter`]. Nothing about the guard is stubbed.
//!
//! ## Why not the spec's `UNIQUE (reality_id, channel_id, channel_event_id)`
//! `events` is `PARTITION BY RANGE (recorded_at)`; PG forbids a parent
//! unique constraint that omits the partition key. The CAS serializes
//! allocation, and `channel_event_index` (non-partitioned, PK = the spec's
//! triple, same tx) carries the hard uniqueness. Spec correction recorded
//! (plan D1, REC-80 candidate).

use std::sync::Arc;

use sqlx::postgres::PgPool;
use uuid::Uuid;

use crate::envelope::EventEnvelope;

/// Channel identity (BIGINT per DP-Ch11; `None` on an event = reality-scoped).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ChannelId(pub i64);

/// A writer lease `(channel_id, epoch)` — DP-Ch12. Possession is necessary
/// but NOT sufficient: every append re-proves it against the DB.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WriterLease {
    pub channel_id: ChannelId,
    pub epoch: i64,
}

#[derive(Debug, thiserror::Error)]
pub enum ChannelError {
    /// DP-Ch13 `DpError::WrongChannelWriter` — the presented epoch is no
    /// longer current. The holder must stop writing and re-acquire (or die:
    /// after a crash-rebuild the NEW writer holds the newer lease).
    #[error("wrong channel writer: channel {channel:?} presented epoch {presented}, fence rejected")]
    WrongChannelWriter { channel: ChannelId, presented: i64 },
    /// The channel has no `channel_writer_state` row — no lease was ever
    /// acquired for it. Appending without a lease is a caller bug.
    #[error("channel {0:?} has no writer state (acquire a lease first)")]
    NoWriterState(ChannelId),
    #[error("db: {0}")]
    Db(#[from] sqlx::Error),
}

/// Acquire (or take over) the writer lease for a channel: bumps
/// `current_epoch` and returns it. Any previously issued lease is dead at
/// the fence from this moment — this call IS the DP-A16 writer reassignment
/// ("reassigned only on writer-node death"; the caller is the host's island
/// manager / CP-to-be).
pub async fn acquire_writer_lease(
    pool: &PgPool,
    reality_id: Uuid,
    channel_id: ChannelId,
) -> Result<WriterLease, ChannelError> {
    let row: (i64,) = sqlx::query_as(
        r#"
        INSERT INTO channel_writer_state (reality_id, channel_id, current_epoch, last_event_id)
        VALUES ($1, $2, 1, 0)
        ON CONFLICT (reality_id, channel_id)
            DO UPDATE SET current_epoch = channel_writer_state.current_epoch + 1,
                          updated_at    = NOW()
        RETURNING current_epoch
        "#,
    )
    .bind(reality_id)
    .bind(channel_id.0)
    .fetch_one(pool)
    .await?;
    Ok(WriterLease { channel_id, epoch: row.0 })
}

/// The channel-scoped writer for one `(reality, channel)` under one lease.
/// Single-threaded by design (the island IS the serialization domain,
/// SL-A9/EVT-L4); clone-cheap pool per Q-L4A-1 conventions.
pub struct ChannelWriter {
    pool: Arc<PgPool>,
    reality_id: Uuid,
    lease: WriterLease,
}

/// A successful channel append: the allocated position.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChannelAppended {
    pub channel_event_id: i64,
}

impl ChannelWriter {
    pub fn new(pool: Arc<PgPool>, reality_id: Uuid, lease: WriterLease) -> Self {
        Self { pool, reality_id, lease }
    }

    pub fn lease(&self) -> WriterLease {
        self.lease
    }

    /// Append ONE channel-scoped event, atomically:
    ///
    /// 1. CAS: `last_event_id += 1 WHERE current_epoch = presented` — the
    ///    allocator and the epoch fence in one statement. 0 rows ⇒ stale
    ///    epoch (or no state row) ⇒ nothing was written, tx rolls back.
    /// 2. `events` row (mirrors `PgEventStore` insert incl. the W3.4
    ///    in-SQL `content_sha256` canonicalizer) with the channel columns.
    /// 3. `channel_event_index` row — the hard uniqueness backstop.
    ///
    /// Allocation is DB-authoritative: no in-memory counter exists to drift
    /// or resurrect after a crash (DP-Ch11's reseed-on-conflict dance is
    /// unnecessary under the CAS).
    pub async fn append(
        &self,
        env: &EventEnvelope,
        causal_refs: &serde_json::Value,
    ) -> Result<ChannelAppended, ChannelError> {
        let mut tx = self.pool.begin().await?;

        // ── 1: allocate + fence, one atomic statement ──
        let allocated: Option<(i64,)> = sqlx::query_as(
            r#"
            UPDATE channel_writer_state
               SET last_event_id = last_event_id + 1,
                   updated_at    = NOW()
             WHERE reality_id = $1 AND channel_id = $2 AND current_epoch = $3
            RETURNING last_event_id
            "#,
        )
        .bind(self.reality_id)
        .bind(self.lease.channel_id.0)
        .bind(self.lease.epoch)
        .fetch_optional(&mut *tx)
        .await?;

        let Some((channel_event_id,)) = allocated else {
            tx.rollback().await.ok();
            // Distinguish "stale epoch" from "no state row" for the caller.
            let exists: Option<(i64,)> = sqlx::query_as(
                "SELECT current_epoch FROM channel_writer_state WHERE reality_id = $1 AND channel_id = $2",
            )
            .bind(self.reality_id)
            .bind(self.lease.channel_id.0)
            .fetch_optional(&*self.pool)
            .await?;
            return Err(match exists {
                Some(_) => ChannelError::WrongChannelWriter {
                    channel: self.lease.channel_id,
                    presented: self.lease.epoch,
                },
                None => ChannelError::NoWriterState(self.lease.channel_id),
            });
        };

        // ── 2: the event row (PgEventStore shape + channel columns) ──
        sqlx::query(
            r#"
            INSERT INTO events (
                event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
                event_type, event_version, payload, metadata, occurred_at, recorded_at,
                content_sha256, channel_id, channel_event_id, writer_epoch, causal_refs
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9,
                $10::timestamptz, $11::timestamptz,
                encode(sha256(convert_to(
                    jsonb_build_object('p', $8::jsonb, 'm', $9::jsonb)::text, 'UTF8')), 'hex'),
                $12, $13, $14, $15
            )
            "#,
        )
        .bind(env.event_id)
        .bind(env.reality_id)
        .bind(&env.aggregate_type)
        .bind(&env.aggregate_id)
        .bind(env.aggregate_version as i64)
        .bind(&env.event_type)
        .bind(env.event_version as i32)
        .bind(&env.payload)
        .bind(env.metadata.as_ref())
        .bind(&env.occurred_at)
        .bind(&env.recorded_at)
        .bind(self.lease.channel_id.0)
        .bind(channel_event_id)
        .bind(self.lease.epoch)
        .bind(causal_refs)
        .execute(&mut *tx)
        .await?;

        // ── 3: hard uniqueness (the spec's UNIQUE triple, same tx) ──
        sqlx::query(
            r#"
            INSERT INTO channel_event_index (reality_id, channel_id, channel_event_id, event_id)
            VALUES ($1, $2, $3, $4)
            "#,
        )
        .bind(self.reality_id)
        .bind(self.lease.channel_id.0)
        .bind(channel_event_id)
        .bind(env.event_id)
        .execute(&mut *tx)
        .await?;

        // ── 4: I13 outbox row, SAME tx (S3b) — every channel event fans
        //    out via the platform publisher (Go, FOR UPDATE SKIP LOCKED
        //    drain → per-reality stream). The atomicity contract is
        //    `outbox.rs`: the row rides the transaction that inserted the
        //    event, or neither exists.
        sqlx::query(crate::outbox::insert_sql())
            .bind(env.event_id)
            .bind(env.reality_id)
            .execute(&mut *tx)
            .await?;

        tx.commit().await?;
        Ok(ChannelAppended { channel_event_id })
    }
}
