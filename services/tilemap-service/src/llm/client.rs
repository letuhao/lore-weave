//! Reqwest-based gateway HTTP client. Phase 0a defines the shape; Phase 0b
//! implements the SSE parsing loop + per-object retry + canonical-default fallback.

use std::time::Duration;

use reqwest::header::{ACCEPT, CONTENT_TYPE, HeaderMap, HeaderName, HeaderValue};
use uuid::Uuid;

use crate::llm::errors::LlmError;
use crate::llm::models::{ChatStreamRequest, GATEWAY_BASE_URL_DEFAULT, INTERNAL_STREAM_PATH};

/// Header name for the service-to-service token. Per
/// `contracts/api/llm-gateway/v1/openapi.yaml` security scheme
/// `internalServiceToken` (`type: apiKey`, `in: header`, `name: X-Internal-Token`).
const INTERNAL_TOKEN_HEADER: &str = "x-internal-token"; // HTTP header names are case-insensitive; lowercase per reqwest convention.

/// Service-to-service gateway client. One instance per tilemap-service process;
/// `reqwest::Client` is internally Arc-wrapped so cloning the `GatewayClient` is
/// cheap and the underlying connection pool is shared.
#[derive(Debug, Clone)]
pub struct GatewayClient {
    base_url: String,
    internal_token: String,
    #[allow(dead_code)] // used by Phase 0b SSE parser
    http: reqwest::Client,
}

impl GatewayClient {
    /// Construct from explicit base URL + internal token. Most callers use
    /// [`GatewayClient::from_env`] instead.
    pub fn new(base_url: impl Into<String>, internal_token: impl Into<String>) -> Self {
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(120))
            .connect_timeout(Duration::from_secs(10))
            .build()
            .expect("default reqwest client builder cannot fail");
        Self {
            base_url: base_url.into(),
            internal_token: internal_token.into(),
            http,
        }
    }

    /// Construct from env vars.
    ///
    /// `LOREWEAVE_INTERNAL_TOKEN` is REQUIRED — fails fast with
    /// [`LlmError::MissingInternalToken`] if unset or empty (CLAUDE.md
    /// "no hardcoded secrets / services fail to start if missing").
    ///
    /// `LOREWEAVE_GATEWAY_URL` is optional; defaults to
    /// [`GATEWAY_BASE_URL_DEFAULT`].
    pub fn from_env() -> Result<Self, LlmError> {
        let token = std::env::var("LOREWEAVE_INTERNAL_TOKEN")
            .ok()
            .filter(|t| !t.is_empty())
            .ok_or(LlmError::MissingInternalToken)?;
        let base = std::env::var("LOREWEAVE_GATEWAY_URL")
            .unwrap_or_else(|_| GATEWAY_BASE_URL_DEFAULT.to_string());
        Ok(Self::new(base, token))
    }

    /// Phase 0a: signature only — returns
    /// [`LlmError::NotImplementedPhase0a`]. Phase 0b will implement the SSE
    /// parsing loop, per-object retry per TMP_008b §5, and canonical-default
    /// fallback per TMP_008b §6.
    ///
    /// `user_id` is the user the call is on behalf of (for billing) and is
    /// required by the `/internal/llm/stream` endpoint per openapi.
    #[allow(clippy::unused_async)]
    pub async fn stream(
        &self,
        _request: ChatStreamRequest,
        _user_id: Uuid,
    ) -> Result<StreamHandle, LlmError> {
        Err(LlmError::NotImplementedPhase0a(
            "SSE parser + per-object retry + canonical-default fallback land in Phase 0b",
        ))
    }

    /// Headers applied to every request — `X-Internal-Token` apiKey + JSON
    /// content-type + SSE accept header.
    #[allow(dead_code)] // used by Phase 0b
    fn auth_headers(&self) -> Result<HeaderMap, LlmError> {
        let mut headers = HeaderMap::new();
        let header_name = HeaderName::from_static(INTERNAL_TOKEN_HEADER);
        let token_value = HeaderValue::from_str(&self.internal_token)
            .map_err(|e| LlmError::InvalidInternalToken(e.to_string()))?;
        headers.insert(header_name, token_value);
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
        headers.insert(ACCEPT, HeaderValue::from_static("text/event-stream"));
        Ok(headers)
    }

    /// Full URL for the service-to-service stream endpoint, including the
    /// required `user_id` query parameter.
    #[allow(dead_code)] // used by Phase 0b
    fn stream_url(&self, user_id: Uuid) -> String {
        format!(
            "{}{}?user_id={}",
            self.base_url.trim_end_matches('/'),
            INTERNAL_STREAM_PATH,
            user_id
        )
    }
}

