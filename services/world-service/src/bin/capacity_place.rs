//! `capacity-place` — W1.1 live drill for the capacity routing glue.
//!
//! Exercises `world_service::capacity_glue` against REAL Postgres (the S12/S13
//! scale rig's meta-pg). Proves provision-time over-subscription enforcement is
//! non-vacuous via the lock-on / lock-off contrast:
//!
//!   -mode snapshot    print the live capacity snapshot (shard_utilization caps
//!                     × reality_registry live count).
//!   -mode concurrent  K parallel placements onto a shard with M<K free slots,
//!                     advisory lock ON → EXACTLY M succeed, K−M refused, final
//!                     reality_registry count == M (never over).
//!   -mode bite        the SAME race with the advisory lock OFF → MORE than M
//!                     register (over-subscription) → final count > M. Proves
//!                     the lock+recount is the enforcer (without it, the TOCTOU
//!                     over-subscribes). NOTRUN if the race happened to
//!                     serialize (==M) — re-run.
//!   -mode smoke       concurrent then bite (the full contrast).
//!
//! Verdict: 0 PASS · 1 FAIL (enforcement leaked, or a vacuous bite) · 2 NOTRUN
//! (setup / race-missed). Re-runnable: it resets reality_registry + reseeds the
//! shard cap each run.

use std::process::ExitCode;

use sqlx::postgres::{PgPool, PgPoolOptions};
use uuid::Uuid;

use world_service::capacity_glue::{live_snapshot, place_reality};
use world_service::capacity_planner::{CapacityPlanner, CapacityThresholds};
use world_service::errors::ProvisionerError;

/// Single registered shard for the drill. `.internal` so the row satisfies BOTH
/// `shard_utilization` and the stricter `reality_registry` db_host CHECK.
const SHARD: &str = "pg-shard-0.internal";
/// Free slots on the shard (`capacity_max_dbs`). M.
const CAP: i32 = 5;
/// Concurrent placement attempts. K > M so the contention is real.
const K: usize = 12;

#[tokio::main]
async fn main() -> ExitCode {
    let mut dsn = std::env::var("CAP_META_DB_URL").unwrap_or_default();
    let mut mode = "smoke".to_string();
    let args: Vec<String> = std::env::args().collect();
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "-dsn" => {
                i += 1;
                dsn = args.get(i).cloned().unwrap_or_default();
            }
            "-mode" => {
                i += 1;
                mode = args.get(i).cloned().unwrap_or_default();
            }
            other => {
                eprintln!("capacity-place: unknown arg {other}");
                return ExitCode::from(2);
            }
        }
        i += 1;
    }
    if dsn.is_empty() {
        eprintln!("capacity-place: -dsn or CAP_META_DB_URL required");
        return ExitCode::from(2);
    }

    match run(&dsn, &mode).await {
        Ok(code) => code,
        Err(e) => {
            eprintln!("capacity-place: NOTRUN(setup): {e}");
            ExitCode::from(2)
        }
    }
}

async fn run(dsn: &str, mode: &str) -> Result<ExitCode, String> {
    // Generous pool: in lock-on mode all K tasks each hold a connection while
    // blocked on the per-shard advisory lock, plus the lock holder's register.
    let pool = PgPoolOptions::new()
        .max_connections(40)
        .connect(dsn)
        .await
        .map_err(|e| format!("connect: {e}"))?;

    match mode {
        "snapshot" => {
            reset(&pool).await?;
            let snap = live_snapshot(&pool)
                .await
                .map_err(|e| format!("live_snapshot: {e}"))?;
            println!("snapshot: {snap:?}");
            Ok(ExitCode::SUCCESS)
        }
        "concurrent" => cmd_concurrent(&pool).await,
        "bite" => cmd_bite(&pool).await,
        "smoke" => {
            let a = cmd_concurrent(&pool).await?;
            if a != ExitCode::SUCCESS {
                return Ok(a);
            }
            cmd_bite(&pool).await
        }
        other => {
            eprintln!("capacity-place: unknown mode {other}");
            Ok(ExitCode::from(2))
        }
    }
}

/// Lock ON → exactly M succeed, final count == M.
async fn cmd_concurrent(pool: &PgPool) -> Result<ExitCode, String> {
    reset(pool).await?;
    let (ok, refused, other) = race(pool, true).await?;
    let total = count_realities(pool).await?;
    println!(
        "[concurrent lock=ON] attempts={K} cap={CAP} succeeded={ok} refused={refused} infra_err={other} final_count={total}"
    );
    if other > 0 {
        eprintln!("NOTRUN(concurrent): {other} infra errors — re-run");
        return Ok(ExitCode::from(2));
    }
    if total as i32 > CAP || ok as i32 > CAP {
        eprintln!(
            "FAIL(concurrent): over-subscription LEAKED — {ok} succeeded / {total} rows on a {CAP}-slot shard with the lock ON"
        );
        return Ok(ExitCode::from(1));
    }
    if total as i32 != CAP || ok as i32 != CAP {
        // Under-fill would mean the gate is too tight (refused a free slot).
        eprintln!(
            "FAIL(concurrent): expected exactly {CAP} placements, got succeeded={ok} final_count={total}"
        );
        return Ok(ExitCode::from(1));
    }
    println!("PASS(concurrent): exactly {CAP} of {K} placements succeeded — the advisory lock + recount prevents over-subscription");
    Ok(ExitCode::SUCCESS)
}

