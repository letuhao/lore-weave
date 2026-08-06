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
///
/// # The field is private, and that is the whole point (REC-102a)
///
/// `DP-Ch1` specifies this newtype as *"module-private constructor — **cannot be
/// forged by feature code**"*, a parallel shape to `RealityId`, whose entire
/// justification (`DP-A12`) is that it *"gates cross-reality leakage at the type
/// level"*. It shipped as `pub i64`, so any caller could write `ChannelId(7)` —
/// which is the same defect `SEALED-SUBJECT` named on the proposal's `actor`
/// field and `PID-D5` named on `event_category`: **a value whose supplier is
/// also its judge.** Third occurrence, same tier, same week.
///
/// The spec says `Uuid`; the build, the wire contract (`Uint64String`) and
/// `DP-Ch11`'s allocator all say 64-bit, and two of three win — `i64` is
/// adopted into the spec rather than the code being changed to `Uuid`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ChannelId(pub(crate) i64);

impl ChannelId {
    // NOTE: `DP-Ch1`'s sanctioned mint — `pub(crate) fn new_verified`, called
    // during SDK channel-tree resolution — is deliberately NOT declared here.
    // It would have no caller, and an unused constructor for a model nothing
    // produces is the orphan shape `scripts/orphan-model-gate.py` exists to
    // refuse. It arrives with `crates/dp`, together with the `channels` table
    // it would resolve against.

    /// Read the raw BIGINT — needed to bind it as a query parameter.
    pub fn get(self) -> i64 {
        self.0
    }

    /// ⚠ **PRE-SDK SEAM — mint a `ChannelId` from a value nothing verified.**
    ///
    /// `DP-Ch1`'s only sanctioned mint is `new_verified`, called during SDK
    /// channel-tree resolution against the `channels` table. **Neither exists
    /// yet**: `crates/dp` is unbuilt (`FLOW-7`) and `channels` has no migration
    /// (`FLOW-9`) — so today there is nothing to resolve a channel *against*,
    /// and every caller here is asserting a subject it did not verify.
    ///
    /// This is deliberately a named, greppable function rather than a public
    /// tuple field. It does not make the mint safe; it makes it **countable**,
    /// and when `crates/dp` lands this function is deleted and the compiler
    /// enumerates the migration. `rg 'ChannelId::unverified'` is the worklist.
    pub fn unverified(raw: i64) -> Self {
        Self(raw)
    }
}

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
    .bind(channel_id.get())
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
        .bind(self.lease.channel_id.get())
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
            .bind(self.lease.channel_id.get())
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
                content_sha256, channel_id, channel_event_id, writer_epoch, causal_refs,
                ruleset_digest
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9,
                $10::timestamptz, $11::timestamptz,
                encode(sha256(convert_to(
                    jsonb_build_object('p', $8::jsonb, 'm', $9::jsonb)::text, 'UTF8')), 'hex'),
                $12, $13, $14, $15,
                -- RLS-A13, NULL when the producer had no pin. See event_store_pg.
                $16
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
        .bind(self.lease.channel_id.get())
        .bind(channel_event_id)
        .bind(self.lease.epoch)
        .bind(causal_refs)
        .bind(env.ruleset_digest.as_ref())
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
        .bind(self.lease.channel_id.get())
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

// ─────────────────────── IMG-A2..A4 — lease liveness ────────────────────────

/// A lease held by a specific process, with an expiry.
///
/// [`WriterLease`] answers *"may I write?"*; this answers *"and for how much
/// longer, and as whom?"* — the two halves the audit (CNC-F9) found split:
/// safety was unconditional at the DB, liveness did not exist at all.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HeldLease {
    pub lease: WriterLease,
    pub holder: Uuid,
}

/// Default lease TTL (IMG-D2). Longer than the slowest thing a writer
/// legitimately does between renewals — one LLM-gated turn at 1–5 s — so a
/// live-but-busy writer is never evicted, and short enough that failover is
/// bounded by half a minute rather than by a human noticing.
pub const LEASE_TTL_SECS: i64 = 30;
/// Renew interval: three attempts inside one TTL, so two may fail transiently
/// without losing the lease.
pub const LEASE_RENEW_SECS: i64 = 10;

