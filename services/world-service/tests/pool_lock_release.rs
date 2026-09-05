//! A released connection must not carry a session advisory lock back into the pool.
//!
//! `capacity_glue::place_reality` holds a session advisory lock across
//! pick→register and unlocks on every RETURN path. Serving that code over HTTP
//! added a path it has none: axum's `TimeoutLayer` **drops** the handler future,
//! and a dropped future runs no unlock. The connection then returns to the pool
//! still holding the shard's placement lock, and a session lock lives until the
//! connection closes — so every later placement on that shard blocks on a
//! request that already gave up.
//!
//! This is a LIVE test. A mock pool cannot show the defect, because the defect
//! is a property of what Postgres does with a session lock on a reused backend.
//!
//! Gated on `LOREWEAVE_TEST_PG_URL`; skips with a printed reason when unset, so
//! a machine with no Postgres does not report a pass it did not earn.

use sqlx::Row;
use world_service::server::db;

/// An arbitrary key, chosen not to collide with `shard_lock_key`'s hashes.
const KEY: i64 = -7_313_370_001;

fn dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_URL").ok().filter(|s| !s.trim().is_empty())
}

async fn advisory_locks_held_by_this_backend(conn: &mut sqlx::PgConnection) -> i64 {
    sqlx::query("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()")
        .fetch_one(conn)
        .await
        .expect("count advisory locks")
        .get::<i64, _>(0)
}

#[tokio::test]
async fn a_released_connection_does_not_carry_an_advisory_lock_back_into_the_pool() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: LOREWEAVE_TEST_PG_URL unset — this test needs a real Postgres");
        return;
    };

    // max_connections(1) forces the second acquire to reuse the SAME backend.
    // With a larger pool the assertion could pass by landing on a fresh
    // connection that never held the lock — true, and about nothing.
    let pool = db::connect(&dsn, "test", 1).await.expect("connect");

    {
        let mut c = pool.acquire().await.expect("acquire");
        let got: bool = sqlx::query("SELECT pg_try_advisory_lock($1)")
            .bind(KEY)
            .fetch_one(&mut *c)
            .await
            .expect("take lock")
            .get(0);
        assert!(got, "could not take the advisory lock; another session holds it");
        assert_eq!(
            advisory_locks_held_by_this_backend(&mut c).await,
            1,
            "the lock was not actually taken — the rest of this test would be about nothing"
        );
        // Dropped here WITHOUT unlocking: exactly what a cancelled future does.
    }

    let mut c2 = pool.acquire().await.expect("re-acquire");
    let held = advisory_locks_held_by_this_backend(&mut c2).await;
    assert_eq!(
        held, 0,
        "the connection came back into the pool holding {held} advisory lock(s). \
         `place_reality` unlocks on every return path but not on cancellation, so a timed-out \
         provision would wedge that shard until the pool recycled the connection."
    );

    // And the key is genuinely free again, which is the property that matters to
    // the next placement — not merely that a counter reads zero.
    let retaken: bool = sqlx::query("SELECT pg_try_advisory_lock($1)")
        .bind(KEY)
        .fetch_one(&mut *c2)
        .await
        .expect("retake")
        .get(0);
    assert!(retaken, "the shard's placement lock is still held by the pooled connection");
}
