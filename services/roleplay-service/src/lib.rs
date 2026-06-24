//! roleplay-service — scripts + actor-memory (charter/state) + start-orchestration.
//!
//! The first user-facing Rust service and the MMO roleplay-service seed. v1 is
//! lean (System + Per-user tiers, single `loreweave_roleplay` pool, reuses
//! chat-service for the turn loop / voice / debrief — no LLM calls here). Built
//! on `crates/service-http` for serve / health / auth / trace / errors / db.

pub mod config;
pub mod http;
pub mod state;

pub use config::Config;
pub use http::build_router;
pub use state::AppState;
