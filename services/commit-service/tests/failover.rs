//! IMG — writer failover, end to end. PG-gated.
//!
//! This is the test doc 24 exists for. Everything else in the island-manager
//! work is machinery; this asserts the property that machinery was for:
//!
//! > **Kill the writer. Another manager takes over only after the lease
//! > expires, recovers what the dead one knew, and no intent applies twice.**
//!
//! Each half has already been proven in isolation — the lease protocol in
//! `dp-kernel/tests/integration_writer_lease.rs`, the recovery replay in
//! `commit-service/tests/recovery.rs`. This is the one that proves they
//! compose, which is where this class of bug actually lives: two correct
//! mechanisms wired in the wrong order (IMG-D6).
//!
//! Gated on `LOREWEAVE_TEST_PG_URL`; skips cleanly when unset. Requires
//! migration 0015. Append-only against random reality UUIDs.

mod hub_fixture;

use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use commit_service::manager::{AdoptOutcome, Manager};
use commit_service::combat::Side;
use commit_service::{CombatDomain, CombatPayload, CombatState, RealityRules};
use dp_kernel::envelope::EventEnvelope;
use sim_core::{

    RulesetEpoch,
    Admitted, Class, DiscardReason, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane,
    Outcome, Producer, QueuedInput, SeenWindow, Seq,
};

mod support;
use support::verified_reality;

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

fn build_island() -> Island<CombatDomain> {
    // F1 — the island runs the reality's RESOLVED ruleset, pinned by a real
    // content digest. Was `RulesetDigest([0u8; 32])`, which pinned nothing.
    let rules = Arc::new(RealityRules::proving_ground());
    let mut state = CombatState::default();
    state.actors.insert(EntityId(1), hub_fixture::actor(&rules, EntityId(1), Side::A, 100));
    state.actors.insert(EntityId(2), hub_fixture::actor(&rules, EntityId(2), Side::B, 100_000));
    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(1),
        0xFA1_10,
        RulesetEpoch(1),
        Arc::clone(&rules),
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
        payload: CombatPayload::Strike { attacker: EntityId(1), target: EntityId(2) },
        preconditions: vec![],
        on_invalid: Fallback::Drop,
        admitted_gen: Gen(0),
        deadline: None,
    })
}

/// Model the passage of time: push a lease's deadline into the past.
///
/// This is how a writer "dies" — the process stops renewing and the TTL
/// lapses. Re-adopting with a negative TTL would NOT model it, because a
/// healthy lease refuses the claim (correctly), so the lease would stay
/// healthy and the test would prove nothing. Sleeping 30 s of real time would
/// model it and cost 30 s per test.
async fn expire_lease(pool: &PgPool, reality: Uuid, channel: i64) {
    sqlx::query(
        "UPDATE channel_writer_state SET lease_expires_at = NOW() - interval '1 second'          WHERE reality_id = $1 AND channel_id = $2",
    )
    .bind(reality)
    .bind(channel)
    .execute(pool)
    .await
    .expect("expire lease");
}

async fn db_now(pool: &PgPool) -> String {
    sqlx::query_scalar(
        "SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')",
    )
    .fetch_one(pool)
    .await
    .expect("now()")
}

fn envelope(reality: Uuid, ver: u64, input_id: u128, turn: u64, ts: &str) -> EventEnvelope {
    EventEnvelope {
        event_id: Uuid::new_v4(),
        event_type: "turn.resolved".into(),
        event_version: 1,
        aggregate_id: "failover-enc".into(),
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

/// **The failover property, end to end.**
///
/// A commits an intent and dies. B cannot take the channel while A's lease is
/// healthy; once it expires B claims, recovers, and the redelivered intent is
/// a recorded duplicate rather than a second attack.
#[tokio::test]
async fn a_dead_writer_is_replaced_without_applying_anything_twice() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — failover suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let channel = 1i64;
    let ts = db_now(&pool).await;
    let in_flight: u128 = 0xF0_1105;

    // ── A adopts the channel with a HEALTHY lease and commits one turn ──
    let mut a = Manager::new(pool.clone(), verified_reality(reality));
    assert!(matches!(
        a.adopt(channel, build_island).await.unwrap(),
        AdoptOutcome::Adopted { .. }
    ));
    {
        let managed = a.get_mut(channel).expect("A holds it");
        managed
            .writer
            .append(&envelope(reality, 1, in_flight, 1, &ts), &serde_json::json!([]))
            .await
            .expect("A commits");
    }

    // ── B cannot steal a HEALTHY lease ──
    let mut b = Manager::new(pool.clone(), verified_reality(reality));
    assert_eq!(
        b.adopt(channel, build_island).await.unwrap(),
        AdoptOutcome::HeldByAnother,
        "failover must NOT fire while the writer is alive — that is eviction, not failover"
    );

    // ── A dies: it stops renewing and its TTL lapses ──
    expire_lease(&pool, reality, channel).await;

    // ── B takes over: claim → recover → step ──
    let mut b2 = Manager::new(pool.clone(), verified_reality(reality));
    let outcome = b2.adopt(channel, build_island).await.unwrap();
    let AdoptOutcome::Adopted { recovered_ids, turn_number } = outcome else {
        panic!("an expired lease must be claimable — this IS failover, got {outcome:?}");
    };

    assert!(recovered_ids >= 1, "B recovered what A committed");
    assert_eq!(turn_number, 1, "and resumed the turn counter instead of rewinding to 0");

    // ── the bus redelivers A's in-flight intent to B ──
    let managed = b2.get_mut(channel).expect("B holds it now");
    managed.island.submit(Lane::Live, strike(in_flight));
    b2.drain(channel);

    let managed = b2.get_mut(channel).unwrap();
    let applied = managed
        .island
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Applied { .. }))
        .count();
    let dupes = managed
        .island
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Discarded { reason: DiscardReason::Duplicate }))
        .count();

    assert_eq!(applied, 0, "the redelivered intent must NOT apply a second time");
    assert_eq!(dupes, 1, "it is DISCARDED with a reason — never silently dropped");
}

