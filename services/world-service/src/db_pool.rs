//! L1.G.3 — App-side pool wrapper for pgbouncer.
//!
//! ## Per-shard-host pool contract (R04 §12D.4)
//!
//! ONE pool per **shard host**, NOT per per-reality DB. The pool's
//! connections are virtual — pgbouncer multiplexes them to a smaller
//! backend pool. So the app sees:
//!
//! ```text
//!   world-service ─┐
//!                  ├─→ pool(pg-shard-0)  ─→ pgbouncer:6432  ─→ Postgres backend (500 real)
//!   travel-service ┘                                   ↑
//!                                          5000 virtual ┘
//! ```
//!
//! ## Why per-host and not per-DB
//!
//! pgbouncer's transaction-pooling mode shares one server-side connection
//! across many client-side connections, but the server-side connection
//! cannot switch DATABASES mid-transaction. So we accept "1 pool per
//! shard host" and `SET search_path = lw_reality_<id>` per transaction
//! to scope reads/writes to the right reality. This trades a tiny per-
//! query overhead for a huge connection-count reduction (1 pool × 5000
//! vs 1000s of realities × 100).
//!
//! ## Why transaction mode (not session)
//!
//! Per Q-L1G-1 lock-in:
//!
//! > Stick with pgbouncer (vs pgcat/Odyssey)? **YES; re-evaluate trigger =
//! > transaction-pool limits hit V3.**
//!
//! Session pooling pins one server connection per client — caps multiplex
//! at backend count. Statement pooling breaks multi-statement transactions.
//! Transaction pooling is the V1 default; consequences (no session-scoped
//! advisory locks, no `LISTEN`/`NOTIFY`, no prepared statements without
//! `default_pool_size = 0` carve-outs) are documented in
//! `runbooks/pgbouncer/connection_exhaustion.md`.
//!
//! ## Cap arithmetic (R04 §12D.4)
//!
//! - `max_client_conn = 5000`  — virtual cap per pgbouncer instance
//! - `default_pool_size = 25`  — backend connections per (db, user) pair
//! - `min_pool_size = 5`       — warm pool baseline
//! - `reserve_pool_size = 5`   — emergency spill above default_pool_size
//! - Backend cap = `default_pool_size + reserve_pool_size` × distinct
//!   (db, user) pairs. With 20 per-shard realities + 1 user: 500 real.
//!
//! The registry below enforces these caps at registration time so a
//! mis-configured DPS can't silently exceed them.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::RwLock;

use crate::errors::ProvisionerError;

/// Maximum **virtual** client connections per pgbouncer instance.
pub const MAX_VIRTUAL_CONNECTIONS: u32 = 5000;
/// Maximum **real** backend Postgres connections per pgbouncer instance.
pub const MAX_BACKEND_CONNECTIONS: u32 = 500;

/// A shard host (typically `pg-shard-N.internal`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct ShardHost(pub String);

impl ShardHost {
    /// Construct from a string slice.
    pub fn new(s: impl Into<String>) -> Self {
        Self(s.into())
    }

    /// Borrow the inner string.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// Connection role — separate pools per role so a runaway analytic
/// `reader` query doesn't starve `writer` quota.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum PoolRole {
    /// Writer pool — routes to the Patroni leader.
    Writer,
    /// Reader pool — routes to the sync replica (read-after-write).
    Reader,
    /// Async reader pool — routes to the async replica (dashboards).
    AsyncReader,
}

/// Composite key for the pool registry — unique per (host, role).
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct DbPoolKey {
    /// Shard host (matches the pgbouncer instance).
    pub host: ShardHost,
    /// Connection role.
    pub role: PoolRole,
}

/// Per-pool configuration. Mirrors the subset of pgbouncer.ini fields the
/// app needs to know about for capacity arithmetic.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DbPoolConfig {
    /// pgbouncer host:port — typically `<shard>:6432`.
    pub pgbouncer_endpoint: String,
    /// Virtual client connections this pool requests.
    pub max_client_conn: u32,
    /// Backend connection cap (pgbouncer `default_pool_size`).
    pub default_pool_size: u32,
    /// Reserve pool (pgbouncer `reserve_pool_size`).
    pub reserve_pool_size: u32,
    /// Min warm connections.
    pub min_pool_size: u32,
}

impl DbPoolConfig {
    /// Computed cap = default + reserve. Compared against
    /// `MAX_BACKEND_CONNECTIONS` for the host.
    pub fn backend_cap(&self) -> u32 {
        self.default_pool_size + self.reserve_pool_size
    }

