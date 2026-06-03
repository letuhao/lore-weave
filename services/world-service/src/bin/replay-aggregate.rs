//! `replay-aggregate` — L3.E/F integrity-checker keystone (per-sampled-row WORKER).
//!
//! Re-derives ONE projection row by replaying its owning event aggregate(s) up to
//! the sampled row's boundary event into a TEMP shadow of the target projection
//! table, then prints the row's `to_jsonb - meta_keys` payload as JSON so the Go
//! integrity-checker can byte-compare it against the live projection row.
//!
//! ## Invocation
//!
//! ```text
//!   REALITY_DB_URL=postgres://…             (env — NOT a flag; password off `ps`)
//!   replay-aggregate
//!     --reality-id <uuid>
//!     --projection <table>                  (an L3.A projection table)
//!     --aggregate <type>:<id>               (repeatable — 1 for single-aggregate
//!                                            tables, 2 for npc_session_memory)
//!     --boundary-event-id <uuid>            (replay events ≤ this one, global order)
//!     --pk '<json {col: value, …}>'         (the sampled row's primary key)
//! ```
//!
//! ## Output / exit code
//!
//! Always prints exactly one [`ReplayOutput`] JSON object to **stdout** and exits
//! `0` for any runtime condition the caller should interpret (clean replay, a row
//! that the replay did not produce, a replay error → SKIP, zero in-bound events →
//! SKIP). Exits `2` ONLY for a bad invocation (missing/invalid flags), printing
//! to stderr. This keeps the subprocess contract simple: exit 0 ⇒ parse stdout.
//!
//! See `docs/plans/2026-06-03-l3ef-integrity-checker.md`.

use std::collections::BTreeMap;
use std::sync::Arc;

use dp_kernel::{EventEnvelope, Projection, ProjectionRunner, ProjectionUpdate};
use rebuilder::ProjectionWriter;
use sqlx::postgres::PgPoolOptions;
use sqlx::{PgPool, Row};
use uuid::Uuid;

use world_service::rebuild::all_projections;
use world_service::rebuild::writer::SqlxProjectionWriter;
use world_service::replay_aggregate::{
    OwningAggregate, ReplayOutput, events_query_sql, payload_select_sql, temp_shadow_ddl,
};

fn main() {
    std::process::exit(run());
}

fn run() -> i32 {
    let args: Vec<String> = std::env::args().collect();

    // REALITY_DB_URL is an env (password off `ps`), resolved before parsing so
    // the arg parser stays env-free + unit-testable.
    let db_url = match std::env::var("REALITY_DB_URL") {
        Ok(u) => u,
        Err(_) => {
            eprintln!(
                "[replay-aggregate] invocation error: REALITY_DB_URL env not set (per-reality shard DSN)"
            );
            return 2;
        }
    };

    // ── Parse invocation (errors here are exit 2: a programming/wiring bug) ──
    let inv = match Invocation::parse(&args, db_url) {
        Ok(i) => i,
        Err(e) => {
            eprintln!("[replay-aggregate] invocation error: {e}");
            return 2;
        }
    };

    // Everything after this point is reported via a stdout ReplayOutput (exit 0)
    // so the Go caller can distinguish clean / drift / skip without inspecting
    // the exit code.
    let out = match execute(&inv) {
        Ok(o) => o,
        Err(e) => ReplayOutput::error(e),
    };
    match serde_json::to_string(&out) {
        Ok(s) => {
            println!("{s}");
            0
        }
        Err(e) => {
            eprintln!("[replay-aggregate] fatal: serialize output: {e}");
            2
        }
    }
}

/// Parsed CLI invocation.
struct Invocation {
    reality_id: Uuid,
    projection: String,
    aggregates: Vec<OwningAggregate>,
    boundary_event_id: Uuid,
    /// PK columns (sorted) + their text values, in matching order.
    pk_columns: Vec<String>,
    pk_values: Vec<String>,
    db_url: String,
}