/// The other half of IMG-D10-style pairing: failover must not break play.
/// A NEW intent arriving after takeover resolves normally — otherwise "nothing
/// applied twice" would be satisfied by a successor that applies nothing.
#[tokio::test]
async fn after_failover_new_intents_still_resolve() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let channel = 2i64;

    let mut dead = Manager::new(pool.clone(), verified_reality(reality));
    dead.adopt(channel, build_island).await.unwrap();
    expire_lease(&pool, reality, channel).await;

    let mut successor = Manager::new(pool.clone(), verified_reality(reality));
    assert!(matches!(
        successor.adopt(channel, build_island).await.unwrap(),
        AdoptOutcome::Adopted { .. }
    ));

    let managed = successor.get_mut(channel).unwrap();
    managed.island.submit(Lane::Live, strike(0xFEED_A11));
    successor.drain(channel);

    let managed = successor.get_mut(channel).unwrap();
    let applied = managed
        .island
        .outcomes()
        .iter()
        .filter(|(_, o)| matches!(o, Outcome::Applied { .. }))
        .count();
    assert_eq!(applied, 1, "a NEW intent resolves after failover — play continues");
}

/// IMG-D5 — a clean handover costs no TTL. Without release, every deploy would
/// stall each channel for a full lease period.
#[tokio::test]
async fn relinquish_hands_over_immediately() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let channel = 3i64;

    let mut a = Manager::new(pool.clone(), verified_reality(reality));
    a.adopt(channel, build_island).await.unwrap();

    let mut b = Manager::new(pool.clone(), verified_reality(reality));
    assert_eq!(
        b.adopt(channel, build_island).await.unwrap(),
        AdoptOutcome::HeldByAnother,
        "held before release"
    );

    assert!(a.relinquish(channel).await.unwrap());
    assert!(a.hosted().is_empty(), "A no longer hosts it");
    assert!(
        matches!(b.adopt(channel, build_island).await.unwrap(), AdoptOutcome::Adopted { .. }),
        "released ⇒ the successor takes over at once, with no TTL wait"
    );
}

/// IMG-D7 — a manager that loses a lease drops THAT island and keeps the
/// rest. Killing the process would throw away every other warm island for
/// what may be a transient blip.
#[tokio::test]
async fn losing_one_lease_does_not_drop_the_others() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();

    // A holds two channels.
    let mut a = Manager::new(pool.clone(), verified_reality(reality));
    a.adopt(10, build_island).await.unwrap();
    a.adopt(11, build_island).await.unwrap();

    // Channel 11's lease lapses (A stalled on that one); someone else claims
    // it, fencing A out of 11 ONLY.
    expire_lease(&pool, reality, 11).await;
    let mut thief = Manager::new(pool.clone(), verified_reality(reality));
    thief.adopt(11, build_island).await.unwrap();

    let lost = a.renew_all().await.unwrap();
    assert!(lost.contains(&11), "the fenced channel is reported lost");
    assert!(!lost.contains(&10), "the healthy channel is untouched");
    assert_eq!(a.hosted(), vec![10], "A keeps stepping what it still holds");
}

/// IMG-D4 — adopting a channel twice yields ONE island. Two proposals for a
/// new encounter arriving together must not race into two.
#[tokio::test]
async fn adopt_is_idempotent_per_channel() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();

    let mut m = Manager::new(pool.clone(), verified_reality(reality));
    m.adopt(20, build_island).await.unwrap();
    m.adopt(20, build_island).await.unwrap();
    assert_eq!(m.hosted(), vec![20], "one channel, one island");
}
