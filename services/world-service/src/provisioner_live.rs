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
//! - **apply_migrations** → apply every migration the manifest registers,
//!   in order, skipping those already in the reality's `schema_migrations`
//!   ledger. (This read "run `0001_initial.up.sql` on the new DB" until
//!   `1b14-06` -- the precise false sentence `1b12-05` blocked on, left in
//!   the header of the file whose body was rewritten to fix it.)
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
        owner_user_id: Option<Uuid>,
    ) -> Result<bool, ProvisionerError> {
        let mut body = serde_json::json!({
            "reality_id": reality_id.to_string(),
            "db_host": db_host,
            "db_name": db_name,
            "locale": locale,
            "deploy_cohort": deploy_cohort,
            "reason": reason,
        });
        // W6 — omitted entirely when absent, so the server's "empty means
        // system-owned" rule is the ONE place the tier is decided.
        if let Some(oid) = owner_user_id {
            body["owner_user_id"] = serde_json::Value::String(oid.to_string());
        }
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

    /// Record the CURRENT finding set for a shard (W5-REMEDIATE).
    ///
    /// Whole-shard replace: the server upserts what is sent and deletes what is
    /// not, so a cleared finding disappears. An EMPTY slice is meaningful — it
    /// says the shard is clean — and is what clears the last stale row.
    ///
    /// Public because `orphan_scanner` is the caller; the two provisioning
    /// methods beside it are private to `LiveEffects`.
    pub async fn record_orphans(
        &self,
        shard_host: &str,
        findings: &[crate::orphan_scan::Finding],
        reason: &str,
    ) -> Result<(u32, u32), ProvisionerError> {
        let items: Vec<serde_json::Value> = findings
            .iter()
            .map(|f| {
                let mut o = serde_json::json!({
                    "db_name": f.db_name(),
                    "finding_class": f.class(),
                    "detail": f.detail(),
                });
                // Omitted entirely for an untracked database, so the server's
                // "empty means no reality" rule is the ONE place that decides.
                if let Some(rid) = f.reality_id() {
                    o["reality_id"] = serde_json::Value::String(rid.to_string());
                }
                o
            })
            .collect();
        let body = serde_json::json!({
            "shard_host": shard_host,
            "findings": items,
            "reason": reason,
        });
        let resp = self
            .http
            .post(format!("{}/internal/provisioner/record-orphans", self.base_url))
            .header("X-Service-Token", &self.token)
            .json(&body)
            .send()
            .await
            .map_err(|e| ProvisionerError::Bridge(format!("record-orphans send: {e}")))?;
        match resp.status().as_u16() {
            200 => {
                let v: serde_json::Value = resp
                    .json()
                    .await
                    .map_err(|e| ProvisionerError::Bridge(format!("record-orphans body: {e}")))?;
                Ok((
                    v["recorded"].as_u64().unwrap_or(0) as u32,
                    v["cleared"].as_u64().unwrap_or(0) as u32,
                ))
            }
            401 => Err(ProvisionerError::Bridge(
                "record-orphans: 401 unauthorized".into(),
            )),
            code => Err(ProvisionerError::Bridge(format!(
                "record-orphans: unexpected {code}: {}",
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

    /// Grant `user` control of `actor` in `reality` (`SEALED-BINDING`).
    ///
    /// Through the bridge and not by a direct INSERT, for the same `I8` reason
    /// every other meta write here goes that way: the `meta_write_audit` row
    /// and the `actor.control.granted` outbox event must land in the SAME
    /// transaction as the binding, and only Go's `MetaWrite` can do that.
    ///
    /// `201` created · `200` the same user already holds it (a retry) · `409`
    /// somebody else does. The last is a normal answer, not a failure.
    pub async fn grant_actor_control(
        &self,
        user_ref_id: Uuid,
        reality_id: Uuid,
        actor_id: Uuid,
        reason: &str,
    ) -> Result<bool, ProvisionerError> {
        let resp = self
            .http
            .post(format!("{}/internal/provisioner/grant-actor-control", self.base_url))
            .header("X-Service-Token", &self.token)
            .json(&serde_json::json!({
                "user_ref_id": user_ref_id.to_string(),
                "reality_id": reality_id.to_string(),
                "actor_id": actor_id.to_string(),
                "reason": reason,
            }))
            .send()
            .await
            .map_err(|e| ProvisionerError::Bridge(format!("grant send: {e}")))?;
        match resp.status().as_u16() {
            201 => Ok(true),  // granted
            200 => Ok(false), // idempotent: this user already drives it
            409 => Err(ProvisionerError::ActorAlreadyDriven(actor_id.to_string())),
            401 => Err(ProvisionerError::Bridge("grant: 401 unauthorized".into())),
            code => Err(ProvisionerError::Bridge(format!(
                "grant: unexpected {code}: {}",
                resp.text().await.unwrap_or_default()
            ))),
        }
    }

    /// End the live binding for `(reality, actor)`.
    ///
    /// `expected_user_ref_id` is the optional CAS: when supplied, the revoke
    /// applies only while that user still holds the binding. Omitting it
    /// revokes whoever holds it, which is what an operator forcibly freeing a
    /// stuck actor wants and is NOT what a client acting on a stale character
    /// list wants.
    ///
    /// Returns whether anything was revoked — `false` means it was already
    /// revoked, which is success by end state.
    pub async fn revoke_actor_control(
        &self,
        reality_id: Uuid,
        actor_id: Uuid,
        expected_user_ref_id: Option<Uuid>,
        reason: &str,
    ) -> Result<bool, ProvisionerError> {
        let mut body = serde_json::json!({
            "reality_id": reality_id.to_string(),
            "actor_id": actor_id.to_string(),
            "reason": reason,
        });
        // Omitted entirely when absent, so "no CAS" and "CAS on the nil uuid"
        // cannot be confused — the same shape `register`'s `owner_user_id` uses.
        if let Some(u) = expected_user_ref_id {
            body["expected_user_ref_id"] = serde_json::Value::String(u.to_string());
        }
        let resp = self
            .http
            .post(format!("{}/internal/provisioner/revoke-actor-control", self.base_url))
            .header("X-Service-Token", &self.token)
            .json(&body)
            .send()
            .await
            .map_err(|e| ProvisionerError::Bridge(format!("revoke send: {e}")))?;
        let code = resp.status().as_u16();
        match code {
            200 => {
                // The bridge distinguishes the two 200s in the body, and the
                // caller needs that difference: "I ended a binding" and "there
                // was nothing to end" are different facts about the world.
                let body: serde_json::Value = resp.json().await.unwrap_or_default();
                Ok(body.get("status").and_then(|s| s.as_str()) == Some("revoked"))
            }
            409 => Err(ProvisionerError::ControlCasMismatch(actor_id.to_string())),
            401 => Err(ProvisionerError::Bridge("revoke: 401 unauthorized".into())),
            _ => Err(ProvisionerError::Bridge(format!(
                "revoke: unexpected {code}: {}",
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

    /// The ordered migration ids from `contracts/migrations/manifest.yaml`.
    ///
    /// A four-line reader rather than a YAML dependency, for the reason
    /// `scripts/migration-manifest-gate.py` gives for the same choice: the shape
    /// is a stable contract stated in the manifest's own header (`- id: "x"`),
    /// and a provisioner that fails to build because of a parser dependency is
    /// worse than one that reads four lines. The gate keeps this file and the
    /// manifest honest in both directions.
    fn manifest_ids(&self) -> Result<Vec<String>, ProvisionerError> {
        let path = format!("{}/../manifest.yaml", self.sql_dir);
        let text = std::fs::read_to_string(&path)
            .map_err(|e| ProvisionerError::ShardEffect(format!("read {path}: {e}")))?;
        let ids = parse_manifest_ids(&text);
        if ids.is_empty() {
            // A manifest that parses to nothing would silently provision an
            // EMPTY reality — the failure mode `1b12-05` exists to end, arriving
            // through the parser instead of through the hardcoded filename.
            return Err(ProvisionerError::ShardEffect(format!(
                "manifest {path} yielded no migration ids"
            )));
        }
        Ok(ids)
    }
}

/// Apply every migration not already in the reality's `schema_migrations`
/// ledger, in order. Returns how many were newly applied.
///
/// Extracted from the trait method **so a live test can drive the real code
/// path** rather than a re-implementation of it. `1b14-01` was found because the
/// unit test covering provisioner re-entry was green against
/// `FakeEffects::apply_migrations`, which is a `HashSet::insert` — the mock had
/// the idempotence and the live code did not. A second re-implementation, this
/// time in a test, would repeat exactly that.
pub async fn apply_pending(
    pool: &sqlx::PgPool,
    migrations: &[(String, String)],
) -> Result<usize, ProvisionerError> {
    sqlx::raw_sql(
        "CREATE TABLE IF NOT EXISTS schema_migrations (\
           id TEXT PRIMARY KEY, \
           applied_at TIMESTAMPTZ NOT NULL DEFAULT now())",
    )
    .execute(pool)
    .await
    .map_err(|e| ProvisionerError::ShardEffect(format!("create ledger: {e}")))?;

    let applied: Vec<(String,)> = sqlx::query_as("SELECT id FROM schema_migrations")
        .fetch_all(pool)
        .await
        .map_err(|e| ProvisionerError::ShardEffect(format!("read ledger: {e}")))?;
    let applied: std::collections::HashSet<String> = applied.into_iter().map(|(id,)| id).collect();

    let mut newly = 0usize;
    for (id, sql) in migrations {
        if applied.contains(id) {
            continue;
        }
        sqlx::raw_sql(sql)
            .execute(pool)
            .await
            .map_err(|e| ProvisionerError::ShardEffect(format!("apply {id}: {e}")))?;
        // Recorded only AFTER the migration succeeded, so a crash between the
        // two re-applies that one file — which IS the retry-safe operation, and
        // the only one this ledger ever asks any migration to perform.
        sqlx::query("INSERT INTO schema_migrations (id) VALUES ($1) ON CONFLICT DO NOTHING")
            .bind(id)
            .execute(pool)
            .await
            .map_err(|e| ProvisionerError::ShardEffect(format!("mark {id}: {e}")))?;
        newly += 1;
    }
    Ok(newly)
}

/// Pull `- id: "<stem>"` out of the manifest, in file order.
fn parse_manifest_ids(text: &str) -> Vec<String> {
    text.lines()
        .map(str::trim)
        .filter(|l| !l.starts_with('#'))
        .filter_map(|l| l.strip_prefix("- id:"))
        .filter_map(|rest| {
            let rest = rest.trim();
            rest.strip_prefix('"')
                .and_then(|r| r.split_once('"'))
                .map(|(id, _)| id.to_string())
        })
        .collect()
}

#[cfg(test)]
mod manifest_tests {
    use super::parse_manifest_ids;

    #[test]
    fn reads_ids_in_order_and_ignores_comments() {
        let text = "# - id: \"0000_commented_out\"\n\
                    migrations:\n  \
                    - id: \"0001_initial\"\n    version: 1\n  \
                    - id: \"0002_events_table\"\n    version: 2\n";
        assert_eq!(
            parse_manifest_ids(text),
            vec!["0001_initial".to_string(), "0002_events_table".to_string()]
        );
    }

    #[test]
    fn a_commented_entry_is_not_a_migration() {
        // The manifest carries long `#` comment blocks that QUOTE entry syntax
        // when explaining a deferral; reading one as a real id would make the
        // provisioner look for a file that does not exist.
        assert!(parse_manifest_ids("  # - id: \"0009_canon_projection\"\n").is_empty());
    }

    #[test]
    fn the_real_manifest_parses_and_is_ordered() {
        // Non-vacuity: this test is worthless if it runs against a fixture. It
        // reads the SHIPPED manifest, so deleting an entry or breaking the
        // format reds here as well as in the Python gate.
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../contracts/migrations/manifest.yaml");
        let text = std::fs::read_to_string(path).expect("the shipped manifest must be readable");
        let ids = parse_manifest_ids(&text);
        // The count is a smoke check on the PARSER (did it return garbage or
        // nothing?), deliberately loose: it was `>= 15` and broke the moment
        // `0008_pgvector_setup` was correctly unregistered for `1b14-05`. A test
        // that fails when a deliberate decision is made is a test that gets its
        // number bumped without being read. The two assertions BELOW are the
        // ones with content.
        assert!(ids.len() >= 10, "the parser returned too little to be the manifest: {ids:?}");
        assert_eq!(ids.first().map(String::as_str), Some("0001_initial"));
        assert!(
            ids.contains(&"0019_channels".to_string()),
            "0019_channels must be registered or a provisioned reality has no `channels` table"
        );
        // `0008` requires pgvector. It was briefly UNregistered (`1b14-05`,
        // because `postgres:18-alpine` has none and the provisioner therefore
        // died at migration 8 of 15), and this assertion was its inverse. The
        // image now builds pgvector from source against its own `pg_config`
        // (`infra/postgres-pgvector.Dockerfile`), so the assertion flips: the
        // thing to guard is that a migration needing an extension does not get
        // registered while the image cannot supply it.
        assert!(
            ids.contains(&"0008_pgvector_setup".to_string()),
            "0008_pgvector_setup is registered nowhere — if the image lost pgvector, unregister it \
             in the manifest AND add its UNREGISTERED row back, rather than leaving the \
             provisioner to die on every new reality"
        );
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
            req.owner_user_id,
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
            let exists: Option<i32> =
                sqlx::query_scalar("SELECT 1 FROM pg_database WHERE datname = $1")
                    .bind(&name)
                    .fetch_optional(&pool)
                    .await
                    .map_err(|e| ProvisionerError::ShardEffect(format!("db exists check: {e}")))?;
            if exists.is_none() {
                // Simple query protocol (&str) — CREATE DATABASE can't run
                // prepared/in a tx.
                sqlx::raw_sql(&format!("CREATE DATABASE {name}"))
                    .execute(&pool)
                    .await
                    .map_err(|e| ProvisionerError::ShardEffect(format!("create database: {e}")))?;
            }
            // I4 isolation: ALWAYS (re)apply REVOKE CONNECT FROM PUBLIC, even on
            // the idempotent re-entry where the DB already existed (review #2).
            // A crash BETWEEN create and revoke would otherwise leave the DB
            // un-isolated forever — the re-run skips create but must still close
            // the isolation. REVOKE is idempotent, so re-applying is a no-op.
            sqlx::raw_sql(&format!("REVOKE CONNECT ON DATABASE {name} FROM PUBLIC"))
                .execute(&pool)
                .await
                .map_err(|e| ProvisionerError::ShardEffect(format!("revoke connect: {e}")))?;
            Ok(exists.is_none())
        })
    }

    fn apply_migrations(
        &mut self,
        _shard: &ShardId,
        db_name: &str,
    ) -> Result<bool, ProvisionerError> {
        safe_ident(db_name)?;

        // ⚠ REWRITTEN 2026-08-08 (`1b12-05`). This applied `0001_initial.up.sql`
        // and nothing else, so **a freshly provisioned reality got the cycle-5
        // skeleton and none of the eighteen migrations after it** — no
        // `channels`, no writer lease, no ruleset digest. `1b7gap-H1` registered
        // `0014`-`0019` in the manifest and I claimed that "changes what the
        // orchestrator applies". A cold-start verifier measured that it does
        // not: registration is necessary and **not sufficient**, because nothing
        // read the manifest here and `migrate` takes one id at a time with no
        // apply-pending path. The claim was false and the table still could not
        // exist in a real database.
        //
        // The manifest is the ORDER, not the directory listing: `0009`-`0012`
        // are deliberately unregistered (they belong to the projection
        // harnesses), so globbing `*.up.sql` would apply four files the
        // orchestrator is not supposed to own. `scripts/migration-manifest-gate.py`
        // keeps the manifest and the directory in agreement.
        let ids = self.manifest_ids()?;
        let mut sqls = Vec::with_capacity(ids.len());
        for id in &ids {
            let path = format!("{}/{id}.up.sql", self.sql_dir);
            let sql = std::fs::read_to_string(&path)
                .map_err(|e| ProvisionerError::ShardEffect(format!("read {path}: {e}")))?;
            sqls.push((id.clone(), sql));
        }

        let dsn = self.reality_dsn(db_name);
        self.handle.clone().block_on(async move {
            let pool = sqlx::PgPool::connect(&dsn)
                .await
                .map_err(|e| ProvisionerError::ShardEffect(format!("connect new db: {e}")))?;
            let newly = apply_pending(&pool, &sqls).await;
            pool.close().await;
            // `false` = nothing to do, which is what the step contract means by
            // idempotent: a completed reality re-provisions to a no-op. The
            // ledger is what makes that TRUE rather than merely documented --
            // see `apply_pending`, and `1b14-01` for what it cost to find out.
            Ok(newly? > 0)
        })
    }

    // (see `manifest_ids` below the impl — a helper, not a trait method)

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
