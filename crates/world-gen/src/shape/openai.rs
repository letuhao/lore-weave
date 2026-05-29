//! **v4.3d** OpenAI Chat Completions provider for [`LlmProvider`].
//!
//! Calls `/v1/chat/completions` with `response_format: { type: "json_schema",
//! strict: true }` so the assistant's reply is guaranteed to validate
//! against our `pick_shape` schema. No tool-use round-trip needed —
//! structured outputs cut a hop vs. Anthropic's tool path.
//!
//! **Cost model (gpt-4o-mini default):** ~$0.0001-0.001 per call without
//! caching; OpenAI automatically prompt-caches prefixes ≥1024 tokens at
//! 50% discount, which our system prompt comfortably exceeds. A default
//! 150-dispatch world runs ~$0.05-0.15.
//!
//! **Not wired to default dispatch.** Engine default stays `Weighted` —
//! users opt in via CLI flag or by constructing `DispatchMode::Llm
//! { provider: Arc::new(OpenAIProvider::new(key)), cache: ... }`.

use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::shape::llm::{
    parse_params_from_value, parse_shape_kind_str, pick_shape_schema_strict,
    shape_dispatch_system_prompt, shape_dispatch_user_message, LlmDecision, LlmError, LlmPrompt,
    LlmProvider,
};

/// Default model — cheapest fast-enough OpenAI option as of 2026-01.
pub const DEFAULT_MODEL: &str = "gpt-4o-mini-2024-07-18";

/// Chat Completions API base URL.
pub const DEFAULT_BASE_URL: &str = "https://api.openai.com";

pub struct OpenAIProvider {
    api_key: String,
    base_url: String,
    model: String,
    client: reqwest::blocking::Client,
}

impl std::fmt::Debug for OpenAIProvider {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("OpenAIProvider")
            .field("model", &self.model)
            .field("base_url", &self.base_url)
            .field("api_key", &"<redacted>")
            .finish()
    }
}

impl OpenAIProvider {
    pub fn with_base_url(
        api_key: impl Into<String>,
        base_url: impl Into<String>,
        model: impl Into<String>,
    ) -> Self {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("reqwest client builder should not fail with default config");
        Self {
            api_key: api_key.into(),
            base_url: base_url.into(),
            model: model.into(),
            client,
        }
    }

    pub fn new(api_key: impl Into<String>) -> Self {
        Self::with_base_url(api_key, DEFAULT_BASE_URL, DEFAULT_MODEL)
    }

