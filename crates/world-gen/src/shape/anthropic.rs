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

use crate::shape::csg::BooleanTemplate;
use crate::shape::llm::{LlmDecision, LlmError, LlmPrompt, LlmProvider};
use crate::shape::{ParamOverride, ShapeKind};

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
            text: build_system_prompt(),
            cache_control: Some(CacheControl {
                control_type: "ephemeral".to_string(),
            }),
        }];

        let user_text = build_user_message(prompt);

        let tool = build_pick_shape_tool();

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
        let kind = parse_shape_kind(kind_str)?;
        if !prompt.allowed_kinds.contains(&kind) {
            return Err(LlmError::InvalidResponse(format!(
                "kind {kind:?} not in allowed_kinds {:?}",
                prompt.allowed_kinds
            )));
        }
        let params = parse_params(kind, tool_use.get("params"))?;
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

// ---------- Prompt / schema builders ----------

fn build_system_prompt() -> String {
    // Capped at ~1200 tokens. Updates require bumping the schema rev in
    // the system message so a stale cached prefix invalidates cleanly.
    String::from(
        "You are a procedural-world-generation dispatcher. For each \
         entity (plate, zone, sub-zone) you pick one shape generator \
         from a fixed catalog and emit a structured `pick_shape` tool \
         call. Output ONLY the tool call — no prose.\n\
         \n\
         ## Catalog (return one of these as `kind`):\n\
         - `Ellipse` — smooth anisotropic ellipsoid with fbm warp. \
           Defaults; works for any rank.\n\
         - `BezierSpine` — cubic Bezier spine + variable-radius sweep. \
           Good for long thin continents (Italy / Korea / Madagascar \
           shapes).\n\
         - `Polar` — superformula closed curve. Picks small-rank \
           rotationally-symmetric continents (Iceland / Hispaniola).\n\
         - `Boolean` — polygon CSG (union / difference / wedge cut). \
           Good for inland seas, gulfs, peanut shapes.\n\
         - `SdfCapsuleChain` — chained capsules + smooth-min. Branching \
           or limb-like landmasses.\n\
         - `MarchingNoise` — noise field contoured. Best for archipelagos \
           and irregular coastlines.\n\
         - `Slime` — multi-agent random walk + concave hull. Most \
           organic / tendrilly continents.\n\
         - `Stamp` — pre-authored signature templates (Italy boot, Japan \
           4-arc, Cuba crescent, etc.). Picks via `template_id`.\n\
         \n\
         ## Parameter overrides (return matching variant in `params`):\n\
         - For `Ellipse` set `params.ellipse.aspect_ratio` in [0.5, 3.0].\n\
         - For `Boolean` set `params.boolean.template` to one of \
           [`EllipseUnion`, `EllipseDifference`, `WedgeCut`].\n\
         - For `Stamp` set `params.stamp.template_id` to a u32 in [0, 9].\n\
         - Other kinds: leave `params` null.\n\
         \n\
         ## Picking rules:\n\
         - Bias by `depth`: plates (0) prefer interesting Bezier/Boolean/\
           Stamp variety; zones (1) skew Ellipse/Polar for cleaner \
           subdivisions; sub-zones (2) lean Ellipse/Polar minimal.\n\
         - Bias by `size_rank`: Giant → branched (Slime, SDF, Bezier); \
           Micro → simple (Ellipse, Polar).\n\
         - Latitude `lat_norm` is `0..1` (north=0). Tropical mid-band \
           may favour archipelagos (MarchingNoise).\n\
         - Stay coherent within a `parent_path` family — sister zones of \
           the same plate should share a stylistic register.",
    )
}

fn build_user_message(prompt: &LlmPrompt) -> String {
    let parent = if prompt.parent_path.is_empty() {
        "(root)".to_string()
    } else {
        prompt
            .parent_path
            .iter()
            .map(|p| p.to_string())
            .collect::<Vec<_>>()
            .join(".")
    };
    let allowed = prompt
        .allowed_kinds
        .iter()
        .map(|k| format!("{k:?}"))
        .collect::<Vec<_>>()
        .join(", ");
    format!(
        "Entity:\n\
         - path: {path}\n\
         - depth: {depth}\n\
         - size_rank: {rank:?}\n\
         - lat_norm: {lat:.3}\n\
         - parent: {parent}\n\
         - allowed_kinds: [{allowed}]\n\
         \n\
         Call `pick_shape` with your choice.",
        path = prompt.entity_path,
        depth = prompt.depth,
        rank = prompt.size_rank,
        lat = prompt.lat_norm,
    )
}

