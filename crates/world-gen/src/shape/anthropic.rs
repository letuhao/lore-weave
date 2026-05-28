//! **v4.3c** Anthropic Claude provider for [`LlmProvider`].
//!
//! Calls the Anthropic Messages API (`/v1/messages`) with a tool-use schema
//! that pins the output to `(ShapeKind, ParamOverride)` so the response
//! cannot decode into a kind the registry doesn't carry. The system
//! prompt — which holds the algorithm catalog + dispatch rubric and is
//! identical for every dispatch site in a `flatworld::generate` call — is
//! tagged with `cache_control: { type: "ephemeral" }` so subsequent calls
//! get the 90% discount on the cached prefix.
//!
//! **Cost model (Haiku 4.5 default):** the catalog system prompt is
//! roughly 800-1200 input tokens; per-call user message is ~100-150
//! tokens; tool-use response ~50 tokens. With prompt caching active that's
//! ~$0.0005-0.001 per cached call after the first. A default world's
//! dispatch surface is ~150 calls (12 plates × 4-6 zones × 2-3 sub-zones)
//! so a full LLM-driven render lands around $0.10-0.20 per generate when
//! the dispatcher cache (in-process `InMemoryDispatchCache`) is also
//! enabled the second world reuse is free.
//!
//! **Not wired to default dispatch.** The engine default still routes
//! through `Weighted` — LLM mode is opt-in via the CLI flag
//! `--llm-anthropic` (see `main.rs`) or by constructing
//! `DispatchMode::Llm { provider: AnthropicProvider, cache: ... }`
//! directly. v3.0 hash pin tests stay green because nothing on the
//! default path constructs this struct.

use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::shape::llm::{
    parse_params_from_value, parse_shape_kind_str, pick_shape_schema_strict,
    shape_dispatch_system_prompt, shape_dispatch_user_message, LlmDecision, LlmError, LlmPrompt,
    LlmProvider,
};

/// Default model — Anthropic's cheapest+fastest as of 2026-01.
pub const DEFAULT_MODEL: &str = "claude-haiku-4-5-20251001";

/// Anthropic Messages API base URL.
pub const DEFAULT_BASE_URL: &str = "https://api.anthropic.com";

/// Anthropic API version pin. Bump in sync with the request format if
/// Anthropic publishes a breaking change.
pub const API_VERSION: &str = "2023-06-01";

/// Configurable Anthropic provider. Hold one instance for the whole
/// `flatworld::generate` invocation and share via `Arc<dyn LlmProvider>` —
/// the inner `reqwest::blocking::Client` pools connections, so the per-
/// dispatch overhead is dominated by network RTT not TCP handshake.
pub struct AnthropicProvider {
    api_key: String,
    base_url: String,
    model: String,
    client: reqwest::blocking::Client,
}

impl std::fmt::Debug for AnthropicProvider {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("AnthropicProvider")
            .field("model", &self.model)
            .field("base_url", &self.base_url)
            .field("api_key", &"<redacted>")
            .finish()
    }
}

impl AnthropicProvider {
    /// Build with a custom base URL — handy for tests that redirect to a
    /// local mock server. Production callers use [`AnthropicProvider::new`]
    /// which defaults `base_url` to [`DEFAULT_BASE_URL`].
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

    /// Convenience: production base URL + default model.
    pub fn new(api_key: impl Into<String>) -> Self {
        Self::with_base_url(api_key, DEFAULT_BASE_URL, DEFAULT_MODEL)
    }

    /// Build the Messages-API request body for a given prompt. Public for
    /// testing — production code reaches it through [`LlmProvider::pick`].
    pub fn build_request(&self, prompt: &LlmPrompt) -> MessagesRequest {
        let system = vec![SystemBlock {
            block_type: "text".to_string(),
            text: shape_dispatch_system_prompt(),
            cache_control: Some(CacheControl {
                control_type: "ephemeral".to_string(),
            }),
        }];

        let user_text = shape_dispatch_user_message(prompt);

        let tool = ToolDef {
            name: "pick_shape".to_string(),
            description: "Choose a shape generator and (optionally) its \
                          parameter override for the described entity."
                .to_string(),
            input_schema: pick_shape_schema_strict(),
        };

        MessagesRequest {
            model: self.model.clone(),
            max_tokens: 256,
            system,
            messages: vec![UserMessage {
                role: "user".to_string(),
                content: vec![ContentBlock::Text { text: user_text }],
            }],
            tools: vec![tool],
            tool_choice: ToolChoice {
                choice_type: "tool".to_string(),
                name: "pick_shape".to_string(),
            },
            temperature: 0.0,
        }
    }

