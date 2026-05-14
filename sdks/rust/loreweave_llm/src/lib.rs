//! `loreweave_llm` — Rust SDK for the LoreWeave unified LLM gateway.
//!
//! Mirror of [`sdks/python/loreweave_llm`](../../python/loreweave_llm) — the
//! Python SDK Phase 1b → 5c-alpha covers translation, chat, knowledge, extraction.
//! This Rust SDK starts at Phase 1b parity (streaming client + typed event
//! envelope) sized for the **service-to-service streaming endpoint**
//! (`/internal/llm/stream`) that tilemap-service consumes.
//!
//! **Wire format source of truth** is [`contracts/api/llm-gateway/v1/openapi.yaml`].
//! If these types drift, the gateway will reject requests or fail to
//! deserialise responses. The integration tests in
//! `tests/wire_format.rs` lock the field names + discriminator values against
//! canonical openapi JSON shapes.
//!
//! Per CLAUDE.md **provider gateway invariant**, callers never speak directly
//! to a provider SDK (anthropic / openai / litellm) — `model_ref: Uuid`
//! selects a model registered in provider-registry-service, and the gateway
//! routes to the underlying provider.
//!
//! # Phase 0a status (this version)
//!
//! - ✅ Wire-type mirrors of `ChatStreamRequest` + `StreamEvent` envelope
//! - ✅ [`GatewayClient`] with `from_env()` (fails fast on missing token)
//! - ✅ Correct `X-Internal-Token` header + required `user_id` query param
//! - ✅ 17 wire-format conformance tests against canonical openapi shapes
//! - ⏸ [`GatewayClient::stream`] returns [`LlmError::NotImplementedPhase0a`] —
//!   SSE parsing loop lands at Phase 0b
//!
//! [`contracts/api/llm-gateway/v1/openapi.yaml`]: ../../../../contracts/api/llm-gateway/v1/openapi.yaml

#![warn(missing_debug_implementations)]
#![warn(rust_2018_idioms)]

pub mod client;
pub mod errors;
pub mod models;

pub use client::{GatewayClient, StreamHandle};
pub use errors::LlmError;
pub use models::{
    ChatStreamRequest, FinishReason, GATEWAY_BASE_URL_DEFAULT, INTERNAL_STREAM_PATH, ModelSource,
    Operation, PUBLIC_STREAM_PATH, StreamEvent, StreamFormat, TEMPERATURE_MAX, TEMPERATURE_MIN,
};
