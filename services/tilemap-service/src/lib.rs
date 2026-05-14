//! tilemap-service — procedural tilemap generation for non-cell LoreWeave channels.
//!
//! This is the **library crate** entry point. The binary entry (`main.rs`) is a
//! CLI runner against fixtures during PoC Phase 0a/0b; Phase 2+ will add an
//! HTTP server surface for service-to-service calls.
//!
//! Source spec: [`docs/03_planning/LLM_MMO_RPG/features/00_tilemap/`] (TMP_001..TMP_008b
//! CANDIDATE-LOCK 2026-05-13). Phase 0a scope: scaffold + types + LLM gateway
//! client signatures — **no actual network call this phase**. See [`DESIGN.md`].
//!
//! [`DESIGN.md`]: ../DESIGN.md

#![warn(missing_debug_implementations)]
#![warn(rust_2018_idioms)]

pub mod error;
pub mod llm;
pub mod seed;
pub mod types;

pub use error::{Error, Result};
pub use seed::{TilemapSeed, derive_seed};
