//! Router assembly — wires the auth middleware + timeout layer over the
//! `/internal/v1/...` route group.

use std::time::Duration;

use axum::Router;
use axum::extract::DefaultBodyLimit;
use axum::http::StatusCode;
use axum::middleware::from_fn_with_state;
use axum::routing::{get, post};
use tower_http::timeout::TimeoutLayer;

use super::AppState;
use super::auth::require_bearer;
use super::health::{livez, readyz};
use super::render::{MAX_BODY_BYTES, render};

/// Default per-request timeout — 30 s. Large grids should finish well
/// under this; a hung request surfaces as 504 from the timeout layer.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);

pub fn build_router(state: AppState) -> Router {
    // Auth-gated route group — only /internal/v1/tilemaps/render today.
    let internal_v1 = Router::new()
        .route("/internal/v1/tilemaps/render", post(render))
        .layer(from_fn_with_state(state.clone(), require_bearer));

    // Health probes — k8s-style. NOT auth-gated; docker healthcheck +
    // load-balancer probes hit these without a token.
    let probes = Router::new()
        .route("/livez", get(livez))
        .route("/readyz", get(readyz));

    Router::new()
        .merge(internal_v1)
        .merge(probes)
        // Body-size cap (MED-2 from /review-impl). Bodies over MAX_BODY_BYTES
        // are rejected by axum before the Json extractor — JsonProblem maps
        // the rejection back into problem+json.
        .layer(DefaultBodyLimit::max(MAX_BODY_BYTES))
        .layer(TimeoutLayer::with_status_code(StatusCode::GATEWAY_TIMEOUT, REQUEST_TIMEOUT))
        .with_state(state)
}
