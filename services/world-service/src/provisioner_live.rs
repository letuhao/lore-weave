//! W1.5 — live production `Effects` for the provisioner.
//!
//! Binds the cycle-5 [`crate::provisioner::Effects`] trait (sync) to its real
//! collaborators:
//!
//! - **register_pending / transition_to** → the Rust→Go meta-write **bridge**
//!   (an internal HTTP call to meta-worker). The registry write MUST go through
//!   Go MetaWrite so the `meta_write_audit` row lands in the same TX (I8) — Rust
//!   cannot write `reality_registry` directly. This is the centerpiece of W1.5.
//! - **create_database** → sqlx `CREATE DATABASE` on the picked shard + the I4
//!   isolation bootstrap (`REVOKE CONNECT … FROM PUBLIC`).
//! - **apply_initial_migration** → run `0001_initial.up.sql` on the new DB.
//! - **pgbouncer / prometheus / backup** → no-op (those subsystems are go-live;
//!   the provisioner calls them through no-op Effects so the core flow runs now).
//!
//! The `Effects` trait is synchronous, but the real I/O (reqwest, sqlx) is
//! async. [`LiveEffects`] bridges the two with a tokio [`Handle`] +
//! `block_on` — so the caller MUST drive `provision_reality` on a blocking
//! thread (`tokio::task::spawn_blocking`), never directly on an async task
//! (that would panic "cannot block the current thread from within a runtime").

use tokio::runtime::Handle;
use uuid::Uuid;

use crate::capacity_planner::ShardId;
use crate::errors::ProvisionerError;
use crate::provisioner::{Effects, ProvisionRequest};

/// HTTP client for the meta-worker provisioner bridge.
#[derive(Clone)]
pub struct BridgeClient {
    base_url: String,
    token: String,
    http: reqwest::Client,
}

impl BridgeClient {
    /// `base_url` e.g. `http://127.0.0.1:8090`; `token` is the shared service token.
    pub fn new(base_url: impl Into<String>, token: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            token: token.into(),
            http: reqwest::Client::new(),
        }
    }

    async fn register(
        &self,
        reality_id: Uuid,
        db_host: &str,
        db_name: &str,
        locale: &str,
        deploy_cohort: u8,
        reason: &str,
    ) -> Result<bool, ProvisionerError> {
        let body = serde_json::json!({
            "reality_id": reality_id.to_string(),
            "db_host": db_host,
            "db_name": db_name,
            "locale": locale,
            "deploy_cohort": deploy_cohort,
            "reason": reason,
        });
        let resp = self
            .http
            .post(format!("{}/internal/provisioner/register-reality", self.base_url))
            .header("X-Service-Token", &self.token)
            .json(&body)
            .send()
            .await
            .map_err(|e| ProvisionerError::Bridge(format!("register send: {e}")))?;
        match resp.status().as_u16() {
            201 => Ok(true),  // created
            200 => Ok(false), // idempotent: already registered
            401 => Err(ProvisionerError::Bridge("register: 401 unauthorized".into())),
            code => Err(ProvisionerError::Bridge(format!(
                "register: unexpected {code}: {}",
                resp.text().await.unwrap_or_default()
            ))),
        }
    }

    async fn transition(
        &self,
        reality_id: Uuid,
        from: &str,
        to: &str,
        reason: &str,
    ) -> Result<(), ProvisionerError> {
        let body = serde_json::json!({
            "reality_id": reality_id.to_string(),
            "from": from,
            "to": to,
            "reason": reason,
        });
        let resp = self
            .http
            .post(format!("{}/internal/provisioner/transition", self.base_url))
            .header("X-Service-Token", &self.token)
            .json(&body)
            .send()
            .await
            .map_err(|e| ProvisionerError::Bridge(format!("transition send: {e}")))?;
        match resp.status().as_u16() {
            200 => Ok(()),
            409 => Err(ProvisionerError::ConcurrentTransition(format!(
                "{from}->{to} rejected (stale state)"
            ))),
            code => Err(ProvisionerError::Bridge(format!(
                "transition {from}->{to}: unexpected {code}: {}",
                resp.text().await.unwrap_or_default()
            ))),
        }
    }
}

/// Production `Effects`. Holds a runtime handle to block on the async bridge +
/// shard I/O from the sync trait methods.
pub struct LiveEffects {
    handle: Handle,
    bridge: BridgeClient,
    /// Admin pool on the shard (maintenance DB) — runs CREATE DATABASE + REVOKE.
    shard_admin: sqlx::PgPool,
    /// `host:port` of the shard, to connect to the freshly-created per-reality DB.
    shard_hostport: String,
    pg_user: String,
    pg_pass: String,
    /// Directory holding `<id>.up.sql` (contracts/migrations/per_reality).
    sql_dir: String,
}

