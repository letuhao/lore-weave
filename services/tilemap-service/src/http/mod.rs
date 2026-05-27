//! HTTP server surface for tilemap-service.
//!
//! Single endpoint today (spec
//! `docs/specs/2026-05-24-tilemap-http-render-endpoint.md`):
//!
//! ```text
//! POST /internal/v1/tilemaps/render
//! Authorization: Bearer <LOREWEAVE_INTERNAL_TOKEN>
//! Content-Type: application/json
//! ```
//!
//! Returns the existing `TilemapView` JSON on 200; RFC 7807 `problem+json`
//! on every error path. The server is launched by the `serve` subcommand
//! on `main.rs` and stays out of the existing CLI subcommands' paths.

pub mod auth;
pub mod error;
pub mod health;
pub mod render;
pub mod router;

pub use auth::AppState;
pub use error::ProblemDetails;
pub use router::build_router;

use std::net::SocketAddr;

/// Validate the `LOREWEAVE_INTERNAL_TOKEN` env value retrieved by `getter`.
///
/// Returns the token on success; returns a structured error if the env
/// var is missing or empty — spec AC-HTTP-9 forbids silent dev-mode
/// bypass. Parameterized on `getter` so a test can inject a closure
/// returning `None` without touching the real process environment.
pub fn require_internal_token<F>(getter: F) -> anyhow::Result<String>
where
    F: FnOnce() -> Option<String>,
{
    let raw = getter().ok_or_else(|| {
        anyhow::anyhow!(
            "LOREWEAVE_INTERNAL_TOKEN is REQUIRED — `serve` refuses to start without it"
        )
    })?;
    // LOW-4 from /review-impl: trim accidental shell-quoting / heredoc
    // pollution. A trailing newline in the env value would otherwise
    // produce a byte-mismatch against every client's Bearer token with
    // no diagnostic. Trim first, THEN check empty so "   " is also
    // rejected.
    let token = raw.trim().to_string();
    if token.is_empty() {
        anyhow::bail!(
            "LOREWEAVE_INTERNAL_TOKEN is set but empty (or whitespace-only) — refusing to start"
        );
    }
    if token != raw {
        tracing::warn!(
            "LOREWEAVE_INTERNAL_TOKEN had leading/trailing whitespace — trimmed; \
             clients must send the trimmed value"
        );
    }
    Ok(token)
}

/// Bind on `addr` and serve the tilemap HTTP API until process exit.
///
/// Fails fast if the listener cannot bind. The caller is responsible for
/// passing `internal_token` — read from `LOREWEAVE_INTERNAL_TOKEN` in
/// `main.rs` (or directly in tests).
pub async fn serve(addr: SocketAddr, internal_token: String) -> anyhow::Result<()> {
    let state = AppState::new(internal_token);
    let router = build_router(state);
    let listener = tokio::net::TcpListener::bind(addr).await?;
    let bound = listener.local_addr()?;
    tracing::info!(%bound, "tilemap-service HTTP listening");
    axum::serve(listener, router)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    tracing::info!("tilemap-service HTTP shut down cleanly");
    Ok(())
}

/// Resolve on the first of: Ctrl-C, or SIGTERM (Unix only).
/// Docker-compose sends SIGTERM on `down`; without this future the
/// container would be hard-killed after the grace period, dropping
/// in-flight requests (MED-3 from /review-impl).
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
        _ = ctrl_c => tracing::info!("received Ctrl-C — initiating graceful shutdown"),
        _ = terminate => tracing::info!("received SIGTERM — initiating graceful shutdown"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ac_http_9_missing_token_refuses_to_start() {
        // Spec §9 AC-HTTP-9: the boot guard MUST reject a missing env
        // var with a clear error — no silent dev-mode bypass. Inject a
        // None-returning getter so the test doesn't touch the real
        // process environment.
        let err = require_internal_token(|| None).expect_err("missing token must fail");
        let msg = err.to_string();
        assert!(
            msg.contains("LOREWEAVE_INTERNAL_TOKEN"),
            "error must name the env var; got: {msg}"
        );
        assert!(msg.contains("REQUIRED"), "error must say REQUIRED; got: {msg}");
    }

    #[test]
    fn empty_token_refuses_to_start() {
        let err = require_internal_token(|| Some(String::new()))
            .expect_err("empty token must fail");
        assert!(err.to_string().contains("empty"));
    }

    #[test]
    fn non_empty_token_returns_ok() {
        let token = require_internal_token(|| Some("s3cret".to_string())).unwrap();
        assert_eq!(token, "s3cret");
    }

    #[test]
    fn low_4_whitespace_only_token_refuses_to_start() {
        // LOW-4 regression: a tab/space/newline-only value would have
        // passed the old `is_empty` check, then silently broken every
        // request via byte-mismatch in the Bearer middleware.
        let err = require_internal_token(|| Some("   \n\t".to_string()))
            .expect_err("whitespace-only token must fail");
        assert!(err.to_string().contains("whitespace-only"));
    }

    #[test]
    fn low_4_token_with_surrounding_whitespace_is_trimmed() {
        // A value like "s3cret\n" (heredoc trailing newline) returns the
        // trimmed token — clients pasting `s3cret` will now match.
        let token = require_internal_token(|| Some("  s3cret\n".to_string())).unwrap();
        assert_eq!(token, "s3cret");
    }
}