impl Invocation {
    fn parse(args: &[String], db_url: String) -> Result<Self, String> {
        let reality_id_raw =
            flag(args, "--reality-id").ok_or_else(|| "missing --reality-id <uuid>".to_string())?;
        let reality_id = Uuid::parse_str(&reality_id_raw)
            .map_err(|e| format!("invalid --reality-id {reality_id_raw:?}: {e}"))?;

        let projection =
            flag(args, "--projection").ok_or_else(|| "missing --projection <table>".to_string())?;

        let boundary_raw = flag(args, "--boundary-event-id")
            .ok_or_else(|| "missing --boundary-event-id <uuid>".to_string())?;
        let boundary_event_id = Uuid::parse_str(&boundary_raw)
            .map_err(|e| format!("invalid --boundary-event-id {boundary_raw:?}: {e}"))?;

        let aggregate_raws = flags_all(args, "--aggregate");
        if aggregate_raws.is_empty() {
            return Err("missing --aggregate <type>:<id> (at least one required)".into());
        }
        let mut aggregates = Vec::with_capacity(aggregate_raws.len());
        for raw in aggregate_raws {
            let (t, id) = raw
                .split_once(':')
                .ok_or_else(|| format!("invalid --aggregate {raw:?} (want <type>:<id>)"))?;
            if t.is_empty() || id.is_empty() {
                return Err(format!("invalid --aggregate {raw:?} (empty type or id)"));
            }
            aggregates.push(OwningAggregate {
                aggregate_type: t.to_string(),
                aggregate_id: id.to_string(),
            });
        }

        let pk_raw = flag(args, "--pk").ok_or_else(|| "missing --pk <json>".to_string())?;
        let pk_json: serde_json::Value = serde_json::from_str(&pk_raw)
            .map_err(|e| format!("invalid --pk {pk_raw:?} (want a JSON object): {e}"))?;
        let pk_obj = pk_json
            .as_object()
            .ok_or_else(|| "--pk must be a JSON object {col: value, …}".to_string())?;
        if pk_obj.is_empty() {
            return Err("--pk object is empty".into());
        }
        // Sort keys for a stable column↔bind order (the predicate is a conjunction,
        // so order is semantically irrelevant — but determinism aids debugging).
        let sorted: BTreeMap<&String, &serde_json::Value> = pk_obj.iter().collect();
        let mut pk_columns = Vec::with_capacity(sorted.len());
        let mut pk_values = Vec::with_capacity(sorted.len());
        for (col, val) in sorted {
            pk_columns.push(col.clone());
            pk_values.push(json_to_text(val));
        }

        Ok(Self {
            reality_id,
            projection,
            aggregates,
            boundary_event_id,
            pk_columns,
            pk_values,
            db_url,
        })
    }
}

/// Connect, build the temp shadow, replay the bounded aggregate set, and select
/// the row. Returns a ReplayOutput; any infra/replay failure is an `Err(String)`
/// that the caller turns into a `status:"error"` (SKIP) output.
fn execute(inv: &Invocation) -> Result<ReplayOutput, String> {
    // Single-CONNECTION (not single-thread): temp tables are connection-local, so
    // the CREATE TEMP, the writer's per-batch transactions, and the final SELECT
    // MUST all run on the SAME physical connection. A `max_connections(1)` pool
    // guarantees that (every acquire returns the one connection; sqlx does not
    // reset the session on release) — that affinity is a property of the POOL,
    // independent of the runtime flavor.
    //
    // The runtime MUST be MULTI-thread: the reused `SqlxProjectionWriter` is a
    // sync `ProjectionWriter`, so `apply_batch` bridges to async sqlx via
    // `Handle::block_on` on this runtime's handle. On a `current_thread` runtime
    // the IO driver is ticked ONLY inside `Runtime::block_on`, so a
    // `Handle::block_on` future that awaits socket readiness never wakes →
    // deadlock (surfaced by the 147 live-smoke; matches the rebuilder bin's
    // "Handle::block_on is sound only across runtimes" note). A multi-thread
    // runtime drives the IO driver on its own thread, so the writer's
    // `Handle::block_on` makes progress while the main thread blocks.
    let db_rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(1)
        .enable_all()
        .build()
        .map_err(|e| format!("runtime: {e}"))?;

    let pool = db_rt
        .block_on(PgPoolOptions::new().max_connections(1).connect(&inv.db_url))
        .map_err(|e| format!("reality DB connect: {e}"))?;
    let pool = Arc::new(pool);

    // Temp shadow of the target projection table (validated allowlist + safe
    // interpolation inside temp_shadow_ddl).
    let ddl = temp_shadow_ddl(&inv.projection)?;
    db_rt
        .block_on(async { sqlx::query(&ddl).execute(&*pool).await })
        .map_err(|e| format!("create temp shadow: {e}"))?;

    // Read the bounded, global-ordered event stream for the requested aggregates.
    let events = db_rt
        .block_on(read_events(&pool, inv))
        .map_err(|e| format!("read events: {e}"))?;
    let events_replayed = events.len() as u64;

    // Replay through the projections into the temp shadow (writer targets the
    // projection table BY NAME → pg_temp shadow). One ordered batch in one TX.
    if events_replayed > 0 {
        let projections = all_projections();
        let mut runner = ProjectionRunner::new();
        for p in &projections {
            runner = runner.with_projection(*p as &dyn Projection);
        }
        let mut updates: Vec<ProjectionUpdate> = Vec::new();
        for env in &events {
            updates.extend(runner.apply_one(env));
        }
        let writer = SqlxProjectionWriter::new(
            pool.clone(),
            db_rt.handle().clone(),
            inv.projection.clone(),
        )?;
        writer.apply_batch(&updates)?;
    }

    // Select the replayed row's canonical payload (or none → found:false).
    let payload = db_rt
        .block_on(select_payload(&pool, inv))
        .map_err(|e| format!("select payload: {e}"))?;

    Ok(ReplayOutput {
        found: payload.is_some(),
        events_replayed,
        status: "ok".into(),
        payload,
        error: None,
    })
}

