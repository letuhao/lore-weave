//! 147 (D-L3EF-REPLAY-LIVE-SMOKE) — the round-trip proof for the L3.E/F
//! integrity-checker keystone.
//!
//! For each case: seed an event stream into a live per-reality `events` table,
//! build the "live" projection row IN-PROCESS through the SAME
//! [`all_projections`] + [`SqlxProjectionWriter`] the bin reuses, then run the
//! compiled `replay-aggregate` bin AS A SUBPROCESS (the exact path the Go
//! integrity-checker `AggregateLoader` invokes) and byte-compare the bin's
//! `to_jsonb − meta` payload against the live row's `to_jsonb − meta`. A clean
//! (non-drifted) row matches byte-for-byte; a tampered row does not.
//!
//! This validates the parts NO unit test can reach:
//!   * the temp-shadow trick (`CREATE TEMP TABLE … (LIKE public.… INCLUDING
//!     ALL)` + `pg_temp` search_path shadowing) reproduces the real table's
//!     casting / defaults / `to_jsonb` rendering identically;
//!   * the bin's subprocess contract end-to-end against real Postgres (arg
//!     parse → bounded multi-aggregate events query → boundary → PK select →
//!     meta-strip → JSON stdout);
//!   * the multi-aggregate (2 `--aggregate` pairs) global-ordered replay path.
//!
//! Gated by `LOREWEAVE_TEST_PG_URL` (a per-reality DB that gets `0002` + `0006`
//! applied — `0002` DROPs+recreates `events`, so point this at a DISPOSABLE
//! DB). Unset → prints a skip line and returns green so dev machines without
//! Postgres still pass `cargo test`. See
//! `docs/plans/2026-06-03-l3ef-integrity-checker.md` (Slice 3).

use std::process::Command;
use std::sync::Arc;

use dp_kernel::{EventEnvelope, Projection, ProjectionRunner, ProjectionUpdate};
use rebuilder::ProjectionWriter;
use serde_json::{Value, json};
use sqlx::Row;
use sqlx::postgres::{PgPool, PgPoolOptions};
use tokio::runtime::Runtime;
use uuid::Uuid;

use world_service::rebuild::all_projections;
use world_service::rebuild::writer::SqlxProjectionWriter;

// ─── Migration helpers (mirror embedding_live.rs) ──────────────────────────

fn migration(rel: &str) -> String {
    let root = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");
    let path = format!("{root}/{rel}");
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read migration {path}: {e}"))
}

async fn apply(pool: &PgPool, rel: &str) {
    let sql = migration(rel);
    sqlx::raw_sql(&sql)
        .execute(pool)
        .await
        .unwrap_or_else(|e| panic!("apply {rel}: {e}"));
}

// ─── Event construction + seeding ──────────────────────────────────────────

/// Build an envelope. `recorded_at` is intentionally a placeholder string: the
/// projection runner derives `applied_at` (a META key) from it, and META keys
/// are stripped on BOTH sides before comparison, so its value never reaches the
/// compared payload. The DB row's `recorded_at` (the partition key + replay
/// order) is set separately by [`seed_events`] via SQL.
fn mk(
    event_id: Uuid,
    event_type: &str,
    aggregate_type: &str,
    aggregate_id: &str,
    aggregate_version: u64,
    reality_id: Uuid,
    occurred_at: &str,
    payload: Value,
) -> EventEnvelope {
    EventEnvelope {
        event_id,
        event_type: event_type.into(),
        event_version: 1,
        aggregate_id: aggregate_id.into(),
        aggregate_type: aggregate_type.into(),
        aggregate_version,
        reality_id,
        occurred_at: occurred_at.into(),
        recorded_at: occurred_at.into(),
        payload,
        metadata: None,
    }
}

/// INSERT the events in global order. `recorded_at` (the partition key) is set
/// to `date_trunc('month', now()) + idx s` so every row lands in the single
/// current-month partition `0002` creates AND the `(recorded_at, event_id)`
/// global order equals the slice order — so the bin's `ORDER BY recorded_at,
/// event_id` replays them in exactly the order they appear here.
async fn seed_events(pool: &PgPool, events: &[EventEnvelope]) {
    for (idx, e) in events.iter().enumerate() {
        sqlx::query(
            "INSERT INTO events \
                 (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version, \
                  event_type, event_version, payload, occurred_at, recorded_at) \
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::timestamptz, \
                     date_trunc('month', now()) + ($10 * interval '1 second'))",
        )
        .bind(e.event_id)
        .bind(e.reality_id)
        .bind(&e.aggregate_type)
        .bind(&e.aggregate_id)
        .bind(e.aggregate_version as i64)
        .bind(&e.event_type)
        .bind(e.event_version as i32)
        .bind(&e.payload)
        .bind(&e.occurred_at)
        .bind(idx as i32)
        .execute(pool)
        .await
        .unwrap_or_else(|err| panic!("seed event {} ({}): {err}", e.event_id, e.event_type));
    }
}

