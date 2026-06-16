//! `freeze-drill` — W1.4 live drill for the kernel write-freeze guard.
//!
//! Exercises `dp_kernel::PgEventStore` + `MetaFreezeGuard` against the real
//! scale rig: the per-reality `events` table lives on a shard DB, the
//! authoritative `reality_registry.status` on the meta DB. Proves the freeze
//! guard is non-vacuous via the guard-on / guard-off contrast:
//!
//!   guarded  status=active → append OK; flip status to migrating /
//!            pending_close / frozen → every append REJECTED (RealityFrozen);
//!            flip back to active → append OK again. The frozen appends NEVER
//!            land (final event count = the 2 active-state appends only).
//!   bite     the SAME flip to migrating but with NO freeze guard → the append
//!            LANDS → the relocation/closure flip would silently lose it.
//!            Proves the guard is the enforcer.
//!
//! Freeze-settle (plan review #1): the guard reads status UNCACHED, so there is
//! no TTL settle-window — an append is rejected the instant after the external
//! flip commits. The bite is therefore an immediate post-flip append.
//!
//! Verdict: 0 PASS · 1 FAIL · 2 NOTRUN(setup). Re-runnable (resets each run).

use std::process::ExitCode;
use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use dp_kernel::{
    event_store::{EventStore, EventStoreError},
    event_store_pg::{MetaFreezeGuard, PgEventStore},
    EventEnvelope,
};

const SHARD_HOST_LOGICAL: &str = "pg-shard-0.internal";

#[tokio::main]
async fn main() -> ExitCode {
    let meta_dsn = env_or(
        "FREEZE_META_DSN",
        "postgres://foundation:foundation@127.0.0.1:55510/w1_freeze?sslmode=disable",
    );
    let reality_dsn = env_or(
        "FREEZE_REALITY_DSN",
        "postgres://foundation:foundation@127.0.0.1:55511/w1f_reality?sslmode=disable",
    );
    let mode = std::env::args().nth(1).unwrap_or_else(|| "smoke".to_string());

    match run(&meta_dsn, &reality_dsn, &mode).await {
        Ok(code) => code,
        Err(e) => {
            eprintln!("freeze-drill: NOTRUN(setup): {e}");
            ExitCode::from(2)
        }
    }
}

async fn run(meta_dsn: &str, reality_dsn: &str, mode: &str) -> Result<ExitCode, String> {
    let meta_pool = Arc::new(connect(meta_dsn).await?);
    let reality_pool = Arc::new(connect(reality_dsn).await?);

    match mode {
        "guarded" => cmd_guarded(meta_pool, reality_pool).await,
        "bite" => cmd_bite(meta_pool, reality_pool).await,
        "smoke" => {
            let a = cmd_guarded(meta_pool.clone(), reality_pool.clone()).await?;
            if a != ExitCode::SUCCESS {
                return Ok(a);
            }
            cmd_bite(meta_pool, reality_pool).await
        }
        other => {
            eprintln!("freeze-drill: unknown mode {other}");
            Ok(ExitCode::from(2))
        }
    }
}

