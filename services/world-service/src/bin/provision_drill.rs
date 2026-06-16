//! `provision-drill` — W1.5 end-to-end live drill for the provisioner + bridge.
//!
//! Runs the REAL 11-step `provision_reality` with `LiveEffects` against the
//! scale rig + a running bridge-server: pick shard → register_pending (bridge →
//! reality_registry, I8) → CREATE DATABASE + REVOKE CONNECT (I4) → skeleton →
//! transition seeding→active (bridge). Then asserts the end state and the
//! non-vacuity bites.
//!
//!   provision  registry row active; meta_write_audit has the reality_registry
//!              rows (I8: register + 2 transitions); the per-reality DB exists;
//!              a foreign role is REVOKE-blocked from it; service_to_service_audit
//!              recorded the bridge calls.
//!   bite       (A) a DB created WITHOUT the REVOKE → the foreign role CONNECTS →
//!              proves REVOKE is the enforcer. (B) a raw reality_registry INSERT
//!              bypassing the bridge → 0 meta_write_audit rows → proves the I8
//!              audit is produced BY MetaWrite (through the bridge), not a trigger.
//!   smoke      provision + bite.
//!
//! Env: PROVISION_META_DSN, PROVISION_SHARD_ADMIN_DSN, PROVISION_BRIDGE_URL,
//! PROVISION_BRIDGE_TOKEN, PROVISION_SHARD_HOSTPORT. Verdict 0/1/2.

use std::process::ExitCode;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use world_service::capacity_planner::{CapacityThresholds, ShardCapacity, ShardId};
use world_service::provisioner::{ProvisionRequest, Provisioner};
use world_service::provisioner_live::{BridgeClient, LiveEffects};

const SHARD_HOST_LOGICAL: &str = "pg-shard-0.internal";
const FOREIGN_ROLE: &str = "w1p_foreign";
const FOREIGN_PASS: &str = "w1p_foreign_pw";

#[tokio::main]
async fn main() -> ExitCode {
    let meta_dsn = env_or("PROVISION_META_DSN", "postgres://foundation:foundation@127.0.0.1:55510/w1_provision?sslmode=disable");
    let shard_admin_dsn = env_or("PROVISION_SHARD_ADMIN_DSN", "postgres://foundation:foundation@127.0.0.1:55511/foundation?sslmode=disable");
    let bridge_url = env_or("PROVISION_BRIDGE_URL", "http://127.0.0.1:8090");
    let bridge_token = env_or("PROVISION_BRIDGE_TOKEN", "w1-bridge-dev-token");
    let shard_hostport = env_or("PROVISION_SHARD_HOSTPORT", "127.0.0.1:55511");
    let mode = std::env::args().nth(1).unwrap_or_else(|| "smoke".to_string());

    let ctx = Ctx {
        meta_dsn, shard_admin_dsn, bridge_url, bridge_token, shard_hostport,
    };
    match ctx.run(&mode).await {
        Ok(code) => code,
        Err(e) => {
            eprintln!("provision-drill: NOTRUN(setup): {e}");
            ExitCode::from(2)
        }
    }
}

struct Ctx {
    meta_dsn: String,
    shard_admin_dsn: String,
    bridge_url: String,
    bridge_token: String,
    shard_hostport: String,
}

impl Ctx {
    async fn run(&self, mode: &str) -> Result<ExitCode, String> {
        let meta = connect(&self.meta_dsn).await?;
        let shard = connect(&self.shard_admin_dsn).await?;
        self.ensure_foreign_role(&shard).await?;
        match mode {
            "provision" => self.cmd_provision(&meta, &shard).await,
            "bite" => self.cmd_bite(&meta, &shard).await,
            "smoke" => {
                let a = self.cmd_provision(&meta, &shard).await?;
                if a != ExitCode::SUCCESS {
                    return Ok(a);
                }
                self.cmd_bite(&meta, &shard).await
            }
            other => {
                eprintln!("provision-drill: unknown mode {other}");
                Ok(ExitCode::from(2))
            }
        }
    }

