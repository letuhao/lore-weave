//! Auth middleware — the security primitives shared across the Rust fleet.
//!
//! `require_user` validates a user JWT (HS256, `sub` → user_id UUID) and
//! injects [`UserId`] as a request extension; handlers read it via
//! `Extension<UserId>`. This mirrors the Go contract in
//! `book-service requireUserID` (Authorization: Bearer, HS256, `JWT_SECRET`).
//!
//! `require_internal` is an exact-match on the `X-Internal-Token` header for
//! service-to-service calls.
//!
//! Both middlewares are generic over the consumer's `AppState`, gated through
//! the [`HasJwtSecret`] / [`HasInternalToken`] traits — so the secret lives in
//! the consumer's state, not duplicated here.

use axum::extract::{Request, State};
use axum::http::header::AUTHORIZATION;
use axum::middleware::Next;
use axum::response::Response;
use jsonwebtoken::{Algorithm, DecodingKey, Validation, decode};
use uuid::Uuid;

use crate::error::ProblemDetails;

/// Header carrying the service-to-service token (matches the platform
/// convention; the Go/Python services use the same header name).
pub const INTERNAL_TOKEN_HEADER: &str = "X-Internal-Token";

/// JWT-resolved caller identity, injected by [`require_user`].
///
/// Handlers MUST read identity from this extension, never from the request
/// body — the token is the source of truth (tenancy invariant INV-T2).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct UserId(pub Uuid);

/// The minimal `sub` claim the user JWT must carry. `exp` is validated by
/// [`Validation`] (not deserialized here).
#[derive(serde::Deserialize)]
struct Claims {
    sub: String,
}

/// Consumer state that exposes the HS256 secret for [`require_user`].
pub trait HasJwtSecret: Clone + Send + Sync + 'static {
    fn jwt_secret(&self) -> &[u8];
}

/// Consumer state that exposes the internal-service token for
/// [`require_internal`].
pub trait HasInternalToken: Clone + Send + Sync + 'static {
    fn internal_token(&self) -> &str;
}

/// Axum middleware: validate `Authorization: Bearer <jwt>` (HS256, `sub`
/// claim → UUID), inject [`UserId`]. Rejects missing / malformed / expired /
/// bad-signature / non-UUID-sub tokens with 401 `problem+json`.
pub async fn require_user<S: HasJwtSecret>(
    State(state): State<S>,
    mut req: Request,
    next: Next,
) -> Result<Response, ProblemDetails> {
    let token = req
        .headers()
        .get(AUTHORIZATION)
        .and_then(|h| h.to_str().ok())
        .and_then(|h| h.strip_prefix("Bearer "))
        .ok_or_else(|| ProblemDetails::unauthorized("missing or malformed Authorization header"))?;

    let mut validation = Validation::new(Algorithm::HS256);
    validation.validate_exp = true;
    // Require BOTH exp and sub. Without exp in the required set, a token lacking
    // an `exp` claim would never expire (validate_exp only checks exp when it is
    // present) — defense-in-depth for this shared fleet-wide primitive.
    validation.set_required_spec_claims(&["exp", "sub"]);

    let data = decode::<Claims>(token, &DecodingKey::from_secret(state.jwt_secret()), &validation)
        .map_err(|_| ProblemDetails::unauthorized("invalid token"))?;

    let user_id = Uuid::parse_str(data.claims.sub.trim())
        .map_err(|_| ProblemDetails::unauthorized("token subject is not a valid user id"))?;

    req.extensions_mut().insert(UserId(user_id));
    Ok(next.run(req).await)
}

