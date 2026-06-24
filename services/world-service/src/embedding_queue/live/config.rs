//! Environment-driven config for the `embedding-worker` binary.
//!
//! V1 single-process scope (Q-L1L-1: world-service N=1 replica). The worker
//! binds ONE per-reality DB pool (from env) + the meta DB pool (for audit).
//! Multi-reality enumeration via `reality_registry` mirrors the publisher's
//! "load active realities" path and is a tracked follow-up (same shape as the
//! publisher's `D-PUBLISHER-REALITY-REFRESH`, row 081) — deferred because the
//! enqueue trigger + provider gateway are themselves deferred, so a multi-pool
//! fan-out would have nothing to drain yet.

use std::net::SocketAddr;
use std::time::Duration;

use uuid::Uuid;

/// Resolved worker configuration. All fields come from env; the binary fails
/// to start (fail-closed, no defaults for secrets/DSNs) if a required var is
/// missing — matching the "No hardcoded secrets" rule.
#[derive(Debug, Clone)]
pub struct Config {
    /// Meta DB DSN (holds `service_to_service_audit`).
    pub meta_db_url: String,
    /// Per-reality DB DSN (holds `npc_session_memory_embedding`).
    pub reality_db_url: String,
    /// The reality this worker instance drains.
    pub reality_id: Uuid,
    /// `/healthz`+`/readyz`+`/metrics` bind address.
    pub http_addr: SocketAddr,
    /// Drain tick interval.
    pub tick_interval: Duration,
    /// Max items drained per tick (bounds wall time per pass).
    pub batch_size: usize,
    /// In-memory queue soft capacity (backpressure threshold).
    pub queue_capacity: usize,
}

impl Config {
    /// Build from process env. Returns a flat error listing every missing /
    /// malformed required var so an operator fixes them in one pass.
    pub fn from_env() -> Result<Self, String> {
        let mut missing: Vec<String> = Vec::new();
        let req = |key: &str, missing: &mut Vec<String>| -> String {
            match std::env::var(key) {
                Ok(v) if !v.is_empty() => v,
                _ => {
                    missing.push(key.to_string());
                    String::new()
                }
            }
        };

        let meta_db_url = req("EMBEDDING_META_DB_URL", &mut missing);
        let reality_db_url = req("EMBEDDING_REALITY_DB_URL", &mut missing);
        let reality_id_raw = req("EMBEDDING_REALITY_ID", &mut missing);

        if !missing.is_empty() {
            return Err(format!("missing required env: {missing:?}"));
        }

        let reality_id = Uuid::parse_str(&reality_id_raw)
            .map_err(|e| format!("EMBEDDING_REALITY_ID is not a UUID: {e}"))?;

        let http_addr: SocketAddr = std::env::var("EMBEDDING_HTTP_ADDR")
            .unwrap_or_else(|_| "0.0.0.0:8080".to_string())
            .parse()
            .map_err(|e| format!("EMBEDDING_HTTP_ADDR invalid: {e}"))?;

        let tick_secs = parse_u64_env("EMBEDDING_TICK_SECS", 5)?;
        if tick_secs == 0 {
            // tokio::time::interval panics on a zero period — reject in config
            // validation rather than crashing the worker at startup.
            return Err("EMBEDDING_TICK_SECS must be > 0".to_string());
        }
        let tick_interval = Duration::from_secs(tick_secs);

        let batch_size = parse_usize_env("EMBEDDING_BATCH_SIZE", 64)?;
        if batch_size == 0 {
            // process_batch(0) drains nothing every tick — a healthy-looking
            // but dead worker. Fail config instead of silently stalling.
            return Err("EMBEDDING_BATCH_SIZE must be > 0".to_string());
        }
        let queue_capacity = parse_usize_env("EMBEDDING_QUEUE_CAPACITY", 10_000)?;
        if queue_capacity == 0 {
            // A zero-capacity queue rejects every enqueue at the backpressure
            // check (depth 0 >= 0) — nothing is ever drainable.
            return Err("EMBEDDING_QUEUE_CAPACITY must be > 0".to_string());
        }

        Ok(Self {
            meta_db_url,
            reality_db_url,
            reality_id,
            http_addr,
            tick_interval,
            batch_size,
            queue_capacity,
        })
    }
}

fn parse_u64_env(key: &str, default: u64) -> Result<u64, String> {
    match std::env::var(key) {
        Ok(v) if !v.is_empty() => v.parse().map_err(|e| format!("{key} invalid: {e}")),
        _ => Ok(default),
    }
}

fn parse_usize_env(key: &str, default: usize) -> Result<usize, String> {
    match std::env::var(key) {
        Ok(v) if !v.is_empty() => v.parse().map_err(|e| format!("{key} invalid: {e}")),
        _ => Ok(default),
    }
}
