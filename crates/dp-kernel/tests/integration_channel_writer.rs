//! Channel-ordered append + DP-A16 epoch fence — PG-gated integration suite.
//!
//! Gated on `LOREWEAVE_TEST_PG_URL` (same convention as
//! `integration_event_store.rs`); skips cleanly when unset. Requires
//! per-reality migrations 0002 + **0005** (outbox) + 0013 + **0014** +
//! **0016** (`ruleset_digest`) + **0020** (`turn_number`) pre-applied, PLUS the
//! `events_y2026m05` partition — the shared-suite `envelope()` pins
//! 2026-05-29 timestamps and migration 0002 only auto-creates the month
//! current at migration time:
//! `CREATE TABLE events_y2026m05 PARTITION OF events FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');`
//! Tests are append-only against random reality UUIDs — no destructive
//! statements.

use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use dp_kernel::channel::{acquire_writer_lease, ChannelError, ChannelId, ChannelWriter};
use dp_kernel::envelope::EventEnvelope;

/// Shared-suite envelope with a RANDOM event_id: the suite derives event_id
/// from aggregate_version, but `events_outbox`'s PK is bare event_id — the
/// derived ids collide across tests sharing one DB.
fn envelope(reality: Uuid, at: &str, ai: &str, ver: u64, et: &str) -> EventEnvelope {
    let mut e = dp_kernel::event_store::shared_test_suite::envelope(reality, at, ai, ver, et);
    e.event_id = Uuid::new_v4();
    e
}

fn dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_URL").ok()
}

async fn pool(url: &str) -> Arc<PgPool> {
    // Pool of 2: cargo runs test binaries AND the tests inside them in
    // parallel, so a large per-test pool multiplies quickly against Postgres
    // `max_connections`. A test uses one connection at a time, so a bigger
    // pool buys nothing. (Sizing hygiene, not a fix for an observed failure —
    // the one time these went red it was the dev container being stopped.)
    Arc::new(
        PgPoolOptions::new()
            .max_connections(2)
            .connect(url)
            .await
            .expect("connect test PG"),
    )
}

/// Allocation is monotonic + gap-free under one lease; rows land in both
/// `events` (channel columns) and `channel_event_index`.
/// Kill-mutations: allocator not DB-authoritative · index insert dropped.
#[tokio::test]
async fn channel_append_allocates_monotonically() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — channel writer suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let ch = ChannelId::unverified(1);

    let lease = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    let writer = ChannelWriter::new(pool.clone(), reality, lease);

    for expect in 1..=5i64 {
        let env = envelope(reality, "combat_session", "enc-1", expect as u64, "turn.resolved");
        let appended = writer.append(&env, &serde_json::json!([])).await.unwrap();
        assert_eq!(appended.channel_event_id, expect, "gap-free monotonic allocation");
    }

    let (count,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM channel_event_index WHERE reality_id = $1 AND channel_id = $2",
    )
    .bind(reality)
    .bind(ch.get())
    .fetch_one(&*pool)
    .await
    .unwrap();
    assert_eq!(count, 5, "index rows written in the same tx");

    let (max_in_events,): (Option<i64>,) = sqlx::query_as(
        "SELECT MAX(channel_event_id) FROM events WHERE reality_id = $1 AND channel_id = $2",
    )
    .bind(reality)
    .bind(ch.get())
    .fetch_one(&*pool)
    .await
    .unwrap();
    assert_eq!(max_in_events, Some(5), "event rows carry the channel columns");

    // S3b: the I13 outbox row rides the SAME tx — one unpublished row per
    // committed event, ready for the platform publisher's drain.
    // Kill-mutation: outbox insert outside the tx (or dropped).
    let (outbox,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM events_outbox WHERE reality_id = $1 AND published = FALSE",
    )
    .bind(reality)
    .fetch_one(&*pool)
    .await
    .unwrap();
    assert_eq!(outbox, 5, "outbox row per committed event, atomically");
}

