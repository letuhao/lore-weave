//! `orphan_scanner` — L1.C.4 nightly reaper for what a half-finished provision
//! leaves behind.
//!
//! ## What changed in W5, and why it had to
//!
//! This binary shipped in cycle 5 as a scaffold. Its dry run classified
//! `let scanned = 0u32` — a literal empty set — and its real mode returned exit
//! 2 with *"real-mode RPC wiring not yet implemented (cycle 6 dependency)"*.
//! So for the whole of its life it could not report an orphan, because it never
//! looked at anything.
//!
//! Two things make that indefensible now. The **dependency it named is up**:
//! the meta bridge runs (`W2`), and the provisioner writes through it. And
//! `W3` gave the platform a **producer** — `admin reality provision` creates
//! realities for real, so a crash between `CREATE DATABASE` and the registry
//! transition now leaves exactly the states this binary was specified to find.
//! A scanner that cannot see them is apparatus without a subject.
//!
//! ## What it does now
//!
//! Reads `reality_registry` (meta) and the shard's `lw_reality_*` databases,
//! and classifies them with [`world_service::orphan_scan::classify`] — a pure
//! function, unit-tested, so the decision rules are provable without a
//! database. Emits one JSON object on stdout and a human summary on stderr.
//!
//! **It is READ-ONLY.** It writes nothing, drops nothing. Remediation needs a
//! `reality_close_audit` write through the bridge, and the bridge exposes only
//! `register-reality` and `transition` today — so `--remediate` REFUSES rather
//! than silently doing nothing (R13 §12L.5: no raw destructive primitive, and
//! never a no-op that reports success).
//!
//! ## Exit codes — designed for cron
//!
//! - `0` — scanned, nothing wrong
//! - `1` — orphans found (cron alerts on this)
//! - `2` — could not scan: missing config, unreachable database
//!
//! `1` and `2` are deliberately distinct: "the shard is dirty" and "I never
//! looked" must never be the same signal to an operator.

use std::process::ExitCode;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use world_service::orphan_scan::{classify, Finding, RegistryRow, ScanThresholds};

/// 7-day grace period — must match `runbooks/provisioner/orphan_resolution.md`.
pub const SOFT_DELETE_GRACE_DAYS: i64 = 7;

/// 24-hour stall threshold for transient `provisioning|seeding` statuses.
pub const TRANSIENT_STALL_HOURS: i64 = 24;

/// Env vars carrying a DSN. No defaults: a credential default silently points a
/// reaper at the wrong server, and this one reads every reality on a shard.
const REQUIRED_ENV: [&str; 2] = ["ORPHAN_META_DSN", "ORPHAN_SHARD_ADMIN_DSN"];

#[tokio::main]
async fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();

    if args.iter().any(|a| a == "--help" || a == "-h") {
        print_usage();
        return ExitCode::SUCCESS;
    }
    if args.iter().any(|a| a == "--remediate") {
        eprintln!(
            "[orphan_scanner] REFUSING: --remediate is not wired. Marking an orphan needs a \
             reality_close_audit write through the meta bridge, which today exposes only \
             register-reality and transition. This binary is read-only; it will not pretend \
             to have remediated anything."
        );
        return ExitCode::from(2);
    }
    if let Some(bad) = args.iter().find(|a| {
        !matches!(a.as_str(), "--dry-run" | "--json" | "--help" | "-h" | "--remediate")
    }) {
        eprintln!("[orphan_scanner] unknown flag {bad}");
        print_usage();
        return ExitCode::from(2);
    }
    let json_only = args.iter().any(|a| a == "--json");

    match run(json_only).await {
        Ok(code) => code,
        Err(e) => {
            eprintln!("[orphan_scanner] NOTRUN(setup): {e}");
            ExitCode::from(2)
        }
    }
}

async fn run(json_only: bool) -> Result<ExitCode, String> {
    let missing: Vec<&str> = REQUIRED_ENV
        .iter()
        .copied()
        .filter(|k| std::env::var(k).map(|v| v.trim().is_empty()).unwrap_or(true))
        .collect();
    if !missing.is_empty() {
        return Err(format!(
            "missing required env: {} (no credential defaults — a default would point the \
             reaper at the wrong server)",
            missing.join(", ")
        ));
    }
    let shard_host = std::env::var("ORPHAN_SHARD_HOST")
        .unwrap_or_else(|_| "pg-shard-0.internal".to_string());

    let meta = connect(&std::env::var("ORPHAN_META_DSN").unwrap_or_default()).await?;
    let shard = connect(&std::env::var("ORPHAN_SHARD_ADMIN_DSN").unwrap_or_default()).await?;

    let rows = read_registry(&meta, &shard_host).await?;
    let databases = read_shard_databases(&shard).await?;
    let thresholds = ScanThresholds {
        stall_hours: TRANSIENT_STALL_HOURS,
        grace_days: SOFT_DELETE_GRACE_DAYS,
    };
    let findings = classify(&rows, &databases, thresholds);

    println!("{}", report_json(&shard_host, &rows, &databases, &findings));

    if !json_only {
        eprintln!(
            "[orphan_scanner] shard={shard_host} registry_rows={} databases={} findings={}",
            rows.len(),
            databases.len(),
            findings.len()
        );
        for f in &findings {
            eprintln!("[orphan_scanner]   {} {}", f.class(), describe(f));
        }
        if findings.is_empty() {
            eprintln!("[orphan_scanner] clean");
        } else {
            eprintln!(
                "[orphan_scanner] {} orphan(s) — see runbooks/provisioner/orphan_resolution.md",
                findings.len()
            );
        }
    }

    Ok(if findings.is_empty() { ExitCode::SUCCESS } else { ExitCode::from(1) })
}

