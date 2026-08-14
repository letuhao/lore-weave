//! Router assembly, and the route table the OpenAPI contract is checked against.

use std::time::Duration;

use axum::Router;
use axum::extract::DefaultBodyLimit;
use axum::http::StatusCode;
use axum::middleware::{from_fn, from_fn_with_state};
use axum::routing::post;
use service_http::{health, require_internal};
use tower_http::timeout::TimeoutLayer;

use crate::server::handlers::{actor_control, realities};
use crate::server::state::AppState;

/// 256 KiB request-body cap. A provision request is a handful of scalars;
/// anything larger is a mistake or an attack.
const MAX_BODY_BYTES: usize = 256 * 1024;

/// Provisioning runs `CREATE DATABASE` plus the whole per-reality migration
/// set against a remote shard, so the platform-default 30s is too tight. This
/// is an admin-gated, low-frequency action; the ceiling exists to bound a wedged
/// call, not to pace a normal one.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(300);

/// Whether a route is behind the internal-token gate.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Gate {
    /// Unauthenticated — health/metrics probes, hit by load balancers.
    Open,
    /// Requires an exact `X-Internal-Token` (`WS-F4` / invariant I1).
    Internal,
}

/// One route this service serves.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RouteSpec {
    /// Lowercase HTTP method.
    pub method: &'static str,
    /// Path as axum and the OpenAPI document both spell it.
    pub path: &'static str,
    /// Auth gate.
    pub gate: Gate,
}

/// **The route table — the single source of truth for what this service serves.**
///
/// `contracts/api/world/provisioning.v1.yaml` is checked against this list by
/// `tests/route_conformance.rs`, in both directions: an entry here with no
/// documented operation fails, and a documented operation with no entry fails.
///
/// The table alone would be a self-witness — it is a list an author edits, so a
/// route added straight to [`build_router`] would never appear in it and would
/// be undocumented *and* unnoticed. The conformance test closes that by also
/// reading the SOURCE of this file and of `service-http`'s health module, and
/// asserting every `.route("…")` literal it finds is listed here.
pub const ROUTES: &[RouteSpec] = &[
    // Merged from `service_http::health::routes` — mounted OUTSIDE the auth
    // layer so a docker healthcheck and a load balancer reach them.
    RouteSpec { method: "get", path: "/livez", gate: Gate::Open },
    RouteSpec { method: "get", path: "/readyz", gate: Gate::Open },
    RouteSpec { method: "get", path: "/metrics", gate: Gate::Open },
    RouteSpec { method: "post", path: "/internal/v1/realities", gate: Gate::Internal },
    // SEALED-BINDING — `actor_control_binding`'s writer. Internal-gated: a
    // grant decides who may act as a subject, so it is never reachable from
    // the public edge.
    RouteSpec { method: "post", path: "/internal/v1/actors", gate: Gate::Internal },
    RouteSpec { method: "post", path: "/internal/v1/actor-control/grant", gate: Gate::Internal },
    RouteSpec { method: "post", path: "/internal/v1/actor-control/revoke", gate: Gate::Internal },
];

/// Assemble the service router.
pub fn build_router(state: AppState) -> Router {
    let probes = health::routes::<AppState>();

    let internal = Router::new()
        .route("/internal/v1/realities", post(realities::provision_reality))
        .route("/internal/v1/actors", post(actor_control::create_actor))
        .route("/internal/v1/actor-control/grant", post(actor_control::grant_control))
        .route("/internal/v1/actor-control/revoke", post(actor_control::revoke_control))
        .layer(from_fn_with_state(state.clone(), require_internal::<AppState>));

    Router::new()
        .merge(probes)
        .merge(internal)
        // Layer order (last = outermost): trace mints/propagates the id, then
        // metrics records. No CORS layer — this surface has no browser client
        // by `WS-F4`; adding one would advertise an origin that should be
        // reaching api-gateway-bff instead.
        .layer(from_fn(service_http::metrics::record))
        .layer(from_fn(service_http::trace::propagate))
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

    use crate::server::config::Config;

    /// A lazy pool never connects until first query, so a router can be built
    /// with no Postgres running — `/livez` does not touch the database.
    fn test_state() -> AppState {
        let pool = || {
            PgPoolOptions::new()
                .connect_lazy("postgres://u:p@127.0.0.1:1/none")
                .expect("lazy pool")
        };
        let config = Config::from_lookup(|k| {
            Some(
                match k {
                    "LOREWEAVE_INTERNAL_TOKEN" => "test-internal-token",
                    "PROVISION_META_DSN" | "PROVISION_SHARD_ADMIN_DSN" => "postgres://x",
                    "PROVISION_BRIDGE_URL" => "http://bridge",
                    "PROVISION_BRIDGE_TOKEN" => "bt",
                    "PROVISION_SHARD_HOSTPORT" => "pg:5432",
                    "PROVISION_PG_USER" => "u",
                    _ => return None,
                }
                .to_string(),
            )
        })
        .expect("test config");
        AppState::new(pool(), pool(), &config)
    }

    #[tokio::test]
    async fn livez_answers_without_a_database() {
        let resp = build_router(test_state())
            .oneshot(Request::builder().uri("/livez").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        assert!(resp.headers().get("x-trace-id").is_some(), "trace layer not wired");
    }

    #[tokio::test]
    async fn metrics_is_served() {
        let resp = build_router(test_state())
            .oneshot(Request::builder().uri("/metrics").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn the_provisioning_route_refuses_a_request_with_no_internal_token() {
        let resp = build_router(test_state())
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/internal/v1/realities")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn a_wrong_internal_token_is_refused() {
        let resp = build_router(test_state())
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/internal/v1/realities")
                    .header("content-type", "application/json")
                    .header("X-Internal-Token", "not-the-token")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn a_correct_token_reaches_the_handler_and_the_body_is_validated_there() {
        // Proves the gate is a GATE and not a wall: with the right token the
        // request gets past auth. `{}` is readable JSON that is not a
        // `ProvisionRequest`, so the extractor rejects it as 422 — the code the
        // contract documents for exactly this, distinct from the 400 an
        // unparseable body gets. Rendered as problem+json by the handler rather
        // than axum's default text/plain.
        let resp = build_router(test_state())
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/internal/v1/realities")
                    .header("content-type", "application/json")
                    .header("X-Internal-Token", "test-internal-token")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_ne!(
            resp.status(),
            StatusCode::UNAUTHORIZED,
            "a valid token must not be rejected by the auth layer"
        );
        assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
        let ct = resp.headers().get("content-type").and_then(|v| v.to_str().ok()).unwrap_or("");
        assert!(ct.contains("problem+json"), "extractor rejection not rendered as RFC 7807: {ct}");
    }

    #[test]
    fn every_gated_route_in_the_table_is_versioned_and_internal() {
        // The boundary rule stated as an assertion: this service exposes no
        // unversioned business route, and no versioned route is Open.
        for r in ROUTES {
            let versioned = r.path.contains("/v1/");
            assert_eq!(
                versioned,
                r.gate == Gate::Internal,
                "{} {} — a versioned route must be Internal and an Open route must be a probe",
                r.method,
                r.path
            );
        }
    }
}