/// Axum middleware: exact-match the `X-Internal-Token` header against the
/// configured service token. Byte-exact comparison (short fixed tokens; a
/// constant-time compare buys nothing over network jitter).
pub async fn require_internal<S: HasInternalToken>(
    State(state): State<S>,
    req: Request,
    next: Next,
) -> Result<Response, ProblemDetails> {
    let provided = req
        .headers()
        .get(INTERNAL_TOKEN_HEADER)
        .and_then(|h| h.to_str().ok())
        .ok_or_else(|| ProblemDetails::unauthorized("missing X-Internal-Token"))?;

    if provided.as_bytes() != state.internal_token().as_bytes() {
        tracing::warn!(reason = "internal token mismatch", "internal auth rejected");
        return Err(ProblemDetails::unauthorized("internal token mismatch"));
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
    use jsonwebtoken::{EncodingKey, Header, encode};
    use serde::Serialize;
    use tower::ServiceExt;

    const SECRET: &[u8] = b"test_secret_at_least_32_chars_long_xx";

    #[derive(Clone)]
    struct TestState;
    impl HasJwtSecret for TestState {
        fn jwt_secret(&self) -> &[u8] {
            SECRET
        }
    }
    impl HasInternalToken for TestState {
        fn internal_token(&self) -> &str {
            "s3cret-internal"
        }
    }

    #[derive(Serialize)]
    struct TestClaims {
        sub: String,
        exp: usize,
    }

    fn make_token(sub: &str, exp: usize, secret: &[u8]) -> String {
        encode(
            &Header::new(Algorithm::HS256),
            &TestClaims { sub: sub.to_string(), exp },
            &EncodingKey::from_secret(secret),
        )
        .unwrap()
    }

    // A far-future / far-past absolute epoch second, computed without touching
    // the wall clock (kept deterministic).
    const FUTURE_EXP: usize = 4_102_444_800; // 2100-01-01
    const PAST_EXP: usize = 1_000_000_000; // 2001-09-09

    async fn ok() -> &'static str {
        "ok"
    }

    fn user_app() -> Router {
        Router::new()
            .route("/p", get(ok))
            .layer(from_fn_with_state(TestState, require_user::<TestState>))
            .with_state(TestState)
    }

    fn internal_app() -> Router {
        Router::new()
            .route("/p", get(ok))
            .layer(from_fn_with_state(TestState, require_internal::<TestState>))
            .with_state(TestState)
    }

    async fn status_for(app: Router, req: AxumRequest<axum::body::Body>) -> StatusCode {
        app.oneshot(req).await.unwrap().status()
    }

    fn bearer(uri: &str, tok: &str) -> AxumRequest<axum::body::Body> {
        AxumRequest::builder()
            .uri(uri)
            .header(AUTHORIZATION, format!("Bearer {tok}"))
            .body(axum::body::Body::empty())
            .unwrap()
    }

    #[tokio::test]
    async fn valid_token_passes() {
        let uid = Uuid::new_v4();
        let tok = make_token(&uid.to_string(), FUTURE_EXP, SECRET);
        assert_eq!(status_for(user_app(), bearer("/p", &tok)).await, StatusCode::OK);
    }

    #[tokio::test]
    async fn expired_token_rejected() {
        let uid = Uuid::new_v4();
        let tok = make_token(&uid.to_string(), PAST_EXP, SECRET);
        assert_eq!(status_for(user_app(), bearer("/p", &tok)).await, StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn bad_signature_rejected() {
        let uid = Uuid::new_v4();
        let tok = make_token(&uid.to_string(), FUTURE_EXP, b"a_different_secret_value_for_signing!");
        assert_eq!(status_for(user_app(), bearer("/p", &tok)).await, StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn non_uuid_sub_rejected() {
        let tok = make_token("not-a-uuid", FUTURE_EXP, SECRET);
        assert_eq!(status_for(user_app(), bearer("/p", &tok)).await, StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn token_without_exp_rejected() {
        // A token lacking `exp` must be rejected (it would otherwise never
        // expire). Mint a claims object with only `sub`.
        #[derive(Serialize)]
        struct SubOnly {
            sub: String,
        }
        let tok = encode(
            &Header::new(Algorithm::HS256),
            &SubOnly { sub: Uuid::new_v4().to_string() },
            &EncodingKey::from_secret(SECRET),
        )
        .unwrap();
        assert_eq!(status_for(user_app(), bearer("/p", &tok)).await, StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn missing_header_rejected() {
        let req = AxumRequest::builder().uri("/p").body(axum::body::Body::empty()).unwrap();
        assert_eq!(status_for(user_app(), req).await, StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn internal_token_exact_match_passes() {
        let req = AxumRequest::builder()
            .uri("/p")
            .header(INTERNAL_TOKEN_HEADER, "s3cret-internal")
            .body(axum::body::Body::empty())
            .unwrap();
        assert_eq!(status_for(internal_app(), req).await, StatusCode::OK);
    }

    #[tokio::test]
    async fn internal_token_mismatch_rejected() {
        let req = AxumRequest::builder()
            .uri("/p")
            .header(INTERNAL_TOKEN_HEADER, "wrong")
            .body(axum::body::Body::empty())
            .unwrap();
        assert_eq!(status_for(internal_app(), req).await, StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn user_id_extension_is_injected() {
        // Handler reads Extension<UserId> and echoes it; assert the sub maps.
        async fn echo(axum::Extension(UserId(uid)): axum::Extension<UserId>) -> String {
            uid.to_string()
        }
        let uid = Uuid::new_v4();
        let tok = make_token(&uid.to_string(), FUTURE_EXP, SECRET);
        let app = Router::new()
            .route("/me", get(echo))
            .layer(from_fn_with_state(TestState, require_user::<TestState>))
            .with_state(TestState);
        let resp = app.oneshot(bearer("/me", &tok)).await.unwrap();
        let body = axum::body::to_bytes(resp.into_body(), 4096).await.unwrap();
        assert_eq!(String::from_utf8_lossy(&body), uid.to_string());
    }
}
