//! Q1 B2b — the sqlx adapter against a REAL Postgres.
//!
//! Every test in `sqlx_pg`'s own module is a string assertion: it proves the
//! builder emits the SQL intended, and proves nothing about whether Postgres
//! accepts it. The entire `jsonb_populate_record` design rests on a claim about
//! server behaviour — *"a record typed by the table's own row type converts each
//! field to that column's type"* — and a claim about a server is settled by a
//! server. Without this file the adapter would ship with high-confidence unit
//! coverage and zero evidence.
//!
//! ## Running it
//!
//! `scripts/meta-rs-pg-live-smoke.sh` creates a throwaway DB, applies the four
//! meta migrations this exercises, and runs these tests against it. Manually:
//!
//! ```text
//! META_RS_TEST_DATABASE_URL=postgres://…/loreweave_test_meta_rs_smoke \
//!   cargo test -p meta-rs --features sqlx-pg --test pg_live
//! ```
//!
//! **Absent env var ⇒ the tests SKIP and say so.** They do not silently pass:
//! a skipped live test that reports success is how a broken adapter stays green.
//!
//! ## Destructive-op posture (CLAUDE.md › "Destructive DB ops in tests")
//!
//! These tests execute **no** DELETE, TRUNCATE or DROP — not as an oversight but
//! because `reality_ruleset_binding` is append-only and could not be cleaned up
//! anyway. Isolation comes from a fresh UUID per test, so runs never collide and
//! nothing needs removing. The DSN is read **only** from a dedicated
//! `META_RS_TEST_*` variable with no fallback to any production var, and the
//! guard below refuses a database whose name does not announce itself as
//! disposable — before the first statement, not after.

#![cfg(feature = "sqlx-pg")]

use meta_rs::allowlist::Allowlist;
use meta_rs::audit::{AuditClock, AuditUuidGen};
use meta_rs::metawrite::{
    meta_write, Actor, ActorType, MetaWriteConfig, MetaWriteIntent, MetaWriteOp, ValueMap,
};
use dp::ControlPlane;
use meta_rs::control_plane::MetaControlPlane;
use meta_rs::routing::DefaultMetaRead;
use meta_rs::session_store::{capability_digest, CapabilityStore, IssuedCapability};
use meta_rs::sqlx_pg::{
    bind_ruleset_intent, PgCapabilityStore, PgConnectionReader, PgConnectionWriter,
    PgOutboxAppender, PgQueryBuilder,
};
use sqlx::postgres::PgPoolOptions;
use sqlx::{PgPool, Row};
use uuid::Uuid;

const DSN_VAR: &str = "META_RS_TEST_DATABASE_URL";

struct WallClock;
impl AuditClock for WallClock {
    fn now_unix_nanos(&self) -> i64 {
        // Past 2020-01-01, which `meta_write_audit`'s plausibility CHECK
        // requires — a fixed 0 here would be refused by the schema, and that
        // refusal is a real constraint worth not fighting.
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock after epoch")
            .as_nanos() as i64
    }
}
struct RealUuid;
impl AuditUuidGen for RealUuid {
    fn new_uuid(&self) -> Uuid {
        Uuid::new_v4()
    }
}

/// `None` = no DSN configured; the caller prints a skip line.
fn dsn() -> Option<String> {
    let raw = std::env::var(DSN_VAR).ok()?;
    let db = raw.rsplit('/').next().unwrap_or("").split('?').next().unwrap_or("");
    assert!(
        ["test", "smoke", "audit", "scratch", "throwaway", "sandbox"]
            .iter()
            .any(|m| db.contains(m)),
        "{DSN_VAR} points at `{db}`, which carries no throwaway marker. These tests \
         write meta tables; refusing before the first statement rather than after."
    );
    Some(raw)
}

fn allowlist() -> Allowlist {
    Allowlist::load("../../contracts/meta/events_allowlist.yaml").expect("allowlist")
}

async fn pool(dsn: &str) -> PgPool {
    PgPoolOptions::new()
        .max_connections(2)
        .connect(dsn)
        .await
        .expect("connect")
}