    /// Parse a Messages-API response into an [`LlmDecision`]. Public for
    /// testing.
    pub fn parse_response(
        response: &MessagesResponse,
        prompt: &LlmPrompt,
    ) -> Result<LlmDecision, LlmError> {
        let tool_use = response
            .content
            .iter()
            .find_map(|b| match b {
                ResponseContentBlock::ToolUse { name, input, .. } if name == "pick_shape" => {
                    Some(input)
                }
                _ => None,
            })
            .ok_or_else(|| {
                LlmError::InvalidResponse(
                    "no `pick_shape` tool_use block in response content".to_string(),
                )
            })?;

        let kind_str = tool_use
            .get("kind")
            .and_then(|v| v.as_str())
            .ok_or_else(|| {
                LlmError::InvalidResponse(
                    "tool_use.input.kind missing or not a string".to_string(),
                )
            })?;
        let kind = parse_shape_kind_str(kind_str)?;
        if !prompt.allowed_kinds.contains(&kind) {
            return Err(LlmError::InvalidResponse(format!(
                "kind {kind:?} not in allowed_kinds {:?}",
                prompt.allowed_kinds
            )));
        }
        let params = parse_params_from_value(kind, tool_use.get("params"))?;
        Ok(LlmDecision { kind, params })
    }
}

impl LlmProvider for AnthropicProvider {
    fn pick(&self, prompt: &LlmPrompt) -> Result<LlmDecision, LlmError> {
        let body = self.build_request(prompt);
        let url = format!("{}/v1/messages", self.base_url.trim_end_matches('/'));
        let http_resp = self
            .client
            .post(&url)
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", API_VERSION)
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .map_err(|e| LlmError::Transport(e.to_string()))?;

        let status = http_resp.status();
        if !status.is_success() {
            let body = http_resp
                .text()
                .unwrap_or_else(|e| format!("<failed to read error body: {e}>"));
            if status.as_u16() == 429 || status.as_u16() == 529 {
                return Err(LlmError::Refused(format!(
                    "anthropic rate-limited (status {status}): {body}"
                )));
            }
            return Err(LlmError::Transport(format!(
                "anthropic returned non-success status {status}: {body}"
            )));
        }
        let parsed: MessagesResponse = http_resp
            .json()
            .map_err(|e| LlmError::InvalidResponse(format!("response JSON parse: {e}")))?;
        Self::parse_response(&parsed, prompt)
    }
}

// ---------- Request/Response types (Anthropic Messages API wire format) ----------

#[derive(Debug, Clone, Serialize)]
pub struct MessagesRequest {
    pub model: String,
    pub max_tokens: u32,
    pub system: Vec<SystemBlock>,
    pub messages: Vec<UserMessage>,
    pub tools: Vec<ToolDef>,
    pub tool_choice: ToolChoice,
    pub temperature: f32,
}

