//! tilemap-service — procedural tilemap generation for non-cell LoreWeave channels.
//!
//! This is the **library crate** entry point. The binary entry (`main.rs`) is a
//! CLI runner against fixtures during PoC Phase 0a/0b; Phase 2+ will add an
//! HTTP server surface for service-to-service calls.
//!
//! LLM gateway access is provided by the [`loreweave_llm`] sibling crate
//! (extracted from this service's original `src/llm/` module at SDK promotion
//! 2026-05-14). tilemap-service consumes the SDK; it does not host the gateway
//! client itself.
//!
//! Source spec: [`docs/03_planning/LLM_MMO_RPG/features/00_tilemap/`] (TMP_001..TMP_008b
//! CANDIDATE-LOCK 2026-05-13). Phase 0a scope: scaffold + types + LLM SDK dep —
//! **no actual network call this phase**. See [`DESIGN.md`].
//!
//! [`DESIGN.md`]: ../DESIGN.md

#![warn(missing_debug_implementations)]
#![warn(rust_2018_idioms)]

pub mod engine;
pub mod error;
pub mod harness;
pub mod http;
pub mod seed;
pub mod types;
pub mod world_inherit;

pub use error::{Error, Result};
pub use seed::{TilemapSeed, derive_seed};

// Re-export the LLM SDK at the crate boundary so downstream tooling that
// links against tilemap-service as a library can reach the gateway client
// without taking a separate dependency on `loreweave_llm`.
pub use loreweave_llm as llm;