/// Drive one intent all the way through `meta_write` with the real adapter.
fn write(pool: &PgPool, intent: MetaWriteIntent) -> Result<i64, meta_rs::MetaError> {
    let mut conn = PgConnectionWriter::new(pool.clone())?;
    let qb = PgQueryBuilder;
    let al = allowlist();
    let outbox = PgOutboxAppender::new(&al);
    let clock = WallClock;
    let uuid = RealUuid;
    let mut cfg = MetaWriteConfig {
        connection: &mut conn,
        allowlist: &al,
        query_builder: &qb,
        outbox: Some(&outbox),
        clock: &clock,
        uuid_gen: &uuid,
    };
    meta_write(&mut cfg, intent).map(|r| r.rows_affected)
}

fn actor() -> Actor {
    Actor {
        actor_type: ActorType::System,
        id: "commit-service".into(),
        svid: None,
    }
}

/// **The claim the whole adapter rests on.** `reality_id` is `uuid`, `epoch` is
/// `int`, `ruleset_digest` is `text` — three different column types, all
/// arriving as JSON, none of them annotated anywhere in Rust. If
/// `jsonb_populate_record` did not type them from the table, this is where
/// Postgres says `column "reality_id" is of type uuid but expression is of type
/// text` and the design is wrong.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_binding_lands_with_every_column_correctly_typed() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let pool = pool(&dsn).await;
    let reality = Uuid::new_v4();
    let digest = "a".repeat(64);

    let rows = write(
        &pool,
        bind_ruleset_intent(&reality.to_string(), 1, &digest, "reality created", actor()),
    )
    .expect("the binding must land");
    assert_eq!(rows, 1);

    let row = sqlx::query(
        "SELECT reality_id, epoch, ruleset_digest, reason, created_at IS NOT NULL AS has_ts \
         FROM reality_ruleset_binding WHERE reality_id = $1",
    )
    .bind(reality)
    .fetch_one(&pool)
    .await
    .expect("the row is readable back");

    // Fetched as the COLUMN's Rust type, not as text. A `uuid` column read into
    // `Uuid` and an `int` read into `i32` is the round-trip proof: had the
    // adapter smuggled them in as text, these decodes would fail.
    assert_eq!(row.get::<Uuid, _>("reality_id"), reality);
    assert_eq!(row.get::<i32, _>("epoch"), 1);
    assert_eq!(row.get::<String, _>("ruleset_digest"), digest);
    assert_eq!(row.get::<String, _>("reason"), "reality created");
    assert!(
        row.get::<bool, _>("has_ts"),
        "created_at is NOT NULL DEFAULT now(); a NULL here means the INSERT listed \
         the column and supplied nothing, which is what SELECT * would have done"
    );
}

/// The audit row and the outbox event ride the SAME transaction as the data
/// row. This is the property `MetaWrite` exists for, and it is invisible to
/// every mock — a fake TX records three calls whether or not the server ever
/// saw one transaction.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_audit_row_and_the_outbox_event_land_with_it() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let reality = Uuid::new_v4();
    write(
        &pool,
        bind_ruleset_intent(&reality.to_string(), 1, &"b".repeat(64), "created", actor()),
    )
    .expect("write");

    let audit = sqlx::query(
        "SELECT operation, actor_type, actor_id, row_pk, scrub_version \
         FROM meta_write_audit \
         WHERE table_name = 'reality_ruleset_binding' AND row_pk->>'reality_id' = $1",
    )
    .bind(reality.to_string())
    .fetch_one(&pool)
    .await
    .expect("an audit row exists for this write");
    assert_eq!(audit.get::<String, _>("operation"), "INSERT");
    assert_eq!(audit.get::<String, _>("actor_type"), "system");
    assert_eq!(audit.get::<String, _>("actor_id"), "commit-service");
    assert_eq!(
        audit.get::<String, _>("scrub_version"),
        "",
        "the Rust audit row has no scrub_version, so the column DEFAULT must \
         supply it — a NULL would violate NOT NULL and a listed-but-unset column \
         is how that happens"
    );

    // Queried through the PAYLOAD, not `aggregate_id`, and that is the point of
    // this block. `pk_as_string` composes a COMPOSITE key as
    // `epoch=1|reality_id=<uuid>` (sorted, mirroring Go) — it is only the bare
    // value for a single-column PK. The first draft of this test looked up the
    // bare UUID, found nothing, and reported a missing event that was sitting
    // right there. A consumer of `reality.ruleset.bound` that reads
    // `aggregate_id` expecting a reality id will make exactly that mistake, so
    // both forms are pinned here.
    let ev = sqlx::query(
        "SELECT event_name, aggregate_id, published FROM meta_outbox \
         WHERE payload->'pk'->>'reality_id' = $1",
    )
    .bind(reality.to_string())
    .fetch_one(&pool)
    .await
    .expect("the allowlist declares reality.ruleset.bound on INSERT, so an event must exist");
    assert_eq!(ev.get::<String, _>("event_name"), "reality.ruleset.bound");
    assert!(!ev.get::<bool, _>("published"));
    assert_eq!(
        ev.get::<String, _>("aggregate_id"),
        format!("epoch=1|reality_id={reality}"),
        "a composite PK composes both columns; a consumer must not read this as a \
         reality id"
    );
}

