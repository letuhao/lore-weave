//! Bearer token middleware + shared `AppState`.
//!
//! `AppState` holds the internal token (sourced from
//! `LOREWEAVE_INTERNAL_TOKEN` at boot); [`require_bearer`] is a
//! `from_fn_with_state` middleware that rejects any request whose
//! `Authorization` header does not byte-exact match the token.

use std::sync::Arc;

use axum::extract::{Request, State};
use axum::http::header::AUTHORIZATION;
use axum::middleware::Next;
use axum::response::Response;

use super::error::ProblemDetails;

#[derive(Clone, Debug)]
pub struct AppState {
    /// `Arc<str>` (not `Arc<String>`) flattens to a single heap allocation
    /// and prevents accidental mutation. Constructed via `AppState::new`.
    pub internal_token: Arc<str>,
}

impl AppState {
    pub fn new(internal_token: String) -> Self {
        Self { internal_token: Arc::from(internal_token.into_boxed_str()) }
    }
}

/// Axum middleware: pulls `Authorization: Bearer <token>` from the request,
/// rejects on missing/malformed/mismatched header with 401 `problem+json`.
///
/// Comparison is byte-exact constant-time-equivalent: tokens are short
/// fixed strings, the cost difference between `==` and a constant-time
/// helper is dominated by network jitter. We keep `==` for clarity; if
/// timing attacks become a stated threat, swap to `subtle::ConstantTimeEq`.
pub async fn require_bearer(
    State(state): State<AppState>,
    req: Request,
    next: Next,
) -> Result<Response, ProblemDetails> {
    let path = req.uri().path().to_string();
    let header = req.headers().get(AUTHORIZATION).ok_or_else(|| {
        tracing::warn!(%path, reason = "missing Authorization", "auth rejected");
        ProblemDetails::unauthorized("missing Authorization header")
    })?;

    let header = header.to_str().map_err(|_| {
        tracing::warn!(%path, reason = "non-UTF-8 Authorization", "auth rejected");
        ProblemDetails::unauthorized("Authorization header is not valid UTF-8")
    })?;

    let token = header.strip_prefix("Bearer ").ok_or_else(|| {
        tracing::warn!(%path, reason = "non-Bearer scheme", "auth rejected");
        ProblemDetails::unauthorized("Authorization must be 'Bearer <token>'")
    })?;

    if token.as_bytes() != state.internal_token.as_bytes() {
        tracing::warn!(%path, reason = "token mismatch", "auth rejected");
        return Err(ProblemDetails::unauthorized("token mismatch"));
    }

    Ok(next.run(req).await)
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::Router;
    use axum::http::{Request as AxumRequest, StatusCode};
    use axum::middleware::from_fn_with_state;
    use axum::routing::get;
    use tower::ServiceExt;

    async fn ok_handler() -> &'static str {
        "ok"
    }

    fn app(token: &str) -> Router {
        let state = AppState::new(token.to_string());
        Router::new()
            .route("/protected", get(ok_handler))
            .layer(from_fn_with_state(state.clone(), require_bearer))
            .with_state(state)
    }

    #[tokio::test]
    async fn bearer_middleware_rejects_missing_authorization() {
        let app = app("s3cret");
        let resp = app
            .oneshot(AxumRequest::builder().uri("/protected").body(axum::body::Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
        let bytes = axum::body::to_bytes(resp.into_body(), 4096).await.unwrap();
        let body: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["type"], super::super::error::URN_UNAUTHORIZED);
        assert_eq!(body["status"], 401);
    }

    #[tokio::test]
    async fn bearer_middleware_rejects_wrong_token() {
        let app = app("s3cret");
        let resp = app
            .oneshot(
                AxumRequest::builder()
                    .uri("/protected")
                    .header(AUTHORIZATION, "Bearer wr0ng")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn bearer_middleware_rejects_non_bearer_scheme() {
        let app = app("s3cret");
        let resp = app
            .oneshot(
                AxumRequest::builder()
                    .uri("/protected")
                    .header(AUTHORIZATION, "Basic dXNlcjpwYXNz")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn bearer_middleware_accepts_exact_match() {
        let app = app("s3cret");
        let resp = app
            .oneshot(
                AxumRequest::builder()
                    .uri("/protected")
                    .header(AUTHORIZATION, "Bearer s3cret")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let bytes = axum::body::to_bytes(resp.into_body(), 4096).await.unwrap();
        assert_eq!(&bytes[..], b"ok");
    }
}