    /// Validates the config in isolation (no cross-pool checks).
    pub fn validate(&self) -> Result<(), ProvisionerError> {
        if self.pgbouncer_endpoint.trim().is_empty() {
            return Err(ProvisionerError::DbPoolInvalid("endpoint empty".into()));
        }
        if self.max_client_conn == 0 {
            return Err(ProvisionerError::DbPoolInvalid(
                "max_client_conn must be > 0".into(),
            ));
        }
        if self.max_client_conn > MAX_VIRTUAL_CONNECTIONS {
            return Err(ProvisionerError::DbPoolInvalid(format!(
                "max_client_conn {} > MAX_VIRTUAL_CONNECTIONS {}",
                self.max_client_conn, MAX_VIRTUAL_CONNECTIONS
            )));
        }
        if self.default_pool_size == 0 {
            return Err(ProvisionerError::DbPoolInvalid(
                "default_pool_size must be > 0".into(),
            ));
        }
        if self.min_pool_size > self.default_pool_size {
            return Err(ProvisionerError::DbPoolInvalid(format!(
                "min_pool_size {} > default_pool_size {}",
                self.min_pool_size, self.default_pool_size
            )));
        }
        if self.backend_cap() > MAX_BACKEND_CONNECTIONS {
            return Err(ProvisionerError::DbPoolInvalid(format!(
                "backend_cap {} > MAX_BACKEND_CONNECTIONS {}",
                self.backend_cap(),
                MAX_BACKEND_CONNECTIONS
            )));
        }
        Ok(())
    }
}

/// L1.G.3 — per-shard-host pool registry.
///
/// Thread-safe via `RwLock`. Caller registers (host, role, config) at
/// startup; subsequent `lookup()` calls are read-only.
///
/// **Crucially**: the registry validates the **aggregate** backend
/// connection count at registration time. If adding a new pool would
/// push `(per-host) sum(backend_cap)` over `MAX_BACKEND_CONNECTIONS`,
/// the registration is rejected with `DbPoolInvalid`. This catches
/// config drift before it overruns pgbouncer in production.
pub struct DbPoolRegistry {
    inner: RwLock<HashMap<DbPoolKey, DbPoolConfig>>,
}

impl Default for DbPoolRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl DbPoolRegistry {
    /// Empty registry.
    pub fn new() -> Self {
        Self { inner: RwLock::new(HashMap::new()) }
    }

    /// Register a pool. Returns:
    ///
    /// - `Ok(())` on success
    /// - `Err(DbPoolConflict)` if the same key is already registered with
    ///   a DIFFERENT config (idempotent re-register with identical config
    ///   succeeds)
    /// - `Err(DbPoolInvalid)` if the config is malformed OR aggregate
    ///   per-host backend cap would be exceeded
    pub fn register(
        &self,
        key: DbPoolKey,
        config: DbPoolConfig,
    ) -> Result<(), ProvisionerError> {
        config.validate()?;
        let mut g = self.inner.write().unwrap();
        if let Some(existing) = g.get(&key) {
            if *existing == config {
                return Ok(()); // idempotent
            }
            return Err(ProvisionerError::DbPoolConflict(key));
        }
        // Aggregate per-host backend count
        let per_host_sum: u32 = g
            .iter()
            .filter(|(k, _)| k.host == key.host)
            .map(|(_, c)| c.backend_cap())
            .sum::<u32>()
            + config.backend_cap();
        if per_host_sum > MAX_BACKEND_CONNECTIONS {
            return Err(ProvisionerError::DbPoolInvalid(format!(
                "per-host {:?} aggregate backend_cap {} > {}",
                key.host, per_host_sum, MAX_BACKEND_CONNECTIONS
            )));
        }
        g.insert(key, config);
        Ok(())
    }

    /// Look up a registered pool config.
    pub fn lookup(&self, key: &DbPoolKey) -> Result<DbPoolConfig, ProvisionerError> {
        let g = self.inner.read().unwrap();
        g.get(key)
            .cloned()
            .ok_or_else(|| ProvisionerError::DbPoolMissing(key.clone()))
    }

    /// Total pools currently registered (across all hosts).
    pub fn len(&self) -> usize {
        self.inner.read().unwrap().len()
    }

