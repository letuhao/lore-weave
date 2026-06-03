//! `rebuilder` — 073 (L3.G/H) per-reality projection rebuild WORKER.
//!
//! The binary the admin-cli `reality rebuild-projection` / `catastrophic-rebuild`
//! commands invoke per reality (Q-L3-3). It freeze-rebuilds ONE projection table:
//! the caller (admin-cli) freezes the reality + TRUNCATEs the target table, then
//! execs this binary, which replays the per-reality `events` log through the L3.B
//! projection crates back into the empty table. On success the caller thaws.
//!
//! ## Invocation
//!
//! ```text
//!   REALITY_DB_URL=postgres://…   (env — NOT a flag; keeps the password off `ps`)
//!   rebuilder --reality-id <uuid> --projection <table>
//!             [--parallel-workers N] [--batch-size N]
//! ```
//!
//! Optional env: `REBUILD_PARALLEL_WORKERS`, `REBUILD_BATCH_SIZE` (flags win).
//!
//! ## Output / exit code
//!
//! Prints one JSON [`world_service::rebuild::RebuildStats`] object to **stdout**
//! (the Go invoker parses it). Exit `0` iff `aggregates_failed == 0`; otherwise
//! exit `1` so the caller LEAVES THE REALITY FROZEN and an operator inspects the
//! dead letter before any manual thaw (R02 §12B.2 fail-loud).
//!
//! ## Status
//!
//! FIRST live projection-apply path; correctness against real events is validated
//! by the not-yet-built L3.E/F integrity checker, so the admin-cli commands that
//! drive this stay gated behind `ADMIN_CLI_ENABLE_UNPROVEN_REBUILD`. See
//! `docs/plans/2026-06-03-073-destructive-admin-commands.md`.

use std::sync::Arc;

use rebuilder::{
    InMemoryCheckpointStore, InMemoryDeadLetterStore, ParallelRebuilder, RebuildConfig, RebuildPlan,
};
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

use world_service::rebuild::event_source::{SqlxEventSource, enumerate_aggregates};
use world_service::rebuild::writer::SqlxProjectionWriter;
use world_service::rebuild::{RebuildStats, all_projections};

fn main() {
    std::process::exit(match run() {
        Ok(code) => code,
        Err(e) => {
            eprintln!("[rebuilder] fatal: {e}");
            2
        }
    });
}

fn run() -> Result<i32, String> {
    let args: Vec<String> = std::env::args().collect();

    let reality_id_raw =
        flag(&args, "--reality-id").ok_or_else(|| "missing --reality-id <uuid>".to_string())?;
    let reality_id = Uuid::parse_str(&reality_id_raw)
        .map_err(|e| format!("invalid --reality-id {reality_id_raw:?}: {e}"))?;
    let projection = flag(&args, "--projection").ok_or_else(|| {
        "missing --projection <table> (one of the L3.A projection tables)".to_string()
    })?;

    let db_url = std::env::var("REALITY_DB_URL")
        .map_err(|_| "REALITY_DB_URL env not set (per-reality shard DSN)".to_string())?;

    let mut config = RebuildConfig::default();
    if let Some(n) =
        flag(&args, "--parallel-workers").or_else(|| env_opt("REBUILD_PARALLEL_WORKERS"))
    {
        config.parallel_workers = parse_usize(&n, "parallel-workers")?;
    }
    if let Some(n) = flag(&args, "--batch-size").or_else(|| env_opt("REBUILD_BATCH_SIZE")) {
        config.batch_size = parse_u64(&n, "batch-size")?;
    }

    // Two runtimes (see rebuild::event_source docs): db_rt drives all sqlx; the
    // orchestration runtime drives ParallelRebuilder::run, whose spawn_blocking
    // workers re-enter db_rt via Handle::block_on (sound only across runtimes).
    let db_rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(4)
        .enable_all()
        .build()
        .map_err(|e| format!("db runtime: {e}"))?;

    let pool = db_rt
        .block_on(async {
            PgPoolOptions::new()
                .max_connections((config.parallel_workers as u32).max(2) + 1)
                .connect(&db_url)
                .await
        })
        .map_err(|e| format!("reality DB connect: {e}"))?;
    let pool = Arc::new(pool);

    let aggregates = db_rt
        .block_on(enumerate_aggregates(&pool, reality_id))
        .map_err(|e| format!("enumerate aggregates: {e}"))?;

    // Validate the target table up front (also done in SqlxProjectionWriter::new).
    let writer = Arc::new(SqlxProjectionWriter::new(
        pool.clone(),
        db_rt.handle().clone(),
        projection.clone(),
    )?);
    let event_source = Arc::new(SqlxEventSource::new(
        pool.clone(),
        db_rt.handle().clone(),
        reality_id,
    ));

    if aggregates.is_empty() {
        // Empty event log ⇒ empty projection is correct; nothing to replay.
        let stats = RebuildStats::default();
        println!(
            "{}",
            serde_json::to_string(&stats).map_err(|e| e.to_string())?
        );
        eprintln!(
            "[rebuilder] reality {reality_id} has no events — projection {projection} left empty"
        );
        return Ok(0);
    }

    let rebuilder = ParallelRebuilder::new(
        config,
        event_source,
        all_projections(),
        writer,
        Arc::new(InMemoryCheckpointStore::default()),
        Arc::new(InMemoryDeadLetterStore::default()),
    )
    .map_err(|e| format!("rebuilder setup: {e:?}"))?;

    let plan = RebuildPlan {
        reality_id,
        aggregates,
        projection_name: projection.clone(),
    };

    let orch_rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .map_err(|e| format!("orchestration runtime: {e}"))?;
    let outcomes = orch_rt.block_on(rebuilder.run(plan));

    let stats = RebuildStats::from_outcomes(&outcomes);
    println!(
        "{}",
        serde_json::to_string(&stats).map_err(|e| e.to_string())?
    );
    eprintln!(
        "[rebuilder] reality={reality_id} projection={projection} rebuilt={} skipped={} failed={} events={} updates={}",
        stats.aggregates_rebuilt,
        stats.aggregates_skipped,
        stats.aggregates_failed,
        stats.events_replayed,
        stats.updates_applied
    );

    // Fail-loud: any dead-lettered aggregate ⇒ exit non-zero so the caller
    // keeps the reality FROZEN and an operator inspects the dead letter.
    Ok(if stats.aggregates_failed == 0 { 0 } else { 1 })
}

/// Return the value following `--name`, if present.
fn flag(args: &[String], name: &str) -> Option<String> {
    args.iter()
        .position(|a| a == name)
        .and_then(|i| args.get(i + 1).cloned())
}

fn env_opt(key: &str) -> Option<String> {
    std::env::var(key).ok().filter(|s| !s.trim().is_empty())
}

fn parse_usize(s: &str, what: &str) -> Result<usize, String> {
    s.trim()
        .parse()
        .map_err(|e| format!("invalid --{what} {s:?}: {e}"))
}

fn parse_u64(s: &str, what: &str) -> Result<u64, String> {
    s.trim()
        .parse()
        .map_err(|e| format!("invalid --{what} {s:?}: {e}"))
}
