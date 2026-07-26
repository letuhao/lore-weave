//! Fail-closed service config, read from the environment at boot.

use std::net::SocketAddr;

use anyhow::Context;
use service_http::config::{optional_env, require_env};

/// Resolved runtime configuration. Secrets are REQUIRED — the binary refuses
/// to start if any is missing (CLAUDE.md "no hardcoded secrets").
#[derive(Clone, Debug)]
pub struct Config {
    pub bind: SocketAddr,
    pub database_url: String,
    pub jwt_secret: String,
    pub internal_token: String,
    pub chat_url: String,
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        let bind = optional_env("ROLEPLAY_HTTP_BIND", "0.0.0.0:7110")
            .parse::<SocketAddr>()
            .context("ROLEPLAY_HTTP_BIND must be a valid SocketAddr (e.g. 0.0.0.0:7110)")?;
        Ok(Self {
            bind,
            database_url: require_env("DATABASE_URL")?,
            jwt_secret: require_env("JWT_SECRET")?,
            // Compose rewrites INTERNAL_SERVICE_TOKEN → LOREWEAVE_INTERNAL_TOKEN
            // (the tilemap convention); read the binary-facing name.
            internal_token: require_env("LOREWEAVE_INTERNAL_TOKEN")?,
            chat_url: require_env("CHAT_SERVICE_URL")?,
        })
    }
}
