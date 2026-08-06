//! CNC-D2 — writer recovery, PG-gated.
//!
//! The audit finding (CNC-F6) was that `metadata.input_id` was written on every
//! committed event and never read back, so a writer that took over a channel
//! started with no memory and re-applied whatever the bus redelivered. These
//! tests drive the REAL recovery query against a REAL Postgres, because the
//! whole defect lived in the gap between "the column has the data" and "some
//! code reads it" — a mocked query would restate the assumption under test.
//!
//! Gated on `LOREWEAVE_TEST_PG_URL` (same convention as the dp-kernel channel
//! suite); skips cleanly when unset. Append-only against a random reality
//! UUID per test — no destructive statements, and no test can see another's
//! rows.

mod hub_fixture;

use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use commit_service::recovery::{recover_writer_state, seed_seen, RECOVERY_TAIL};
use commit_service::combat::Side;
use commit_service::{CombatDomain, CombatState, RealityRules};
use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};
use dp_kernel::envelope::EventEnvelope;
use sim_core::{

    RulesetEpoch,
    Admitted, Class, DiscardReason, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane,
    Outcome, Producer, QueuedInput, SeenWindow, Seq, StepStatus,
};

/// Default aggregate for single-channel tests. The `events` PK is
/// (reality, aggregate_type, aggregate_id, aggregate_version, recorded_at), so
/// two channels writing the same aggregate at the same version COLLIDE — one
/// aggregate has one version line, regardless of how many channels exist.
fn envelope(reality: Uuid, ver: u64, input_id: u128, turn: u64, ts: &str) -> EventEnvelope {
    envelope_for(reality, "enc-1", ver, input_id, turn, ts)
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
    Arc::new(PgPoolOptions::new().max_connections(2).connect(url).await.expect("connect test PG"))
}

/// A committed event shaped like the spine's: the dedup key rides `metadata`
/// as a DECIMAL STRING (CWC-A2 — a JSON number corrupts a 128-bit id).
fn envelope_for(
    reality: Uuid,
    agg: &str,
    ver: u64,
    input_id: u128,
    turn: u64,
    ts: &str,
) -> EventEnvelope {
    EventEnvelope {
        event_id: Uuid::new_v4(),
        event_type: "turn.resolved".into(),
        event_version: 1,
        aggregate_id: agg.into(),
        aggregate_type: "combat_session".into(),
        aggregate_version: ver,
        reality_id: reality,
        occurred_at: ts.into(),
        recorded_at: ts.into(),
        payload: serde_json::json!({ "events": [] }),
        metadata: Some(serde_json::json!({
            "event_category": "T6",
            "input_id": input_id.to_string(),
            "turn_number": turn.to_string(),
        })),
        ruleset_digest: None,
    }
}

async fn db_now(pool: &PgPool) -> String {
    sqlx::query_scalar(
        "SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')",
    )
    .fetch_one(pool)
    .await
    .expect("now()")
}

fn island() -> Island<CombatDomain> {
    // F1 — the island runs the reality's RESOLVED ruleset, pinned by a real
    // content digest. Was `RulesetDigest([0u8; 32])`, which pinned nothing.
    let rules = Arc::new(RealityRules::proving_ground());
    let mut state = CombatState::default();
    state.actors.insert(EntityId(1), hub_fixture::actor(&rules, EntityId(1), Side::A, 100));
    state.actors.insert(EntityId(2), hub_fixture::actor(&rules, EntityId(2), Side::B, 100_000));
    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(1),
        0xC2D2,
        RulesetEpoch(1),
        Arc::clone(&rules),
        // The TTL window is the realistic case: a recovered id stamped at a
        // PAST tick would expire on arrival and re-open the hole.
        SeenWindow::TtlTicks(300),
        state,
    );
    isle.spawn_entity(EntityId(1));
    isle.spawn_entity(EntityId(2));
    isle
}

fn strike(input_id: u128) -> Admitted<CombatDomain> {
    Admitted::unchecked(QueuedInput {
        seq: Seq(u64::MAX),
        input_id: InputId(input_id),
        class: Class::B,
        source: Producer::PlayerInput,
        payload: commit_service::CombatPayload::Strike {
            attacker: EntityId(1),
            target: EntityId(2),
        },
        preconditions: vec![],
        on_invalid: Fallback::Drop,
        admitted_gen: Gen(0),
        deadline: None,
    })
}

/// The recovery query reads back what the spine wrote: dedup keys, the DP-A17
/// turn counter, and the version high-water.
/// Kill-mutations: ordering by `recorded_at` (a wall clock, ties across nodes)
/// · parsing `input_id` as a JSON number (corrupts past 2^53).
#[tokio::test]
async fn recovery_reads_back_what_the_writer_committed() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — recovery suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let ch = ChannelId::unverified(1);
    let ts = db_now(&pool).await;

    let lease = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    let writer = ChannelWriter::new(pool.clone(), reality, lease);

    // A 128-bit id well past 2^53, which is exactly where a JSON number breaks.
    let big: u128 = 340_282_366_920_938_463_463_374_607_431_768_211_455 / 7;
    for (i, id) in [big, big + 1, big + 2].iter().enumerate() {
        let env = envelope(reality, i as u64 + 1, *id, i as u64 + 1, &ts);
        writer.append(&env, &serde_json::json!([])).await.unwrap();
    }

    let rec = recover_writer_state(&pool, reality, ch.get(), RECOVERY_TAIL).await.unwrap();
    assert_eq!(rec.seen_input_ids.len(), 3, "every committed dedup key came back");
    assert!(rec.seen_input_ids.contains(&InputId(big)), "128-bit id survived the round trip");
    assert_eq!(rec.turn_number, 3, "turn counter recovered, not reset to 0");
    assert_eq!(rec.aggregate_version, 3, "version high-water recovered");
}

