//! Real BYOK-gateway [`EmbeddingProvider`] — 089 D-EMBEDDING-PROVIDER-WIRING.
//!
//! Calls provider-registry-service `POST /internal/embed` (OUR BYOK gateway — NOT a
//! vendor SDK, per the CLAUDE.md provider-gateway invariant) with a PLATFORM embedding
//! credential. NPC-memory embedding is system background work (the audit is already
//! `system_only`; a reality is a shared world via book_reality_subscription with no
//! single owner), so a platform-owned `user_id` + `model_ref` pays. Those are constant
//! per worker → the [`EmbeddingProvider`] trait stays `embed(&self, text)` (no per-call
//! user resolution). Per-reality/per-user attribution is deferred
//! (D-EMBEDDING-PER-REALITY-ATTRIBUTION); this replaces the fail-closed
//! [`super::NotWiredProvider`] the binary wired before.

use std::time::Duration;

use async_trait::async_trait;
use serde::Deserialize;
use uuid::Uuid;

use crate::embedding_queue::{EmbedResult, EmbeddingProvider};

/// Provider-gateway config (platform embedding credential). [`from_env`] returns `None`
/// when NONE of the vars are set (worker keeps the fail-closed NotWiredProvider), and
/// an `Err` when SOME-but-not-all are set or a UUID is malformed (mis-config fails loud
/// rather than silently downgrading).
#[derive(Debug, Clone)]
pub struct EmbedProviderConfig {
    /// provider-registry base URL, e.g. `http://provider-registry-service:8085`.
    pub gateway_url: String,
    /// `X-Internal-Token` s2s secret (matches provider-registry `InternalServiceToken`).
    pub internal_token: String,
    /// Platform embedding account (the `?user_id=` the gateway uses to select the cred).
    pub user_id: Uuid,
    /// The platform's `user_models` embedding row (the gateway's `model_ref`).
    pub model_ref: Uuid,
}

impl EmbedProviderConfig {
    /// Read from `EMBEDDING_GATEWAY_URL` / `EMBEDDING_INTERNAL_TOKEN` /
    /// `EMBEDDING_PLATFORM_USER_ID` / `EMBEDDING_MODEL_REF`.
    pub fn from_env() -> Result<Option<Self>, String> {
        Self::from_parts(
            std::env::var("EMBEDDING_GATEWAY_URL").unwrap_or_default(),
            std::env::var("EMBEDDING_INTERNAL_TOKEN").unwrap_or_default(),
            std::env::var("EMBEDDING_PLATFORM_USER_ID").unwrap_or_default(),
            std::env::var("EMBEDDING_MODEL_REF").unwrap_or_default(),
        )
    }

    /// Pure constructor from the 4 raw values (unit-testable without process env).
    pub fn from_parts(
        gateway_url: String,
        internal_token: String,
        user_id: String,
        model_ref: String,
    ) -> Result<Option<Self>, String> {
        let any = [&gateway_url, &internal_token, &user_id, &model_ref]
            .iter()
            .any(|v| !v.is_empty());
        if !any {
            return Ok(None); // nothing configured → NotWired fallback
        }
        let all = [&gateway_url, &internal_token, &user_id, &model_ref]
            .iter()
            .all(|v| !v.is_empty());
        if !all {
            return Err("partial EMBEDDING_* provider config: set ALL of \
                 EMBEDDING_GATEWAY_URL / EMBEDDING_INTERNAL_TOKEN / \
                 EMBEDDING_PLATFORM_USER_ID / EMBEDDING_MODEL_REF, or none"
                .to_string());
        }
        let user_id = Uuid::parse_str(&user_id)
            .map_err(|e| format!("EMBEDDING_PLATFORM_USER_ID not a UUID: {e}"))?;
        let model_ref = Uuid::parse_str(&model_ref)
            .map_err(|e| format!("EMBEDDING_MODEL_REF not a UUID: {e}"))?;
        Ok(Some(Self {
            gateway_url: gateway_url.trim_end_matches('/').to_string(),
            internal_token,
            user_id,
            model_ref,
        }))
    }
}

/// reqwest-backed provider calling the BYOK gateway's `POST /internal/embed`.
pub struct HttpEmbeddingProvider {
    client: reqwest::Client,
    cfg: EmbedProviderConfig,
}

impl HttpEmbeddingProvider {
    /// Build the provider with a 30s request timeout (context-free; the gateway's
    /// upstream call can be slow for a cold local-embeddings model).
    pub fn new(cfg: EmbedProviderConfig) -> Result<Self, String> {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|e| format!("embedding http client: {e}"))?;
        Ok(Self { client, cfg })
    }
}