/// Phase 0a placeholder for the streaming response handle. Phase 0b refines
/// to a `futures::Stream<Item = StreamEvent>` wrapper.
#[derive(Debug)]
pub struct StreamHandle {
    /// Phase 0a: empty marker. Phase 0b replaces with reqwest::Response + SSE parser.
    _phase_0a_placeholder: (),
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::llm::models::{ModelSource, StreamFormat};

    #[test]
    fn from_env_fails_without_token() {
        // SAFETY: `std::env::remove_var` is `unsafe` in Rust 2024 because env
        // mutation is racy w.r.t. other threads. This is safe here because no
        // other test in this crate reads or writes `LOREWEAVE_INTERNAL_TOKEN`
        // (verified by a project-wide grep at Phase 0a write time). If a future
        // test sets that env var, this assertion may flake under cargo test's
        // default multi-thread runner — adopt the `serial_test` crate then.
        unsafe {
            std::env::remove_var("LOREWEAVE_INTERNAL_TOKEN");
        }
        let result = GatewayClient::from_env();
        assert!(matches!(result, Err(LlmError::MissingInternalToken)));
    }

    #[test]
    fn stream_url_includes_user_id_query_parameter() {
        let c = GatewayClient::new("http://gateway", "tok");
        let user = Uuid::parse_str("11111111-2222-3333-4444-555555555555").unwrap();
        let url = c.stream_url(user);
        assert_eq!(
            url,
            "http://gateway/internal/llm/stream?user_id=11111111-2222-3333-4444-555555555555"
        );
    }

    #[test]
    fn stream_url_trims_trailing_slash_on_base() {
        let c = GatewayClient::new("http://gateway/", "tok");
        let user = Uuid::nil();
        let url = c.stream_url(user);
        assert!(url.starts_with("http://gateway/internal/llm/stream?user_id="));
        assert!(!url.contains("//internal"));
    }

    #[test]
    fn auth_headers_uses_x_internal_token() {
        let c = GatewayClient::new("http://gateway", "secret-token-123");
        let headers = c.auth_headers().expect("token has valid header characters");
        let token_value = headers
            .get(INTERNAL_TOKEN_HEADER)
            .expect("X-Internal-Token header present");
        assert_eq!(
            token_value.to_str().unwrap(),
            "secret-token-123",
            "raw token in X-Internal-Token (NOT Bearer-prefixed)"
        );
        // Defensive: never set Authorization Bearer for the internal endpoint.
        assert!(
            headers.get(reqwest::header::AUTHORIZATION).is_none(),
            "/internal/llm/stream uses X-Internal-Token, not Authorization Bearer"
        );
    }

    #[test]
    fn auth_headers_rejects_invalid_token() {
        // CR/LF in a header value triggers reqwest's InvalidHeaderValue.
        let c = GatewayClient::new("http://gateway", "bad\r\ntoken");
        let result = c.auth_headers();
        assert!(matches!(result, Err(LlmError::InvalidInternalToken(_))));
    }

    #[tokio::test]
    async fn stream_returns_not_implemented_in_phase_0a() {
        let c = GatewayClient::new("http://gateway", "tok");
        let req = ChatStreamRequest::new_chat_with_tools(
            ModelSource::PlatformModel,
            Uuid::nil(),
            vec![],
            vec![],
            StreamFormat::Anthropic,
        );
        let result = c.stream(req, Uuid::nil()).await;
        assert!(matches!(result, Err(LlmError::NotImplementedPhase0a(_))));
    }
}
