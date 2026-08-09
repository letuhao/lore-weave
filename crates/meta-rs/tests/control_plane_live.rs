//! `5A` LIVE — `MetaControlPlane` against the REAL `reality_registry`.
//!
//! # Why the unit tests are not enough here
//!
//! `control_plane.rs`'s tests drive a mock `MetaRead`, which proves the
//! decision logic and nothing about the query. The DoD's LIVE RUN axis is
//! explicit that "mocks, fixtures, dead code, test-only consumers ... do not
//! count", and the thing most likely to be wrong is exactly what a mock cannot
//! reach: the column list, the status string decoding, and whether
//! `RealityStatus::from_str` accepts what the database actually stores.
//!
//! This drives `PgConnectionReader` -> `DefaultMetaRead` -> `MetaControlPlane`
//! -> `dp::SessionContext::bind` against a live meta database, and asserts on
//! the resulting `RealityId` — the value that could not be obtained in
//! production at all before `5A`.
//!
//! Gated by `LOREWEAVE_TEST_META_URL`. Unset -> skipped, and the skip says so.
//! Read-only: it SELECTs and binds; it writes nothing, so it is safe against a
//! developer's real meta database.

#![cfg(feature = "sqlx-pg")]

use meta_rs::control_plane::MetaControlPlane;
use meta_rs::routing::{DefaultMetaRead, MetaRead, RealityStatus};
use meta_rs::sqlx_pg::PgConnectionReader;

fn meta_url() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_META_URL").ok().filter(|s| !s.is_empty())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_real_registry_row_binds_and_yields_a_real_reality_id() {
    let Some(url) = meta_url() else {
        eprintln!("skipped: LOREWEAVE_TEST_META_URL unset");
        return;
    };

    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(2)
        .connect(&url)
        .await
        .expect("connect to meta");

    // Find a reality the registry says is bindable. Chosen from live data
    // rather than seeded, because the point is to exercise what is actually
    // stored — including whatever status strings this deployment has.
    let candidate: Option<(uuid::Uuid, String)> = sqlx::query_as(
        "SELECT reality_id, status FROM reality_registry \
         WHERE status IN ('active','pending_close') ORDER BY reality_id LIMIT 1",
    )
    .fetch_optional(&pool)
    .await
    .expect("query registry");

    let Some((reality_id, status)) = candidate else {
        eprintln!("skipped: no bindable reality in this registry");
        return;
    };

    let reader = PgConnectionReader::new(pool.clone()).expect("reader");
    let meta = DefaultMetaRead::new(reader);

    // The adapter decodes what the database stores.
    let routing = meta
        .get_reality_routing(reality_id)
        .expect("read")
        .expect("the row we just selected must be readable");
    assert_eq!(routing.reality_id, reality_id);
    assert!(!routing.db_name.is_empty(), "db_name must come back populated");
    assert!(
        routing.accepts_commands(),
        "selected status {status} decoded to {:?}, which does not accept commands",
        routing.status
    );

    // THE THING THAT WAS IMPOSSIBLE BEFORE 5A: a production path producing a
    // `dp::RealityId`.
    let plane = MetaControlPlane::new(meta);
    let ctx = dp::SessionContext::bind(
        &plane,
        dp::BindRequest { reality: reality_id, node: "live-test".into() },
        now_ms(),
    )
    .expect("bind against the live registry");

    assert_eq!(
        ctx.reality_id().as_uuid(),
        reality_id,
        "the bound RealityId must be the reality that was verified"
    );
    assert!(ctx.check_live(now_ms()).is_ok(), "a freshly minted capability must be live");

    println!(
        "LIVE: bound reality {} (status {:?}, db {}) -> session {}",
        reality_id,
        routing.status,
        routing.db_name,
        ctx.session_id()
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_absent_reality_is_refused_by_the_live_path() {
    let Some(url) = meta_url() else {
        eprintln!("skipped: LOREWEAVE_TEST_META_URL unset");
        return;
    };
    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(2)
        .connect(&url)
        .await
        .expect("connect to meta");

    let reader = PgConnectionReader::new(pool).expect("reader");
    let plane = MetaControlPlane::new(DefaultMetaRead::new(reader));

    // A uuid that cannot be in the registry. The refusal must come from the
    // real query returning no row, not from a mock deciding to.
    let err = dp::SessionContext::bind(
        &plane,
        dp::BindRequest { reality: uuid::Uuid::nil(), node: "live-test".into() },
        now_ms(),
    )
    .expect_err("the nil uuid must not be bindable");

    assert_eq!(err.variant_name(), "RealityMismatch", "got {err}");
    println!("LIVE: nil reality refused with {err}");
}

/// Unix-epoch milliseconds — the timebase `dp::Millis` specifies, and the one
/// `MetaControlPlane` stamps its expiry in.
fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("system clock before the unix epoch")
        .as_millis() as u64
}

/// A sanity check that runs WITHOUT a database, so the file is not silently
/// empty on a machine with no meta URL: it proves the enum this adapter decodes
/// into still contains the two statuses the live query filters on. If a rename
/// ever desynchronised them, the live test would skip ("no bindable reality")
/// and look like a pass.
#[test]
fn the_bindable_statuses_the_live_query_filters_on_still_exist() {
    use std::str::FromStr;
    assert_eq!(RealityStatus::from_str("active").unwrap(), RealityStatus::Active);
    assert_eq!(
        RealityStatus::from_str("pending_close").unwrap(),
        RealityStatus::PendingClose
    );
}