    /// True if no pools registered.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg(default: u32, reserve: u32) -> DbPoolConfig {
        DbPoolConfig {
            pgbouncer_endpoint: "pg-shard-0:6432".into(),
            max_client_conn: 1000,
            default_pool_size: default,
            reserve_pool_size: reserve,
            min_pool_size: 5,
        }
    }

    fn key(host: &str, role: PoolRole) -> DbPoolKey {
        DbPoolKey { host: ShardHost::new(host), role }
    }

    #[test]
    fn register_lookup_roundtrip() {
        let reg = DbPoolRegistry::new();
        let k = key("pg-shard-0", PoolRole::Writer);
        reg.register(k.clone(), cfg(25, 5)).expect("ok");
        let got = reg.lookup(&k).expect("ok");
        assert_eq!(got.default_pool_size, 25);
    }

    #[test]
    fn idempotent_reregister_same_config() {
        let reg = DbPoolRegistry::new();
        let k = key("pg-shard-0", PoolRole::Writer);
        reg.register(k.clone(), cfg(25, 5)).expect("ok 1");
        reg.register(k, cfg(25, 5)).expect("ok 2");
    }

    #[test]
    fn conflict_on_different_config() {
        let reg = DbPoolRegistry::new();
        let k = key("pg-shard-0", PoolRole::Writer);
        reg.register(k.clone(), cfg(25, 5)).expect("ok");
        let err = reg.register(k, cfg(50, 5)).unwrap_err();
        assert!(matches!(err, ProvisionerError::DbPoolConflict(_)));
    }

    #[test]
    fn rejects_zero_max_client_conn() {
        let reg = DbPoolRegistry::new();
        let mut c = cfg(25, 5);
        c.max_client_conn = 0;
        let err = reg
            .register(key("pg-shard-0", PoolRole::Writer), c)
            .unwrap_err();
        assert!(matches!(err, ProvisionerError::DbPoolInvalid(_)));
    }

    #[test]
    fn rejects_client_conn_over_5000_cap() {
        let reg = DbPoolRegistry::new();
        let mut c = cfg(25, 5);
        c.max_client_conn = 5001;
        let err = reg
            .register(key("pg-shard-0", PoolRole::Writer), c)
            .unwrap_err();
        assert!(matches!(err, ProvisionerError::DbPoolInvalid(_)));
    }

    #[test]
    fn rejects_min_pool_over_default() {
        let reg = DbPoolRegistry::new();
        let mut c = cfg(10, 5);
        c.min_pool_size = 20;
        let err = reg
            .register(key("pg-shard-0", PoolRole::Writer), c)
            .unwrap_err();
        assert!(matches!(err, ProvisionerError::DbPoolInvalid(_)));
    }

    #[test]
    fn per_host_aggregate_cap_enforced() {
        let reg = DbPoolRegistry::new();
        // 3 roles × 250 + 5 reserve each = 765 — over 500 backend cap.
        // Register writer first (255). reader (255 ⇒ 510) should reject.
        reg.register(key("pg-shard-0", PoolRole::Writer), cfg(250, 5))
            .expect("writer ok");
        let err = reg
            .register(key("pg-shard-0", PoolRole::Reader), cfg(250, 5))
            .unwrap_err();
        assert!(matches!(err, ProvisionerError::DbPoolInvalid(_)));
    }

    #[test]
    fn per_host_aggregate_cap_under_limit_ok() {
        let reg = DbPoolRegistry::new();
        // Two roles at backend_cap=200+50=250 each = 500 total → exactly at cap, OK.
        reg.register(key("pg-shard-0", PoolRole::Writer), cfg(200, 50))
            .expect("writer ok");
        reg.register(key("pg-shard-0", PoolRole::Reader), cfg(200, 50))
            .expect("reader ok");
    }

    #[test]
    fn different_hosts_have_independent_caps() {
        let reg = DbPoolRegistry::new();
        reg.register(key("pg-shard-0", PoolRole::Writer), cfg(250, 5))
            .expect("ok");
        // Same writer config on a DIFFERENT host — should succeed, fresh budget.
        reg.register(key("pg-shard-1", PoolRole::Writer), cfg(250, 5))
            .expect("ok");
        assert_eq!(reg.len(), 2);
    }

    #[test]
    fn missing_key_returns_typed_error() {
        let reg = DbPoolRegistry::new();
        let err = reg.lookup(&key("nothere", PoolRole::Reader)).unwrap_err();
        assert!(matches!(err, ProvisionerError::DbPoolMissing(_)));
    }
}