/// **This one is weaker than it looks, and the next test is the real proof.**
///
/// The data write is refused, so `meta_write` returns before it ever attempts
/// the audit row — the three zeroes below therefore follow from CONTROL FLOW,
/// not from transactionality, and would hold for an implementation with no
/// transaction at all. What it does still earn: the connection is not left
/// wedged with an open transaction (every later query here runs fine), and the
/// diagnostic reaches the caller intact.
///
/// Kept, labelled, rather than deleted or quietly presented as more than it is.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_refused_data_write_leaves_no_audit_and_no_event() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let reality = Uuid::new_v4();

    // Epoch 2 with no epoch 1 — refused by the trigger, inside the TX.
    let err = write(
        &pool,
        bind_ruleset_intent(&reality.to_string(), 2, &"c".repeat(64), "skipped one", actor()),
    )
    .expect_err("epoch 2 without epoch 1 must be refused");
    assert!(
        format!("{err}").contains("must be 1"),
        "refused for the wrong reason: {err}"
    );

    for (table, sql) in [
        ("reality_ruleset_binding", "SELECT count(*) FROM reality_ruleset_binding WHERE reality_id = $1::uuid"),
        ("meta_write_audit", "SELECT count(*) FROM meta_write_audit WHERE row_pk->>'reality_id' = $1"),
        // Through the payload, NOT `aggregate_id`. This line said
        // `WHERE aggregate_id = $1` and passed — vacuously: a composite PK
        // composes `epoch=2|reality_id=…`, so the bare UUID matches nothing
        // whether the rollback worked or not. It would have reported a clean
        // rollback for a transaction that leaked every row.
        ("meta_outbox", "SELECT count(*) FROM meta_outbox WHERE payload->'pk'->>'reality_id' = $1"),
    ] {
        let n: i64 = sqlx::query_scalar(sql)
            .bind(reality.to_string())
            .fetch_one(&pool)
            .await
            .expect("count");
        assert_eq!(n, 0, "{table} kept a row from a transaction that failed");
    }
}

/// **The atomicity proof: a SUCCEEDING data write, rolled back by a failure
/// downstream of it.**
///
/// The fault is injected with the schema's own constraint rather than a mock:
/// `meta_write_audit.actor_id` is `CHECK (length(actor_id) > 0)` (migration
/// 013), and `MetaWriteIntent::validate` does not require a non-empty actor id.
/// So an empty actor lets the binding INSERT succeed and then makes the audit
/// INSERT fail — the exact ordering that separates "one transaction" from
/// "three statements in a row".
///
/// Without this, the whole live suite would prove only that failures fail. The
/// binding row must be GONE afterwards; if it survives, `MetaWrite` is writing
/// domain rows that no audit trail records, which is the one thing the I8
/// invariant exists to prevent.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_failed_audit_write_rolls_the_successful_data_write_back() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let reality = Uuid::new_v4();

    let err = write(
        &pool,
        bind_ruleset_intent(
            &reality.to_string(),
            1,
            &"9".repeat(64),
            "created",
            Actor {
                actor_type: ActorType::System,
                id: String::new(), // fails meta_write_audit's CHECK, not the binding's
                svid: None,
            },
        ),
    )
    .expect_err("an empty actor_id must fail the audit insert");
    assert!(
        format!("{err}").contains("actor_id_nonempty"),
        "the fault must land on the AUDIT row — if it landed on the binding INSERT \
         instead, this test degenerates into the control-flow one above: {err}"
    );

    let n: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM reality_ruleset_binding WHERE reality_id = $1",
    )
    .bind(reality)
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(
        n, 0,
        "the binding INSERT SUCCEEDED and was then rolled back by the audit failure. \
         A surviving row here means the data write and its audit are not one \
         transaction — a domain write no audit trail records (I8)."
    );
}