/// THE DP-A16 fence bite: after a newer lease exists, the old writer's
/// append fails AT THE DB with WrongChannelWriter and writes NOTHING.
/// Kill-mutations: dropping `current_epoch = $3` from the CAS WHERE ·
/// committing the event row before the CAS.
#[tokio::test]
async fn stale_epoch_writer_is_fenced_at_the_db() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — fence bite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let ch = ChannelId::unverified(7);

    let old_lease = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    let old_writer = ChannelWriter::new(pool.clone(), reality, old_lease);
    old_writer
        .append(&envelope(reality, "combat_session", "enc-1", 1, "turn.resolved"), &serde_json::json!([]))
        .await
        .unwrap();

    // Writer reassignment (crash rebuild / migration): a NEWER lease exists.
    let new_lease = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    assert!(new_lease.epoch > old_lease.epoch);

    // The old writer is now dead at the fence — no partial writes.
    let err = old_writer
        .append(&envelope(reality, "combat_session", "enc-1", 2, "turn.resolved"), &serde_json::json!([]))
        .await
        .unwrap_err();
    assert!(
        matches!(err, ChannelError::WrongChannelWriter { presented, .. } if presented == old_lease.epoch),
        "stale epoch must be rejected, got: {err:?}"
    );
    let (count,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM events WHERE reality_id = $1 AND channel_id = $2",
    )
    .bind(reality)
    .bind(ch.get())
    .fetch_one(&*pool)
    .await
    .unwrap();
    assert_eq!(count, 1, "the fenced append wrote NOTHING");

    // The new writer continues the sequence — no reset, no gap.
    let new_writer = ChannelWriter::new(pool.clone(), reality, new_lease);
    let appended = new_writer
        .append(&envelope(reality, "combat_session", "enc-1", 2, "turn.resolved"), &serde_json::json!([]))
        .await
        .unwrap();
    assert_eq!(appended.channel_event_id, 2, "new epoch continues the channel order");
}

/// Appending to a channel that never acquired a lease is a caller bug with
/// a distinct error (not WrongChannelWriter). Kill-mutation: collapsing the
/// two 0-row causes into one error.
#[tokio::test]
async fn append_without_lease_is_distinct_error() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — no-lease test skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    // Forge a lease that has no state row behind it.
    let writer = ChannelWriter::new(
        pool.clone(),
        reality,
        dp_kernel::channel::WriterLease { channel_id: ChannelId::unverified(99), epoch: 1 },
    );
    let err = writer
        .append(&envelope(reality, "combat_session", "enc-1", 1, "turn.resolved"), &serde_json::json!([]))
        .await
        .unwrap_err();
    assert!(matches!(err, ChannelError::NoWriterState(_)), "got: {err:?}");
}

// ───────────────────────── DP-Ch21 / DP-Ch22 — turn boundaries ─────────────────────────
//
// WHICH "TURN": the per-channel page-flip counter every member of the channel
// shares, NOT `dp_kernel::turn::TurnContext`'s request lifecycle. See
// `ChannelWriter::advance_turn`.
//
// Requires per-reality migration 0020 in addition to the set named at the top.

/// Turn 0 is the never-advanced steady state (DP-Ch24), `advance_turn` opens
/// turn 1, and every ordinary append in between rides the CURRENT turn.
///
/// Kill-mutations: the CASE in the CAS always increments (turn 0 disappears) ·
/// the insert stamps the state row instead of the CAS result (an append after a
/// concurrent advance would carry the wrong turn).
/// Commit one `channel.turn_boundary` through the real writer path.
///
/// A helper rather than a method on `ChannelWriter`: the production surface is
/// `advance_turn(env, causal_refs)`, and giving the test a shorter spelling of
/// it would mean the tests exercise something the callers do not.
async fn append_turn(
    w: &ChannelWriter,
    reality: Uuid,
    ver: u64,
) -> dp_kernel::channel::ChannelAppended {
    w.advance_turn(
        &envelope(reality, "channel", "ch", ver, "channel.turn_boundary"),
        &serde_json::json!([]),
    )
    .await
    .expect("advance_turn")
}

