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
//!
//! **Retargeted twice on 2026-08-05.** All five cases ran against `pc_projection`
//! / `npc_session_memory_projection` until `0017` deleted those projectors, which
//! left the smoke BROKEN, not merely stale — measured against a real DB it failed
//! at setup with `unknown projection table "pc_projection"`, and the env-var gate
//! meant nobody saw it. They moved to `region_projection` / `session_participants`,
//! and then the orphan gate learned to read `#[cfg(test)]` modules and showed that
//! those had no producer either. `0018` removed them; the fixtures now sit on
//! `canon_projection`, the only projection anything writes.
//!
//! **One property was LOST rather than moved, and is recorded here:** case 3 used
//! to exercise a COMPOSITE primary key. `session_participants` was the last
//! multi-column PK in the schema and `canon_projection`'s is a single column, so
//! there is nothing left to carry that half. The multi-aggregate IN-list and the
//! global ordering — case 3's other two properties — do survive.

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

/// Build an envelope. `recorded_at` starts as a placeholder and [`seed_events`]
/// OVERWRITES it with the value the DB actually stored.
///
/// This comment used to say the placeholder was harmless — *"META keys are
/// stripped on BOTH sides before comparison, so its value never reaches the
/// compared payload."* That was true of every projector the harness had ever run,
/// and false in general: `canon` writes `recorded_at` into `last_synced_at`, an
/// ordinary compared column. The claim was not wrong when written; it was
/// UNGUARDED, and it silently stopped being true.
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
        ruleset_digest: None,
    }
}