#[derive(Debug, Clone, Serialize)]
pub struct SystemBlock {
    #[serde(rename = "type")]
    pub block_type: String,
    pub text: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_control: Option<CacheControl>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CacheControl {
    #[serde(rename = "type")]
    pub control_type: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct UserMessage {
    pub role: String,
    pub content: Vec<ContentBlock>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ContentBlock {
    Text { text: String },
}

#[derive(Debug, Clone, Serialize)]
pub struct ToolDef {
    pub name: String,
    pub description: String,
    pub input_schema: serde_json::Value,
}

#[derive(Debug, Clone, Serialize)]
pub struct ToolChoice {
    #[serde(rename = "type")]
    pub choice_type: String,
    pub name: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MessagesResponse {
    pub content: Vec<ResponseContentBlock>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ResponseContentBlock {
    Text {
        text: String,
    },
    ToolUse {
        id: String,
        name: String,
        input: serde_json::Value,
    },
}

// Prompt + schema + response-parsing helpers were extracted to
// `crate::shape::llm` in v4.3d so the OpenAI and Ollama providers share
// them. Anthropic uses the strict schema even though tool_use doesn't
// require strict mode — keeping a single schema definition is worth
// more than the marginal output-space loss.

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;
    use crate::shape::csg::BooleanTemplate;
    use crate::shape::{ParamOverride, ShapeKind};

    fn sample_prompt() -> LlmPrompt {
        LlmPrompt {
            entity_path: "plate.3.zone.1".to_string(),
            depth: 1,
            size_rank: SizeRank::Medium,
            lat_norm: 0.42,
            parent_path: vec![3],
            allowed_kinds: vec![
                ShapeKind::Ellipse,
                ShapeKind::Boolean,
                ShapeKind::Stamp,
            ],
        }
    }

    #[test]
    fn build_request_marks_system_prompt_with_cache_control() {
        let p = AnthropicProvider::new("test-key");
        let req = p.build_request(&sample_prompt());
        assert_eq!(req.system.len(), 1);
        let block = &req.system[0];
        let cache = block
            .cache_control
            .as_ref()
            .expect("system block should be cached");
        assert_eq!(cache.control_type, "ephemeral");
        // The system prompt should mention every kind to anchor the LLM.
        for tag in [
            "Ellipse",
            "BezierSpine",
            "Polar",
            "Boolean",
            "SdfCapsuleChain",
            "MarchingNoise",
            "Slime",
            "Stamp",
        ] {
            assert!(
                block.text.contains(tag),
                "system prompt should mention `{tag}`, did not in: {first}…",
                first = &block.text[..120.min(block.text.len())],
            );
        }
    }

    #[test]
    fn build_request_pins_temperature_zero_and_tool_choice() {
        let p = AnthropicProvider::new("test-key");
        let req = p.build_request(&sample_prompt());
        assert_eq!(req.temperature, 0.0, "must pin temperature=0 for determinism");
        assert_eq!(req.tool_choice.choice_type, "tool");
        assert_eq!(req.tool_choice.name, "pick_shape");
        assert_eq!(req.tools.len(), 1);
        assert_eq!(req.tools[0].name, "pick_shape");
    }

    #[test]
    fn build_request_user_message_carries_path_and_allowed_kinds() {
        let p = AnthropicProvider::new("test-key");
        let req = p.build_request(&sample_prompt());
        let ContentBlock::Text { text } = &req.messages[0].content[0];
        assert!(text.contains("plate.3.zone.1"), "user msg missing path");
        assert!(text.contains("Ellipse"));
        assert!(text.contains("Boolean"));
        assert!(text.contains("Stamp"));
        assert!(text.contains("depth: 1"));
    }

    fn fake_tool_use_response(kind: &str, params: serde_json::Value) -> MessagesResponse {
        MessagesResponse {
            content: vec![ResponseContentBlock::ToolUse {
                id: "tool-1".to_string(),
                name: "pick_shape".to_string(),
                input: serde_json::json!({
                    "kind": kind,
                    "params": params,
                }),
            }],
        }
    }

    #[test]
    fn parse_response_ellipse_aspect_ratio() {
        let resp = fake_tool_use_response(
            "Ellipse",
            serde_json::json!({ "ellipse": { "aspect_ratio": 1.7 } }),
        );
        let d = AnthropicProvider::parse_response(&resp, &sample_prompt())
            .expect("should parse Ellipse decision");
        assert_eq!(d.kind, ShapeKind::Ellipse);
        match d.params {
            Some(ParamOverride::Ellipse { aspect_ratio: Some(r) }) => {
                assert!((r - 1.7).abs() < 1e-4);
            }
            other => panic!("expected Ellipse aspect_ratio, got {other:?}"),
        }
    }

    #[test]
    fn parse_response_boolean_template() {
        let resp = fake_tool_use_response(
            "Boolean",
            serde_json::json!({ "boolean": { "template": "WedgeCut" } }),
        );
        let d = AnthropicProvider::parse_response(&resp, &sample_prompt())
            .expect("should parse Boolean decision");
        assert_eq!(d.kind, ShapeKind::Boolean);
        assert!(matches!(
            d.params,
            Some(ParamOverride::Boolean { template: Some(BooleanTemplate::WedgeCut) })
        ));
    }

    #[test]
    fn parse_response_stamp_template_id() {
        let resp = fake_tool_use_response(
            "Stamp",
            serde_json::json!({ "stamp": { "template_id": 4 } }),
        );
        let d = AnthropicProvider::parse_response(&resp, &sample_prompt())
            .expect("should parse Stamp decision");
        assert_eq!(d.kind, ShapeKind::Stamp);
        assert!(matches!(
            d.params,
            Some(ParamOverride::Stamp { template_id: Some(4) })
        ));
    }

    #[test]
    fn parse_response_kind_outside_allowed_kinds_rejected() {
        // sample_prompt allows {Ellipse, Boolean, Stamp}; Slime should be rejected.
        let resp = fake_tool_use_response("Slime", serde_json::json!(null));
        let err = AnthropicProvider::parse_response(&resp, &sample_prompt())
            .expect_err("Slime not in allowed_kinds — should fail");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }

    #[test]
    fn parse_response_unknown_kind_rejected() {
        let resp = fake_tool_use_response("PointCloud", serde_json::json!(null));
        let err = AnthropicProvider::parse_response(&resp, &sample_prompt())
            .expect_err("PointCloud is not a registered kind");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }

    #[test]
    fn parse_response_missing_tool_use_rejected() {
        let resp = MessagesResponse {
            content: vec![ResponseContentBlock::Text {
                text: "Sorry I can't help with that".to_string(),
            }],
        };
        let err = AnthropicProvider::parse_response(&resp, &sample_prompt())
            .expect_err("text-only response should be rejected");
        assert!(matches!(err, LlmError::InvalidResponse(_)));
    }
}
