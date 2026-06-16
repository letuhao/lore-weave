//! axum `/healthz` + `/readyz` + `/metrics` surface (DEFERRED-059 part 5).
//!
//! Mirrors the Go workers' ops endpoints (publisher/archive/retention) using
//! the repo's Rust HTTP convention (axum — already used by tilemap-service).

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use axum::Router;
use axum::extract::State;
use axum::http::{StatusCode, header};
use axum::response::IntoResponse;
use axum::routing::get;

use super::metrics::Metrics;

/// Shared HTTP state: the metrics registry + a readiness flag the worker flips
/// to `false` while draining on shutdown.
#[derive(Clone)]
pub struct AppState {
    /// Metrics registry (encoded by `/metrics`).
    pub metrics: Arc<Metrics>,
    /// Readiness flag — `/readyz` returns 503 when this is `false`.
    pub ready: Arc<AtomicBool>,
}

/// Build the worker's HTTP router.
pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/readyz", get(readyz))
        .route("/metrics", get(metrics_handler))
        .with_state(state)
}

async fn healthz() -> impl IntoResponse {
    (StatusCode::OK, "ok")
}

async fn readyz(State(state): State<AppState>) -> impl IntoResponse {
    if state.ready.load(Ordering::SeqCst) {
        (StatusCode::OK, "ready")
    } else {
        (StatusCode::SERVICE_UNAVAILABLE, "draining")
    }
}

async fn metrics_handler(State(state): State<AppState>) -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/plain; version=0.0.4")],
        state.metrics.encode(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn readiness_flag_round_trips() {
        let ready = Arc::new(AtomicBool::new(true));
        assert!(ready.load(Ordering::SeqCst));
        ready.store(false, Ordering::SeqCst);
        assert!(!ready.load(Ordering::SeqCst));
    }
}
