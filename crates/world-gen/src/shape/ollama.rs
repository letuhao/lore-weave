//! **v4.3d** Ollama provider for [`LlmProvider`].
//!
//! Calls a local Ollama HTTP daemon (`/api/chat`) with the same
//! `pick_shape` JSON schema as the other two providers, passed via the
//! `format` parameter so the daemon constrains the output. The Ollama
//! daemon is presumed to be locally hosted (default
//! `http://localhost:11434`) so latency dominates over $; we still pin
//! `temperature: 0.0` for determinism.
//!
//! **Cost model:** $0 — runs on the user's hardware. Default model is a
//! small instruction-tuned model the user has pulled (`llama3.1` is a
//! reasonable default; the user can override). Per-call latency on a
//! GPU is ~200-500ms.
//!
//! **Not wired to default dispatch.** Engine default stays `Weighted` —
//! opt in via CLI flag or by constructing `DispatchMode::Llm
//! { provider: Arc::new(OllamaProvider::new("llama3.1")), cache: ... }`.

use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::shape::llm::{
    parse_params_from_value, parse_shape_kind_str, pick_shape_schema_strict,
    shape_dispatch_system_prompt, shape_dispatch_user_message, LlmDecision, LlmError, LlmPrompt,
    LlmProvider,
};

/// Default model — user is expected to have `ollama pull llama3.1` before
/// running. Switch via [`OllamaProvider::with_base_url`].
pub const DEFAULT_MODEL: &str = "llama3.1";

/// Default Ollama daemon URL.
pub const DEFAULT_BASE_URL: &str = "http://localhost:11434";

pub struct OllamaProvider {
    base_url: String,
    model: String,
    client: reqwest::blocking::Client,
}

impl std::fmt::Debug for OllamaProvider {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("OllamaProvider")
            .field("model", &self.model)
            .field("base_url", &self.base_url)
            .finish()
    }
}

impl OllamaProvider {
    pub fn with_base_url(
        base_url: impl Into<String>,
        model: impl Into<String>,
    ) -> Self {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(60))
            .build()
            .expect("reqwest client builder should not fail with default config");
        Self {
            base_url: base_url.into(),
            model: model.into(),
            client,
        }
    }

    pub fn new(model: impl Into<String>) -> Self {
        Self::with_base_url(DEFAULT_BASE_URL, model)
    }

    pub fn build_request(&self, prompt: &LlmPrompt) -> OllamaChatRequest {
        OllamaChatRequest {
            model: self.model.clone(),
            messages: vec![
                OllamaMessage {
                    role: "system".to_string(),
                    content: shape_dispatch_system_prompt(),
                },
                OllamaMessage {
                    role: "user".to_string(),
                    content: shape_dispatch_user_message(prompt),
                },
            ],
            format: pick_shape_schema_strict(),
            stream: false,
            options: OllamaOptions {
                temperature: 0.0,
            },
        }
    }

    pub fn parse_response(
        response: &OllamaChatResponse,
        prompt: &LlmPrompt,
    ) -> Result<LlmDecision, LlmError> {
        let content = &response.message.content;
        let parsed: serde_json::Value = serde_json::from_str(content).map_err(|e| {
            LlmError::InvalidResponse(format!("ollama format content not JSON: {e}"))
        })?;
        let kind_str = parsed
            .get("kind")
            .and_then(|v| v.as_str())
            .ok_or_else(|| {
                LlmError::InvalidResponse("decoded JSON missing string `kind`".to_string())
            })?;
        let kind = parse_shape_kind_str(kind_str)?;
        if !prompt.allowed_kinds.contains(&kind) {
            return Err(LlmError::InvalidResponse(format!(
                "kind {kind:?} not in allowed_kinds {:?}",
                prompt.allowed_kinds
            )));
        }
        let params = parse_params_from_value(kind, parsed.get("params"))?;
        Ok(LlmDecision { kind, params })
    }
}

impl LlmProvider for OllamaProvider {
    fn pick(&self, prompt: &LlmPrompt) -> Result<LlmDecision, LlmError> {
        let body = self.build_request(prompt);
        let url = format!("{}/api/chat", self.base_url.trim_end_matches('/'));
        let http_resp = self
            .client
            .post(&url)
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .map_err(|e| LlmError::Transport(e.to_string()))?;
        let status = http_resp.status();
        if !status.is_success() {
            let body = http_resp
                .text()
                .unwrap_or_else(|e| format!("<failed to read error body: {e}>"));
            return Err(LlmError::Transport(format!(
                "ollama returned non-success status {status}: {body}"
            )));
        }
        let parsed: OllamaChatResponse = http_resp
            .json()
            .map_err(|e| LlmError::InvalidResponse(format!("response JSON parse: {e}")))?;
        Self::parse_response(&parsed, prompt)
    }
}