/// **The CNC-F6 regression.** A writer that takes over a channel and replays a
/// still-in-flight intent must DISCARD it as a duplicate — not apply it again.
///
/// The test asserts both halves in one run, so the seeding cannot be
/// vacuously "passing": the same intent is fed to an unseeded island (applies
/// — the bug) and a seeded one (discards — the fix).
#[tokio::test]
async fn a_redelivered_intent_does_not_apply_twice_after_writer_handover() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — recovery suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let ch = ChannelId::unverified(2);
    let ts = db_now(&pool).await;

    // Node A commits one resolution, then dies before ACKing the bus.
    let lease_a = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    let writer_a = ChannelWriter::new(pool.clone(), reality, lease_a);
    let in_flight: u128 = 0xDEAD_BEEF_CAFE;
    writer_a
        .append(&envelope(reality, 1, in_flight, 1, &ts), &serde_json::json!([]))
        .await
        .unwrap();

    // Node B takes the lease and the bus redelivers the SAME intent.
    let _lease_b = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    let rec = recover_writer_state(&pool, reality, ch.get(), RECOVERY_TAIL).await.unwrap();
    assert!(rec.seen_input_ids.contains(&InputId(in_flight)));

    // (a) WITHOUT recovery — the pre-fix behaviour, kept as the control. If
    //     this ever stops applying, the test below proves nothing.
    let mut blind = island();
    blind.submit(Lane::Live, strike(in_flight));
    while matches!(blind.step(), StepStatus::Processed(_)) {}
    let applied_blind = blind
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Applied { .. }))
        .count();
    assert_eq!(applied_blind, 1, "control: a blind writer DOES re-apply (this was CNC-F6)");

    // (b) WITH recovery — the same intent is now a recorded duplicate.
    let mut seeded = island();
    let at = seeded.tick_now();
    seed_seen(&mut seeded, &rec.seen_input_ids, at);
    seeded.submit(Lane::Live, strike(in_flight));
    while matches!(seeded.step(), StepStatus::Processed(_)) {}

    let duplicates = seeded
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Discarded { reason: DiscardReason::Duplicate }))
        .count();
    let applied = seeded
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Applied { .. }))
        .count();
    assert_eq!(applied, 0, "the redelivered intent must NOT apply a second time");
    assert_eq!(duplicates, 1, "it is DISCARDED with a reason, never silently dropped");
}

/// A fresh, unrelated intent must still get through after seeding — otherwise
/// "no double-apply" would be satisfied by a writer that applies nothing.
/// This is the IAS-D10 pairing rule: a test that abuse is blocked needs a
/// partner asserting legitimate use survives.
#[tokio::test]
async fn recovery_does_not_block_new_intents() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — recovery suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let ch = ChannelId::unverified(3);
    let ts = db_now(&pool).await;

    let lease = acquire_writer_lease(&pool, reality, ch).await.unwrap();
    let writer = ChannelWriter::new(pool.clone(), reality, lease);
    writer.append(&envelope(reality, 1, 0xAAA, 1, &ts), &serde_json::json!([])).await.unwrap();

    let rec = recover_writer_state(&pool, reality, ch.get(), RECOVERY_TAIL).await.unwrap();
    let mut isle = island();
    let at = isle.tick_now();
    seed_seen(&mut isle, &rec.seen_input_ids, at);

    isle.submit(Lane::Live, strike(0xBBB)); // never committed before
    while matches!(isle.step(), StepStatus::Processed(_)) {}
    let applied = isle
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Applied { .. }))
        .count();
    assert_eq!(applied, 1, "a NEW intent still resolves — recovery is not a global block");
}

/// Recovery is scoped to ONE channel. A neighbour's dedup keys must not leak
/// in: they would suppress legitimate actions on this channel with no visible
/// cause. Kill-mutation: dropping `channel_id` from the WHERE clause.
#[tokio::test]
async fn recovery_is_scoped_to_its_own_channel() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — recovery suite skipped");
        return;
    };

    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let ts = db_now(&pool).await;

    for (ch, id) in [(10i64, 0x111u128), (11, 0x222)] {
        let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(ch)).await.unwrap();
        let w = ChannelWriter::new(pool.clone(), reality, lease);
        // Distinct aggregate per channel — see `envelope`'s note on the PK.
        let env = envelope_for(reality, &format!("enc-ch{ch}"), 1, id, 1, &ts);
        w.append(&env, &serde_json::json!([])).await.unwrap();
    }

    let rec = recover_writer_state(&pool, reality, 10, RECOVERY_TAIL).await.unwrap();
    assert!(rec.seen_input_ids.contains(&InputId(0x111)), "own key present");
    assert!(!rec.seen_input_ids.contains(&InputId(0x222)), "neighbour's key must NOT leak in");
}

/// Seeded ids are stamped at the island's CURRENT tick. Stamping them at their
/// original (past) tick under a TTL window would expire them immediately and
/// silently restore CNC-F6 — the recovery would run, report success, and
/// protect nothing.
#[test]
fn seeded_ids_survive_the_ttl_window() {
    let mut isle = island();
    isle.tick(250); // island clock well past 0
    let at = isle.tick_now();
    seed_seen(&mut isle, &[InputId(0x777)], at);

    isle.submit(Lane::Live, strike(0x777));
    while matches!(isle.step(), StepStatus::Processed(_)) {}
    assert!(
        isle.outcomes()
            .iter()
            .any(|(_, o)| matches!(o, Outcome::Discarded { reason: DiscardReason::Duplicate })),
        "a seeded id stamped at the current tick still dedups at tick {at:?}"
    );
}
