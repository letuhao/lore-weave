//! # service-http
//!
//! Shared HTTP infrastructure for LoreWeave's Rust services. The axum skeleton
//! reached its third copy (tilemap, world, now roleplay) — rule-of-three:
//! extract. And `require_user` is a security primitive that must live once.
//!
//! This crate provides the generic plumbing; each service still owns its
//! routes, handlers, error enum, and config struct.
//!
//! ```text
//! serve(addr, router)            graceful-shutdown axum server
//! health::routes::<S>()          /livez /readyz (DB-aware) /metrics
//! ProblemDetails                 RFC 7807 + FE-readable `message`
//! require_user / require_internal JWT (HS256, sub→UserId) + X-Internal-Token
//! trace::init_tracing / propagate JSON logs + X-Trace-Id in/out
//! metrics::record                prometheus request count/latency
//! config::require_env / optional_env  fail-closed env reading
//! db::init(url, migrator)        PgPool + sqlx::migrate!
//! ```
//!
//! roleplay-service is the first consumer (built on it day one). tilemap/world
//! migrate opportunistically when next touched — not a forced refactor.

pub mod auth;
pub mod config;
pub mod db;
pub mod error;
pub mod health;
pub mod metrics;
pub mod trace;

use std::net::SocketAddr;

use axum::Router;

pub use auth::{HasInternalToken, HasJwtSecret, UserId, require_internal, require_user};
pub use error::ProblemDetails;
pub use health::HasPool;
pub use trace::{TraceId, init_tracing};

/// Bind on `addr` and serve `router` until Ctrl-C / SIGTERM, then drain.
pub async fn serve(addr: SocketAddr, router: Router) -> anyhow::Result<()> {
    let listener = tokio::net::TcpListener::bind(addr).await?;
    let bound = listener.local_addr()?;
    tracing::info!(%bound, "HTTP listening");
    axum::serve(listener, router)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    tracing::info!("HTTP shut down cleanly");
    Ok(())
}

/// Resolve on the first of Ctrl-C or SIGTERM (Unix). Docker-compose sends
/// SIGTERM on `down`; without this the container is hard-killed after the
/// grace period, dropping in-flight requests.
async fn shutdown_signal() {
    let ctrl_c = async {
        if let Err(err) = tokio::signal::ctrl_c().await {
            tracing::warn!(%err, "installing Ctrl-C handler failed");
        }
    };

    #[cfg(unix)]
    let terminate = async {
        use tokio::signal::unix::{SignalKind, signal};
        match signal(SignalKind::terminate()) {
            Ok(mut s) => {
                s.recv().await;
            }
            Err(err) => {
                tracing::warn!(%err, "installing SIGTERM handler failed");
                std::future::pending::<()>().await
            }
        }
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => tracing::info!("received Ctrl-C — graceful shutdown"),
        _ = terminate => tracing::info!("received SIGTERM — graceful shutdown"),
    }
}
