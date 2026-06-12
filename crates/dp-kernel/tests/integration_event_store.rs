//! L4.A — `PgEventStore` integration test against a real Postgres.
//!
//! ## Gating
//!
//! Skipped unless `LOREWEAVE_TEST_PG_URL` is set, e.g.:
//!   `postgres://lw:lw@localhost:55432/dp_kernel_test`
//!
//! Local + CI bring up the test DB via the cycle-1
//! `infra/foundation-dev/docker-compose.yml` Postgres + apply per-reality
//! migrations 0002 (events) + 0004 (aggregate_snapshots).
//!
//! ## What this gates
//!
//! Runs the FULL `crate::event_store::shared_test_suite::run_event_store_tests`
//! harness — identical to the one the in-memory impl already passes — so the
//! Postgres impl is forced to honor the same contract.
//!
//! ## Hygiene
//!
//! Each test run uses a fresh `reality_id` (`Uuid::new_v4()`) to avoid
//! collisions with prior data. The events + aggregate_snapshots rows
//! associated with a reality are left in the DB after the test; the
//! docker-compose volume is wiped between CI runs.

use dp_kernel::event_store::shared_test_suite::run_event_store_tests;
use dp_kernel::PgEventStore;
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

fn dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_URL").ok()
}

#[tokio::test]
async fn pg_event_store_passes_shared_suite() {
    let Some(url) = dsn() else {
        eprintln!(
            "[skip] LOREWEAVE_TEST_PG_URL not set — \
             PgEventStore integration suite skipped (in-memory suite still runs in unit tests)"
        );
        return;
    };

    let pool = PgPoolOptions::new()
        .max_connections(4)
        .connect(&url)
        .await
        .expect("connect to test pg");

    // Sanity: the schema we expect (cycle 8 + 9 migrations applied) MUST be
    // present. Surfacing this as a panic with a clear message beats a
    // confusing query error from the suite later.
    let has_events: bool = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'events')",
    )
    .fetch_one(&pool)
    .await
    .expect("schema probe");
    let has_snapshots: bool = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'aggregate_snapshots')",
    )
    .fetch_one(&pool)
    .await
    .expect("schema probe");
    assert!(
        has_events && has_snapshots,
        "test DB missing events / aggregate_snapshots tables — \
         run per-reality migrations 0002 + 0004 before this test"
    );

    let store = PgEventStore::new(pool);
    // Use a fresh reality_id per run for isolation.
    let reality_id = Uuid::new_v4();
    run_event_store_tests(&store, reality_id).await;
}
