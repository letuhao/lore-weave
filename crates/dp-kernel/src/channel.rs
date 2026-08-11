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

/// Channel identity — **re-exported from `crates/dp`** (slice `5D`).
///
/// # There was a second `ChannelId` here, and two types with one name is worse
/// than either
///
/// This module defined its own `ChannelId(i64)` from before `crates/dp`
/// existed, with the argument for `i64` over the spec's `Uuid` written out
/// here: *"the build, the wire contract (`Uint64String`) and `DP-Ch11`'s
/// allocator all say 64-bit, and two of three win."* That argument was right
/// and `dp::ChannelId` adopts it — `contracts/migrations/per_reality/0019_channels`
/// says `id BIGINT` too.
///
/// What could not stand is TWO of them. `crates/dp` is the contract crate and
/// `SessionContext` now carries a channel, so a distinct `dp_kernel::ChannelId`
/// would have meant every value crossing the seam needed a conversion — and a
/// conversion between two "verified" newtypes is a hole with a cast in it.
///
/// The escape hatch moved with the type: `dp::ChannelId::unverified` is the
/// same pre-SDK seam, now ratcheted by `scripts/channel-id-adoption-gate.py`
/// rather than only counted by a grep in a doc comment. Every call site here is
/// unchanged, because the name and signature did not change.
pub use dp::ChannelId;

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