/// `RLS-A3` binds once. The Rust path must surface that refusal as an error
/// rather than as a silent zero-row success — `meta_write` returns
/// `rows_affected`, and a caller that only checked for `Ok` would read "bound"
/// from a write that never happened.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn rebinding_the_same_epoch_is_an_error_not_a_quiet_no_op() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let reality = Uuid::new_v4();
    let id = reality.to_string();

    assert_eq!(
        write(&pool, bind_ruleset_intent(&id, 1, &"d".repeat(64), "created", actor())).unwrap(),
        1
    );
    let err = write(
        &pool,
        bind_ruleset_intent(&id, 1, &"e".repeat(64), "re-created", actor()),
    )
    .expect_err("a second binding at epoch 1 must be refused");
    assert!(
        format!("{err}").contains("must be epoch 2"),
        "refused for the wrong reason: {err}"
    );

    // …and the first binding is untouched, which is the point of refusing.
    let digest: String =
        sqlx::query_scalar("SELECT ruleset_digest FROM reality_ruleset_binding WHERE reality_id = $1")
            .bind(reality)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(digest, "d".repeat(64));
}

/// Advancing to epoch 2 is the operation `Q0b` will perform, and the history it
/// leaves behind is what `QTY-A5`'s never-reuse rule is recomputed over. If a
/// later epoch replaced the earlier row instead of adding to it, the high-water
/// ordinal would be computed from one ruleset instead of all of them.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_epoch_switch_adds_to_the_history_rather_than_replacing_it() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let id = Uuid::new_v4().to_string();
    write(&pool, bind_ruleset_intent(&id, 1, &"1".repeat(64), "created", actor())).unwrap();
    write(&pool, bind_ruleset_intent(&id, 2, &"2".repeat(64), "rules changed", actor())).unwrap();

    let rows: Vec<(i32, String)> = sqlx::query_as(
        "SELECT epoch, ruleset_digest FROM reality_ruleset_binding \
         WHERE reality_id = $1::uuid ORDER BY epoch",
    )
    .bind(&id)
    .fetch_all(&pool)
    .await
    .unwrap();
    assert_eq!(rows.len(), 2, "both epochs must survive");
    assert_eq!(rows[0], (1, "1".repeat(64)));
    assert_eq!(rows[1], (2, "2".repeat(64)));
}

/// An UPDATE through the adapter must be refused by the table, not by Rust.
/// This is what proves the append-only guarantee survives the code path that
/// could most plausibly bypass it — a generic `MetaWrite` that will happily
/// build an UPDATE for any allowlisted table.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn meta_write_cannot_update_an_append_only_binding() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let id = Uuid::new_v4().to_string();
    write(&pool, bind_ruleset_intent(&id, 1, &"f".repeat(64), "created", actor())).unwrap();

    let mut pk = ValueMap::new();
    pk.insert("reality_id".into(), serde_json::json!(id));
    pk.insert("epoch".into(), serde_json::json!(1));
    let mut new_values = ValueMap::new();
    new_values.insert("ruleset_digest".into(), serde_json::json!("0".repeat(64)));
    let err = write(
        &pool,
        MetaWriteIntent {
            table: "reality_ruleset_binding".into(),
            operation: MetaWriteOp::Update,
            pk,
            expected_before: ValueMap::new(),
            new_values,
            actor: actor(),
            reason: "should not be possible".into(),
            request_context: Default::default(),
        },
    )
    .expect_err("the table refuses UPDATE for every role");
    assert!(format!("{err}").contains("append-only"), "{err}");
}

// ── the adapter's UPDATE / DELETE / CAS paths ───────────────────────────────
//
// `reality_ruleset_binding` is append-only, so every test above can only ever
// prove that an UPDATE is REFUSED. That leaves `build_update`, `build_delete`
// and the CAS guard verified by string assertions alone — for an adapter whose
// whole purpose is to serve every meta table, not just this one. These run
// against `reality_registry`: allowlisted, writable, and the canonical
// CAS-guarded state machine in the meta schema.