fn build_pick_shape_tool() -> ToolDef {
    let schema = serde_json::json!({
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": [
                    "Ellipse",
                    "BezierSpine",
                    "Polar",
                    "Boolean",
                    "SdfCapsuleChain",
                    "MarchingNoise",
                    "Slime",
                    "Stamp"
                ],
                "description": "Which generator from the catalog to use."
            },
            "params": {
                "type": "object",
                "properties": {
                    "ellipse": {
                        "type": "object",
                        "properties": {
                            "aspect_ratio": { "type": "number", "minimum": 0.5, "maximum": 3.0 }
                        }
                    },
                    "boolean": {
                        "type": "object",
                        "properties": {
                            "template": {
                                "type": "string",
                                "enum": ["EllipseUnion", "EllipseDifference", "WedgeCut"]
                            }
                        }
                    },
                    "stamp": {
                        "type": "object",
                        "properties": {
                            "template_id": { "type": "integer", "minimum": 0, "maximum": 9 }
                        }
                    }
                }
            }
        },
        "required": ["kind"]
    });
    ToolDef {
        name: "pick_shape".to_string(),
        description: "Choose a shape generator and (optionally) its \
                      parameter override for the described entity."
            .to_string(),
        input_schema: schema,
    }
}

// ---------- Response parsing helpers ----------

fn parse_shape_kind(s: &str) -> Result<ShapeKind, LlmError> {
    Ok(match s {
        "Ellipse" => ShapeKind::Ellipse,
        "BezierSpine" => ShapeKind::BezierSpine,
        "Polar" => ShapeKind::Polar,
        "Boolean" => ShapeKind::Boolean,
        "SdfCapsuleChain" => ShapeKind::SdfCapsuleChain,
        "MarchingNoise" => ShapeKind::MarchingNoise,
        "Slime" => ShapeKind::Slime,
        "Stamp" => ShapeKind::Stamp,
        other => {
            return Err(LlmError::InvalidResponse(format!(
                "unknown ShapeKind `{other}`"
            )));
        }
    })
}

fn parse_boolean_template(s: &str) -> Result<BooleanTemplate, LlmError> {
    Ok(match s {
        "EllipseUnion" => BooleanTemplate::EllipseUnion,
        "EllipseDifference" => BooleanTemplate::EllipseDifference,
        "WedgeCut" => BooleanTemplate::WedgeCut,
        // `Ring` is reserved for v3.3+ — not picked by v4.3c.
        other => {
            return Err(LlmError::InvalidResponse(format!(
                "unknown BooleanTemplate `{other}`"
            )));
        }
    })
}

fn parse_params(
    kind: ShapeKind,
    params_node: Option<&serde_json::Value>,
) -> Result<Option<ParamOverride>, LlmError> {
    let Some(params_node) = params_node.filter(|v| !v.is_null()) else {
        return Ok(None);
    };
    let obj = match params_node.as_object() {
        Some(o) => o,
        None => return Ok(None),
    };
    Ok(match kind {
        ShapeKind::Ellipse => obj.get("ellipse").and_then(|e| e.as_object()).map(|e| {
            ParamOverride::Ellipse {
                aspect_ratio: e
                    .get("aspect_ratio")
                    .and_then(|v| v.as_f64())
                    .map(|n| n as f32),
            }
        }),
        ShapeKind::Boolean => match obj.get("boolean").and_then(|b| b.as_object()) {
            Some(b) => {
                let template = match b.get("template").and_then(|v| v.as_str()) {
                    Some(s) => Some(parse_boolean_template(s)?),
                    None => None,
                };
                Some(ParamOverride::Boolean { template })
            }
            None => None,
        },
        ShapeKind::Stamp => obj
            .get("stamp")
            .and_then(|s| s.as_object())
            .map(|s| ParamOverride::Stamp {
                template_id: s.get("template_id").and_then(|v| v.as_u64()).map(|n| n as u32),
            }),
        _ => None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::SizeRank;
    use crate::shape::ParamOverride;

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