/// A successful channel append: the allocated position, and the turn it landed in.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChannelAppended {
    pub channel_event_id: i64,
    /// `DP-Ch22`. For an ordinary append this is the channel's CURRENT turn —
    /// the value every event carries until the next boundary. For
    /// [`ChannelWriter::advance_turn`] it is the NEW turn, i.e. previous + 1.
    ///
    /// 0 means the channel has never advanced a turn, which DP-Ch24 makes a
    /// legitimate steady state rather than an uninitialised one: a feature that
    /// does not use turn semantics leaves it at 0 forever.
    pub turn_number: i64,
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
        self.append_inner(env, causal_refs, false).await
    }

    /// `DP-Ch21` / `DP-Ch22` — advance this channel's turn counter by one and
    /// commit the caller's `channel.turn_boundary` event at the new turn.
    ///
    /// # Which "turn" this is
    ///
    /// The per-channel page-flip counter every member of the channel shares —
    /// **not** [`crate::turn::TurnContext`], which is one REQUEST's lifecycle
    /// (`pending → validating → … → completed`) and whose mutator is
    /// `TurnContext::advance`. The two carry the same scope keys and their
    /// names are one word apart; nothing mechanical separates them, so this
    /// paragraph and its twins in `0020_turn_boundary.up.sql` and
    /// `contracts/events/channel.go` are the separation.
    ///
    /// # Why it is the SAME statement as the allocation
    ///
    /// DP-Ch22 requires the `last_turn_number` update to be in the same
    /// transaction as the event insert, so no partial state is observable. It
    /// goes further here and puts it in the same *statement* as the
    /// `channel_event_id` CAS — which also makes the epoch fence cover the turn
    /// allocation for free. A separate `UPDATE … SET last_turn_number` would be
    /// a second write that a stale writer could land after losing the fence.
    ///
    /// This is why DP-Ch22's `MAX(turn_number)` reseed-on-takeover is
    /// unnecessary, exactly as `append`'s doc says of DP-Ch11's: allocation is
    /// DB-authoritative, so there is no in-memory counter to drift. The spec's
    /// failover race — *"N2 queries MAX, gets 4, allocates 5 again"* — cannot
    /// occur, because no one ever queries `MAX`.
    pub async fn advance_turn(
        &self,
        env: &EventEnvelope,
        causal_refs: &serde_json::Value,
    ) -> Result<ChannelAppended, ChannelError> {
        self.append_inner(env, causal_refs, true).await
    }

    async fn append_inner(
        &self,
        env: &EventEnvelope,
        causal_refs: &serde_json::Value,
        advance_turn: bool,
    ) -> Result<ChannelAppended, ChannelError> {
        let mut tx = self.pool.begin().await?;

        // ── 1: allocate + fence, one atomic statement ──
        //
        // `$4` decides whether this append OPENS a new turn or rides the
        // current one. Both branches are the same UPDATE so the epoch fence
        // covers the turn allocation too — see `advance_turn`'s doc.
        let allocated: Option<(i64, i64)> = sqlx::query_as(
            r#"
            UPDATE channel_writer_state
               SET last_event_id    = last_event_id + 1,
                   last_turn_number = last_turn_number + CASE WHEN $4 THEN 1 ELSE 0 END,
                   updated_at       = NOW()
             WHERE reality_id = $1 AND channel_id = $2 AND current_epoch = $3
            RETURNING last_event_id, last_turn_number
            "#,
        )
        .bind(self.reality_id)
        .bind(self.lease.channel_id.get())
        .bind(self.lease.epoch)
        .bind(advance_turn)
        .fetch_optional(&mut *tx)
        .await?;

        let Some((channel_event_id, turn_number)) = allocated else {
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

        // ── 1b: DP-Ch21 — the writer STAMPS the allocated turn into the
        // payload. It cannot be the caller's to supply.
        //
        // `TurnBoundary { turn_number, turn_data }` puts the number in the
        // payload, and `advance_turn(ctx, channel, turn_data, causal_refs)`
        // does not let the caller pass one — because the caller cannot know it:
        // it is allocated here, under the epoch fence, at commit time. A
        // caller-authored value is a guess, and a guess that disagrees with the
        // column is two SSOTs for one fact with no rule for which wins.
        //
        // Found by a subscriber test asserting the two agree: the payload said
        // 3 and the column said 2, because the test helper had authored the
        // number. That assertion was written as a consistency check and turned
        // out to be a design check.
        let payload = if advance_turn {
            let mut p = env.payload.clone();
            if let Some(obj) = p.as_object_mut() {
                obj.insert("turn_number".into(), serde_json::json!(turn_number));
            }
            p
        } else {
            env.payload.clone()
        };

        // ── 2: the event row (PgEventStore shape + channel columns) ──
        sqlx::query(
            r#"
            INSERT INTO events (
                event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
                event_type, event_version, payload, metadata, occurred_at, recorded_at,
                content_sha256, channel_id, channel_event_id, writer_epoch, causal_refs,
                ruleset_digest, turn_number
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9,
                $10::timestamptz, $11::timestamptz,
                encode(sha256(convert_to(
                    jsonb_build_object('p', $8::jsonb, 'm', $9::jsonb)::text, 'UTF8')), 'hex'),
                $12, $13, $14, $15,
                -- RLS-A13, NULL when the producer had no pin. See event_store_pg.
                $16,
                -- DP-Ch22: every channel event carries the turn it landed in.
                -- For an ordinary append that is the CURRENT turn; for
                -- advance_turn it is the new one, and both come from the same
                -- CAS above so the value cannot disagree with the state row.
                $17
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
        .bind(&payload)
        .bind(env.metadata.as_ref())
        .bind(&env.occurred_at)
        .bind(&env.recorded_at)
        .bind(self.lease.channel_id.get())
        .bind(channel_event_id)
        .bind(self.lease.epoch)
        .bind(causal_refs)
        .bind(env.ruleset_digest.as_ref())
        .bind(turn_number)
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
        Ok(ChannelAppended { channel_event_id, turn_number })
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

// ───────────────────────── DP-Ch51 — the advisory turn slot ─────────────────────────

/// `DP-Ch51` — who is expected to act on this channel, and until when.
///
/// **Advisory.** `21_llm_turn_slot.md` says so twice: it *"does not block other
/// writes from being committed at DP level"*. Blocking is `channel_pause`'s job
/// (DP-Ch35, unbuilt). A reader who treats a held slot as a lock will be wrong.
///
/// `actor` is opaque JSON. DP-Ch51 types it `ActorId` and no such type exists —
/// four spellings of "who is acting" already do (`sim-core::EntityId`, two meta
/// `actor_id` columns, `pii_sdk`'s `actor_id: String`), so this does not add a
/// fifth. See `SF-6` in the turn-loop run-state.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TurnSlot {
    pub actor: serde_json::Value,
    pub started_at: chrono::DateTime<chrono::Utc>,
    /// SOFT deadline. Passing it does not stop anything on its own; DP-Ch52's
    /// auto-timeout scheduler is what would act on it, and it is unbuilt.
    pub expected_until: chrono::DateTime<chrono::Utc>,
    pub reason: String,
}

impl ChannelWriter {
    /// `DP-Ch51` — claim the advisory slot. Last writer wins.
    ///
    /// Epoch-fenced like every other write to this row: a writer that has lost
    /// the lease cannot leave a stale "NPC X is thinking…" behind it. Nothing
    /// in DP-Ch51 requires that, but the alternative is an indicator no live
    /// writer can clear, and the fence is free here because the state row is
    /// already keyed by epoch.
    pub async fn claim_turn_slot(&self, slot: &TurnSlot) -> Result<(), ChannelError> {
        self.set_slot(Some(slot)).await
    }

    /// `DP-Ch51` — release the slot. Idempotent: releasing an empty slot is not
    /// an error, because the auto-timeout scheduler (DP-Ch52) and the feature
    /// that claimed it can both legitimately try.
    pub async fn release_turn_slot(&self) -> Result<(), ChannelError> {
        self.set_slot(None).await
    }

    async fn set_slot(&self, slot: Option<&TurnSlot>) -> Result<(), ChannelError> {
        let n = sqlx::query(
            r#"
            UPDATE channel_writer_state
               SET current_turn_actor  = $4,
                   turn_started_at     = $5,
                   turn_expected_until = $6,
                   turn_slot_reason    = $7,
                   updated_at          = NOW()
             WHERE reality_id = $1 AND channel_id = $2 AND current_epoch = $3
            "#,
        )
        .bind(self.reality_id)
        .bind(self.lease.channel_id.get())
        .bind(self.lease.epoch)
        .bind(slot.map(|s| s.actor.clone()))
        .bind(slot.map(|s| s.started_at))
        .bind(slot.map(|s| s.expected_until))
        .bind(slot.map(|s| s.reason.clone()))
        .execute(&*self.pool)
        .await?
        .rows_affected();

        if n == 0 {
            return Err(ChannelError::WrongChannelWriter {
                channel: self.lease.channel_id,
                presented: self.lease.epoch,
            });
        }
        Ok(())
    }

    /// `DP-Ch51` — read the slot. `None` = nobody holds it.
    ///
    /// NOT epoch-fenced: reading who is expected to act is what the UI does,
    /// and a UI holds no writer lease. DP-Ch51 lists *"read by UI"* as the
    /// primary consumer, so requiring a lease to read would make the primitive
    /// unusable by the thing it was written for.
    pub async fn get_turn_slot(&self) -> Result<Option<TurnSlot>, ChannelError> {
        let row: Option<(
            Option<serde_json::Value>,
            Option<chrono::DateTime<chrono::Utc>>,
            Option<chrono::DateTime<chrono::Utc>>,
            Option<String>,
        )> = sqlx::query_as(
            "SELECT current_turn_actor, turn_started_at, turn_expected_until, turn_slot_reason \
             FROM channel_writer_state WHERE reality_id = $1 AND channel_id = $2",
        )
        .bind(self.reality_id)
        .bind(self.lease.channel_id.get())
        .fetch_optional(&*self.pool)
        .await?;

        Ok(match row {
            Some((Some(actor), Some(started_at), Some(expected_until), Some(reason))) => {
                Some(TurnSlot { actor, started_at, expected_until, reason })
            }
            // A partially-populated slot is treated as absent rather than
            // reconstructed with defaults: the four columns are written and
            // cleared together, so a partial row means something else wrote it.
            _ => None,
        })
    }
}

// ─────────────────── DP-Ch16 / DP-Ch17 — durable per-channel subscribe ───────────────────

/// `DP-Ch16` — a feature-side channel event type.
///
/// The discriminator matches `events.event_type`, which is the authoritative
/// registry's name (`contracts/events/_registry.yaml`) — so a type whose
/// `EVENT_TYPE` is unregistered can never match a committed row, by
/// construction rather than by convention.
pub trait ChannelEvent: serde::de::DeserializeOwned + Send + 'static {
    /// Discriminator, e.g. `channel.turn_boundary`.
    const EVENT_TYPE: &'static str;
}

/// `DP-Ch16` — one item from a channel's durable stream.
///
/// `Heartbeat` and `StreamEnd` are part of the LOCKED shape and are not emitted
/// by [`ChannelWriter::read_channel_events_durable`], which is a bounded
/// catch-up read rather than a live tail — see `DF-1`. They exist here so the
/// enum a consumer matches on does not change when the tail lands; adding a
/// variant later would break every `match`.
#[derive(Debug, Clone, PartialEq)]
pub enum DurableStreamItem<S> {
    Event {
        channel_event_id: i64,
        writer_epoch: i64,
        /// `DP-Ch22` — the turn this event landed in. 0 = the channel has never
        /// advanced one.
        turn_number: i64,
        causal_refs: serde_json::Value,
        payload: S,
        occurred_at: chrono::DateTime<chrono::Utc>,
    },
    /// Emitted on an idle channel so a consumer can tell "quiet" from "lost".
    /// Not produced by the catch-up read; reserved for the live tail.
    Heartbeat { last_event_id: i64 },
    /// Graceful close. Reserved for the live tail.
    StreamEnd { reason: String },
}

impl ChannelWriter {
    /// `DP-Ch16` — read this channel's events from `from_event_id` forward, in
    /// `DP-A15` per-channel total order.
    ///
    /// `from_event_id = 0` means "from the beginning of retention", per DP-Ch16.
    /// The bound is EXCLUSIVE: pass the last `channel_event_id` you processed
    /// and you get what comes after it, which is what makes the resume token
    /// composable — a consumer that crashes mid-item re-reads nothing it has
    /// already acknowledged.
    ///
    /// # Which tier this reads, and why that is the canonical one
    ///
    /// Postgres, not Redis. `DP-Ch17` specifies two backing stores and calls
    /// the Postgres `events` table **canonical** and the Redis tail
    /// *"best-effort live"*. The Redis stream `dp:events:{reality}:{channel}`
    /// **does not exist in any source file in this repository** — measured, see
    /// the durable-subscribe run-state §1.2 — so this reads the half that is
    /// real. `DF-1` defers the tail; it is a latency optimisation, and building
    /// a relay for a stream with no reader would have been the wrong order.
    ///
    /// # Not a live stream
    ///
    /// This returns a Vec, not an async stream. DP-Ch16's `DurableEventStream`
    /// is a live subscription whose cancellation semantics are tied to a gRPC
    /// server-streaming RPC that does not exist either. Returning a bounded
    /// page is the honest shape for a catch-up read over a table, and it is
    /// what every consumer needs first: you cannot tail a channel until you
    /// have caught up to its head.
    ///
    /// # Visibility
    ///
    /// DP-Ch16 requires a capability check at subscribe time. This method is
    /// on `ChannelWriter`, which already holds a lease for the channel — a
    /// stronger claim than the read capability DP-Ch16 asks for. A caller with
    /// only observer rights needs the SDK surface, which waits on `DF-2`.
    pub async fn read_channel_events_durable<S: ChannelEvent>(
        &self,
        from_event_id: i64,
        limit: i64,
    ) -> Result<Vec<DurableStreamItem<S>>, ChannelError> {
        let rows: Vec<(i64, Option<i64>, i64, serde_json::Value, serde_json::Value, chrono::DateTime<chrono::Utc>)> =
            sqlx::query_as(
                r#"
                SELECT channel_event_id, writer_epoch, turn_number, causal_refs, payload, occurred_at
                  FROM events
                 WHERE reality_id = $1
                   AND channel_id = $2
                   AND channel_event_id > $3
                   AND event_type   = $4
                 ORDER BY channel_event_id
                 LIMIT $5
                "#,
            )
            .bind(self.reality_id)
            .bind(self.lease.channel_id.get())
            .bind(from_event_id)
            .bind(S::EVENT_TYPE)
            .bind(limit)
            .fetch_all(&*self.pool)
            .await?;

        let mut out = Vec::with_capacity(rows.len());
        for (channel_event_id, writer_epoch, turn_number, causal_refs, payload, occurred_at) in rows {
            let decoded: S = serde_json::from_value(payload).map_err(|e| {
                // A row whose payload does not fit its own declared type is a
                // contract break between the writer and the registry, not a
                // "skip it and carry on" — silently dropping it would make a
                // gap in a stream whose ONLY promise is total order.
                ChannelError::Db(sqlx::Error::Decode(Box::new(e)))
            })?;
            out.push(DurableStreamItem::Event {
                channel_event_id,
                // `writer_epoch` is nullable in the schema (reality-scoped rows
                // leave it NULL); a channel row always has one, and 0 here
                // would be indistinguishable from a real epoch.
                writer_epoch: writer_epoch.unwrap_or(-1),
                turn_number,
                causal_refs,
                payload: decoded,
                occurred_at,
            });
        }
        Ok(out)
    }
}
