//! RFC 7807 `application/problem+json` error envelope, shared across the
//! LoreWeave Rust fleet.
//!
//! Two deliberate additions over a bare RFC-7807 body:
//!  * **`message`** — the LoreWeave FE's `apiJson` helper reads `err.message`
//!    to surface a human-readable error instead of a bare `statusText`. Every
//!    `ProblemDetails` carries it (defaulted to `detail`) so a Rust service's
//!    errors render in the UI like every Go/Python service's do.
//!  * stable `type` URNs are constructed per-status so clients MAY match on the
//!    URN rather than the (localizable) `title`.

use axum::Json;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde::Serialize;

/// RFC 7807 `application/problem+json` body. The `type` JSON key (a Rust
/// reserved word) maps to the `type_` field via serde rename. `message`
/// mirrors `detail` for FE-readability (see module docs).
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ProblemDetails {
    #[serde(rename = "type")]
    pub type_: String,
    pub title: String,
    pub status: u16,
    pub detail: String,
    /// FE-readable copy of `detail` — the LoreWeave frontend reads `message`.
    pub message: String,
}

impl ProblemDetails {
    /// Construct from an explicit status + title + detail. `message` is set
    /// to `detail` so the FE always has something readable.
    pub fn new(status: StatusCode, urn_suffix: &str, title: impl Into<String>, detail: impl Into<String>) -> Self {
        let detail = detail.into();
        Self {
            type_: format!("urn:loreweave:error:{urn_suffix}"),
            title: title.into(),
            status: status.as_u16(),
            message: detail.clone(),
            detail,
        }
    }

    /// 400 Bad Request.
    pub fn bad_request(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::BAD_REQUEST, "bad-request", "Bad request", detail)
    }

    /// 401 Unauthorized — missing / invalid credentials.
    pub fn unauthorized(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::UNAUTHORIZED, "unauthorized", "Unauthorized", detail)
    }

    /// 403 Forbidden — authenticated but not allowed.
    pub fn forbidden(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::FORBIDDEN, "forbidden", "Forbidden", detail)
    }

    /// 404 Not Found — also the tenancy-deny response (a row the caller may
    /// not see is indistinguishable from one that does not exist).
    pub fn not_found(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::NOT_FOUND, "not-found", "Not found", detail)
    }

    /// 409 Conflict — uniqueness / state conflict.
    pub fn conflict(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::CONFLICT, "conflict", "Conflict", detail)
    }

    /// 502 Bad Gateway — an upstream dependency call failed.
    pub fn bad_gateway(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::BAD_GATEWAY, "bad-gateway", "Upstream error", detail)
    }

    /// 503 Service Unavailable — a dependency (e.g. DB) is unreachable.
    pub fn unavailable(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::SERVICE_UNAVAILABLE, "unavailable", "Service unavailable", detail)
    }

    /// 500 Internal Server Error.
    pub fn internal(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::INTERNAL_SERVER_ERROR, "internal", "Internal server error", detail)
    }

    fn axum_status(&self) -> StatusCode {
        StatusCode::from_u16(self.status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR)
    }
}

impl IntoResponse for ProblemDetails {
    fn into_response(self) -> Response {
        let mut resp = (self.axum_status(), Json(&self)).into_response();
        resp.headers_mut().insert(
            axum::http::header::CONTENT_TYPE,
            axum::http::HeaderValue::from_static("application/problem+json"),
        );
        resp
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serializes_type_and_message_fields() {
        let p = ProblemDetails::bad_request("missing field 'code'");
        let j = serde_json::to_value(&p).unwrap();
        assert!(j.get("type").is_some(), "wire JSON must use 'type': {j}");
        assert!(j.get("type_").is_none(), "must not leak 'type_': {j}");
        assert_eq!(j["status"], 400);
        assert_eq!(j["detail"], "missing field 'code'");
        // FE-readability: `message` must be present and mirror `detail`.
        assert_eq!(j["message"], "missing field 'code'");
    }

    #[test]
    fn status_helpers_map_to_correct_codes() {
        assert_eq!(ProblemDetails::unauthorized("x").status, 401);
        assert_eq!(ProblemDetails::forbidden("x").status, 403);
        assert_eq!(ProblemDetails::not_found("x").status, 404);
        assert_eq!(ProblemDetails::conflict("x").status, 409);
        assert_eq!(ProblemDetails::unavailable("x").status, 503);
        assert_eq!(ProblemDetails::internal("x").status, 500);
    }
}
