//! Router assembly.
//!
//! R0 (infra gate) wires only the health/metrics surface + the shared
//! trace/metrics/CORS layers. The user-JWT route group (`/v1/roleplay/scripts*`
//! plus `/start`) lands in R1 — it mounts under `require_user` (see the
//! reserved block in `build_router`).

use std::time::Duration;

use axum::Router;
use axum::extract::DefaultBodyLimit;
use axum::http::{HeaderValue, Method, StatusCode};
use axum::middleware::{from_fn, from_fn_with_state};
use axum::routing::{get, post};
use tower_http::cors::CorsLayer;
use tower_http::timeout::TimeoutLayer;
use service_http::{health, require_user};

use crate::handlers::{scripts, start};
use crate::state::AppState;

/// 1 MiB request-body cap (scripts are small JSON; protects the JSON extractor).
const MAX_BODY_BYTES: usize = 1024 * 1024;
const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);

/// Dev CORS origins; production traffic comes through api-gateway-bff
/// (single-origin). Comma-separated `LOREWEAVE_CORS_ORIGINS` overrides.
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
        .allow_methods([Method::GET, Method::POST, Method::PATCH, Method::DELETE, Method::OPTIONS])
        .allow_headers([axum::http::header::AUTHORIZATION, axum::http::header::CONTENT_TYPE])
}

pub fn build_router(state: AppState) -> Router {
    // Bare probes — for the docker healthcheck (in-container `wget /livez`)
    // and ops dashboards: /livez /readyz /metrics.
    let probes = health::routes::<AppState>();

    // Gateway-facing probes — the `/v1/roleplay` proxy forwards the path
    // unchanged, so a through-gateway `GET /v1/roleplay/livez` lands here.
    let gateway_probes = Router::new()
        .route("/v1/roleplay/livez", get(health::livez))
        .route("/v1/roleplay/readyz", get(health::readyz::<AppState>));

    // User-JWT route group: scripts CRUD + start-orchestration. Every handler
    // reads identity from Extension<UserId> injected by require_user.
    let user = Router::new()
        .route("/v1/roleplay/scripts", get(scripts::list).post(scripts::create))
        .route(
            "/v1/roleplay/scripts/:id",
            get(scripts::get_one).patch(scripts::patch).delete(scripts::del),
        )
        .route("/v1/roleplay/scripts/:id/start", post(start::start))
        .layer(from_fn_with_state(state.clone(), require_user::<AppState>));

    Router::new()
        .merge(probes)
        .merge(gateway_probes)
        .merge(user)
        // Layer order (last = outermost): CORS answers preflight first, then
        // trace mints/propagates the id + spans the request, then metrics.
        .layer(from_fn(service_http::metrics::record))
        .layer(from_fn(service_http::trace::propagate))
        .layer(cors_layer())
        .layer(DefaultBodyLimit::max(MAX_BODY_BYTES))
        .layer(TimeoutLayer::with_status_code(StatusCode::GATEWAY_TIMEOUT, REQUEST_TIMEOUT))
        .with_state(state)
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::Request;
    use sqlx::postgres::PgPoolOptions;
    use tower::ServiceExt;

    use crate::config::Config;

    // A lazy pool never connects until first query, so this builds an AppState
    // without any running Postgres — `/livez` doesn't touch the DB.
    fn test_state() -> AppState {
        let pool = PgPoolOptions::new()
            .connect_lazy("postgres://u:p@127.0.0.1:5432/none")
            .expect("lazy pool");
        let config = Config {
            bind: "0.0.0.0:7110".parse().unwrap(),
            database_url: "x".into(),
            jwt_secret: "test_secret_value_at_least_32_chars_x".into(),
            internal_token: "tok".into(),
            chat_url: "http://chat".into(),
        };
        AppState::new(pool, &config)
    }

    #[tokio::test]
    async fn bare_livez_returns_200() {
        let app = build_router(test_state());
        let resp = app
            .oneshot(Request::builder().uri("/livez").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn gateway_livez_returns_200_with_trace_header() {
        let app = build_router(test_state());
        let resp = app
            .oneshot(Request::builder().uri("/v1/roleplay/livez").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        // trace::propagate echoes an X-Trace-Id even when none was supplied.
        assert!(resp.headers().get("x-trace-id").is_some(), "missing X-Trace-Id");
    }

    #[tokio::test]
    async fn metrics_endpoint_serves_prometheus_text() {
        let app = build_router(test_state());
        let resp = app
            .oneshot(Request::builder().uri("/metrics").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }
}