    pub fn build_request(&self, prompt: &LlmPrompt) -> ChatCompletionsRequest {
        ChatCompletionsRequest {
            model: self.model.clone(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: shape_dispatch_system_prompt(),
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: shape_dispatch_user_message(prompt),
                },
            ],
            response_format: ResponseFormat {
                format_type: "json_schema".to_string(),
                json_schema: JsonSchemaSpec {
                    name: "pick_shape".to_string(),
                    strict: true,
                    schema: pick_shape_schema_strict(),
                },
            },
            temperature: 0.0,
        }
    }

    pub fn parse_response(
        response: &ChatCompletionsResponse,
        prompt: &LlmPrompt,
    ) -> Result<LlmDecision, LlmError> {
        let choice = response.choices.first().ok_or_else(|| {
            LlmError::InvalidResponse("response.choices is empty".to_string())
        })?;
        let content = &choice.message.content;
        let parsed: serde_json::Value = serde_json::from_str(content).map_err(|e| {
            LlmError::InvalidResponse(format!("structured-output content not JSON: {e}"))
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

impl LlmProvider for OpenAIProvider {
    fn pick(&self, prompt: &LlmPrompt) -> Result<LlmDecision, LlmError> {
        let body = self.build_request(prompt);
        let url = format!(
            "{}/v1/chat/completions",
            self.base_url.trim_end_matches('/')
        );
        let http_resp = self
            .client
            .post(&url)
            .bearer_auth(&self.api_key)
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .map_err(|e| LlmError::Transport(e.to_string()))?;
        let status = http_resp.status();
        if !status.is_success() {
            let body = http_resp
                .text()
                .unwrap_or_else(|e| format!("<failed to read error body: {e}>"));
            if status.as_u16() == 429 {
                return Err(LlmError::Refused(format!(
                    "openai rate-limited (status {status}): {body}"
                )));
            }
            return Err(LlmError::Transport(format!(
                "openai returned non-success status {status}: {body}"
            )));
        }
        let parsed: ChatCompletionsResponse = http_resp
            .json()
            .map_err(|e| LlmError::InvalidResponse(format!("response JSON parse: {e}")))?;
        Self::parse_response(&parsed, prompt)
    }
}

// ---------- Wire types ----------

#[derive(Debug, Clone, Serialize)]
pub struct ChatCompletionsRequest {
    pub model: String,
    pub messages: Vec<ChatMessage>,
    pub response_format: ResponseFormat,
    pub temperature: f32,
}

#[derive(Debug, Clone, Serialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ResponseFormat {
    #[serde(rename = "type")]
    pub format_type: String,
    pub json_schema: JsonSchemaSpec,
}

#[derive(Debug, Clone, Serialize)]
pub struct JsonSchemaSpec {
    pub name: String,
    pub strict: bool,
    pub schema: serde_json::Value,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ChatCompletionsResponse {
    pub choices: Vec<Choice>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Choice {
    pub message: ResponseMessage,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ResponseMessage {
    pub role: String,
    pub content: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;
    use crate::shape::{ParamOverride, ShapeKind};

    fn sample_prompt() -> LlmPrompt {
        LlmPrompt {
            entity_path: "plate.4.zone.0".to_string(),
            depth: 1,
            size_rank: SizeRank::Large,
            lat_norm: 0.18,
            parent_path: vec![4],
            allowed_kinds: vec![ShapeKind::Ellipse, ShapeKind::Boolean, ShapeKind::Stamp],
        }
    }

    #[test]
    fn build_request_pins_strict_json_schema_and_temperature_zero() {
        let p = OpenAIProvider::new("test-key");
        let req = p.build_request(&sample_prompt());
        assert_eq!(req.temperature, 0.0);
        assert_eq!(req.response_format.format_type, "json_schema");
        assert!(req.response_format.json_schema.strict);
        assert_eq!(req.response_format.json_schema.name, "pick_shape");
    }

    #[test]
    fn build_request_uses_system_then_user_messages() {
        let p = OpenAIProvider::new("test-key");
        let req = p.build_request(&sample_prompt());
        assert_eq!(req.messages.len(), 2);
        assert_eq!(req.messages[0].role, "system");
        assert_eq!(req.messages[1].role, "user");
        assert!(req.messages[1].content.contains("plate.4.zone.0"));
        assert!(req.messages[1].content.contains("Ellipse"));
    }

    fn fake_choice(json_str: &str) -> ChatCompletionsResponse {
        ChatCompletionsResponse {
            choices: vec![Choice {
                message: ResponseMessage {
                    role: "assistant".to_string(),
                    content: json_str.to_string(),
                },
            }],
        }
    }

    #[test]
    fn parse_response_ellipse_aspect_ratio() {
        let resp = fake_choice(r#"{"kind":"Ellipse","params":{"ellipse":{"aspect_ratio":2.1}}}"#);
        let d = OpenAIProvider::parse_response(&resp, &sample_prompt()).expect("parse Ellipse");
        assert_eq!(d.kind, ShapeKind::Ellipse);
        match d.params {
            Some(ParamOverride::Ellipse { aspect_ratio: Some(r) }) => {
                assert!((r - 2.1).abs() < 1e-4);
            }
            other => panic!("expected Ellipse aspect_ratio, got {other:?}"),
        }
    }

    #[test]
    fn parse_response_boolean_template() {
        let resp = fake_choice(r#"{"kind":"Boolean","params":{"boolean":{"template":"EllipseDifference"}}}"#);
        let d = OpenAIProvider::parse_response(&resp, &sample_prompt()).expect("parse Boolean");
        assert_eq!(d.kind, ShapeKind::Boolean);
        assert!(matches!(
            d.params,
            Some(ParamOverride::Boolean {
                template: Some(crate::shape::csg::BooleanTemplate::EllipseDifference)
            })
        ));
    }

    #[test]
    fn parse_response_stamp_template_id() {
        let resp = fake_choice(r#"{"kind":"Stamp","params":{"stamp":{"template_id":7}}}"#);
        let d = OpenAIProvider::parse_response(&resp, &sample_prompt()).expect("parse Stamp");
        assert_eq!(d.kind, ShapeKind::Stamp);
        assert!(matches!(
            d.params,
            Some(ParamOverride::Stamp { template_id: Some(7) })
        ));
    }

    #[test]
    fn parse_response_kind_outside_allowed_kinds_rejected() {
        let resp = fake_choice(r#"{"kind":"Slime"}"#);
        let err = OpenAIProvider::parse_response(&resp, &sample_prompt())
            .expect_err("Slime not in allowed_kinds");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }

    #[test]
    fn parse_response_invalid_content_json_rejected() {
        let resp = fake_choice("not json{");
        let err = OpenAIProvider::parse_response(&resp, &sample_prompt())
            .expect_err("non-JSON content");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }

    #[test]
    fn parse_response_empty_choices_rejected() {
        let resp = ChatCompletionsResponse { choices: vec![] };
        let err = OpenAIProvider::parse_response(&resp, &sample_prompt())
            .expect_err("empty choices");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }
}
