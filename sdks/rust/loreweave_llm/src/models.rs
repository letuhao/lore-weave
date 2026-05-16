//! Rust mirrors of the [LLM gateway OpenAPI types]
//! ([`contracts/api/llm-gateway/v1/openapi.yaml`]). Hand-rolled (not generated)
//! because the surface this SDK consumes is small.
//!
//! **The openapi YAML is the source of truth — if these types drift, the
//! gateway will reject requests or fail to deserialize responses.**
//! Wire-format tests in `tests/wire_format.rs` lock the field names +
//! discriminator values.
//!
//! Naming follows the openapi:
//! - [`ChatStreamRequest`] mirrors `ChatStreamRequest` (one variant of the
//!   `StreamRequest` `oneOf`; the other is TTS, not used by this SDK).
//! - [`StreamEvent`] mirrors the canonical `StreamEventEnvelope` discriminated
//!   union (`propertyName: event`).
//!
//! [`contracts/api/llm-gateway/v1/openapi.yaml`]: ../../../../contracts/api/llm-gateway/v1/openapi.yaml

use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Default base URL for service-to-service gateway calls (provider-registry
/// in-cluster name). Override via the `LOREWEAVE_GATEWAY_URL` env var.
pub const GATEWAY_BASE_URL_DEFAULT: &str = "http://provider-registry-service:8085";

/// Public, user-auth endpoint. Not used by this SDK's service-to-service mode;
/// documented for completeness.
pub const PUBLIC_STREAM_PATH: &str = "/v1/llm/stream";

/// Service-to-service streaming endpoint. SDK callers use this with the
/// `X-Internal-Token` apiKey header + a `user_id` query parameter (billing).
pub const INTERNAL_STREAM_PATH: &str = "/internal/llm/stream";

/// Operation discriminator on `ChatStreamRequest`. Phase 5a addition; the
/// gateway defaults to `chat` when the field is absent
/// (regression-locked by `TestStreamHandler_OperationDefaultIsChat`), but we
/// send it explicitly for future-proofing.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Operation {
    #[default]
    Chat,
}

/// Model selection scope. Mirrors openapi `ModelSource`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelSource {
    /// User-registered model in provider-registry (per-user BYOK).
    UserModel,
    /// Platform-registered model (shared across tenants).
    PlatformModel,
}

/// SSE response envelope shape. Mirrors openapi `StreamFormat`. Controls the
/// RESPONSE envelope, NOT the request `tools` field — `tools` is always
/// OpenAI-shaped per the openapi contract regardless of `stream_format`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum StreamFormat {
    #[default]
    #[serde(rename = "openai")]
    Openai,
    #[serde(rename = "anthropic")]
    Anthropic,
    #[serde(rename = "vercel-ai-ui-v1")]
    VercelAiUiV1,
}

/// Wire shape for `POST /internal/llm/stream` (chat variant).
///
/// Mirrors openapi `ChatStreamRequest`. **Tool definitions go in the `tools`
/// field as OpenAI-shaped function-tool objects** (per openapi description
/// "Optional. OpenAI-shaped tool definitions"). The gateway translates to the
/// underlying provider's native tool format before dispatching the call —
/// callers do not pass Anthropic-shaped `input_schema` / `tool_choice`
/// directly even when `stream_format` is `Anthropic`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatStreamRequest {
    /// Explicit `operation: "chat"`. Optional in openapi (gateway defaults to
    /// chat when absent), but we send it explicitly for future-proofing.
    #[serde(default)]
    pub operation: Operation,

    pub model_source: ModelSource,
    pub model_ref: Uuid,
    pub messages: Vec<serde_json::Value>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub tools: Option<Vec<serde_json::Value>>,

    /// OpenAI-shaped tool-choice control — the string `"auto"` / `"none"` /
    /// `"required"`, or an object `{"type":"function","function":{"name":...}}`
    /// to force a specific tool. Honored only by providers that support tools
    /// (the gateway rejects a request setting this for a non-supporting
    /// provider with `400 LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER`).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_choice: Option<serde_json::Value>,

    /// 0.0..=2.0 per openapi `temperature` schema (minimum: 0, maximum: 2).
    /// Use [`ChatStreamRequest::normalize`] to clamp out-of-range values.
    #[serde(default)]
    pub temperature: f32,

    /// `Some(0)` is treated as omit by the gateway SDK convention (Python SDK
    /// strips it pre-send); [`ChatStreamRequest::normalize`] coerces it to None.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u32>,

    #[serde(default)]
    pub stream_format: StreamFormat,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,
}

/// serde `skip_serializing_if` predicate — omit a `u32` field when it is 0,
/// mirroring the Go gateway's `omitempty` so the tool-call `index` round-trips
/// symmetrically across the Go / Rust / Python SDKs.
fn is_zero(n: &u32) -> bool {
    *n == 0
}

