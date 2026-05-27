//! Liveness + readiness probes (k8s-style).
//!
//! `/livez` — the process is alive. Always returns 200 if the binary is
//!            running; used by the orchestrator to decide whether to
//!            restart the container.
//! `/readyz` — the service is ready to accept traffic. Today identical to
//!             `/livez` (no external deps to probe); when Phase 4+ adds
//!             Postgres / DP / Forge integrations, this is where the
//!             readiness check exercises them.
//!
//! Neither endpoint is auth-gated — they must be reachable by docker
//! healthcheck, load-balancer probes, and `kubectl get pods` without a
//! token.

use axum::Json;
use axum::http::StatusCode;
use serde::Serialize;

/// Shape returned by both probes. Pinned wire JSON so future operators
/// can grep logs / dashboards by the `endpoint` field.
///
/// LOW-5 from /review-impl 2026-05-24: `version` is opt-in via
/// `TILEMAP_HEALTH_VERBOSE=1`. Default OFF so the probe doesn't leak
/// the package version to unauthenticated scanners — a fingerprinting
/// vector if /livez ever becomes exposed beyond the docker network.
#[derive(Debug, Serialize)]
pub struct HealthBody {
    pub status: &'static str,
    pub endpoint: &'static str,
    pub service: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<&'static str>,
}

impl HealthBody {
    pub fn ok(endpoint: &'static str) -> Self {
        Self {
            status: "ok",
            endpoint,
            service: "tilemap-service",
            version: if is_verbose() {
                Some(env!("CARGO_PKG_VERSION"))
            } else {
                None
            },
        }
    }
}

fn is_verbose() -> bool {
    std::env::var("TILEMAP_HEALTH_VERBOSE")
        .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
        .unwrap_or(false)
}

pub async fn livez() -> (StatusCode, Json<HealthBody>) {
    (StatusCode::OK, Json(HealthBody::ok("livez")))
}

/// **TODO(readiness):** when Phase 4+ adds dependencies (Postgres, DP,
/// Forge, etc.), this MUST exercise them and return 503 on any
/// degraded dep — otherwise load balancers will route traffic to a
/// broken service. The current "identical to livez" behavior is
/// load-bearing ONLY while tilemap-service has no external deps.
///
/// Grep `TODO(readiness)` when adding any Postgres / Redis / HTTP
/// dependency so this readiness check is updated in lockstep.
/// (LOW-4 from /review-impl 2026-05-24.)
pub async fn readyz() -> (StatusCode, Json<HealthBody>) {
    (StatusCode::OK, Json(HealthBody::ok("readyz")))
}