/// `SELECT … FROM events WHERE reality_id=$1 AND (type,id) IN (…) AND
/// (recorded_at,event_id) <= (boundary) ORDER BY recorded_at, event_id`.
async fn read_events(pool: &PgPool, inv: &Invocation) -> Result<Vec<EventEnvelope>, sqlx::Error> {
    let sql = events_query_sql(inv.aggregates.len()).map_err(|e| sqlx::Error::Protocol(e))?;
    let mut q = sqlx::query(&sql)
        .bind(inv.reality_id)
        .bind(inv.boundary_event_id);
    for a in &inv.aggregates {
        q = q.bind(&a.aggregate_type).bind(&a.aggregate_id);
    }
    let rows = q.fetch_all(pool).await?;
    let mut out = Vec::with_capacity(rows.len());
    for row in rows {
        out.push(EventEnvelope {
            event_id: row.try_get("event_id")?,
            event_type: row.try_get("event_type")?,
            event_version: row.try_get::<i32, _>("event_version")? as u32,
            aggregate_id: row.try_get("aggregate_id")?,
            aggregate_type: row.try_get("aggregate_type")?,
            aggregate_version: row.try_get::<i64, _>("aggregate_version")? as u64,
            reality_id: row.try_get("reality_id")?,
            occurred_at: row.try_get("occurred_at")?,
            recorded_at: row.try_get("recorded_at")?,
            payload: row.try_get("payload")?,
            metadata: row.try_get("metadata")?,
        });
    }
    Ok(out)
}

/// Select the temp-shadow row at the requested PK, as `to_jsonb - meta_keys`.
async fn select_payload(
    pool: &PgPool,
    inv: &Invocation,
) -> Result<Option<serde_json::Value>, sqlx::Error> {
    let cols: Vec<&str> = inv.pk_columns.iter().map(String::as_str).collect();
    let sql = payload_select_sql(&inv.projection, &cols).map_err(sqlx::Error::Protocol)?;
    let mut q = sqlx::query(&sql);
    for v in &inv.pk_values {
        q = q.bind(v);
    }
    match q.fetch_optional(pool).await? {
        Some(row) => Ok(Some(row.try_get::<serde_json::Value, _>("payload")?)),
        None => Ok(None),
    }
}

