//! `meta-rs` — Rust port of `contracts/meta` (Go).
//!
//! ## Purpose (Q-L1B-4)
//!
//! The Go library `contracts/meta` is the canonical Meta Access Library.
//! Per Q-L1B-4 resolution:
//!
//! > Per-language port for hot-path callers; RPC via meta-worker for cold-path.
//!
//! The Rust kernel (`crates/world-gen` and future Rust services) is a HOT-PATH
//! caller — every command needs `GetRealityRouting(reality_id)` AND every
//! lifecycle change runs through MetaWrite. RPC overhead is unacceptable for
//! either path, so this crate is the FORMAL hot-path port (Q-L1B-4):
//! **no RPC fallback** is exposed for the surface below.
//!
//! ## Cycle history
//!
//! - **Cycle 2** (L1.B): initial read-only surface — `MetaRead`,
//!   `RealityRouting`, `RealityStatus`, sensitive-paths parser.
//! - **Cycle 20 (this cycle — L4.C):** EXTENDED to the FULL meta surface so
//!   Rust hot-path callers match Go parity:
//!   - `metawrite::{meta_write, meta_write_batch, ...}` — Q-L1B-3 multi-table TX.
//!   - `transitions::{TransitionGraph, attempt_state_transition, ...}` —
//!     state-machine wrapper + reachability/mutex validation.
//!   - `allowlist::Allowlist` — defense-in-depth on every MetaWrite.
//!   - `cache::{Cache, KeyRegistry, InMemoryCache}` — caching contract.
//!   - `audit::{MetaWriteAuditRow, LifecycleTransitionAuditRow, ...}` — typed
//!     audit row shapes + outbox event envelope shared with Go.
//!
//! ## What is NOT in this crate
//!
//! - Concrete `sqlx` / `tokio-postgres` adapters — caller-supplied via
//!   [`metawrite::ConnectionWriter`] / [`metawrite::TransactionExecutor`].
//!   That keeps `meta-rs` driver-agnostic + cheap to test (matches the Go
//!   `Tx` interface pattern).
//! - Redis adapter — caller-supplied via [`cache::Cache`]. Production wires a
//!   Redis Sentinel client; tests use [`cache::InMemoryCache`].
//! - PII crypto-shred / OpenPII — Go-only path (L1.A-2). Rust callers needing
//!   PII go through the meta-worker RPC (cold path) per Q-L1B-4.

#![forbid(unsafe_code)]
#![warn(missing_docs, rust_2018_idioms)]

pub mod allowlist;
pub mod audit;
pub mod cache;
pub mod errors;
pub mod metawrite;
pub mod routing;
pub mod sensitive_paths;
pub mod transitions;

// ── Cycle 2 surface (unchanged) ──────────────────────────────────────────────
pub use errors::MetaError;
pub use routing::{Connection, MetaRead, RealityRouting, RealityStatus};
pub use sensitive_paths::{SensitivePath, SensitivePaths};

// ── Cycle 20 (L4.C) surface ──────────────────────────────────────────────────
pub use allowlist::{Allowlist, AllowlistEntry, EventBinding};
pub use audit::{
    AuditClock, AuditUuidGen, FixedClock, FixedUuid, LifecycleTransitionAuditRow,
    MetaWriteAuditRow, NoopOutbox, OutboxAppender, OutboxEvent, SystemClock, V4UuidGen,
};
pub use cache::{Cache, CacheValue, InMemoryCache, Key, KeyEntry, KeyKind, KeyRegistry};
pub use metawrite::{
    is_concurrent, meta_write, meta_write_batch, pk_as_string, Actor, ActorType,
    ConnectionWriter, MetaWriteConfig, MetaWriteIntent, MetaWriteOp, MetaWriteResult,
    QueryBuilder, RequestContext, TransactionExecutor, ValueMap,
};
pub use transitions::{
    attempt_state_transition, default_pk_lookup, LifecycleAuditSink, PkColumnLookup,
    ResourceGraph, TransitionGraph, TransitionRequest, TransitionResult,
};
