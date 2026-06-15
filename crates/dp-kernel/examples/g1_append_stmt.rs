//! G1 (structural perf-shape gate) — statement-shape harness for the REAL event
//! append path. Driven by `scripts/perf/w5-append-stmt-shape.sh`.
//!
//! ## The invariant
//!
//! `PgEventStore::append_events` issues, per call, ONE high-water
//! `SELECT MAX(aggregate_version) FROM events …` regardless of the batch size K
//! (the K event INSERTs scale with K — that is correct-by-design, not a
//! regression). The structural risk a HIGHER layer can introduce is an N+1: a
//! refactor that moves the high-water read inside the per-event loop, making the
//! SELECT scale with K. This harness measures the real append's statement shape
//! via `pg_stat_statements` so that regression is detectable.
//!
//! ## Why this is honest (review F1/F2)
//!
//!   * CLEAN mode calls the REAL `PgEventStore::append_events` (NOT the Go
//!     workload generator, which re-implements the INSERT and has no high-water
//!     SELECT at all — F1). So the measured shape is the production code's.
//!   * BITE mode runs a REAL append against live PG that deliberately issues a
//!     per-event high-water SELECT (the N+1). Its `pg_stat_statements` capture is
//!     a genuine measurement of a real (buggy) append — NOT a fabricated number
//!     (F2). It proves the gate's assertion CAN fail.
//!
//! ## Self-contained
//!
//! Creates its own throwaway schema + a minimal `events` table (just the columns
//! `append_events` binds) so it runs against ANY live PG with `pg_stat_statements`
//! preloaded — no pre-applied per-reality migrations needed. The minimal table
//! does not affect the SELECT-count invariant (the high-water query is identical).
//!
//! Usage: `cargo run -p dp-kernel --example g1_append_stmt -- <clean|bite> <K>`
//! Env:   `LOREWEAVE_TEST_PG_URL` (required).
//! Output (stdout, last line): `SELECT_MAX_CALLS=<n> INSERT_CALLS=<m>`

use dp_kernel::PgEventStore;
use dp_kernel::envelope::EventEnvelope;
use dp_kernel::event_store::EventStore;
use sqlx::postgres::PgPoolOptions;
use sqlx::{PgPool, Row};
use uuid::Uuid;

const EVENTS_DDL: &str = r#"
CREATE TABLE events (
    event_id          uuid PRIMARY KEY,
    reality_id        uuid NOT NULL,
    aggregate_type    text NOT NULL,
    aggregate_id      text NOT NULL,
    aggregate_version bigint NOT NULL,
    event_type        text NOT NULL,
    event_version     int  NOT NULL,
    payload           jsonb NOT NULL,
    metadata          jsonb,
    occurred_at       timestamptz NOT NULL,
    recorded_at       timestamptz NOT NULL,
    content_sha256    text NOT NULL
)
"#;

/// The SAME high-water query text the real `append_events` uses, so the BITE's
/// per-event SELECT groups under the same `pg_stat_statements` entry pattern.
const HIGH_WATER_SQL: &str = "SELECT MAX(aggregate_version) FROM events \
     WHERE reality_id = $1 AND aggregate_type = $2 AND aggregate_id = $3";

// A fixed UTC instant for the appended rows. The exact value is irrelevant to
// the statement-shape measurement (we count statement CALLS, not timestamps), so
// a constant keeps the harness deterministic. PG parses the trailing 'Z'.
const FIXED_TS: &str = "2026-01-01T00:00:00Z";

fn make_batch(reality: Uuid, atype: &str, aid: &str, k: u64) -> Vec<EventEnvelope> {
    (1..=k)
        .map(|v| EventEnvelope {
            event_id: Uuid::new_v4(),
            event_type: "npc.said".to_string(),
            event_version: 1,
            aggregate_id: aid.to_string(),
            aggregate_type: atype.to_string(),
            aggregate_version: v,
            reality_id: reality,
            occurred_at: FIXED_TS.to_string(),
            recorded_at: FIXED_TS.to_string(),
            payload: serde_json::json!({"text": "hello", "n": v}),
            metadata: Some(serde_json::json!({"session_id": "sess-1"})),
        })
        .collect()
}