impl LiveEffects {
    /// Construct. `handle` is the current tokio runtime handle (capture with
    /// `Handle::current()` from async context before spawn_blocking).
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        handle: Handle,
        bridge: BridgeClient,
        shard_admin: sqlx::PgPool,
        shard_hostport: impl Into<String>,
        pg_user: impl Into<String>,
        pg_pass: impl Into<String>,
        sql_dir: impl Into<String>,
    ) -> Self {
        Self {
            handle,
            bridge,
            shard_admin,
            shard_hostport: shard_hostport.into(),
            pg_user: pg_user.into(),
            pg_pass: pg_pass.into(),
            sql_dir: sql_dir.into(),
        }
    }

    fn reality_dsn(&self, db_name: &str) -> String {
        format!(
            "postgres://{}:{}@{}/{}?sslmode=disable",
            self.pg_user, self.pg_pass, self.shard_hostport, db_name
        )
    }
}

/// Reject anything but a safe lowercase identifier so a db_name can be
/// string-interpolated into DDL (CREATE DATABASE can't bind parameters).
fn safe_ident(s: &str) -> Result<(), ProvisionerError> {
    if !s.is_empty()
        && s.len() <= 63
        && s.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
    {
        Ok(())
    } else {
        Err(ProvisionerError::ShardEffect(format!("unsafe db identifier: {s:?}")))
    }
}

impl Effects for LiveEffects {
    fn register_pending(
        &mut self,
        reality_id: Uuid,
        shard: &ShardId,
        db_name: &str,
        req: &ProvisionRequest,
    ) -> Result<bool, ProvisionerError> {
        self.handle.clone().block_on(self.bridge.register(
            reality_id,
            shard.as_str(),
            db_name,
            &req.locale,
            req.deploy_cohort,
            &req.reason,
        ))
    }

    fn create_database(
        &mut self,
        _shard: &ShardId,
        db_name: &str,
    ) -> Result<bool, ProvisionerError> {
        safe_ident(db_name)?;
        let pool = self.shard_admin.clone();
        let name = db_name.to_string();
        self.handle.clone().block_on(async move {
            // Idempotent: skip if the DB already exists.
            let exists: Option<i32> =
                sqlx::query_scalar("SELECT 1 FROM pg_database WHERE datname = $1")
                    .bind(&name)
                    .fetch_optional(&pool)
                    .await
                    .map_err(|e| ProvisionerError::ShardEffect(format!("db exists check: {e}")))?;
            if exists.is_some() {
                return Ok(false);
            }
            // CREATE DATABASE + I4 isolation: REVOKE CONNECT FROM PUBLIC so only
            // the owner (and explicitly-granted roles) can connect. Simple query
            // protocol (&str) — CREATE DATABASE can't run prepared/in a tx.
            sqlx::raw_sql(&format!("CREATE DATABASE {name}"))
                .execute(&pool)
                .await
                .map_err(|e| ProvisionerError::ShardEffect(format!("create database: {e}")))?;
            sqlx::raw_sql(&format!("REVOKE CONNECT ON DATABASE {name} FROM PUBLIC"))
                .execute(&pool)
                .await
                .map_err(|e| ProvisionerError::ShardEffect(format!("revoke connect: {e}")))?;
            Ok(true)
        })
    }

    fn apply_initial_migration(
        &mut self,
        _shard: &ShardId,
        db_name: &str,
    ) -> Result<bool, ProvisionerError> {
        safe_ident(db_name)?;
        let path = format!("{}/0001_initial.up.sql", self.sql_dir);
        let sql = std::fs::read_to_string(&path)
            .map_err(|e| ProvisionerError::ShardEffect(format!("read {path}: {e}")))?;
        let dsn = self.reality_dsn(db_name);
        self.handle.clone().block_on(async move {
            let pool = sqlx::PgPool::connect(&dsn)
                .await
                .map_err(|e| ProvisionerError::ShardEffect(format!("connect new db: {e}")))?;
            // The skeleton is IF-NOT-EXISTS-shaped → idempotent re-run.
            sqlx::raw_sql(&sql)
                .execute(&pool)
                .await
                .map_err(|e| ProvisionerError::ShardEffect(format!("apply skeleton: {e}")))?;
            pool.close().await;
            Ok(true)
        })
    }

    // pgbouncer / prometheus / backup registration are go-live infra — no-op so
    // the core provision flow runs now (returns "skipped").
    fn register_with_pgbouncer(&mut self, _: &ShardId, _: &str) -> Result<bool, ProvisionerError> {
        Ok(false)
    }
    fn register_prometheus_scrape(&mut self, _: &ShardId, _: &str) -> Result<bool, ProvisionerError> {
        Ok(false)
    }
    fn register_backup_policy(&mut self, _: Uuid) -> Result<bool, ProvisionerError> {
        Ok(false)
    }

    fn transition_to(
        &mut self,
        reality_id: Uuid,
        from: &str,
        to: &str,
        reason: &str,
    ) -> Result<bool, ProvisionerError> {
        self.handle
            .clone()
            .block_on(self.bridge.transition(reality_id, from, to, reason))
            .map(|()| true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_ident_accepts_reality_db_names() {
        assert!(safe_ident("lw_reality_deadbeef0000").is_ok());
        assert!(safe_ident("w1p_000").is_ok());
    }

    #[test]
    fn safe_ident_rejects_injection() {
        assert!(safe_ident("lw; DROP DATABASE foundation").is_err());
        assert!(safe_ident("Foo").is_err()); // uppercase
        assert!(safe_ident("").is_err());
    }
}