/// The gateway's 200 response (`provider.EmbedResult`). No token usage is returned →
/// audit `tokens = 0` (tracked: D-EMBEDDING-TOKEN-ACCOUNTING).
#[derive(Deserialize)]
struct EmbedResponse {
    embeddings: Vec<Vec<f64>>,
    #[allow(dead_code)]
    dimension: i64,
    #[serde(default)]
    model: String,
}

#[async_trait]
impl EmbeddingProvider for HttpEmbeddingProvider {
    async fn embed(&self, text: &str) -> (String, EmbedResult) {
        let url = format!("{}/internal/embed", self.cfg.gateway_url);
        let body = serde_json::json!({
            "model_source": "user_model",
            "model_ref": self.cfg.model_ref.to_string(),
            "texts": [text],
        });
        let fallback = self.cfg.model_ref.to_string();
        let resp = self
            .client
            .post(&url)
            .query(&[("user_id", self.cfg.user_id.to_string())])
            .header("X-Internal-Token", &self.cfg.internal_token)
            .json(&body)
            .send()
            .await;
        match resp {
            Ok(r) => {
                let status = r.status().as_u16();
                match r.bytes().await {
                    Ok(bytes) => parse_embed_response(status, &bytes, &fallback),
                    Err(e) => (
                        fallback,
                        EmbedResult::ProviderError(format!("read embed body: {e}")),
                    ),
                }
            }
            Err(e) => (
                fallback,
                EmbedResult::ProviderError(format!("embed request: {e}")),
            ),
        }
    }

    fn provider_name(&self) -> &str {
        "byok-gateway"
    }
}