/// INSERT the events in global order. `recorded_at` (the partition key) is set
/// to `date_trunc('month', now()) + idx s` so every row lands in the single
/// current-month partition `0002` creates AND the `(recorded_at, event_id)`
/// global order equals the slice order — so the bin's `ORDER BY recorded_at,
/// event_id` replays them in exactly the order they appear here.
///
/// **It writes the STORED `recorded_at` back into the envelope**, rendered by the
/// same `to_char` the real event source uses. That is not bookkeeping. The harness
/// assumed `recorded_at` only ever reaches a META key (`applied_at`), which both
/// sides strip before comparing — true of every projector it was written against.
/// `canon` breaks the assumption: `last_synced_at` is an ordinary compared column
/// derived from `recorded_at`. The in-process side read the envelope's value and
/// the bin read the DB's, so a CLEAN row failed its own byte-match on a field
/// neither side had got wrong. Measured 2026-08-05, the first time this harness
/// met a projector that puts `recorded_at` in a real column.
async fn seed_events(pool: &PgPool, events: &mut [EventEnvelope]) {
    for (idx, e) in events.iter_mut().enumerate() {
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

        // Same rendering as `rebuild::event_source::EVENT_COLUMNS`, so the two
        // sides of the byte-compare agree on the string, not merely the instant.
        let stored: String = sqlx::query_scalar(
            "SELECT to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') \
               FROM events WHERE event_id = $1",
        )
        .bind(e.event_id)
        .fetch_one(pool)
        .await
        .unwrap_or_else(|err| panic!("read back recorded_at for {}: {err}", e.event_id));
        e.recorded_at = stored;
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
    // 0009 creates canon_projection — the only projection left after `0018`,
    // and it was never in 0006.
    rt.block_on(apply(
        &pool,
        "contracts/migrations/per_reality/0009_canon_projection.up.sql",
    ));

    let reality_id = Uuid::new_v4();

    // ══ Case 1 — canon, single-aggregate, CLEAN ═════════════════════════════
    let canon_id = Uuid::new_v4();
    let book_id = Uuid::new_v4();
    let created = Uuid::new_v4();
    let updated = Uuid::new_v4();
    let mut canon_events = vec![
        mk(
            created,
            "canon.entry.created",
            "canon",
            &canon_id.to_string(),
            1,
            reality_id,
            "2026-06-15T12:00:00Z",
            json!({
                "canon_entry_id": canon_id.to_string(),
                "book_id": book_id.to_string(),
                "attribute_path": "characters/aria/race",
                "value": "elf",
                "canon_layer": "L2_seeded",
                "lock_level": "soft",
            }),
        ),
        mk(
            updated,
            "canon.entry.updated",
            "canon",
            &canon_id.to_string(),
            2,
            reality_id,
            "2026-06-15T12:05:00Z",
            json!({
                "canon_entry_id": canon_id.to_string(),
                "new_value": "high elf",
                "canon_layer": "L2_seeded",
            }),
        ),
    ];
    rt.block_on(seed_events(&pool, &mut canon_events));
    apply_live(&rt, pool.clone(), "canon_projection", &canon_events);

    let canon_agg = vec![format!("canon:{canon_id}")];
    let canon_pk = format!(r#"{{"canon_entry_id":"{canon_id}"}}"#);
    let out = run_bin(
        &db_url,
        reality_id,
        "canon_projection",
        &canon_agg,
        updated,
        &canon_pk,
    );
    assert_eq!(out["status"], "ok", "canon replay status: {out}");
    assert_eq!(out["found"], true, "canon replay found a row: {out}");
    assert_eq!(out["events_replayed"], 2, "canon replayed both events: {out}");

    let live = rt
        .block_on(live_payload(
            &pool,
            "canon_projection",
            &[("canon_entry_id", canon_id)],
        ))
        .expect("live canon row exists");
    assert_eq!(
        out["payload"], live,
        "CLEAN: replayed canon payload must byte-match the live row\nreplay: {}\nlive:   {}",
        out["payload"], live
    );
    // Spot-check the value the second event wrote landed (replay applied the change).
    assert_eq!(live["value"], json!("high elf"));
    assert_eq!(live["attribute_path"], json!("characters/aria/race"));

    // ══ Case 2 — canon DRIFT detection ═══════════════════════════════════════
    // Tamper the live row; the replay is unaffected, so the byte-compare must
    // now DIFFER (the checker catches drift, not a rubber-stamp).
    rt.block_on(async {
        sqlx::query(
            "UPDATE canon_projection SET attribute_path = 'Tampered' \
              WHERE canon_entry_id = $1",
        )
        .bind(canon_id)
        .execute(&*pool)
        .await
        .expect("tamper canon row");
    });
    let out_drift = run_bin(
        &db_url,
        reality_id,
        "canon_projection",
        &canon_agg,
        updated,
        &canon_pk,
    );
    let live_drift = rt
        .block_on(live_payload(
            &pool,
            "canon_projection",
            &[("canon_entry_id", canon_id)],
        ))
        .expect("tampered canon row exists");
    assert_ne!(
        out_drift["payload"], live_drift,
        "DRIFT: tampered live row must NOT match the replay"
    );
    assert_eq!(
        out_drift["payload"]["attribute_path"],
        json!("characters/aria/race"),
        "replay holds the correct attribute_path"
    );
    assert_eq!(
        live_drift["attribute_path"],
        json!("Tampered"),
        "live row holds the tampered attribute_path"
    );

    // ══ Case 3 — multi-aggregate invocation, CLEAN ═══════════════════════════
    // **The composite-PK half of this case is GONE, not moved.**
    // `session_participants` was the last multi-column PK in the schema and `0018`
    // removed it; `canon_projection`'s PK is one column. The remaining properties
    // — the 2-pair IN-list and global ordering across aggregates — are intact.
    // canon_projection built from canon.entry.* events (Insert→Update), with a
    // SECOND canon aggregate's event interleaved by recorded_at. That event
    // contributes no update to the QUERIED row — its purpose is to exercise the
    // 2-pair `IN`-list events query + global ordering across aggregates against
    // real PG. Also proves the writer-Insert fix: the Insert row omits the NOT NULL
    // `applied_at` (→ DEFAULT), where it used to omit `summary`/`facts`.
    let canon_x = Uuid::new_v4();
    let canon_y = Uuid::new_v4();
    let (x_created, y_created, x_promoted) =
        (Uuid::new_v4(), Uuid::new_v4(), Uuid::new_v4());
    let mut sess_events = vec![
        mk(
            x_created,
            "canon.entry.created",
            "canon",
            &canon_x.to_string(),
            1,
            reality_id,
            "2026-06-15T14:00:00Z",
            json!({
                "canon_entry_id": canon_x.to_string(),
                "book_id": Uuid::new_v4().to_string(),
                "attribute_path": "regions/vault/climate",
                "value": "cold",
                "canon_layer": "L2_seeded",
            }),
        ),
        mk(
            y_created,
            "canon.entry.created",
            "canon",
            &canon_y.to_string(),
            1,
            reality_id,
            "2026-06-15T14:01:00Z",
            json!({
                "canon_entry_id": canon_y.to_string(),
                "book_id": Uuid::new_v4().to_string(),
                "attribute_path": "regions/other/climate",
                "value": "warm",
                "canon_layer": "L2_seeded",
            }),
        ),
        mk(
            x_promoted,
            "canon.entry.promoted",
            "canon",
            &canon_x.to_string(),
            2,
            reality_id,
            "2026-06-15T14:30:00Z",
            json!({
                "canon_entry_id": canon_x.to_string(),
                "to_layer": "L1_axiom",
            }),
        ),
    ];
    rt.block_on(seed_events(&pool, &mut sess_events));
    apply_live(&rt, pool.clone(), "canon_projection", &sess_events);

    let sess_aggs = vec![format!("canon:{canon_x}"), format!("canon:{canon_y}")];
    let sess_pk = format!(r#"{{"canon_entry_id":"{canon_x}"}}"#);
    let out_sess = run_bin(
        &db_url,
        reality_id,
        "canon_projection",
        &sess_aggs,
        x_promoted,
        &sess_pk,
    );
    assert_eq!(out_sess["status"], "ok", "canon replay status: {out_sess}");
    assert_eq!(out_sess["found"], true, "canon replay found a row: {out_sess}");
    // All 3 events are in-bound for the 2-aggregate query (the second aggregate's
    // create included, even though it writes a different ROW) — the IN-list breadth.
    assert_eq!(
        out_sess["events_replayed"], 3,
        "all 3 events replayed: {out_sess}"
    );

    let live_sess = rt
        .block_on(live_payload(
            &pool,
            "canon_projection",
            &[("canon_entry_id", canon_x)],
        ))
        .expect("live canon row exists");
    assert_eq!(
        out_sess["payload"], live_sess,
        "CLEAN: replayed canon payload must byte-match the live row\nreplay: {}\nlive:   {}",
        out_sess["payload"], live_sess
    );
    // The promoted Update landed on top of the created Insert, and the
    // writer-Insert fix let the OMITTED NOT NULL `applied_at` take its DEFAULT (the
    // bug 147 surfaced). `applied_at` is a META key, stripped from the compared
    // payload — so its survival is proved by the Insert having succeeded at all.
    assert_eq!(live_sess["canon_layer"], json!("L1_axiom"));
    assert_eq!(live_sess["value"], json!("cold"));

    // ══ Case 4 — ORPHAN DRIFT verdict: replay ran (events>0) but produced NO row
    // at the queried PK. The Go checker marks this DRIFT (a live projection row
    // the events do not produce); here we assert the BIN's signal end-to-end
    // against real PG: status=ok, found=false, events_replayed>0. (148)
    let canon_c = Uuid::new_v4();
    let created_c = Uuid::new_v4();
    let canon_foreign = Uuid::new_v4(); // a PK the replay never writes
    let mut orphan_events = vec![mk(
        created_c,
        "canon.entry.created",
        "canon",
        &canon_c.to_string(),
        1,
        reality_id,
        "2026-06-15T18:00:00Z",
        json!({
            "canon_entry_id": canon_c.to_string(),
            "book_id": Uuid::new_v4().to_string(),
            "attribute_path": "ghosts/one/kind",
            "value": "ghost",
            "canon_layer": "L2_seeded",
        }),
    )];
    rt.block_on(seed_events(&pool, &mut orphan_events));
    let out_orphan = run_bin(
        &db_url,
        reality_id,
        "canon_projection",
        &[format!("canon:{canon_c}")],
        created_c,
        &format!(r#"{{"canon_entry_id":"{canon_foreign}"}}"#),
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
        "the canon aggregate's event WAS replayed (events>0 distinguishes DRIFT from SKIP): {out_orphan}"
    );

    // ══ Case 5 — SKIP verdict: the aggregate has NO in-bound events (pruned /
    // never-existed) → events_replayed=0 → the checker SKIPs (cannot verify),
    // never drift. Assert the bin's zero-events signal against real PG. (148)
    let canon_empty = Uuid::new_v4();
    let out_skip = run_bin(
        &db_url,
        reality_id,
        "canon_projection",
        &[format!("canon:{canon_empty}")],
        Uuid::new_v4(), // a boundary event_id with no matching row → 0 in-bound events
        &format!(r#"{{"canon_entry_id":"{canon_empty}"}}"#),
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