/// Lowest valid `temperature` per openapi schema.
pub const TEMPERATURE_MIN: f32 = 0.0;
/// Highest valid `temperature` per openapi schema.
pub const TEMPERATURE_MAX: f32 = 2.0;

impl ChatStreamRequest {
    /// Construct a chat request with tool definitions. The `tools` argument
    /// is OpenAI-shaped per the gateway contract (each item is an
    /// `{"type":"function","function":{...}}` object); the gateway translates
    /// internally for non-OpenAI providers.
    pub fn new_chat_with_tools(
        model_source: ModelSource,
        model_ref: Uuid,
        messages: Vec<serde_json::Value>,
        tools: Vec<serde_json::Value>,
        stream_format: StreamFormat,
    ) -> Self {
        Self {
            operation: Operation::Chat,
            model_source,
            model_ref,
            messages,
            tools: Some(tools),
            tool_choice: None,
            temperature: 0.0,
            max_tokens: None,
            stream_format,
            trace_id: None,
        }
    }

    /// Set the OpenAI-shaped `tool_choice` (builder style). Pass e.g.
    /// `serde_json::json!({"type":"function","function":{"name":"..."}})`
    /// to force a specific tool call.
    pub fn with_tool_choice(mut self, tool_choice: serde_json::Value) -> Self {
        self.tool_choice = Some(tool_choice);
        self
    }

    /// Apply gateway-SDK conventions before sending: clamp temperature into
    /// the openapi range; coerce `max_tokens = Some(0)` → `None`.
    pub fn normalize(mut self) -> Self {
        // `f32::clamp` panics on NaN inputs — guard explicitly since `temperature`
        // is caller-supplied. NaN falls through to TEMPERATURE_MIN (safe default).
        if self.temperature.is_nan() {
            self.temperature = TEMPERATURE_MIN;
        } else {
            self.temperature = self.temperature.clamp(TEMPERATURE_MIN, TEMPERATURE_MAX);
        }
        if matches!(self.max_tokens, Some(0)) {
            self.max_tokens = None;
        }
        self
    }
}

/// Closed-enum finish reason on `DoneEvent`. Mirrors openapi
/// `DoneEvent.finish_reason` enum `[stop, length, content_filter, tool_calls, error]`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FinishReason {
    Stop,
    Length,
    ContentFilter,
    ToolCalls,
    Error,
}

/// Canonical streaming event from the gateway.
///
/// Mirrors openapi `StreamEventEnvelope.discriminator { propertyName: event }`.
/// **The wire discriminator field is `event`, NOT `event_type`** — earlier
/// SDK drafts mirrored the Python SDK Pythonic field name and broke; the
/// openapi is the contract. See wire-format tests in `tests/wire_format.rs`.
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "event", rename_all = "snake_case")]
pub enum StreamEvent {
    Token {
        delta: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        index: Option<u32>,
    },
    Reasoning {
        delta: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        index: Option<u32>,
    },
    Usage {
        #[serde(default)]
        input_tokens: u32,
        #[serde(default)]
        output_tokens: u32,
        /// Populated for thinking models (Qwen3.x, OpenAI o-series, etc.).
        #[serde(default, skip_serializing_if = "Option::is_none")]
        reasoning_tokens: Option<u32>,
    },
    Done {
        /// Optional + nullable per openapi `DoneEvent` schema.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        finish_reason: Option<FinishReason>,
    },
    Error {
        code: String,
        message: String,
    },
    /// One incremental fragment of a tool call the model is emitting,
    /// re-framed from OpenAI `delta.tool_calls[]` / Anthropic
    /// `input_json_delta`. Reassemble by `index` — see
    /// [`crate::tool::ToolCallAccumulator`]. The first fragment for an index
    /// carries `id` + `name`; later fragments carry only `arguments_delta`.
    /// There is no per-index terminal marker — completion is the `Done` event.
    ToolCall {
        /// Which tool call within the turn (0-based) — a semantic call
        /// identifier, NOT a monotonic counter. Absent on the wire ⇒ `0`.
        #[serde(default, skip_serializing_if = "is_zero")]
        index: u32,
        /// Provider tool-call id — present on the first fragment for this index.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        /// Tool/function name — present on the first fragment for this index.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        /// Incremental tool-call arguments JSON fragment. Absent on the wire
        /// ⇒ `""` — the gateway omits an empty value (shared-struct `omitempty`).
        #[serde(default)]
        arguments_delta: String,
    },
    /// Phase 5a TTS event — included so the discriminator union covers every
    /// variant the gateway might emit; chat-only consumers will treat its
    /// arrival as an upstream misroute.
    #[serde(rename = "audio-chunk")]
    AudioChunk {
        sequence_id: u32,
        /// base64-encoded audio bytes.
        data: String,
        /// `final` is a Rust reserved keyword; wire name is `final`.
        #[serde(default, rename = "final")]
        is_final: bool,
    },
}
