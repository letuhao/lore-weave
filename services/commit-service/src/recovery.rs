//! CNC-D2 — writer recovery: rebuild the dedup state from the committed log.
//!
//! ## The gap this closes (audit doc 23, CNC-F6)
//!
//! The idempotency key was already being persisted — `spine` writes
//! `metadata.input_id` on every committed event — and **nothing ever read it
//! back**. Every layer that could have caught a redelivery was in RAM and died
//! with the process:
//!
//! * the EVT-L3 `DedupCache` is a process-local map with a 60 s TTL;
//! * the island's I2 `seen` set is in-memory;
//! * `IslandCheckpoint` carries `seen`, but is never persisted anywhere.
//!
//! The bus is at-least-once **by design** (EVT-L2: ACK only after success,
//! `XAUTOCLAIM` reclaims a dead consumer's PEL). So the failure was not exotic:
//! writer node A commits, dies before ACK, node B reclaims the entry and takes
//! the lease with an empty cache and a fresh island — and applies the same
//! intent a second time. The DP-A16 epoch fence does not help, because B
//! legitimately holds the lease. One attack, applied twice, on a restart.
//!
//! ## Why replay rather than a checkpoint
//!
//! Persisting island checkpoints would work and is strictly more machinery:
//! another storage format, another thing to version, another thing that can be
//! stale. The committed log is **already** the recovery source of truth
//! (GDA-D7 makes a fresh join and a reconnect one code path — this simply
//! makes writer recovery a third caller of the same idea). Nothing new becomes
//! authoritative.
//!
//! ## Why a bounded tail is enough (and why the bound is not arbitrary)
//!
//! Recovery only has to cover intents that can still be *redelivered*, which is
//! bounded by what sits in the Redis PEL. Replaying the entire channel would
//! grow unboundedly for a guarantee that does not improve past that window, so
//! the tail is capped — deliberately generously, since the read is one indexed
//! query at lease acquisition and not on any hot path.

use sqlx::postgres::PgPool;
use sqlx::Row;
use uuid::Uuid;

use sim_core::{InputId, Tick};

/// How many committed events to replay when rebuilding dedup state.
///
/// Sized against the redelivery window, not the channel's history: an entry
/// only needs covering while it can still be reclaimed from the PEL. 2 000
/// events is ~10× a busy encounter's whole lifetime at the CEI-2 commit rate,
/// so the bound is not the thing that will fail first.
pub const RECOVERY_TAIL: i64 = 2_000;

/// What a writer needs to resume a channel without repeating itself.
#[derive(Debug, Default, Clone)]
pub struct WriterRecovery {
    /// Intents already resolved on this channel — seeds the island's I2 set.
    pub seen_input_ids: Vec<InputId>,
    /// The DP-A17 turn counter as of the last committed resolution.
    ///
    /// Recovered for the same reason as the dedup set: `spine` seeded it to 0
    /// on every start, so a restart silently rewound the turn number and every
    /// client's `turn_number` went backwards. Same class of bug as CNC-F6
    /// (recovery state that lives only in RAM), same query, so it is fixed
    /// here rather than left as a known-broken sibling.
    pub turn_number: u64,
    /// Highest `aggregate_version` seen — the next append continues from here
    /// instead of colliding at version 1.
    pub aggregate_version: u64,
}

/// Read the channel's committed tail and rebuild what the writer lost.
///
/// Ordered by `channel_event_id`, which is the channel's total order (DP-Ch11)
/// — not `recorded_at`, which is a wall clock and can tie or go backwards
/// across nodes.
pub async fn recover_writer_state(
    pool: &PgPool,
    reality_id: Uuid,
    channel_id: i64,
    tail: i64,
) -> Result<WriterRecovery, sqlx::Error> {
    let rows = sqlx::query(
        r#"
        SELECT metadata->>'input_id'    AS input_id,
               metadata->>'turn_number' AS turn_number,
               aggregate_version
          FROM events
         WHERE reality_id = $1 AND channel_id = $2
         ORDER BY channel_event_id DESC
         LIMIT $3
        "#,
    )
    .bind(reality_id)
    .bind(channel_id)
    .bind(tail)
    .fetch_all(pool)
    .await?;

    let mut out = WriterRecovery::default();
    for row in &rows {
        // Both fields are decimal STRINGS on the wire (CWC-A2): these are
        // 64/128-bit values, and a JSON number would silently corrupt them
        // past 2^53. A row whose metadata predates the field, or was written
        // by a producer that does not set it, is skipped rather than guessed
        // at — a fabricated dedup key is worse than a missing one.
        if let Some(raw) = row.get::<Option<String>, _>("input_id")
            && let Ok(v) = raw.parse::<u128>()
        {
            out.seen_input_ids.push(InputId(v));
        }
        if let Some(raw) = row.get::<Option<String>, _>("turn_number")
            && let Ok(v) = raw.parse::<u64>()
        {
            out.turn_number = out.turn_number.max(v);
        }
        let ver: i64 = row.get("aggregate_version");
        out.aggregate_version = out.aggregate_version.max(ver.max(0) as u64);
    }
    Ok(out)
}

/// Seed an island's I2 set so a redelivered intent discards as `Duplicate`
/// instead of applying twice.
///
/// `at` is the tick the ids are recorded against. Recovered ids are stamped at
/// the island's CURRENT tick rather than their original one: under a
/// `SeenWindow::TtlTicks` window, stamping them in the past would let them
/// expire immediately and hand back the exact hole this closes.
pub fn seed_seen(isle: &mut sim_core::Island<crate::domain::CombatDomain>, ids: &[InputId], at: Tick) {
    for id in ids {
        isle.seed_seen(*id, at);
    }
}