/// Every `reality_registry` row on this shard — ALL statuses, not just the
/// transient ones. An `active` row is what proves its database is tracked, so
/// filtering here would make every healthy database look untracked.
async fn read_registry(meta: &PgPool, shard_host: &str) -> Result<Vec<RegistryRow>, String> {
    let rows: Vec<(Uuid, String, String, String, i64)> = sqlx::query_as(
        r#"
        SELECT reality_id,
               db_name,
               db_host,
               status,
               GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - created_at)) / 3600))::bigint
          FROM reality_registry
         WHERE db_host = $1
        "#,
    )
    .bind(shard_host)
    .fetch_all(meta)
    .await
    .map_err(|e| format!("read reality_registry: {e}"))?;

    Ok(rows
        .into_iter()
        .map(|(reality_id, db_name, db_host, status, age_hours)| RegistryRow {
            reality_id,
            db_name,
            db_host,
            status,
            age_hours,
        })
        .collect())
}

/// Every per-reality database physically present on the shard.
///
/// The `lw_reality_` prefix is the provisioner's own naming (`db_name_for`), so
/// this deliberately does NOT sweep unrelated databases: a reaper that can see
/// `loreweave_auth` is a reaper that can eventually be told to drop it.
async fn read_shard_databases(shard: &PgPool) -> Result<Vec<String>, String> {
    sqlx::query_scalar(
        "SELECT datname FROM pg_database WHERE datname LIKE 'lw\\_reality\\_%' ORDER BY 1",
    )
    .fetch_all(shard)
    .await
    .map_err(|e| format!("read pg_database: {e}"))
}

fn describe(f: &Finding) -> String {
    match f {
        Finding::StalledProvision { reality_id, db_name, status, age_hours, database_present } => {
            format!(
                "{reality_id} db={db_name} status={status} age={age_hours}h database_present={database_present}"
            )
        }
        Finding::MissingDatabase { reality_id, db_name, status } => {
            format!("{reality_id} db={db_name} status={status} (registry claims a database that is not there)")
        }
        Finding::UntrackedDatabase { db_name } => {
            format!("{db_name} (no registry row — invisible to capacity, which counts registry rows)")
        }
        Finding::DropEligible { reality_id, db_name, age_hours } => {
            format!("{reality_id} db={db_name} soft_deleted for {age_hours}h")
        }
    }
}

fn report_json(
    shard_host: &str,
    rows: &[RegistryRow],
    databases: &[String],
    findings: &[Finding],
) -> String {
    let items: Vec<String> = findings
        .iter()
        .map(|f| {
            serde_json::to_string(f).unwrap_or_else(|_| "{\"class\":\"unserialisable\"}".into())
        })
        .collect();
    format!(
        r#"{{"shard":{},"registry_rows":{},"databases":{},"findings":{},"detail":[{}]}}"#,
        serde_json::to_string(shard_host).unwrap_or_else(|_| "\"?\"".into()),
        rows.len(),
        databases.len(),
        findings.len(),
        items.join(",")
    )
}

async fn connect(dsn: &str) -> Result<PgPool, String> {
    PgPoolOptions::new()
        .max_connections(2)
        .connect(dsn)
        .await
        // Never interpolate the DSN — it carries the password.
        .map_err(|e| format!("connect failed: {e}"))
}

fn print_usage() {
    println!(
        "orphan_scanner — L1.C.4 reaper for partial provisions and stale databases\n\
         \n\
         READ-ONLY. Writes nothing, drops nothing.\n\
         \n\
         USAGE:\n\
           orphan_scanner            # scan + report\n\
           orphan_scanner --json     # stdout JSON only (no stderr summary)\n\
           orphan_scanner --dry-run  # accepted; the scanner is read-only regardless\n\
           orphan_scanner --help\n\
         \n\
         ENV (required, no defaults):\n\
           ORPHAN_META_DSN           # the meta database\n\
           ORPHAN_SHARD_ADMIN_DSN    # the shard, to list pg_database\n\
           ORPHAN_SHARD_HOST         # logical shard name (default pg-shard-0.internal)\n\
         \n\
         EXIT:\n\
           0  clean\n\
           1  orphans found\n\
           2  could not scan (config/connection) — NOT the same as clean\n\
         \n\
         CONSTANTS:\n\
           SOFT_DELETE_GRACE_DAYS = {SOFT_DELETE_GRACE_DAYS}\n\
           TRANSIENT_STALL_HOURS  = {TRANSIENT_STALL_HOURS}\n\
         \n\
         RUNBOOK: runbooks/provisioner/orphan_resolution.md"
    );
}