    async fn cmd_provision(&self, meta: &PgPool, shard: &PgPool) -> Result<ExitCode, String> {
        let rid = Uuid::new_v4();
        let db_name = format!("lw_reality_{}", &rid.simple().to_string()[..12]);
        cleanup(meta, shard, &db_name).await?;

        let report = self.provision(rid).await?;
        if report.db_name != db_name {
            return Ok(fail(format!("db_name mismatch: {} != {}", report.db_name, db_name)));
        }

        // Registry row active.
        let status: Option<String> =
            sqlx::query_scalar("SELECT status FROM reality_registry WHERE reality_id=$1")
                .bind(rid).fetch_optional(meta).await.map_err(|e| e.to_string())?;
        // I8: register INSERT + 2 transition UPDATEs = 3 meta_write_audit rows.
        let mwa: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM meta_write_audit WHERE table_name='reality_registry' AND row_pk->>'reality_id' = $1")
            .bind(rid.to_string()).fetch_one(meta).await.unwrap_or(-1);
        // Bridge audited its calls.
        let s2s: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM service_to_service_audit WHERE callee_service='meta-worker' AND result='ok'")
            .fetch_one(meta).await.unwrap_or(-1);
        // The per-reality DB exists.
        let db_exists: Option<i32> = sqlx::query_scalar("SELECT 1 FROM pg_database WHERE datname=$1")
            .bind(&db_name).fetch_optional(shard).await.map_err(|e| e.to_string())?;
        // Isolation: the foreign role must be REVOKE-blocked from the new DB.
        let foreign_blocked = self.foreign_connect(&db_name).await.is_err();

        println!(r#"{{"mode":"provision","status":{status:?},"mwa_reality":{mwa},"s2s_ok":{s2s},"db_exists":{},"foreign_blocked":{foreign_blocked}}}"#, db_exists.is_some());

        if status.as_deref() != Some("active") {
            return Ok(fail(format!("expected status=active, got {status:?}")));
        }
        if mwa < 3 {
            return Ok(fail(format!("I8: expected >=3 meta_write_audit rows for this reality (register + 2 transitions), got {mwa}")));
        }
        if s2s < 3 {
            return Ok(fail(format!("bridge audit: expected >=3 ok service_to_service_audit rows, got {s2s}")));
        }
        if db_exists.is_none() {
            return Ok(fail(format!("per-reality DB {db_name} was not created")));
        }
        if !foreign_blocked {
            return Ok(fail("isolation: the foreign role CONNECTED to the new reality DB despite REVOKE".into()));
        }
        Ok(pass(format!("provisioned end-to-end: status=active, {mwa} I8 audit rows, DB created + REVOKE-isolated, {s2s} bridge audits")))
    }

    async fn cmd_bite(&self, meta: &PgPool, shard: &PgPool) -> Result<ExitCode, String> {
        // Bite A — a DB created WITHOUT the REVOKE: the foreign role CAN connect.
        let open_db = "w1p_norevoke";
        let _ = sqlx::raw_sql(&format!("DROP DATABASE IF EXISTS {open_db} WITH (FORCE)")).execute(shard).await;
        sqlx::raw_sql(&format!("CREATE DATABASE {open_db}")).execute(shard).await.map_err(|e| e.to_string())?;
        // NO revoke here.
        let foreign_can_connect = self.foreign_connect(open_db).await.is_ok();

        // Bite B — a raw reality_registry INSERT bypassing the bridge: 0 audit.
        let rid = Uuid::new_v4();
        let mwa_before: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM meta_write_audit WHERE table_name='reality_registry' AND row_pk->>'reality_id'=$1")
            .bind(rid.to_string()).fetch_one(meta).await.unwrap_or(-1);
        sqlx::query(
            r#"INSERT INTO reality_registry
                 (reality_id, db_host, db_name, status, locale,
                  session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
               VALUES ($1,$2,'w1p_raw','provisioning','en',10,10,20,0)"#)
            .bind(rid).bind(SHARD_HOST_LOGICAL).execute(meta).await.map_err(|e| e.to_string())?;
        let mwa_after: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM meta_write_audit WHERE table_name='reality_registry' AND row_pk->>'reality_id'=$1")
            .bind(rid.to_string()).fetch_one(meta).await.unwrap_or(-1);
        let raw_audit_delta = mwa_after - mwa_before;

        let _ = sqlx::raw_sql(&format!("DROP DATABASE IF EXISTS {open_db} WITH (FORCE)")).execute(shard).await;
        println!(r#"{{"mode":"bite","foreign_can_connect_no_revoke":{foreign_can_connect},"raw_insert_audit_delta":{raw_audit_delta}}}"#);

        if !foreign_can_connect {
            return Ok(fail("bite A VACUOUS: the foreign role could NOT connect even WITHOUT a revoke — something else blocks it, so the REVOKE isn't the enforcer".into()));
        }
        if raw_audit_delta != 0 {
            return Ok(fail(format!("bite B VACUOUS: a raw INSERT bypassing the bridge still produced {raw_audit_delta} meta_write_audit row(s) — the I8 check is vacuous (a trigger audits regardless)")));
        }
        Ok(pass("bite A: foreign role connects to a non-revoked DB (REVOKE is the isolation enforcer); bite B: raw bypass leaves 0 meta_write_audit (I8 audit is produced BY the bridge's MetaWrite)".into()))
    }

    /// Run the real 11-step provision on a blocking thread (LiveEffects blocks
    /// on async I/O internally, so it must NOT run on an async task).
    async fn provision(&self, rid: Uuid) -> Result<world_service::ProvisionReport, String> {
        let bridge = BridgeClient::new(self.bridge_url.clone(), self.bridge_token.clone());
        let shard_admin = connect(&self.shard_admin_dsn).await?;
        let handle = tokio::runtime::Handle::current();
        let shard_hostport = self.shard_hostport.clone();
        let report = tokio::task::spawn_blocking(move || {
            let mut effects = LiveEffects::new(
                handle, bridge, shard_admin, shard_hostport,
                "foundation", "foundation", "contracts/migrations/per_reality",
            );
            let snapshot = vec![ShardCapacity {
                shard_id: ShardId::new(SHARD_HOST_LOGICAL),
                used_realities: 0,
                total_realities: 100,
            }];
            let req = ProvisionRequest {
                reality_id: rid,
                locale: "en".into(),
                deploy_cohort: 0,
                reason: "w1.5-provision-drill".into(),
            };
            Provisioner::new(CapacityThresholds::default()).provision_reality(req, &snapshot, &mut effects)
        })
        .await
        .map_err(|e| format!("join: {e}"))?;
        report.map_err(|e| format!("provision_reality: {e}"))
    }

    async fn ensure_foreign_role(&self, shard: &PgPool) -> Result<(), String> {
        // A non-superuser login role that relies on PUBLIC CONNECT (so REVOKE
        // FROM PUBLIC blocks it). Idempotent.
        let exists: Option<i32> = sqlx::query_scalar("SELECT 1 FROM pg_roles WHERE rolname=$1")
            .bind(FOREIGN_ROLE).fetch_optional(shard).await.map_err(|e| e.to_string())?;
        if exists.is_none() {
            sqlx::raw_sql(&format!("CREATE ROLE {FOREIGN_ROLE} LOGIN PASSWORD '{FOREIGN_PASS}' NOSUPERUSER"))
                .execute(shard).await.map_err(|e| format!("create foreign role: {e}"))?;
        }
        Ok(())
    }

    async fn foreign_connect(&self, db_name: &str) -> Result<(), String> {
        let dsn = format!("postgres://{FOREIGN_ROLE}:{FOREIGN_PASS}@{}/{}?sslmode=disable", self.shard_hostport, db_name);
        let pool = PgPoolOptions::new().max_connections(1)
            .acquire_timeout(std::time::Duration::from_secs(3))
            .connect(&dsn).await.map_err(|e| e.to_string())?;
        // Force a real connection (connect is lazy-ish).
        sqlx::query("SELECT 1").execute(&pool).await.map_err(|e| e.to_string())?;
        pool.close().await;
        Ok(())
    }
}

async fn cleanup(meta: &PgPool, shard: &PgPool, db_name: &str) -> Result<(), String> {
    let _ = sqlx::query("DELETE FROM reality_registry WHERE db_name=$1").bind(db_name).execute(meta).await;
    let _ = sqlx::raw_sql(&format!("DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")).execute(shard).await;
    Ok(())
}

async fn connect(dsn: &str) -> Result<PgPool, String> {
    PgPoolOptions::new().max_connections(4).connect(dsn).await.map_err(|e| format!("connect {dsn}: {e}"))
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

fn pass(msg: String) -> ExitCode {
    eprintln!("PASS: {msg}");
    ExitCode::SUCCESS
}
fn fail(msg: String) -> ExitCode {
    eprintln!("FAIL: {msg}");
    ExitCode::from(1)
}