/// Claim a channel whose lease is **unheld or expired** (IMG-A3).
///
/// Returns `Ok(None)` when a healthy holder still has it — that is a normal
/// outcome, not an error: it is how a manager discovers a channel is already
/// covered.
///
/// The epoch bump is kept (IMG-A4). Expiry decides who may *try*; the CAS
/// decides who *wins*. Neither alone suffices — expiry without the fence
/// permits two writers during a clock skew, and the fence without expiry is
/// exactly today's state, where a dead node's channel is claimable by anyone
/// at any time with no way to tell failover from a misconfiguration.
///
/// Every time comparison uses Postgres `now()`, never a node clock (IMG-D2):
/// the only skew that can matter is between Postgres and itself.
pub async fn claim_writer_lease(
    pool: &PgPool,
    reality_id: Uuid,
    channel_id: ChannelId,
    holder: Uuid,
    ttl_secs: i64,
) -> Result<Option<HeldLease>, ChannelError> {
    let row: Option<(i64,)> = sqlx::query_as(
        r#"
        INSERT INTO channel_writer_state
            (reality_id, channel_id, current_epoch, last_event_id, holder_id, lease_expires_at)
        VALUES ($1, $2, 1, 0, $3, NOW() + make_interval(secs => $4))
        ON CONFLICT (reality_id, channel_id) DO UPDATE
            SET current_epoch    = channel_writer_state.current_epoch + 1,
                holder_id        = $3,
                lease_expires_at = NOW() + make_interval(secs => $4),
                updated_at       = NOW()
            WHERE channel_writer_state.lease_expires_at IS NULL
               OR channel_writer_state.lease_expires_at < NOW()
        RETURNING current_epoch
        "#,
    )
    .bind(reality_id)
    .bind(channel_id.get())
    .bind(holder)
    .bind(ttl_secs as f64)
    .fetch_optional(pool)
    .await?;

    Ok(row.map(|(epoch,)| HeldLease { lease: WriterLease { channel_id, epoch }, holder }))
}

/// Extend a lease this process still holds (IMG-A3).
///
/// Scoped to `holder` **and** `epoch`: a process that was fenced out — because
/// someone claimed its expired lease while it was paused — cannot extend a
/// lease it no longer has.
///
/// `Ok(false)` is the signal that matters, and callers must treat it as
/// "stop stepping now" rather than waiting to be told at the next append
/// (IMG-D7). Discovering it at the append is *safe*, because the fence rejects
/// the write, but it is wasteful: an island can burn a whole LLM decision on a
/// turn it will never be allowed to commit.
pub async fn renew_writer_lease(
    pool: &PgPool,
    reality_id: Uuid,
    held: HeldLease,
    ttl_secs: i64,
) -> Result<bool, ChannelError> {
    let res = sqlx::query(
        r#"
        UPDATE channel_writer_state
           SET lease_expires_at = NOW() + make_interval(secs => $4),
               updated_at       = NOW()
         WHERE reality_id = $1 AND channel_id = $2
           AND holder_id = $3 AND current_epoch = $5
        "#,
    )
    .bind(reality_id)
    .bind(held.lease.channel_id.get())
    .bind(held.holder)
    .bind(ttl_secs as f64)
    .bind(held.lease.epoch)
    .execute(pool)
    .await?;
    Ok(res.rows_affected() == 1)
}

/// Give the lease up immediately (IMG-D5).
///
/// Without this, a clean shutdown leaves the channel unclaimable for a full
/// TTL — turning every deploy into a ~30 s outage per channel, which is the
/// kind of self-inflicted downtime that gets failover disabled entirely.
/// Scoped to holder+epoch like renew, so a fenced process cannot release
/// someone else's lease.
pub async fn release_writer_lease(
    pool: &PgPool,
    reality_id: Uuid,
    held: HeldLease,
) -> Result<bool, ChannelError> {
    let res = sqlx::query(
        r#"
        UPDATE channel_writer_state
           SET lease_expires_at = NOW(), updated_at = NOW()
         WHERE reality_id = $1 AND channel_id = $2
           AND holder_id = $3 AND current_epoch = $4
        "#,
    )
    .bind(reality_id)
    .bind(held.lease.channel_id.get())
    .bind(held.holder)
    .bind(held.lease.epoch)
    .execute(pool)
    .await?;
    Ok(res.rows_affected() == 1)
}