/// Produce the "live" projection row by replaying `events` through the SAME
/// projection set + writer the bin reuses, targeting the REAL `target` table.
/// This is the in-process analogue of the live projection consumer. Sync (the
/// writer drives its own `handle.block_on`); MUST be called outside any
/// `rt.block_on(...)` to avoid a nested-runtime panic (mirrors the bin, which
/// runs discrete `block_on`s then `apply_batch`).
fn apply_live(rt: &Runtime, pool: Arc<PgPool>, target: &str, events: &[EventEnvelope]) {
    let projections = all_projections();
    let mut runner = ProjectionRunner::new();
    for p in &projections {
        runner = runner.with_projection(*p as &dyn Projection);
    }
    let mut updates: Vec<ProjectionUpdate> = Vec::new();
    for e in events {
        updates.extend(runner.apply_one(e));
    }
    let writer = SqlxProjectionWriter::new(pool, rt.handle().clone(), target.to_string())
        .expect("known projection table");
    writer.apply_batch(&updates).expect("apply live batch");
}

/// The live row's canonical payload — `to_jsonb(t)` minus the 5 META keys,
/// exactly matching the bin's `payload_select_sql`. `pk` is `(column, uuid)`
/// pairs (all L3.A PKs touched here are UUID). `None` when no row exists.
async fn live_payload(pool: &PgPool, table: &str, pk: &[(&str, Uuid)]) -> Option<Value> {
    let where_clause = pk
        .iter()
        .enumerate()
        .map(|(i, (c, _))| format!("t.{c} = ${}", i + 1))
        .collect::<Vec<_>>()
        .join(" AND ");
    let sql = format!(
        "SELECT to_jsonb(t) - 'event_id' - 'aggregate_version' - 'applied_at' \
                        - 'last_verified_event_version' - 'last_verified_at' AS payload \
           FROM {table} t WHERE {where_clause} LIMIT 1"
    );
    let mut q = sqlx::query(&sql);
    for (_, v) in pk {
        q = q.bind(*v);
    }
    q.fetch_optional(pool)
        .await
        .expect("live payload query")
        .map(|row| row.try_get::<Value, _>("payload").expect("payload column"))
}

// ─── Bin invocation ────────────────────────────────────────────────────────

/// Run the compiled `replay-aggregate` bin and return its parsed stdout JSON.
/// `aggregates` are `<type>:<id>` strings (repeatable). Panics on a non-zero
/// exit (that is an invocation/wiring error — exit 2 — never a SKIP).
fn run_bin(
    db_url: &str,
    reality_id: Uuid,
    projection: &str,
    aggregates: &[String],
    boundary_event_id: Uuid,
    pk_json: &str,
) -> Value {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_replay-aggregate"));
    cmd.env("REALITY_DB_URL", db_url)
        .args(["--reality-id", &reality_id.to_string()])
        .args(["--projection", projection])
        .args(["--boundary-event-id", &boundary_event_id.to_string()])
        .args(["--pk", pk_json]);
    for a in aggregates {
        cmd.args(["--aggregate", a]);
    }
    let out = cmd.output().expect("spawn replay-aggregate bin");
    assert!(
        out.status.success(),
        "replay-aggregate exited {:?}\nstderr: {}",
        out.status.code(),
        String::from_utf8_lossy(&out.stderr)
    );
    let stdout = String::from_utf8(out.stdout).expect("utf8 stdout");
    serde_json::from_str(&stdout).unwrap_or_else(|e| panic!("parse bin stdout {stdout:?}: {e}"))
}

// ─── The round-trip test ───────────────────────────────────────────────────

