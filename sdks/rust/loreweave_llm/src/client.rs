//! Reqwest-based gateway HTTP client + SSE parsing loop (Phase 0b).

use std::time::Duration;

use reqwest::header::{ACCEPT, CONTENT_TYPE, HeaderMap, HeaderName, HeaderValue};
use uuid::Uuid;

use crate::errors::LlmError;
use crate::models::{ChatStreamRequest, GATEWAY_BASE_URL_DEFAULT, INTERNAL_STREAM_PATH, StreamEvent};
use crate::sse::SseDecoder;

/// Header name for the service-to-service token. Per
/// `contracts/api/llm-gateway/v1/openapi.yaml` security scheme
/// `internalServiceToken` (`type: apiKey`, `in: header`, `name: X-Internal-Token`).
/// HTTP header names are case-insensitive; lowercase form per reqwest convention.
const INTERNAL_TOKEN_HEADER: &str = "x-internal-token";

/// Service-to-service gateway client. One instance per service process;
/// `reqwest::Client` is internally Arc-wrapped so cloning the `GatewayClient` is
/// cheap and the underlying connection pool is shared.
#[derive(Debug, Clone)]
pub struct GatewayClient {
    base_url: String,
    internal_token: String,
    http: reqwest::Client,
}

impl GatewayClient {
    /// Construct from explicit base URL + internal token. Most callers use
    /// [`GatewayClient::from_env`] instead.
    pub fn new(base_url: impl Into<String>, internal_token: impl Into<String>) -> Self {
        let http = reqwest::Client::builder()
            // NO total-request `.timeout()` — an SSE stream from a slow
            // thinking model (Qwen3.x, etc.) can legitimately run for
            // minutes; a total timeout would abort a healthy stream
            // mid-flight (the Go gateway deliberately has no wall-clock
            // timeout on this path either). `.read_timeout` is a per-read
            // IDLE timeout: the connection is killed only if no bytes arrive
            // for the window — the correct guard for a streamed response.
            .connect_timeout(Duration::from_secs(10))
            .read_timeout(Duration::from_secs(180))
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

    /// Open a streaming chat completion against `/internal/llm/stream`.
    ///
    /// POSTs `request` as JSON, then returns a [`StreamHandle`] that yields
    /// canonical [`StreamEvent`]s as the SSE body arrives. A non-2xx status
    /// (e.g. `400 LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER`) is surfaced as
    /// [`LlmError::GatewayHttpStatus`] before any event.
    ///
    /// `user_id` is the user the call is on behalf of (for billing) and is
    /// required by the `/internal/llm/stream` endpoint per openapi.
    pub async fn stream(
        &self,
        request: ChatStreamRequest,
        user_id: Uuid,
    ) -> Result<StreamHandle, LlmError> {
        let url = self.stream_url(user_id);
        let headers = self.auth_headers()?;
        let resp = self
            .http
            .post(&url)
            .headers(headers)
            .json(&request)
            .send()
            .await?;
        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(LlmError::GatewayHttpStatus { status, body });
        }
        Ok(StreamHandle::new(resp))
    }

    /// Headers applied to every request — `X-Internal-Token` apiKey + JSON
    /// content-type + SSE accept header.
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
    fn stream_url(&self, user_id: Uuid) -> String {
        format!(
            "{}{}?user_id={}",
            self.base_url.trim_end_matches('/'),
            INTERNAL_STREAM_PATH,
            user_id
        )
    }
}

/// Streaming response handle. Call [`StreamHandle::next`] in a loop until it
/// returns `None`; each `Some(Ok(_))` is one canonical [`StreamEvent`].
///
/// A thin async loop over [`reqwest::Response::chunk`] feeding an
/// [`SseDecoder`] — see [`crate::sse`] for the byte-level parsing.
#[derive(Debug)]
pub struct StreamHandle {
    resp: reqwest::Response,
    decoder: SseDecoder,
    /// Set once the body is exhausted, the decoder hit a terminal event, or a
    /// transport error occurred.
    finished: bool,
}

impl StreamHandle {
    fn new(resp: reqwest::Response) -> Self {
        Self {
            resp,
            decoder: SseDecoder::new(),
            finished: false,
        }
    }

    /// Yield the next canonical event. `None` marks the end of the stream.
    /// A `Some(Err(_))` is terminal — subsequent calls return `None`.
    pub async fn next(&mut self) -> Option<Result<StreamEvent, LlmError>> {
        loop {
            if let Some(item) = self.decoder.pop() {
                return Some(item);
            }
            // The decoder terminated (error event / parse failure) and its
            // queue is now drained — stop without reading more body.
            if self.finished || self.decoder.terminated() {
                return None;
            }
            match self.resp.chunk().await {
                Ok(Some(bytes)) => self.decoder.feed(&bytes),
                Ok(None) => {
                    self.decoder.finish();
                    self.finished = true;
                }
                Err(e) => {
                    self.finished = true;
                    return Some(Err(LlmError::Http(e)));
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{ModelSource, StreamFormat};

    #[test]
    fn from_env_fails_without_token() {
        // SAFETY: `std::env::remove_var` is `unsafe` in Rust 2024 because env
        // mutation is racy w.r.t. other threads. This is safe here because no
        // other test in this crate reads or writes `LOREWEAVE_INTERNAL_TOKEN`
        // (verified by a project-wide grep). If a future test sets that env
        // var, this assertion may flake under cargo test's default multi-thread
        // runner — adopt the `serial_test` crate then.
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

    #[test]
    fn chat_request_with_tools_constructs() {
        // Smoke: the tool-call request shape builds with a forced tool_choice.
        let req = ChatStreamRequest::new_chat_with_tools(
            ModelSource::PlatformModel,
            Uuid::nil(),
            vec![],
            vec![],
            StreamFormat::Openai,
        )
        .with_tool_choice(serde_json::json!({"type": "function", "function": {"name": "x"}}));
        assert!(req.tool_choice.is_some());
    }
}
