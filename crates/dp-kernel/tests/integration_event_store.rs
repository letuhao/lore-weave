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

    let store = PgEventStore::new(pool.clone());
    // Use a fresh reality_id per run for isolation.
    let reality_id = Uuid::new_v4();
    run_event_store_tests(&store, reality_id).await;

    // W3.4 — the kernel append now stamps events.content_sha256 with the
    // PG-canonical hash of payload+metadata. Assert every appended row carries a
    // self-consistent checksum, then tamper BITEs proving it detects post-write
    // mutation of BOTH payload and metadata. Requires the 0013 migration;
    // skip-with-note if absent so the suite still passes on an un-migrated DB.
    assert_checksum_stamped_and_detects_tamper(&pool, reality_id).await;
}

/// W3.4 content-checksum re-derive expression — MUST stay byte-identical to the
/// writers' (event_store_pg.rs append + emit.go) and the migration comment.
/// Covers payload AND metadata via jsonb_build_object.
const CHECKSUM_EXPR: &str =
    "encode(sha256(convert_to(jsonb_build_object('p', payload, 'm', metadata)::text, 'UTF8')), 'hex')";

/// W3.4 kernel-side stored-checksum assertion + tamper bites. See the SQL design
/// in 0013_events_content_sha256.up.sql: the checksum is the PG-canonical hash of
/// {payload, metadata}, frozen at INSERT in a PLAIN column, so a later UPDATE to
/// either (that does NOT recompute it) is detectable.
async fn assert_checksum_stamped_and_detects_tamper(pool: &sqlx::PgPool, reality_id: Uuid) {
    let has_col: bool = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns \
         WHERE table_name = 'events' AND column_name = 'content_sha256')",
    )
    .fetch_one(pool)
    .await
    .expect("checksum-column probe");
    if !has_col {
        eprintln!(
            "[skip] events.content_sha256 absent — apply migration 0013 to exercise \
             the W3.4 kernel checksum assertion"
        );
        return;
    }

    let total: i64 = sqlx::query_scalar("SELECT count(*) FROM events WHERE reality_id = $1")
        .bind(reality_id)
        .fetch_one(pool)
        .await
        .expect("count appended rows");
    assert!(
        total > 0,
        "the shared suite should have appended at least one event for this reality"
    );

    // Every appended row: non-NULL checksum that re-derives from its own content.
    let inconsistent: i64 = sqlx::query_scalar(&format!(
        "SELECT count(*) FROM events WHERE reality_id = $1 \
           AND (content_sha256 IS NULL OR content_sha256 <> {CHECKSUM_EXPR})"
    ))
    .bind(reality_id)
    .fetch_one(pool)
    .await
    .expect("checksum-consistency probe");
    assert_eq!(
        inconsistent, 0,
        "kernel append must stamp a self-consistent content_sha256 on every appended row"
    );

    // BITE 1 — PAYLOAD tamper: mutate one row's payload WITHOUT touching
    // content_sha256 (a plain column — UPDATE doesn't recompute it) → the stored
    // checksum must now diverge for exactly that row.
    assert_one_tamper_caught(
        pool,
        reality_id,
        "UPDATE events SET payload = payload || '{\"rot\":1}'::jsonb \
          WHERE ctid = (SELECT ctid FROM events WHERE reality_id = $1 LIMIT 1)",
        "payload",
    )
    .await;

    // Heal the rotted row so BITE 2 isolates the metadata case (re-stamp the
    // frozen checksum to match the now-current content for ALL rows of this
    // reality). This proves the check returns to clean, then catches a fresh
    // metadata-only tamper.
    sqlx::query(&format!(
        "UPDATE events SET content_sha256 = {CHECKSUM_EXPR} WHERE reality_id = $1"
    ))
    .bind(reality_id)
    .execute(pool)
    .await
    .expect("re-stamp checksums");
    let after_heal: i64 = sqlx::query_scalar(&format!(
        "SELECT count(*) FROM events WHERE reality_id = $1 AND content_sha256 <> {CHECKSUM_EXPR}"
    ))
    .bind(reality_id)
    .fetch_one(pool)
    .await
    .expect("post-heal probe");
    assert_eq!(after_heal, 0, "re-stamp should restore a clean checksum state");

    // BITE 2 — METADATA tamper: mutate one row's metadata only. content_sha256
    // covers metadata too, so this MUST be caught (a payload-only checksum would
    // have missed it — the gap review finding #2 closed).
    assert_one_tamper_caught(
        pool,
        reality_id,
        "UPDATE events SET metadata = coalesce(metadata, '{}'::jsonb) || '{\"rot\":1}'::jsonb \
          WHERE ctid = (SELECT ctid FROM events WHERE reality_id = $1 LIMIT 1)",
        "metadata",
    )
    .await;
}

/// Applies a tampering UPDATE (must affect exactly one row) and asserts the
/// content checksum then diverges for exactly one row.
async fn assert_one_tamper_caught(pool: &sqlx::PgPool, reality_id: Uuid, update_sql: &str, what: &str) {
    let tampered = sqlx::query(update_sql)
        .bind(reality_id)
        .execute(pool)
        .await
        .unwrap_or_else(|e| panic!("tamper {what}: {e}"))
        .rows_affected();
    assert_eq!(tampered, 1, "expected to tamper exactly one row ({what})");

    let mismatches: i64 = sqlx::query_scalar(&format!(
        "SELECT count(*) FROM events WHERE reality_id = $1 AND content_sha256 IS NOT NULL \
           AND content_sha256 <> {CHECKSUM_EXPR}"
    ))
    .bind(reality_id)
    .fetch_one(pool)
    .await
    .expect("post-tamper checksum probe");
    assert_eq!(
        mismatches, 1,
        "tampering {what} must make exactly one stored checksum diverge — \
         the kernel-written content checksum detects byte-rot (non-vacuous)"
    );
}
