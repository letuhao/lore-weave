//! `meta-rs` — Rust hot-path port of `contracts/meta` (Go).
//!
//! ## Purpose (Q-L1B-4)
//!
//! The Go library `contracts/meta` is the canonical Meta Access Library.
//! Per Q-L1B-4 resolution:
//!
//! > Per-language port for hot-path callers; RPC via meta-worker for cold-path.
//!
//! The Rust kernel (`crates/world-gen` and future Rust services) is a HOT-PATH
//! caller — every command needs `GetRealityRouting(reality_id)`. RPC overhead is
//! unacceptable. So we ship this thin Rust port with the **read-only**
//! routing surface.
//!
//! Writes (MetaWrite, AttemptStateTransition) are NOT exposed here. Rust callers
//! that need to write delegate to the Go meta-worker via RPC (the cold path
//! per Q-L1B-4).
//!
//! ## Cycle 2 surface (this crate)
//!
//! - `MetaRead`              — trait for routing + entity-status reads
//! - `RealityRouting`        — value object returned by `get_reality_routing`
//! - `RealityStatus`         — enum mirroring `reality_registry.status` CHECK
//! - `MetaError`             — canonical error type (mirrors Go errors.go)
//! - `Connection` trait      — backend abstraction (pgx-style); concrete impl in later cycle
//! - `sensitive_paths::*`    — parse meta-sensitive-read-paths.yml so Rust callers
//!                              can mark their reads with the same id namespace as Go
//!
//! Hot-path performance accessors (cache, prefetch) ship alongside the Redis
//! infrastructure in later cycles.

#![forbid(unsafe_code)]
#![warn(missing_docs, rust_2018_idioms)]

pub mod errors;
pub mod routing;
pub mod sensitive_paths;

pub use errors::MetaError;
pub use routing::{Connection, MetaRead, RealityRouting, RealityStatus};
pub use sensitive_paths::{SensitivePath, SensitivePaths};