fn registry_intent(reality: Uuid, status: &str) -> MetaWriteIntent {
    let mut pk = ValueMap::new();
    pk.insert("reality_id".into(), serde_json::json!(reality.to_string()));
    let mut new_values = ValueMap::new();
    for (k, v) in [
        ("db_host", serde_json::json!("pg-shard-1.internal")),
        ("db_name", serde_json::json!("loreweave_test_reality")),
        ("status", serde_json::json!(status)),
        ("locale", serde_json::json!("en-US")),
        ("session_max_pcs", serde_json::json!(4)),
        ("session_max_npcs", serde_json::json!(4)),
        ("session_max_total", serde_json::json!(8)),
        ("deploy_cohort", serde_json::json!(7)),
    ] {
        new_values.insert(k.into(), v);
    }
    MetaWriteIntent {
        table: "reality_registry".into(),
        operation: MetaWriteOp::Insert,
        pk,
        expected_before: ValueMap::new(),
        new_values,
        actor: actor(),
        reason: String::new(),
        request_context: Default::default(),
    }
}

/// A matching CAS updates exactly the intended row; a stale CAS updates none
/// and reports the conflict rather than succeeding quietly.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn update_honours_the_cas_guard_and_hits_only_the_intended_row() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let target = Uuid::new_v4();
    let bystander = Uuid::new_v4();
    write(&pool, registry_intent(target, "provisioning")).expect("seed target");
    write(&pool, registry_intent(bystander, "provisioning")).expect("seed bystander");

    let mut ok = registry_intent(target, "active");
    ok.operation = MetaWriteOp::Update;
    ok.new_values = ValueMap::from_iter([("status".to_string(), serde_json::json!("active"))]);
    ok.expected_before =
        ValueMap::from_iter([("status".to_string(), serde_json::json!("provisioning"))]);
    assert_eq!(write(&pool, ok.clone()).expect("matching CAS"), 1);

    let after: String = sqlx::query_scalar("SELECT status FROM reality_registry WHERE reality_id=$1")
        .bind(target)
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(after, "active");

    let untouched: String =
        sqlx::query_scalar("SELECT status FROM reality_registry WHERE reality_id=$1")
            .bind(bystander)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(
        untouched, "provisioning",
        "the UPDATE reached a row it did not name — the WHERE is not pinning the PK"
    );

    // The same CAS again is now stale: the row moved to `active`.
    let err = write(&pool, ok).expect_err("a stale CAS must not succeed");
    assert!(
        meta_rs::metawrite::is_concurrent(&err),
        "a CAS miss must surface as ConcurrentStateTransition, not as a quiet \
         zero-row success: {err}"
    );
}

/// A CAS on a column that is ALSO the primary key must not retarget the row.
/// Merging the two records made the CAS value overwrite the PK, so the UPDATE
/// silently hit whatever row held the CAS value. This is the live half of
/// `a_cas_on_a_pk_column_does_not_retarget_the_row`.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_cas_on_the_pk_column_cannot_reach_another_row() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let target = Uuid::new_v4();
    let victim = Uuid::new_v4();
    write(&pool, registry_intent(target, "provisioning")).expect("seed target");
    write(&pool, registry_intent(victim, "provisioning")).expect("seed victim");

    let mut evil = registry_intent(target, "active");
    evil.operation = MetaWriteOp::Update;
    evil.new_values = ValueMap::from_iter([("status".to_string(), serde_json::json!("frozen"))]);
    // pk = target, but expected_before names the VICTIM's id for the same column.
    evil.expected_before =
        ValueMap::from_iter([("reality_id".to_string(), serde_json::json!(victim.to_string()))]);

    // Unsatisfiable (`t.reality_id = target AND t.reality_id = victim`), so it
    // must report a conflict — never touch the victim.
    let err = write(&pool, evil).expect_err("no row can satisfy both");
    assert!(meta_rs::metawrite::is_concurrent(&err), "{err}");

    for (who, id) in [("victim", victim), ("target", target)] {
        let status: String =
            sqlx::query_scalar("SELECT status FROM reality_registry WHERE reality_id=$1")
                .bind(id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(status, "provisioning", "{who} was modified");
    }
}

