//! RFC 7807 `application/problem+json` error envelope.
//!
//! Stable `type` URNs are constants in this module — clients SHOULD match
//! on the URN, not on `title`. Mapping from `crate::Error` to status code
//! lives in `From<crate::Error>` below; spec §3.4 has the canonical table.

use axum::Json;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde::Serialize;

/// Stable URN keys — clients match on these instead of `title`.
pub const URN_BAD_REQUEST: &str = "urn:tilemap-service:error:bad-request";
pub const URN_UNAUTHORIZED: &str = "urn:tilemap-service:error:unauthorized";
pub const URN_REQUEST_TOO_LARGE: &str = "urn:tilemap-service:error:request-too-large";
pub const URN_PLACEMENT: &str = "urn:tilemap-service:error:placement";
pub const URN_EMPTY_ZONE: &str = "urn:tilemap-service:error:empty-zone";
pub const URN_DEPENDENCY_CYCLE: &str = "urn:tilemap-service:error:dependency-cycle";
pub const URN_MODIFICATOR: &str = "urn:tilemap-service:error:modificator";
pub const URN_CONFIG: &str = "urn:tilemap-service:error:config";
pub const URN_INTERNAL: &str = "urn:tilemap-service:error:internal";

/// RFC 7807 `application/problem+json` body. The `type` JSON key (a Rust
/// reserved word) maps to the `type_` field via serde rename.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ProblemDetails {
    #[serde(rename = "type")]
    pub type_: String,
    pub title: String,
    pub status: u16,
    pub detail: String,
}

impl ProblemDetails {
    /// 400 Bad Request — request body fails to parse / wrong shape.
    pub fn bad_request(detail: impl Into<String>) -> Self {
        Self {
            type_: URN_BAD_REQUEST.to_string(),
            title: "Bad request".to_string(),
            status: StatusCode::BAD_REQUEST.as_u16(),
            detail: detail.into(),
        }
    }

    /// 413 Payload Too Large — request inputs exceed safe bounds
    /// (grid_size × tile_count, zones.len(), …) — protects against
    /// memory-exhaustion DoS before placement allocates.
    pub fn request_too_large(detail: impl Into<String>) -> Self {
        Self {
            type_: URN_REQUEST_TOO_LARGE.to_string(),
            title: "Request too large".to_string(),
            status: StatusCode::PAYLOAD_TOO_LARGE.as_u16(),
            detail: detail.into(),
        }
    }

    /// 401 Unauthorized — missing or invalid Bearer token.
    pub fn unauthorized(detail: impl Into<String>) -> Self {
        Self {
            type_: URN_UNAUTHORIZED.to_string(),
            title: "Unauthorized".to_string(),
            status: StatusCode::UNAUTHORIZED.as_u16(),
            detail: detail.into(),
        }
    }

    /// 500 Internal Server Error — unrecoverable server-side fault
    /// (config, IO, spawn_blocking panic).
    pub fn internal(detail: impl Into<String>) -> Self {
        Self {
            type_: URN_INTERNAL.to_string(),
            title: "Internal server error".to_string(),
            status: StatusCode::INTERNAL_SERVER_ERROR.as_u16(),
            detail: detail.into(),
        }
    }

    fn axum_status(&self) -> StatusCode {
        StatusCode::from_u16(self.status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR)
    }
}

impl IntoResponse for ProblemDetails {
    fn into_response(self) -> Response {
        let mut resp = (self.axum_status(), Json(&self)).into_response();
        // Override the default "application/json" with "application/problem+json"
        // per RFC 7807.
        resp.headers_mut().insert(
            axum::http::header::CONTENT_TYPE,
            axum::http::HeaderValue::from_static("application/problem+json"),
        );
        resp
    }
}

/// Map every `crate::Error` variant to a status code + stable URN. Spec
/// §3.4 is the canonical table.
impl From<crate::Error> for ProblemDetails {
    fn from(err: crate::Error) -> Self {
        use crate::Error;
        let (status, type_, title) = match &err {
            Error::Json(_) => (
                StatusCode::BAD_REQUEST,
                URN_BAD_REQUEST,
                "Bad request",
            ),
            Error::Placement(_) => (
                StatusCode::UNPROCESSABLE_ENTITY,
                URN_PLACEMENT,
                "Zone placement failed",
            ),
            Error::EmptyZone(_) => (
                StatusCode::UNPROCESSABLE_ENTITY,
                URN_EMPTY_ZONE,
                "Zone was assigned no tiles",
            ),
            Error::DependencyCycle(_) => (
                StatusCode::UNPROCESSABLE_ENTITY,
                URN_DEPENDENCY_CYCLE,
                "Modificator dependency cycle",
            ),
            Error::Modificator { .. } => (
                StatusCode::UNPROCESSABLE_ENTITY,
                URN_MODIFICATOR,
                "Modificator failed",
            ),
            Error::Config(_) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                URN_CONFIG,
                "Server configuration error",
            ),
            Error::Io(_) | Error::Llm(_) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                URN_INTERNAL,
                "Internal server error",
            ),
        };
        Self {
            type_: type_.to_string(),
            title: title.to_string(),
            status: status.as_u16(),
            detail: err.to_string(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn problem_details_serializes_with_type_field_renamed() {
        // The Rust field is `type_` but the wire key must be `type` per
        // RFC 7807. Verify the rename round-trips through JSON.
        let p = ProblemDetails::bad_request("missing field 'seed'");
        let j = serde_json::to_value(&p).unwrap();
        assert!(j.get("type").is_some(), "wire JSON must use 'type' not 'type_': {j}");
        assert!(j.get("type_").is_none(), "wire JSON must not leak 'type_': {j}");
        assert_eq!(j["type"], URN_BAD_REQUEST);
        assert_eq!(j["status"], 400);
        assert_eq!(j["detail"], "missing field 'seed'");
    }

    #[test]
    fn crate_error_placement_maps_to_422_with_correct_urn() {
        let p: ProblemDetails =
            crate::Error::Placement("force-directed did not converge".to_string()).into();
        assert_eq!(p.status, 422);
        assert_eq!(p.type_, URN_PLACEMENT);
        assert!(p.detail.contains("force-directed"), "detail should contain the inner message: {p:?}");
    }

    #[test]
    fn crate_error_empty_zone_maps_to_422_with_correct_urn() {
        let p: ProblemDetails = crate::Error::EmptyZone("capital".to_string()).into();
        assert_eq!(p.status, 422);
        assert_eq!(p.type_, URN_EMPTY_ZONE);
    }

    #[test]
    fn crate_error_dependency_cycle_maps_to_422() {
        let p: ProblemDetails =
            crate::Error::DependencyCycle("treasure_placer".to_string()).into();
        assert_eq!(p.status, 422);
        assert_eq!(p.type_, URN_DEPENDENCY_CYCLE);
    }

    #[test]
    fn crate_error_config_maps_to_500() {
        let p: ProblemDetails =
            crate::Error::Config("LOREWEAVE_INTERNAL_TOKEN unset".to_string()).into();
        assert_eq!(p.status, 500);
        assert_eq!(p.type_, URN_CONFIG);
    }
}