/// Lock OFF → the TOCTOU over-subscribes: final count > M.
async fn cmd_bite(pool: &PgPool) -> Result<ExitCode, String> {
    reset(pool).await?;
    let (ok, refused, other) = race(pool, false).await?;
    let total = count_realities(pool).await?;
    println!(
        "[bite lock=OFF] attempts={K} cap={CAP} succeeded={ok} refused={refused} infra_err={other} final_count={total}"
    );
    if other > 0 {
        eprintln!("NOTRUN(bite): {other} infra errors — re-run");
        return Ok(ExitCode::from(2));
    }
    if total as i32 <= CAP {
        // The race serialized — no over-subscription this run. Not a failure of
        // the system (it just didn't reproduce); ask for a re-run rather than
        // declaring the bite vacuous.
        eprintln!(
            "NOTRUN(bite): lock OFF produced only {total} rows (<= cap {CAP}) — the race serialized this run; re-run to reproduce the over-subscription"
        );
        return Ok(ExitCode::from(2));
    }
    println!(
        "PASS(bite): with the lock OFF, {total} realities registered onto a {CAP}-slot shard (> cap) — over-subscription reproduced, so the lock is the enforcer (non-vacuous)"
    );
    Ok(ExitCode::SUCCESS)
}

/// Spawn K concurrent placements; return (succeeded, refused, infra_err).
async fn race(pool: &PgPool, lock_enabled: bool) -> Result<(usize, usize, usize), String> {
    let mut handles = Vec::with_capacity(K);
    for _ in 0..K {
        let pool = pool.clone();
        handles.push(tokio::spawn(async move {
            let planner = CapacityPlanner::new(CapacityThresholds::default());
            let rid = Uuid::new_v4();
            let reg_pool = pool.clone();
            place_reality(&pool, &planner, lock_enabled, move |shard| {
                let pool = reg_pool;
                let shard = shard.as_str().to_string();
                async move { register_insert(&pool, rid, &shard).await }
            })
            .await
        }));
    }
    let (mut ok, mut refused, mut other) = (0usize, 0usize, 0usize);
    for h in handles {
        match h.await {
            Ok(Ok(_)) => ok += 1,
            Ok(Err(ProvisionerError::NoShardCapacity)) => refused += 1,
            Ok(Err(e)) => {
                eprintln!("  placement error: {e}");
                other += 1;
            }
            Err(e) => {
                eprintln!("  task join error: {e}");
                other += 1;
            }
        }
    }
    Ok((ok, refused, other))
}

/// The `register` callback — a direct reservation INSERT. In production W1.5
/// routes this through the Go meta-write bridge (so the I8 meta_write_audit row
/// lands); here it stands in to exercise the placement race only.
async fn register_insert(pool: &PgPool, rid: Uuid, shard: &str) -> Result<(), ProvisionerError> {
    let db_name = format!("lw_reality_{}", &rid.simple().to_string()[..12]);
    sqlx::query(
        r#"INSERT INTO reality_registry
             (reality_id, db_host, db_name, status, locale,
              session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
           VALUES ($1, $2, $3, 'provisioning', 'en', 10, 10, 20, 0)"#,
    )
    .bind(rid)
    .bind(shard)
    .bind(&db_name)
    .execute(pool)
    .await
    .map_err(|e| ProvisionerError::BadCapacity(format!("register insert: {e}")))?;
    Ok(())
}

/// Reset to a clean single-shard fixture: empty registry, one shard cap = CAP.
async fn reset(pool: &PgPool) -> Result<(), String> {
    sqlx::query("TRUNCATE reality_registry")
        .execute(pool)
        .await
        .map_err(|e| format!("truncate registry: {e}"))?;
    sqlx::query("DELETE FROM shard_utilization")
        .execute(pool)
        .await
        .map_err(|e| format!("clear shard_utilization: {e}"))?;
    sqlx::query(
        r#"INSERT INTO shard_utilization
             (snapshot_id, shard_host, current_db_count, total_storage_bytes,
              cpu_load_pct, connection_count, capacity_max_dbs, capacity_max_bytes)
           VALUES (gen_random_uuid(), $1, 0, 1000, 10, 10, $2, 1000000)"#,
    )
    .bind(SHARD)
    .bind(CAP)
    .execute(pool)
    .await
    .map_err(|e| format!("seed shard cap: {e}"))?;
    Ok(())
}

async fn count_realities(pool: &PgPool) -> Result<i64, String> {
    let (n,): (i64,) = sqlx::query_as("SELECT count(*)::bigint FROM reality_registry")
        .fetch_one(pool)
        .await
        .map_err(|e| format!("count: {e}"))?;
    Ok(n)
}
