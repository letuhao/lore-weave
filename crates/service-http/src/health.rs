//! Liveness + readiness probes (k8s-style), DB-aware.
//!
//! `/livez`  — the process is alive (always 200 if the binary runs).
//! `/readyz` — ready to serve: pings the Postgres pool, 503 if unreachable.
//! `/metrics` — prometheus text exposition (see [`crate::metrics`]).
//!
//! None are auth-gated — docker healthcheck / load-balancer probes hit them
//! without a token.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Router;
use serde::Serialize;
use sqlx::PgPool;

/// Consumer state that exposes the Postgres pool for the readiness probe.
pub trait HasPool: Clone + Send + Sync + 'static {
    fn pool(&self) -> &PgPool;
}

#[derive(Debug, Serialize)]
pub struct HealthBody {
    pub status: &'static str,
    pub endpoint: &'static str,
}

/// `GET /livez` — process liveness; always 200 while the binary runs.
pub async fn livez() -> (StatusCode, Json<HealthBody>) {
    (StatusCode::OK, Json(HealthBody { status: "ok", endpoint: "livez" }))
}

/// `GET /readyz` — readiness; pings the pool, 503 if the DB is unreachable.
pub async fn readyz<S: HasPool>(State(state): State<S>) -> Response {
    match sqlx::query("SELECT 1").execute(state.pool()).await {
        Ok(_) => (StatusCode::OK, Json(HealthBody { status: "ok", endpoint: "readyz" })).into_response(),
        Err(err) => {
            tracing::warn!(%err, "readyz: database ping failed");
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(HealthBody { status: "degraded", endpoint: "readyz" }),
            )
                .into_response()
        }
    }
}

/// Build the probe routes (`/livez`, `/readyz`, `/metrics`) as a `Router<S>`
/// for a state that exposes a Postgres pool. Merge into the service router
/// **outside** any auth layer.
pub fn routes<S: HasPool>() -> Router<S> {
    Router::new()
        .route("/livez", get(livez))
        .route("/readyz", get(readyz::<S>))
        .route("/metrics", get(crate::metrics::render))
}