/// BITE: a deliberately-regressed append that issues a per-event high-water
/// SELECT (the N+1) before each INSERT. Real SQL against live PG — its
/// `pg_stat_statements` capture is genuine. Mirrors the real INSERT shape.
async fn bite_append(pool: &PgPool, batch: &[EventEnvelope]) -> Result<(), sqlx::Error> {
    let mut tx = pool.begin().await?;
    for ev in batch {
        // The injected N+1: one high-water SELECT PER EVENT (vs once per call).
        let _hw: Option<i64> = sqlx::query_scalar(HIGH_WATER_SQL)
            .bind(ev.reality_id)
            .bind(&ev.aggregate_type)
            .bind(&ev.aggregate_id)
            .fetch_one(&mut *tx)
            .await?;
        sqlx::query(
            "INSERT INTO events (event_id, reality_id, aggregate_type, aggregate_id, \
             aggregate_version, event_type, event_version, payload, metadata, occurred_at, \
             recorded_at, content_sha256) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::timestamptz,\
             $11::timestamptz, encode(sha256(convert_to(jsonb_build_object('p',$8::jsonb,\
             'm',$9::jsonb)::text,'UTF8')),'hex'))",
        )
        .bind(ev.event_id)
        .bind(ev.reality_id)
        .bind(&ev.aggregate_type)
        .bind(&ev.aggregate_id)
        .bind(ev.aggregate_version as i64)
        .bind(&ev.event_type)
        .bind(ev.event_version as i32)
        .bind(&ev.payload)
        .bind(ev.metadata.as_ref())
        .bind(&ev.occurred_at)
        .bind(&ev.recorded_at)
        .execute(&mut *tx)
        .await?;
    }
    tx.commit().await?;
    Ok(())
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let mode = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "clean".to_string());
    let k: u64 = std::env::args()
        .nth(2)
        .and_then(|s| s.parse().ok())
        .unwrap_or(1);
    let url = std::env::var("LOREWEAVE_TEST_PG_URL")
        .expect("LOREWEAVE_TEST_PG_URL must be set (the G1 live gate target)");

    let schema = format!("g1_{}", Uuid::new_v4().simple());

    // Bootstrap connection: ensure the extension, create the throwaway schema +
    // minimal events table. The pool below pins search_path to this schema.
    let boot = PgPoolOptions::new()
        .max_connections(1)
        .connect(&url)
        .await
        .expect("connect (bootstrap)");
    sqlx::query("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        .execute(&boot)
        .await
        .expect("pg_stat_statements must be preloaded (shared_preload_libraries)");
    sqlx::query(&format!("CREATE SCHEMA {schema}"))
        .execute(&boot)
        .await
        .expect("create schema");
    sqlx::query(&format!("SET search_path TO {schema}, public"))
        .execute(&boot)
        .await
        .expect("set search_path (boot)");
    sqlx::query(EVENTS_DDL)
        .execute(&boot)
        .await
        .expect("create events table");

    // The measured pool: every connection pins search_path to the throwaway
    // schema so the real append's unqualified `FROM events` resolves there.
    let sch = schema.clone();
    let pool = PgPoolOptions::new()
        .max_connections(2)
        .after_connect(move |conn, _meta| {
            let sch = sch.clone();
            Box::pin(async move {
                sqlx::query(&format!("SET search_path TO {sch}, public"))
                    .execute(conn)
                    .await?;
                Ok(())
            })
        })
        .connect(&url)
        .await
        .expect("connect (measured pool)");

    let reality = Uuid::new_v4();
    let batch = make_batch(reality, "npc", "agg-1", k);

    // Reset AFTER setup so only the append's statements are measured.
    sqlx::query("SELECT pg_stat_statements_reset()")
        .execute(&boot)
        .await
        .expect("pg_stat_statements_reset");

    match mode.as_str() {
        "clean" => {
            let store = PgEventStore::new(pool.clone());
            store
                .append_events(reality, "npc", "agg-1", 0, &batch)
                .await
                .expect("real append_events");
        }
        "bite" => {
            bite_append(&pool, &batch).await.expect("bite append");
        }
        other => panic!("unknown mode {other:?} (use clean|bite)"),
    }

    // Read the per-statement call counts. pg_stat_statements aggregates by
    // normalized query; sum calls for the high-water SELECT and the events
    // INSERT regardless of which schema/binding variant grouped them.
    let select_calls: i64 = sqlx::query(
        "SELECT COALESCE(SUM(calls),0)::bigint FROM pg_stat_statements \
         WHERE query LIKE '%MAX(aggregate_version)%' AND query LIKE '%events%'",
    )
    .fetch_one(&boot)
    .await
    .map(|r| r.get::<i64, _>(0))
    .unwrap_or(-1);
    let insert_calls: i64 = sqlx::query(
        "SELECT COALESCE(SUM(calls),0)::bigint FROM pg_stat_statements \
         WHERE query LIKE 'INSERT INTO events%'",
    )
    .fetch_one(&boot)
    .await
    .map(|r| r.get::<i64, _>(0))
    .unwrap_or(-1);

    // Best-effort cleanup (the dev volume is wiped between CI runs anyway).
    let _ = sqlx::query(&format!("DROP SCHEMA IF EXISTS {schema} CASCADE"))
        .execute(&boot)
        .await;

    println!("mode={mode} K={k} SELECT_MAX_CALLS={select_calls} INSERT_CALLS={insert_calls}");
}