// ---------- Wire types ----------

#[derive(Debug, Clone, Serialize)]
pub struct OllamaChatRequest {
    pub model: String,
    pub messages: Vec<OllamaMessage>,
    pub format: serde_json::Value,
    pub stream: bool,
    pub options: OllamaOptions,
}

#[derive(Debug, Clone, Serialize)]
pub struct OllamaMessage {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct OllamaOptions {
    pub temperature: f32,
}

#[derive(Debug, Clone, Deserialize)]
pub struct OllamaChatResponse {
    pub message: OllamaResponseMessage,
}

#[derive(Debug, Clone, Deserialize)]
pub struct OllamaResponseMessage {
    pub role: String,
    pub content: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;
    use crate::shape::csg::BooleanTemplate;
    use crate::shape::{ParamOverride, ShapeKind};

    fn sample_prompt() -> LlmPrompt {
        LlmPrompt {
            entity_path: "plate.0.zone.0".to_string(),
            depth: 1,
            size_rank: SizeRank::Small,
            lat_norm: 0.95,
            parent_path: vec![0],
            allowed_kinds: vec![ShapeKind::Ellipse, ShapeKind::Boolean, ShapeKind::Stamp],
        }
    }

    #[test]
    fn build_request_pins_format_schema_no_stream_temperature_zero() {
        let p = OllamaProvider::new("llama3.1");
        let req = p.build_request(&sample_prompt());
        assert!(!req.stream);
        assert_eq!(req.options.temperature, 0.0);
        // format schema must mention `kind` enum
        let formatted = serde_json::to_string(&req.format).unwrap();
        assert!(formatted.contains("Ellipse"));
        assert!(formatted.contains("Stamp"));
    }

    #[test]
    fn build_request_uses_system_then_user_messages() {
        let p = OllamaProvider::new("llama3.1");
        let req = p.build_request(&sample_prompt());
        assert_eq!(req.messages.len(), 2);
        assert_eq!(req.messages[0].role, "system");
        assert_eq!(req.messages[1].role, "user");
        assert!(req.messages[1].content.contains("plate.0.zone.0"));
    }

    fn fake_response(content: &str) -> OllamaChatResponse {
        OllamaChatResponse {
            message: OllamaResponseMessage {
                role: "assistant".to_string(),
                content: content.to_string(),
            },
        }
    }

    #[test]
    fn parse_response_ellipse_aspect_ratio() {
        let resp = fake_response(r#"{"kind":"Ellipse","params":{"ellipse":{"aspect_ratio":1.4}}}"#);
        let d = OllamaProvider::parse_response(&resp, &sample_prompt()).expect("parse Ellipse");
        assert_eq!(d.kind, ShapeKind::Ellipse);
        match d.params {
            Some(ParamOverride::Ellipse { aspect_ratio: Some(r) }) => {
                assert!((r - 1.4).abs() < 1e-4);
            }
            other => panic!("expected Ellipse aspect_ratio, got {other:?}"),
        }
    }

    #[test]
    fn parse_response_boolean_template() {
        let resp = fake_response(r#"{"kind":"Boolean","params":{"boolean":{"template":"EllipseUnion"}}}"#);
        let d = OllamaProvider::parse_response(&resp, &sample_prompt()).expect("parse Boolean");
        assert!(matches!(
            d.params,
            Some(ParamOverride::Boolean { template: Some(BooleanTemplate::EllipseUnion) })
        ));
    }

    #[test]
    fn parse_response_stamp_template_id() {
        let resp = fake_response(r#"{"kind":"Stamp","params":{"stamp":{"template_id":3}}}"#);
        let d = OllamaProvider::parse_response(&resp, &sample_prompt()).expect("parse Stamp");
        assert!(matches!(
            d.params,
            Some(ParamOverride::Stamp { template_id: Some(3) })
        ));
    }

    #[test]
    fn parse_response_kind_outside_allowed_kinds_rejected() {
        let resp = fake_response(r#"{"kind":"Slime"}"#);
        let err = OllamaProvider::parse_response(&resp, &sample_prompt())
            .expect_err("Slime not in allowed_kinds");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }

    #[test]
    fn parse_response_invalid_content_json_rejected() {
        let resp = fake_response("not json{");
        let err = OllamaProvider::parse_response(&resp, &sample_prompt())
            .expect_err("non-JSON content");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }
}
