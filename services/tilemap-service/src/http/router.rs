//! Router assembly — wires the auth middleware + timeout layer over the
//! `/internal/v1/...` route group.

use std::time::Duration;

use axum::Router;
use axum::extract::DefaultBodyLimit;
use axum::http::{HeaderValue, Method, StatusCode};
use axum::middleware::from_fn_with_state;
use axum::routing::{get, post};
use tower_http::cors::CorsLayer;
use tower_http::timeout::TimeoutLayer;

use super::AppState;
use super::auth::require_bearer;
use super::health::{livez, readyz};
use super::render::{MAX_BODY_BYTES, render};

/// Default per-request timeout — 30 s. Large grids should finish well
/// under this; a hung request surfaces as 504 from the timeout layer.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);

/// Dev-only CORS origins. Production goes through api-gateway-bff
/// (single-origin per spec §8 + AC-FG-13). For Session D V0 browser
/// smoke, the frontend-game dev server at :5174 needs to be allowed.
/// Comma-separated env var overrides this default.
fn cors_layer() -> CorsLayer {
    let raw = std::env::var("LOREWEAVE_CORS_ORIGINS")
        .unwrap_or_else(|_| "http://localhost:5174".to_string());
    let origins: Vec<HeaderValue> = raw
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .filter_map(|s| HeaderValue::from_str(s).ok())
        .collect();
    CorsLayer::new()
        .allow_origin(origins)
        .allow_methods([Method::GET, Method::POST, Method::OPTIONS])
        .allow_headers([axum::http::header::AUTHORIZATION, axum::http::header::CONTENT_TYPE])
}

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
        // CORS for dev browser smoke per spec AC-FG-13. Layer order:
        // CORS outermost so preflight (OPTIONS) is answered before any
        // body-size / timeout middleware runs.
        .layer(cors_layer())
        // Body-size cap (MED-2 from /review-impl). Bodies over MAX_BODY_BYTES
        // are rejected by axum before the Json extractor — JsonProblem maps
        // the rejection back into problem+json.
        .layer(DefaultBodyLimit::max(MAX_BODY_BYTES))
        .layer(TimeoutLayer::with_status_code(StatusCode::GATEWAY_TIMEOUT, REQUEST_TIMEOUT))
        .with_state(state)
}
