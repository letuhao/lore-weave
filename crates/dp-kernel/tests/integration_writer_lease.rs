//! IMG-A2..A4 — writer-lease liveness, PG-gated.
//!
//! The audit (CNC-F9) found safety without liveness: the epoch fence made two
//! writers impossible, but nothing could tell a dead holder from a live one,
//! so takeover was unconditional and failover did not exist.
//!
//! Every test here asserts a NEGATIVE — a healthy lease cannot be stolen, a
//! fenced holder cannot renew, a released lease is immediately claimable.
//! Positives alone would pass against an implementation that simply said yes
//! to everything, which is precisely the pre-fix behaviour.
//!
//! Gated on `LOREWEAVE_TEST_PG_URL`; skips cleanly when unset. Requires
//! migration 0015. Append-only against random reality UUIDs.

use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use dp_kernel::channel::{
    claim_writer_lease, release_writer_lease, renew_writer_lease, ChannelId, LEASE_TTL_SECS,
};

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

/// A free channel is claimable; a HELD one is not. The second half is the
/// point: before IMG-A2 every claim succeeded, so a healthy writer could be
/// evicted mid-encounter by any misconfigured process.
#[tokio::test]
async fn a_healthy_lease_cannot_be_stolen() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — writer-lease suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let (reality, ch) = (Uuid::new_v4(), ChannelId::unverified(1));
    let (a, b) = (Uuid::new_v4(), Uuid::new_v4());

    let held = claim_writer_lease(&pool, reality, ch, a, LEASE_TTL_SECS).await.unwrap();
    assert!(held.is_some(), "an unheld channel is claimable");

    let stolen = claim_writer_lease(&pool, reality, ch, b, LEASE_TTL_SECS).await.unwrap();
    assert!(stolen.is_none(), "a live lease must NOT be claimable by anyone else");
}

/// Failover: once the TTL lapses, another process takes over — and the epoch
/// BUMPS, so the old holder is fenced even if it is alive and merely
/// partitioned (IMG-A4). A negative TTL is how the test reaches an expired
/// state without sleeping; the comparison is Postgres's `now()` either way.
#[tokio::test]
async fn an_expired_lease_is_claimable_and_bumps_the_epoch() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let (reality, ch) = (Uuid::new_v4(), ChannelId::unverified(2));
    let (a, b) = (Uuid::new_v4(), Uuid::new_v4());

    let held_a = claim_writer_lease(&pool, reality, ch, a, -1).await.unwrap().unwrap();
    let held_b = claim_writer_lease(&pool, reality, ch, b, LEASE_TTL_SECS)
        .await
        .unwrap()
        .expect("an expired lease is claimable — this IS failover");

    assert_eq!(held_b.holder, b);
    assert!(
        held_b.lease.epoch > held_a.lease.epoch,
        "takeover bumps the epoch, so the old holder is fenced at its next append"
    );
}

/// A holder renews itself; a process that was fenced out cannot. Without the
/// epoch in the WHERE clause a stale holder could keep extending a lease it no
/// longer owns, and two processes would each believe they were the writer —
/// the exact split-brain the fence exists to prevent.
#[tokio::test]
async fn a_fenced_holder_cannot_renew() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let (reality, ch) = (Uuid::new_v4(), ChannelId::unverified(3));
    let (a, b) = (Uuid::new_v4(), Uuid::new_v4());

    let held_a = claim_writer_lease(&pool, reality, ch, a, -1).await.unwrap().unwrap();
    // Renewed to a still-EXPIRED deadline on purpose: it proves the holder can
    // renew (the positive) without making the lease healthy, which would stop
    // B claiming and turn the negative below into a vacuous pass.
    assert!(
        renew_writer_lease(&pool, reality, held_a, -1).await.unwrap(),
        "the holder can renew while it still holds"
    );

    // B takes over the (still-expired) lease, bumping the epoch.
    let _held_b = claim_writer_lease(&pool, reality, ch, b, LEASE_TTL_SECS).await.unwrap().unwrap();

    assert!(
        !renew_writer_lease(&pool, reality, held_a, LEASE_TTL_SECS).await.unwrap(),
        "a fenced holder must NOT be able to extend a lease it lost"
    );
}

/// Release makes the channel immediately claimable (IMG-D5) — otherwise every
/// clean shutdown costs a full TTL of unavailability per channel, which is how
/// failover gets switched off in practice.
#[tokio::test]
async fn release_makes_the_channel_immediately_claimable() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let (reality, ch) = (Uuid::new_v4(), ChannelId::unverified(4));
    let (a, b) = (Uuid::new_v4(), Uuid::new_v4());

    let held_a = claim_writer_lease(&pool, reality, ch, a, LEASE_TTL_SECS).await.unwrap().unwrap();
    assert!(
        claim_writer_lease(&pool, reality, ch, b, LEASE_TTL_SECS).await.unwrap().is_none(),
        "still held before release"
    );

    assert!(release_writer_lease(&pool, reality, held_a).await.unwrap());
    assert!(
        claim_writer_lease(&pool, reality, ch, b, LEASE_TTL_SECS).await.unwrap().is_some(),
        "released ⇒ claimable at once, no TTL wait"
    );
}

/// A process that no longer holds the lease cannot release it either.
/// Kill-mutation: dropping holder/epoch from release's WHERE clause would let
/// a stale process free a HEALTHY writer's lease — a remote eviction primitive
/// handed to whoever is most confused.
#[tokio::test]
async fn a_stale_holder_cannot_release_someone_elses_lease() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let (reality, ch) = (Uuid::new_v4(), ChannelId::unverified(5));
    let (a, b) = (Uuid::new_v4(), Uuid::new_v4());

    let held_a = claim_writer_lease(&pool, reality, ch, a, -1).await.unwrap().unwrap();
    let _held_b = claim_writer_lease(&pool, reality, ch, b, LEASE_TTL_SECS).await.unwrap().unwrap();

    assert!(
        !release_writer_lease(&pool, reality, held_a).await.unwrap(),
        "a stale holder must NOT be able to release the current holder's lease"
    );
    assert!(
        claim_writer_lease(&pool, reality, ch, a, LEASE_TTL_SECS).await.unwrap().is_none(),
        "…and B's lease is still healthy afterwards"
    );
}

/// Two managers racing the same expired lease: exactly one wins. This is the
/// property the CAS provides and a coordination service would have had to be
/// correct AND available to provide.
#[tokio::test]
async fn two_claimants_racing_an_expired_lease_resolve_to_exactly_one() {
    let Some(url) = dsn() else { return };
    let pool = pool(&url).await;
    let (reality, ch) = (Uuid::new_v4(), ChannelId::unverified(6));

    // Seed an expired lease, then race N claimants at it concurrently.
    let _ = claim_writer_lease(&pool, reality, ch, Uuid::new_v4(), -1).await.unwrap();

    let mut tasks = Vec::new();
    for _ in 0..8 {
        let pool = pool.clone();
        tasks.push(tokio::spawn(async move {
            claim_writer_lease(&pool, reality, ch, Uuid::new_v4(), LEASE_TTL_SECS)
                .await
                .unwrap()
                .is_some()
        }));
    }
    let mut winners = 0;
    for t in tasks {
        if t.await.unwrap() {
            winners += 1;
        }
    }
    assert_eq!(winners, 1, "exactly one claimant wins the race, with no coordinator");
}