/// guard ON: frozen states reject; only active-state appends land.
async fn cmd_guarded(meta_pool: Arc<PgPool>, reality_pool: Arc<PgPool>) -> Result<ExitCode, String> {
    let rid = reset(&meta_pool, &reality_pool).await?;
    let store = PgEventStore::from_arc(reality_pool.clone())
        .with_freeze_guard(Arc::new(MetaFreezeGuard::new(meta_pool.clone())));

    // 1) active → append v1 OK.
    if let Err(e) = append(&store, rid, 1).await {
        return Ok(fail(format!("active append should succeed, got {e}")));
    }

    // 2) each frozen state must REJECT an append with RealityFrozen.
    for status in ["migrating", "pending_close", "frozen"] {
        set_status(&meta_pool, rid, status).await?;
        match append(&store, rid, 2).await {
            Err(EventStoreError::RealityFrozen { status: s, .. }) if s == status => {}
            Err(e) => return Ok(fail(format!("status={status}: wrong error: {e}"))),
            Ok(_) => {
                return Ok(fail(format!(
                    "status={status}: append SUCCEEDED but should be frozen (the guard let it through)"
                )))
            }
        }
    }

    // 3) recovery: back to active → append v2 OK.
    set_status(&meta_pool, rid, "active").await?;
    if let Err(e) = append(&store, rid, 2).await {
        return Ok(fail(format!("recovery append (active) should succeed, got {e}")));
    }

    // The 3 frozen-state appends must have left NO rows — only v1 + v2 landed.
    let n = count_events(&reality_pool, rid).await?;
    println!(r#"{{"mode":"guarded","events_landed":{n},"expected":2}}"#);
    if n != 2 {
        return Ok(fail(format!(
            "expected exactly 2 events (active v1 + recovery v2), got {n} — a frozen append leaked"
        )));
    }
    Ok(pass("guard ON: appends rejected in migrating/pending_close/frozen; only the 2 active-state appends landed; recovery after →active works"))
}

/// guard OFF (the bite): an append during migrating LANDS — would be lost.
async fn cmd_bite(meta_pool: Arc<PgPool>, reality_pool: Arc<PgPool>) -> Result<ExitCode, String> {
    let rid = reset(&meta_pool, &reality_pool).await?;
    // NO freeze guard.
    let store = PgEventStore::from_arc(reality_pool.clone());

    set_status(&meta_pool, rid, "migrating").await?;
    let appended = append(&store, rid, 1).await.is_ok();
    let n = count_events(&reality_pool, rid).await?;
    println!(r#"{{"mode":"bite","appended_during_migrating":{appended},"events_landed":{n}}}"#);

    if !appended || n != 1 {
        return Ok(fail(format!(
            "bite VACUOUS: an unguarded append during migrating did NOT land (appended={appended}, n={n}) — something else blocks it"
        )));
    }
    Ok(pass(
        "guard OFF: an append during migrating LANDED (1 event) — the relocation/closure flip would lose it; the guard (guarded mode) is the enforcer (non-vacuous)",
    ))
}

// ── helpers ──────────────────────────────────────────────────────────────────

async fn append(store: &PgEventStore, rid: Uuid, version: u64) -> Result<u64, EventStoreError> {
    let ev = EventEnvelope {
        event_id: Uuid::new_v4(),
        event_type: "w1f.tick".to_string(),
        event_version: 1,
        aggregate_id: "agg-1".to_string(),
        aggregate_type: "W1F".to_string(),
        aggregate_version: version,
        reality_id: rid,
        occurred_at: "2026-06-14T00:00:00Z".to_string(),
        recorded_at: "2026-06-14T00:00:00Z".to_string(),
        payload: serde_json::json!({"v": version}),
        metadata: None,
    };
    store
        .append_events(rid, "W1F", "agg-1", version - 1, &[ev])
        .await
}

/// reset: fresh events table + one seeded active reality. Returns its id.
async fn reset(meta_pool: &PgPool, reality_pool: &PgPool) -> Result<Uuid, String> {
    // Minimal events table matching the columns PgEventStore::append_events
    // touches (this drill tests the freeze guard, not the events schema).
    sqlx::query("DROP TABLE IF EXISTS events")
        .execute(reality_pool)
        .await
        .map_err(|e| format!("drop events: {e}"))?;
    sqlx::query(
        r#"CREATE TABLE events (
            event_id uuid NOT NULL,
            reality_id uuid NOT NULL,
            aggregate_type text NOT NULL,
            aggregate_id text NOT NULL,
            aggregate_version bigint NOT NULL,
            event_type text NOT NULL,
            event_version int NOT NULL,
            payload jsonb NOT NULL,
            metadata jsonb,
            occurred_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL,
            PRIMARY KEY (reality_id, aggregate_type, aggregate_id, aggregate_version)
        )"#,
    )
    .execute(reality_pool)
    .await
    .map_err(|e| format!("create events: {e}"))?;

    let rid = Uuid::new_v4();
    sqlx::query("DELETE FROM reality_registry WHERE db_name = 'w1f_reality'")
        .execute(meta_pool)
        .await
        .map_err(|e| format!("clear registry: {e}"))?;
    sqlx::query(
        r#"INSERT INTO reality_registry
            (reality_id, db_host, db_name, status, locale,
             session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
           VALUES ($1, $2, 'w1f_reality', 'active', 'en', 10, 10, 20, 0)"#,
    )
    .bind(rid)
    .bind(SHARD_HOST_LOGICAL)
    .execute(meta_pool)
    .await
    .map_err(|e| format!("seed registry: {e}"))?;
    Ok(rid)
}

async fn set_status(meta_pool: &PgPool, rid: Uuid, status: &str) -> Result<(), String> {
    sqlx::query("UPDATE reality_registry SET status = $1 WHERE reality_id = $2")
        .bind(status)
        .bind(rid)
        .execute(meta_pool)
        .await
        .map_err(|e| format!("set status {status}: {e}"))?;
    Ok(())
}

async fn count_events(reality_pool: &PgPool, rid: Uuid) -> Result<i64, String> {
    let (n,): (i64,) = sqlx::query_as("SELECT count(*)::bigint FROM events WHERE reality_id = $1")
        .bind(rid)
        .fetch_one(reality_pool)
        .await
        .map_err(|e| format!("count events: {e}"))?;
    Ok(n)
}

async fn connect(dsn: &str) -> Result<PgPool, String> {
    PgPoolOptions::new()
        .max_connections(4)
        .connect(dsn)
        .await
        .map_err(|e| format!("connect {dsn}: {e}"))
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

fn pass(msg: &str) -> ExitCode {
    eprintln!("PASS: {msg}");
    ExitCode::SUCCESS
}
fn fail(msg: String) -> ExitCode {
    eprintln!("FAIL: {msg}");
    ExitCode::from(1)
}