/// Canonical text form of a JSON PK value (strings unquoted; everything else via
/// its JSON text). All L3.A pk columns are UUID/TEXT, so values arrive as strings.
fn json_to_text(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

/// Return the value following the FIRST occurrence of `--name`.
fn flag(args: &[String], name: &str) -> Option<String> {
    args.iter()
        .position(|a| a == name)
        .and_then(|i| args.get(i + 1).cloned())
}

/// Return the values following EVERY occurrence of `--name` (repeatable flag).
fn flags_all(args: &[String], name: &str) -> Vec<String> {
    let mut out = Vec::new();
    for (i, a) in args.iter().enumerate() {
        if a == name {
            if let Some(v) = args.get(i + 1) {
                out.push(v.clone());
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn argv(parts: &[&str]) -> Vec<String> {
        parts.iter().map(|s| s.to_string()).collect()
    }

    fn base_args() -> Vec<String> {
        argv(&[
            "replay-aggregate",
            "--reality-id",
            "00000000-0000-0000-0000-000000000001",
            "--projection",
            "pc_inventory_projection",
            "--boundary-event-id",
            "00000000-0000-0000-0000-0000000000aa",
        ])
    }

    #[test]
    fn parse_single_aggregate_and_sorted_composite_pk() {
        let mut args = base_args();
        args.extend(argv(&["--aggregate", "pc:pc-1"]));
        // PK given out of order → parse sorts columns (item_code < pc_id).
        args.extend(argv(&["--pk", r#"{"pc_id":"pc-1","item_code":"sword"}"#]));

        let inv = Invocation::parse(&args, "postgres://x".into()).unwrap();
        assert_eq!(inv.aggregates.len(), 1);
        assert_eq!(inv.aggregates[0].aggregate_type, "pc");
        assert_eq!(inv.aggregates[0].aggregate_id, "pc-1");
        // sorted: item_code, pc_id — and values track the columns.
        assert_eq!(inv.pk_columns, vec!["item_code", "pc_id"]);
        assert_eq!(inv.pk_values, vec!["sword", "pc-1"]);
        assert_eq!(inv.projection, "pc_inventory_projection");
    }

    #[test]
    fn parse_repeatable_aggregate_for_cross_aggregate_table() {
        let mut args = base_args();
        args.extend(argv(&[
            "--aggregate",
            "session:s-9",
            "--aggregate",
            "npc:n-3",
        ]));
        args.extend(argv(&["--pk", r#"{"npc_id":"n-3","session_id":"s-9"}"#]));
        let inv = Invocation::parse(&args, "postgres://x".into()).unwrap();
        assert_eq!(inv.aggregates.len(), 2);
        assert_eq!(inv.aggregates[0].aggregate_id, "s-9");
        assert_eq!(inv.aggregates[1].aggregate_type, "npc");
    }

    #[test]
    fn parse_rejects_bad_aggregate_and_missing_pk() {
        let mut bad_agg = base_args();
        bad_agg.extend(argv(&[
            "--aggregate",
            "no-colon",
            "--pk",
            r#"{"pc_id":"x"}"#,
        ]));
        assert!(Invocation::parse(&bad_agg, "u".into()).is_err());

        let mut no_agg = base_args();
        no_agg.extend(argv(&["--pk", r#"{"pc_id":"x"}"#]));
        assert!(Invocation::parse(&no_agg, "u".into()).is_err());

        let mut bad_pk = base_args();
        bad_pk.extend(argv(&["--aggregate", "pc:x", "--pk", "not-json"]));
        assert!(Invocation::parse(&bad_pk, "u".into()).is_err());

        let mut empty_pk = base_args();
        empty_pk.extend(argv(&["--aggregate", "pc:x", "--pk", "{}"]));
        assert!(Invocation::parse(&empty_pk, "u".into()).is_err());
    }

    #[test]
    fn parse_rejects_bad_uuids() {
        let mut args = argv(&[
            "replay-aggregate",
            "--reality-id",
            "not-a-uuid",
            "--projection",
            "pc_projection",
            "--boundary-event-id",
            "00000000-0000-0000-0000-0000000000aa",
            "--aggregate",
            "pc:x",
            "--pk",
            r#"{"pc_id":"x"}"#,
        ]);
        assert!(Invocation::parse(&args, "u".into()).is_err());
        // also bad boundary
        args[4] = "pc_projection".into();
        args[2] = "00000000-0000-0000-0000-000000000001".into();
        args[6] = "nope".into();
        assert!(Invocation::parse(&args, "u".into()).is_err());
    }

    #[test]
    fn json_to_text_unquotes_strings_only() {
        assert_eq!(json_to_text(&serde_json::json!("abc")), "abc");
        assert_eq!(json_to_text(&serde_json::json!(42)), "42");
        assert_eq!(json_to_text(&serde_json::json!(true)), "true");
    }

    #[test]
    fn flags_all_collects_every_occurrence() {
        let args = argv(&["bin", "--x", "a", "--y", "z", "--x", "b"]);
        assert_eq!(flags_all(&args, "--x"), vec!["a", "b"]);
        assert_eq!(flag(&args, "--y"), Some("z".to_string()));
        assert_eq!(flag(&args, "--missing"), None);
    }
}