#[tokio::test]
async fn turn_number_starts_at_zero_and_advances_only_on_advance_turn() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — turn suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let ch = ChannelId::unverified(21);
    let lease = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    let writer = ChannelWriter::new(pool.clone(), reality, lease);

    // A channel that has never advanced sits at turn 0 — not 1, and not NULL.
    let a = writer
        .append(&envelope(reality, "combat_session", "enc-1", 1, "npc.said"), &serde_json::json!([]))
        .await
        .unwrap();
    assert_eq!(a.turn_number, 0, "an append before any boundary is turn 0 (DP-Ch24)");

    // The boundary itself carries the NEW number, not the old one (DP-Ch24).
    let b = append_turn(&writer, reality, 2).await;
    assert_eq!(b.turn_number, 1, "the TurnBoundary event is tagged with the new turn");

    // ...and subsequent ordinary events ride it until the next boundary.
    let c = writer
        .append(&envelope(reality, "combat_session", "enc-1", 3, "npc.said"), &serde_json::json!([]))
        .await
        .unwrap();
    assert_eq!(c.turn_number, 1, "events after a boundary carry the current turn");

    let d = append_turn(&writer, reality, 4).await;
    assert_eq!(d.turn_number, 2, "strictly previous + 1");

    // The event log agrees with the acks — the values are READ BACK, because an
    // ack is what the code believed and the row is what it wrote.
    let rows: Vec<(i64, i64)> = sqlx::query_as(
        "SELECT channel_event_id, turn_number FROM events \
         WHERE reality_id = $1 AND channel_id = $2 ORDER BY channel_event_id",
    )
    .bind(reality)
    .bind(ch.get())
    .fetch_all(&*pool)
    .await
    .unwrap();
    assert_eq!(rows, vec![(1, 0), (2, 1), (3, 1), (4, 2)], "the log carries the same turns");

    // And the state row tracks the last allocation.
    let (last,): (i64,) = sqlx::query_as(
        "SELECT last_turn_number FROM channel_writer_state WHERE reality_id = $1 AND channel_id = $2",
    )
    .bind(reality)
    .bind(ch.get())
    .fetch_one(&*pool)
    .await
    .unwrap();
    assert_eq!(last, 2);
}

/// **The property DP-Ch22's `MAX(turn_number)` reseed was written for**, proven
/// against the implementation that deliberately does NOT reseed.
///
/// The spec anticipated a failover race: *"N1 commits turn 5 then dies; N2
/// queries MAX, gets 4, allocates 5 again"* — two boundaries sharing a number.
/// That race is a property of reseeding from a query. Allocation here is
/// DB-authoritative inside the epoch CAS, so there is nothing to reseed and the
/// race has no mechanism — but "has no mechanism" is a claim, so this test is
/// the evidence: hand the channel to a new writer mid-sequence and the turns
/// continue without repeating.
///
/// Kill-mutation: move the turn increment out of the CAS into its own UPDATE.
#[tokio::test]
async fn turn_allocation_survives_writer_handoff_without_duplicating() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — handoff turn test skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let ch = ChannelId::unverified(22);

    let old_lease = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    let old = ChannelWriter::new(pool.clone(), reality, old_lease);
    assert_eq!(append_turn(&old, reality, 1).await.turn_number, 1);
    assert_eq!(append_turn(&old, reality, 2).await.turn_number, 2);

    // Handoff: a new lease bumps the epoch and fences the old writer out.
    let new_lease = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    assert!(new_lease.epoch > old_lease.epoch, "handoff must bump the epoch");
    let new = ChannelWriter::new(pool.clone(), reality, new_lease);

    // The new writer CONTINUES the sequence. No MAX query, no reseed, no repeat.
    assert_eq!(append_turn(&new, reality, 3).await.turn_number, 3);

    // The fenced-out writer cannot advance the turn either — the epoch CAS
    // covers the turn allocation because they are the same statement. This is
    // the half that a separate `UPDATE ... SET last_turn_number` would lose.
    let err = old
        .advance_turn(
            &envelope(reality, "channel", "ch-22", 99, "channel.turn_boundary"),
            &serde_json::json!([]),
        )
        .await
        .unwrap_err();
    assert!(
        matches!(err, ChannelError::WrongChannelWriter { .. }),
        "a stale writer must not be able to advance the turn; got {err:?}"
    );

    // ...and it did not move the counter on its way out.
    let (last,): (i64,) = sqlx::query_as(
        "SELECT last_turn_number FROM channel_writer_state WHERE reality_id = $1 AND channel_id = $2",
    )
    .bind(reality)
    .bind(ch.get())
    .fetch_one(&*pool)
    .await
    .unwrap();
    assert_eq!(last, 3, "the refused advance left the counter alone");

    // No two boundaries share a turn number — the anomaly DP-Ch22 named.
    let turns: Vec<(i64,)> = sqlx::query_as(
        "SELECT turn_number FROM events WHERE reality_id = $1 AND channel_id = $2 \
           AND event_type = 'channel.turn_boundary' ORDER BY turn_number",
    )
    .bind(reality)
    .bind(ch.get())
    .fetch_all(&*pool)
    .await
    .unwrap();
    let nums: Vec<i64> = turns.into_iter().map(|(t,)| t).collect();
    assert_eq!(nums, vec![1, 2, 3], "gap-free and duplicate-free across the handoff");
}
