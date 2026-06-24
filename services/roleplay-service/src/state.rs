//! Shared application state + the `crates/service-http` trait wiring.
//!
//! `AppState` is the single state threaded through the axum router. It
//! implements the kit's [`HasJwtSecret`] / [`HasInternalToken`] / [`HasPool`]
//! traits so the shared `require_user` / `require_internal` / `readyz`
//! middleware resolve their secrets + pool from here.

use std::sync::Arc;

use service_http::{HasInternalToken, HasJwtSecret, HasPool};
use sqlx::PgPool;

use crate::config::Config;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    jwt_secret: Arc<[u8]>,
    internal_token: Arc<str>,
    /// Base URL of chat-service for the start-orchestration call (R1).
    pub chat_url: Arc<str>,
    /// Reused HTTP client for the chat-service internal call (R1).
    pub http: reqwest::Client,
}

impl AppState {
    pub fn new(pool: PgPool, config: &Config) -> Self {
        Self {
            pool,
            jwt_secret: Arc::from(config.jwt_secret.as_bytes()),
            internal_token: Arc::from(config.internal_token.as_str()),
            chat_url: Arc::from(config.chat_url.trim_end_matches('/')),
            http: reqwest::Client::new(),
        }
    }
}

impl HasJwtSecret for AppState {
    fn jwt_secret(&self) -> &[u8] {
        &self.jwt_secret
    }
}

impl HasInternalToken for AppState {
    fn internal_token(&self) -> &str {
        &self.internal_token
    }
}

impl HasPool for AppState {
    fn pool(&self) -> &PgPool {
        &self.pool
    }
}