/// `build_delete` removes the named row and only that one; a DELETE matching
/// nothing is a conflict, not a silent success.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn delete_removes_exactly_the_named_row() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let doomed = Uuid::new_v4();
    let bystander = Uuid::new_v4();
    write(&pool, registry_intent(doomed, "provisioning")).expect("seed");
    write(&pool, registry_intent(bystander, "provisioning")).expect("seed");

    let mut del = registry_intent(doomed, "provisioning");
    del.operation = MetaWriteOp::Delete;
    del.new_values = ValueMap::new();
    del.reason = "live adapter test".into();
    assert_eq!(write(&pool, del.clone()).expect("delete"), 1);

    let gone: i64 = sqlx::query_scalar("SELECT count(*) FROM reality_registry WHERE reality_id=$1")
        .bind(doomed)
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(gone, 0);
    let survived: i64 =
        sqlx::query_scalar("SELECT count(*) FROM reality_registry WHERE reality_id=$1")
            .bind(bystander)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(survived, 1, "the DELETE reached a row it did not name");

    let err = write(&pool, del).expect_err("deleting it twice must not be a quiet success");
    assert!(meta_rs::metawrite::is_concurrent(&err), "{err}");
}

/// The topic reaches the ROW, not just the parser. `reality.ruleset.bound`
/// declares none, so it must land NULL — the negative half; the positive half
/// (`user.erased`) has no Rust writer to drive it and is covered by
/// `a_declared_xreality_topic_survives_the_rust_parser` plus the Go appender's
/// own live test.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_event_with_no_declared_topic_lands_with_a_null_xreality_topic() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset");
        return;
    };
    let pool = pool(&dsn).await;
    let reality = Uuid::new_v4();
    write(
        &pool,
        bind_ruleset_intent(&reality.to_string(), 1, &"7".repeat(64), "created", actor()),
    )
    .expect("write");

    let topic: Option<String> = sqlx::query_scalar(
        "SELECT xreality_topic FROM meta_outbox WHERE payload->'pk'->>'reality_id' = $1",
    )
    .bind(reality.to_string())
    .fetch_one(&pool)
    .await
    .expect("the outbox row exists");
    assert_eq!(topic, None);
}

// ─────────────────────────────────────────────────────────────────────────────
// `5B` — the CAPABILITY STORE against a real server.
//
// `control_plane.rs`'s unit tests drive an in-memory store, which proves the
// decision logic and nothing about the SQL. Three things here can only be
// settled by Postgres, and each one is a plausible way to ship a broken store
// with green unit coverage:
//
//   1. `capability_hash` is BYTEA arriving as JSON. Every other column this
//      adapter writes is a uuid, an int or text. If the hex-escape form is
//      wrong, the digest lands mangled and EVERY lookup misses — a capability
//      store that issues and then never recognises.
//   2. `expires_at` / `revoked_at` are TIMESTAMPTZ arriving as RFC-3339 text,
//      and coming back as `chrono::DateTime`. A round trip that loses the
//      offset moves every expiry by the server's timezone.
//   3. The CAS on `revoked_at IS NULL` has to render as `IS NULL` rather than
//      `= NULL`. As equality it is never true, so revoke and refresh would
//      report "nothing to do" forever — silently, and identically to the
//      correct answer for an already-revoked row.
// ─────────────────────────────────────────────────────────────────────────────

/// Build a store bound to this pool, with the same actor the rest of the file
/// uses.
fn capability_store(pool: &PgPool) -> PgCapabilityStore {
    PgCapabilityStore::new(pool.clone(), allowlist(), actor()).expect("capability store")
}