#[test]
fn replay_aggregate_round_trip_live_smoke() {
    let Ok(db_url) = std::env::var("LOREWEAVE_TEST_PG_URL") else {
        eprintln!("SKIP replay_aggregate_live: set LOREWEAVE_TEST_PG_URL to run");
        return;
    };

    let rt = Runtime::new().expect("tokio runtime");
    let pool = rt
        .block_on(PgPoolOptions::new().max_connections(5).connect(&db_url))
        .expect("connect test DB");
    let pool = Arc::new(pool);

    // Real schema (idempotent). 0002 DROPs+recreates `events`; 0006 creates the
    // projection tables IF NOT EXISTS. Fresh UUIDs per run avoid PK collisions.
    rt.block_on(apply(
        &pool,
        "contracts/migrations/per_reality/0002_events_table.up.sql",
    ));
    rt.block_on(apply(
        &pool,
        "contracts/migrations/per_reality/0006_projections.up.sql",
    ));

    let reality_id = Uuid::new_v4();

    // ══ Case 1 — pc, single-aggregate, CLEAN ════════════════════════════════
    let pc_id = Uuid::new_v4();
    let user_id = Uuid::new_v4();
    let region_1 = Uuid::new_v4();
    let region_2 = Uuid::new_v4();
    let spawn = Uuid::new_v4();
    let moved = Uuid::new_v4();
    let pc_events = vec![
        mk(
            spawn,
            "pc.spawned",
            "pc",
            &pc_id.to_string(),
            1,
            reality_id,
            "2026-06-15T12:00:00Z",
            json!({
                "user_id": user_id.to_string(),
                "name": "Aria",
                "spawn_region_id": region_1.to_string(),
                "stats": { "hp": 100, "level": 3 },
            }),
        ),
        mk(
            moved,
            "pc.moved",
            "pc",
            &pc_id.to_string(),
            2,
            reality_id,
            "2026-06-15T12:05:00Z",
            json!({ "to_region_id": region_2.to_string() }),
        ),
    ];
    rt.block_on(seed_events(&pool, &pc_events));
    apply_live(&rt, pool.clone(), "pc_projection", &pc_events);

    let pc_agg = vec![format!("pc:{pc_id}")];
    let pc_pk = format!(r#"{{"pc_id":"{pc_id}"}}"#);
    let out = run_bin(&db_url, reality_id, "pc_projection", &pc_agg, moved, &pc_pk);
    assert_eq!(out["status"], "ok", "pc replay status: {out}");
    assert_eq!(out["found"], true, "pc replay found a row: {out}");
    assert_eq!(out["events_replayed"], 2, "pc replayed both events: {out}");

    let live = rt
        .block_on(live_payload(&pool, "pc_projection", &[("pc_id", pc_id)]))
        .expect("live pc row exists");
    assert_eq!(
        out["payload"], live,
        "CLEAN: replayed pc payload must byte-match the live row\nreplay: {}\nlive:   {}",
        out["payload"], live
    );
    // Spot-check the value the second event wrote landed (replay applied the move).
    assert_eq!(live["current_region_id"], json!(region_2.to_string()));
    assert_eq!(live["last_event_version"], json!(2));

    // ══ Case 2 — pc DRIFT detection ══════════════════════════════════════════
    // Tamper the live row; the replay is unaffected, so the byte-compare must
    // now DIFFER (the checker catches drift, not a rubber-stamp).
    rt.block_on(async {
        sqlx::query("UPDATE pc_projection SET name = 'Tampered' WHERE pc_id = $1")
            .bind(pc_id)
            .execute(&*pool)
            .await
            .expect("tamper pc row");
    });
    let out_drift = run_bin(&db_url, reality_id, "pc_projection", &pc_agg, moved, &pc_pk);
    let live_drift = rt
        .block_on(live_payload(&pool, "pc_projection", &[("pc_id", pc_id)]))
        .expect("tampered pc row exists");
    assert_ne!(
        out_drift["payload"], live_drift,
        "DRIFT: tampered live row must NOT match the replay"
    );
    assert_eq!(
        out_drift["payload"]["name"],
        json!("Aria"),
        "replay holds the correct name"
    );
    assert_eq!(
        live_drift["name"],
        json!("Tampered"),
        "live row holds the tampered name"
    );

    // ══ Case 3 — multi-aggregate invocation, composite-PK, CLEAN ═════════════
    // npc_session_memory_projection built from session.* events (Insert→Update),
    // with an npc.created event from a SECOND aggregate interleaved by
    // recorded_at. The npc event contributes no update to THIS target (dropped)
    // — its purpose is to exercise the 2-pair `IN`-list events query + global
    // ordering across aggregates against real PG. Also proves the writer-Insert
    // fix: session.started omits NOT NULL `summary`/`facts` (→ DEFAULT).
    let npc_id = Uuid::new_v4();
    let session_id = Uuid::new_v4();
    let synthetic_agg = Uuid::new_v4();
    let npc_region = Uuid::new_v4();
    let (s_started, n_created, s_ended) = (Uuid::new_v4(), Uuid::new_v4(), Uuid::new_v4());
    let sess_events = vec![
        mk(
            s_started,
            "session.started",
            "session",
            &session_id.to_string(),
            1,
            reality_id,
            "2026-06-15T14:00:00Z",
            json!({
                "npc_id": npc_id.to_string(),
                "session_id": session_id.to_string(),
                "aggregate_id": synthetic_agg.to_string(),
            }),
        ),
        mk(
            n_created,
            "npc.created",
            "npc",
            &npc_id.to_string(),
            1,
            reality_id,
            "2026-06-15T14:01:00Z",
            json!({
                "glossary_entity_id": null,
                "spawn_region_id": npc_region.to_string(),
                "initial_mood": "neutral",
                "core_beliefs": { "loyal": true },
            }),
        ),
        mk(
            s_ended,
            "session.ended",
            "session",
            &session_id.to_string(),
            2,
            reality_id,
            "2026-06-15T14:30:00Z",
            json!({
                "npc_id": npc_id.to_string(),
                "session_id": session_id.to_string(),
            }),
        ),
    ];
    rt.block_on(seed_events(&pool, &sess_events));
    apply_live(
        &rt,
        pool.clone(),
        "npc_session_memory_projection",
        &sess_events,
    );

    let sess_aggs = vec![format!("session:{session_id}"), format!("npc:{npc_id}")];
    let sess_pk = format!(r#"{{"npc_id":"{npc_id}","session_id":"{session_id}"}}"#);
    let out_sess = run_bin(
        &db_url,
        reality_id,
        "npc_session_memory_projection",
        &sess_aggs,
        s_ended,
        &sess_pk,
    );
    assert_eq!(
        out_sess["status"], "ok",
        "session replay status: {out_sess}"
    );
    assert_eq!(
        out_sess["found"], true,
        "session replay found a row: {out_sess}"
    );
    // All 3 events are in-bound for the 2-aggregate query (npc.created included
    // even though it writes a different table) — proves the IN-list breadth.
    assert_eq!(
        out_sess["events_replayed"], 3,
        "all 3 events replayed: {out_sess}"
    );

    let live_sess = rt
        .block_on(live_payload(
            &pool,
            "npc_session_memory_projection",
            &[("npc_id", npc_id), ("session_id", session_id)],
        ))
        .expect("live session row exists");
    assert_eq!(
        out_sess["payload"], live_sess,
        "CLEAN: replayed session payload must byte-match the live row\nreplay: {}\nlive:   {}",
        out_sess["payload"], live_sess
    );
    // session.ended Update landed; the writer-Insert fix gave summary/facts
    // their NOT NULL DEFAULTs (the bug 147 surfaced).
    assert_eq!(live_sess["archive_status"], json!("faded"));
    assert_eq!(live_sess["summary"], json!(""));
    assert_eq!(live_sess["facts"], json!({}));

    // ══ Case 4 — ORPHAN DRIFT verdict: replay ran (events>0) but produced NO row
    // at the queried PK. The Go checker marks this DRIFT (a live projection row
    // the events do not produce); here we assert the BIN's signal end-to-end
    // against real PG: status=ok, found=false, events_replayed>0. (148)
    let pc_c = Uuid::new_v4();
    let spawn_c = Uuid::new_v4();
    let pc_foreign = Uuid::new_v4(); // a PK the replay never writes
    let orphan_events = vec![mk(
        spawn_c,
        "pc.spawned",
        "pc",
        &pc_c.to_string(),
        1,
        reality_id,
        "2026-06-15T18:00:00Z",
        json!({
            "user_id": Uuid::new_v4().to_string(),
            "name": "Ghost",
            "spawn_region_id": Uuid::new_v4().to_string(),
            "stats": {},
        }),
    )];
    rt.block_on(seed_events(&pool, &orphan_events));
    let out_orphan = run_bin(
        &db_url,
        reality_id,
        "pc_projection",
        &[format!("pc:{pc_c}")],
        spawn_c,
        &format!(r#"{{"pc_id":"{pc_foreign}"}}"#),
    );
    assert_eq!(
        out_orphan["status"], "ok",
        "orphan replay status: {out_orphan}"
    );
    assert_eq!(
        out_orphan["found"], false,
        "replay produced no row at the foreign PK → orphan-drift signal: {out_orphan}"
    );
    assert_eq!(
        out_orphan["events_replayed"], 1,
        "the pc aggregate's event WAS replayed (events>0 distinguishes DRIFT from SKIP): {out_orphan}"
    );

    // ══ Case 5 — SKIP verdict: the aggregate has NO in-bound events (pruned /
    // never-existed) → events_replayed=0 → the checker SKIPs (cannot verify),
    // never drift. Assert the bin's zero-events signal against real PG. (148)
    let pc_empty = Uuid::new_v4();
    let out_skip = run_bin(
        &db_url,
        reality_id,
        "pc_projection",
        &[format!("pc:{pc_empty}")],
        Uuid::new_v4(), // a boundary event_id with no matching row → 0 in-bound events
        &format!(r#"{{"pc_id":"{pc_empty}"}}"#),
    );
    assert_eq!(out_skip["status"], "ok", "skip status: {out_skip}");
    assert_eq!(
        out_skip["events_replayed"], 0,
        "no in-bound events → 0 replayed (→ Skippable, not drift): {out_skip}"
    );
    assert_eq!(
        out_skip["found"], false,
        "no row produced from 0 events: {out_skip}"
    );
}
