//! Shared application state + the `crates/service-http` trait wiring.

use std::sync::Arc;

use service_http::{HasInternalToken, HasPool};
use sqlx::PgPool;

use crate::capacity_planner::{CapacityPlanner, CapacityThresholds};
use crate::provision_flow::EffectsConfig;
use crate::server::config::Config;

/// The single state threaded through the axum router.
///
/// It implements [`HasInternalToken`] and [`HasPool`] so the shared
/// `require_internal` middleware and the `readyz` probe resolve their token and
/// pool from here. It deliberately does **not** implement `HasJwtSecret`: this
/// surface is internal by `WS-F4`, and a service with no user-JWT routes should
/// not be carrying a user-JWT secret.
#[derive(Clone)]
pub struct AppState {
    /// Meta database — `reality_registry` + `shard_utilization`. Also the pool
    /// the readiness probe pings, because a world-service that cannot reach
    /// meta cannot provision anything.
    pub meta: PgPool,
    /// The shard's maintenance database, used for `CREATE DATABASE`.
    pub shard_admin: PgPool,
    /// Capacity thresholds, fixed for the process lifetime.
    pub planner: Arc<CapacityPlanner>,
    /// Everything the provisioning effects need.
    pub effects: Arc<EffectsConfig>,
    internal_token: Arc<str>,
}

impl AppState {
    /// Assemble from the two live pools and the resolved config.
    pub fn new(meta: PgPool, shard_admin: PgPool, config: &Config) -> Self {
        Self {
            meta,
            shard_admin,
            planner: Arc::new(CapacityPlanner::new(CapacityThresholds::default())),
            effects: Arc::new(config.effects.clone()),
            internal_token: Arc::from(config.internal_token.as_str()),
        }
    }
}

impl HasInternalToken for AppState {
    fn internal_token(&self) -> &str {
        &self.internal_token
    }
}

impl HasPool for AppState {
    fn pool(&self) -> &PgPool {
        &self.meta
    }
}
