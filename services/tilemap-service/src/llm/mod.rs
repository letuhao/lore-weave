//! LLM gateway client. Service-to-service calls go via `/internal/llm/stream`
//! on the unified LLM gateway (see [`contracts/api/llm-gateway/v1/openapi.yaml`]).
//!
//! Per CLAUDE.md **provider gateway invariant**, tilemap-service never calls
//! any provider SDK directly — model selection is by `model_ref: UUID` (the
//! gateway resolves the provider). Internal endpoint authentication is via
//! the `X-Internal-Token` apiKey header + a required `user_id` query parameter.
//!
//! Phase 0a: type definitions + client signature only. Phase 0b implements the
//! SSE parsing loop, per-object retry per [TMP_008b §5], and canonical-default
//! fallback per [TMP_008b §6].
//!
//! [`contracts/api/llm-gateway/v1/openapi.yaml`]: ../../../../contracts/api/llm-gateway/v1/openapi.yaml
//! [TMP_008b §5]: ../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_008b_llm_contract_spec.md
//! [TMP_008b §6]: ../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_008b_llm_contract_spec.md

pub mod client;
pub mod errors;
pub mod models;

pub use client::GatewayClient;
pub use errors::LlmError;
pub use models::{
    ChatStreamRequest, FinishReason, GATEWAY_BASE_URL_DEFAULT, INTERNAL_STREAM_PATH, ModelSource,
    Operation, PUBLIC_STREAM_PATH, StreamEvent, StreamFormat, TEMPERATURE_MAX, TEMPERATURE_MIN,
};