/// A distinct issuance, so concurrent runs never collide on the digest UNIQUE.
fn issuance(secret: &str, expires_at_ms: u64) -> IssuedCapability {
    IssuedCapability {
        session_id: Uuid::new_v4(),
        reality_id: Uuid::new_v4(),
        node_id: "pg-live-node".into(),
        service_identity: "meta-rs-pg-live-test".into(),
        capability_hash: capability_digest(secret),
        // A fixed, obviously-synthetic instant rather than `now()`: the
        // assertions below compare exact millisecond values, and a wall-clock
        // reading would make the round-trip test compare a number against
        // itself-plus-drift.
        issued_at_ms: 1_700_000_000_000,
        expires_at_ms,
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_capability_round_trips_through_a_real_session_registry() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let pool = pool(&dsn).await;
    let store = capability_store(&pool);

    let secret = format!("live-secret-{}", Uuid::new_v4());
    let issued = issuance(&secret, 1_700_000_900_000);
    store.record(&issued).expect("record must reach the server");

    // The lookup that proves the BYTEA round trip. A mangled digest fails here
    // and nowhere else.
    let found = store
        .lookup(&capability_digest(&secret))
        .expect("lookup")
        .expect("the capability just recorded must be found by its digest");

    assert_eq!(found.session_id, issued.session_id);
    assert_eq!(found.reality_id, issued.reality_id);
    assert_eq!(found.node_id, "pg-live-node");
    assert_eq!(found.service_identity, "meta-rs-pg-live-test");
    assert_eq!(
        found.expires_at_ms, issued.expires_at_ms,
        "TIMESTAMPTZ must round-trip to the same instant — a lost offset shows up here"
    );
    assert_eq!(found.revoked_at_ms, None);
    assert!(found.is_live(issued.expires_at_ms - 1));
    assert!(!found.is_live(issued.expires_at_ms));

    // A digest that was never issued must not match anything, on a table that
    // now definitely has rows in it.
    assert!(
        store
            .lookup(&capability_digest("a-secret-nobody-minted"))
            .expect("lookup")
            .is_none(),
        "an unissued digest must not resolve"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_session_is_routable_by_id_without_presenting_its_capability() {
    // `5C`'s `GetSessionNode` (DP-C1) asks a ROUTING question — "where is
    // session S pinned" — from a node that does not hold S's capability. This
    // is the second SQL query in the store, on a different key, and it exists
    // so answering a routing question never requires passing a credential
    // around.
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let pool = pool(&dsn).await;
    let store = capability_store(&pool);

    let secret = format!("live-secret-{}", Uuid::new_v4());
    let issued = issuance(&secret, 1_700_000_900_000);
    store.record(&issued).expect("record");

    let found = store
        .find_by_session(issued.session_id)
        .expect("find_by_session")
        .expect("the session just recorded must be findable by its id");
    assert_eq!(found.node_id, "pg-live-node");
    assert_eq!(found.session_id, issued.session_id);
    assert_eq!(found.expires_at_ms, issued.expires_at_ms);

    // An unknown session is absent, not an error — and the two must not be
    // confused, because `GetSessionNode` reports absence as `assigned = false`.
    assert!(store.find_by_session(Uuid::new_v4()).expect("absent").is_none());

    // AND IT ANSWERS FOR A DEAD SESSION TOO. Routing and authorization are
    // different questions: a node handling a late message needs to know where
    // the session lived even after the grant died, and returning None would
    // make a stale route indistinguishable from a session that never existed.
    store
        .revoke(issued.session_id, 1_700_001_000_000, "routing-after-revocation")
        .expect("revoke");
    let after = store
        .find_by_session(issued.session_id)
        .expect("find")
        .expect("a revoked session is still routable");
    assert_eq!(after.node_id, "pg-live-node");
    assert_eq!(after.revoked_at_ms, Some(1_700_001_000_000));
    assert!(!after.is_live(1_700_000_800_000), "…while being plainly dead");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_audit_row_lands_in_the_same_transaction_as_the_capability() {
    // I8's whole requirement, and the reason this store goes through
    // `meta_write` instead of a hand-rolled INSERT. `crates/meta-rs/` is on
    // `meta-write-discipline-lint.sh`'s exclusion list, so nothing but this
    // test would notice the port being bypassed.
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let pool = pool(&dsn).await;
    let store = capability_store(&pool);

    let secret = format!("live-secret-{}", Uuid::new_v4());
    let issued = issuance(&secret, 1_700_000_900_000);
    store.record(&issued).expect("record");

    // `row_pk`, not `pk` — the column name the live server insisted on, and
    // exactly the kind of thing a string-asserting unit test agrees with you
    // about.
    let audited: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM meta_write_audit \
         WHERE table_name = 'session_registry' AND row_pk::text LIKE $1",
    )
    .bind(format!("%{}%", issued.session_id))
    .fetch_one(&pool)
    .await
    .expect("audit query");

    assert_eq!(
        audited, 1,
        "the capability write must have produced exactly one audit row for its session"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn revoke_and_refresh_cas_against_a_real_server() {
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let pool = pool(&dsn).await;
    let store = capability_store(&pool);

    let secret = format!("live-secret-{}", Uuid::new_v4());
    let issued = issuance(&secret, 1_700_000_900_000);
    store.record(&issued).expect("record");

    // REFRESH — the CAS holds the expiry that was read.
    assert!(
        store
            .extend(issued.session_id, issued.expires_at_ms, 1_700_001_800_000)
            .expect("extend"),
        "a refresh holding the current expiry must apply"
    );
    assert!(
        !store
            .extend(issued.session_id, issued.expires_at_ms, 1_700_002_700_000)
            .expect("stale extend"),
        "a refresh holding the OLD expiry must not apply — this is the lost-update guard"
    );
    let after = store
        .lookup(&capability_digest(&secret))
        .expect("lookup")
        .expect("row");
    assert_eq!(
        after.expires_at_ms, 1_700_001_800_000,
        "the stale refresh must not have overwritten the successful one"
    );

    // REVOKE — and the `revoked_at IS NULL` guard rendering correctly is the
    // only reason the second call answers `false`.
    assert!(
        store
            .revoke(issued.session_id, 1_700_001_000_000, "pg-live drill")
            .expect("revoke"),
        "an unrevoked capability must revoke"
    );
    assert!(
        !store
            .revoke(issued.session_id, 1_700_001_500_000, "again")
            .expect("second revoke"),
        "a second revocation must report false rather than overwrite the first timestamp"
    );

    let revoked = store
        .lookup(&capability_digest(&secret))
        .expect("lookup")
        .expect("row");
    assert_eq!(
        revoked.revoked_at_ms,
        Some(1_700_001_000_000),
        "the FIRST revocation's instant is the fact an incident review wants"
    );
    assert!(
        !revoked.is_live(1_700_001_100_000),
        "a revoked capability is dead before its expiry"
    );

    // …and a revoked row does not refresh, which is what stops revocation from
    // being a suggestion.
    assert!(
        !store
            .extend(issued.session_id, 1_700_001_800_000, 1_700_009_000_000)
            .expect("extend revoked"),
        "a revoked capability must not be resurrected by a refresh"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_control_plane_end_to_end_against_a_real_store() {
    // Bind through the real `MetaControlPlane` onto the real store, then
    // validate and revoke. This is the DoD's LIVE RUN axis for 5B: no double
    // anywhere in the path except the registry read, which needs a reality row
    // this throwaway database does have.
    let Some(dsn) = dsn() else {
        eprintln!("SKIP: {DSN_VAR} unset — run scripts/meta-rs-pg-live-smoke.sh");
        return;
    };
    let pool = pool(&dsn).await;

    // Seed a bindable reality. This database is throwaway (the DSN guard
    // refuses anything else), and the row is scoped to a fresh uuid.
    let reality = Uuid::new_v4();
    // Every NOT NULL column that has no default. The capacity trio is not
    // optional — the live server refused the row without it — and a seed that
    // omits a required column is a fixture that drifts out of the schema the
    // day another NOT NULL is added.
    sqlx::query(
        "INSERT INTO reality_registry \
         (reality_id, db_host, db_name, status, locale, \
          session_max_pcs, session_max_npcs, session_max_total, deploy_cohort) \
         VALUES ($1, 'pg-shard-0.internal', 'lw_reality_pg_live', 'active', 'en', 8, 24, 32, 0)",
    )
    .bind(reality)
    .execute(&pool)
    .await
    .expect("seed reality");

    let reader = PgConnectionReader::new(pool.clone()).expect("reader");
    let plane = MetaControlPlane::new(DefaultMetaRead::new(reader), capability_store(&pool));

    let req = dp::BindRequest {
        reality,
        node: "pg-live-node".into(),
        service: dp::ServiceIdentity::new("meta-rs-pg-live-test").expect("valid"),
    };
    let bound = plane.verify_bind(&req).expect("bind against the live registry and store");

    let now = now_ms();
    let record = plane
        .validate_capability(&bound.capability_secret, now)
        .expect("the capability just issued must validate against the real table");
    assert_eq!(record.session_id, bound.session);
    assert_eq!(record.reality_id, reality);
    assert_eq!(record.service_identity, "meta-rs-pg-live-test");

    // Revocation, end to end: the same secret stops validating.
    assert!(plane.revoke_session(bound.session, "pg-live drill").expect("revoke"));
    let err = plane
        .validate_capability(&bound.capability_secret, now)
        .expect_err("a revoked capability must not validate");
    assert_eq!(err.variant_name(), "CapabilityExpired", "got {err}");

    println!(
        "LIVE 5B: bound session {} for reality {}, validated, revoked, re-validation refused",
        bound.session, reality
    );
}

/// Unix-epoch milliseconds — the timebase `dp::Millis` specifies.
fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("system clock before the unix epoch")
        .as_millis() as u64
}