/// Pure response parser — unit-tested without a server. 200 + ≥1 embedding → `Ok`
/// (f64→f32; tokens=0); empty/bad-JSON/non-200 → `ProviderError`. Dimension is left to
/// the `Worker` guard (it rejects ≠`EMBEDDING_DIM` as `dim_mismatch`).
pub fn parse_embed_response(
    status: u16,
    body: &[u8],
    fallback_model: &str,
) -> (String, EmbedResult) {
    if status != 200 {
        let snippet: String = String::from_utf8_lossy(body).chars().take(300).collect();
        return (
            fallback_model.to_string(),
            EmbedResult::ProviderError(format!("gateway status {status}: {snippet}")),
        );
    }
    let parsed: EmbedResponse = match serde_json::from_slice(body) {
        Ok(p) => p,
        Err(e) => {
            return (
                fallback_model.to_string(),
                EmbedResult::ProviderError(format!("decode embed response: {e}")),
            );
        }
    };
    let model = if parsed.model.is_empty() {
        fallback_model.to_string()
    } else {
        parsed.model
    };
    let Some(first) = parsed.embeddings.into_iter().next() else {
        return (
            model,
            EmbedResult::ProviderError("gateway returned no embeddings".to_string()),
        );
    };
    let vector: Vec<f32> = first.into_iter().map(|x| x as f32).collect();
    (model, EmbedResult::Ok { vector, tokens: 0 })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn from_parts_none_when_unset() {
        assert!(
            EmbedProviderConfig::from_parts(
                String::new(),
                String::new(),
                String::new(),
                String::new()
            )
            .unwrap()
            .is_none()
        );
    }

    #[test]
    fn from_parts_err_when_partial() {
        let r = EmbedProviderConfig::from_parts(
            "http://x".into(),
            String::new(),
            String::new(),
            String::new(),
        );
        assert!(
            r.is_err(),
            "partial config must fail loud, not silently downgrade"
        );
    }

    #[test]
    fn from_parts_some_when_all_valid_and_trims_slash() {
        let u = Uuid::from_u128(1).to_string();
        let m = Uuid::from_u128(2).to_string();
        let cfg = EmbedProviderConfig::from_parts("http://gw:8085/".into(), "tok".into(), u, m)
            .unwrap()
            .expect("all-valid → Some");
        assert_eq!(cfg.gateway_url, "http://gw:8085", "trailing slash trimmed");
        assert_eq!(cfg.internal_token, "tok");
    }

    #[test]
    fn from_parts_err_on_bad_uuid() {
        let r = EmbedProviderConfig::from_parts(
            "http://x".into(),
            "tok".into(),
            "not-a-uuid".into(),
            Uuid::from_u128(2).to_string(),
        );
        assert!(r.is_err());
    }

    #[test]
    fn parse_ok_converts_first_embedding_f64_to_f32() {
        let body =
            br#"{"embeddings":[[0.5,-1.25,2.0]],"dimension":3,"model":"text-embedding-ada-002"}"#;
        let (model, res) = parse_embed_response(200, body, "fallback");
        assert_eq!(model, "text-embedding-ada-002");
        match res {
            EmbedResult::Ok { vector, tokens } => {
                assert_eq!(vector, vec![0.5f32, -1.25, 2.0]);
                assert_eq!(tokens, 0, "gateway returns no usage → tokens 0");
            }
            other => panic!("expected Ok, got {other:?}"),
        }
    }

    #[test]
    fn parse_does_not_enforce_dim_leaves_it_to_the_worker_guard() {
        // The parser must NOT coerce/pad/reject on length — it passes the gateway's
        // actual vector length through so the Worker's EMBEDDING_DIM guard is the single
        // dim authority (a 768-dim gateway response is caught there as dim_mismatch).
        let body = br#"{"embeddings":[[0.1,0.2]],"dimension":2,"model":"m"}"#;
        let (_m, res) = parse_embed_response(200, body, "f");
        match res {
            EmbedResult::Ok { vector, .. } => {
                assert_eq!(vector.len(), 2, "length passed through verbatim")
            }
            other => panic!("expected Ok, got {other:?}"),
        }
    }

    #[test]
    fn parse_uses_fallback_model_when_response_model_empty() {
        let body = br#"{"embeddings":[[0.1]],"dimension":1}"#;
        let (model, _res) = parse_embed_response(200, body, "model-ref-uuid");
        assert_eq!(model, "model-ref-uuid");
    }

    #[test]
    fn parse_empty_embeddings_is_provider_error() {
        let body = br#"{"embeddings":[],"dimension":0,"model":"m"}"#;
        let (_m, res) = parse_embed_response(200, body, "f");
        assert!(matches!(res, EmbedResult::ProviderError(_)));
    }

    #[test]
    fn parse_non_200_is_provider_error_with_status() {
        let (_m, res) = parse_embed_response(502, b"upstream down", "f");
        match res {
            EmbedResult::ProviderError(e) => assert!(e.contains("502")),
            other => panic!("expected ProviderError, got {other:?}"),
        }
    }

    #[test]
    fn parse_bad_json_is_provider_error() {
        let (_m, res) = parse_embed_response(200, b"{not json", "f");
        assert!(matches!(res, EmbedResult::ProviderError(_)));
    }

    #[test]
    fn provider_name_is_stable() {
        let cfg = EmbedProviderConfig {
            gateway_url: "http://x".into(),
            internal_token: "t".into(),
            user_id: Uuid::from_u128(1),
            model_ref: Uuid::from_u128(2),
        };
        let p = HttpEmbeddingProvider::new(cfg).unwrap();
        assert_eq!(p.provider_name(), "byok-gateway");
    }

    // H1: pin the cross-service REQUEST shape against the provider-registry contract
    // (server.go internalEmbed). wiremock fails the test (404 → ProviderError + the
    // expect(1) assertion on drop) if ANY matcher misses — so a future rename of the
    // query param / header / body field on either side is caught here, not in prod as a
    // silent audited ProviderError "embedding blackout".
    #[tokio::test]
    async fn http_provider_sends_contract_shaped_request() {
        use wiremock::matchers::{body_partial_json, header, method, path, query_param};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let server = MockServer::start().await;
        let user = Uuid::from_u128(7);
        let model = Uuid::from_u128(9);
        Mock::given(method("POST"))
            .and(path("/internal/embed"))
            .and(query_param("user_id", user.to_string().as_str()))
            .and(header("X-Internal-Token", "sekret"))
            .and(body_partial_json(serde_json::json!({
                "model_source": "user_model",
                "model_ref": model.to_string(),
                "texts": ["hello"],
            })))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "embeddings": [[0.1, 0.2]],
                "dimension": 2,
                "model": "text-embedding-test",
            })))
            .expect(1)
            .mount(&server)
            .await;

        let cfg = EmbedProviderConfig {
            gateway_url: server.uri(),
            internal_token: "sekret".into(),
            user_id: user,
            model_ref: model,
        };
        let provider = HttpEmbeddingProvider::new(cfg).unwrap();
        let (model_out, res) = provider.embed("hello").await;
        assert_eq!(model_out, "text-embedding-test");
        assert!(
            matches!(res, EmbedResult::Ok { .. }),
            "matched request → Ok, got {res:?}"
        );
        // server drop verifies expect(1): the request matched method+path+query+header+body.
    }
}
