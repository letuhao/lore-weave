//! Canonical errors for `meta-rs`.  Mirrors `contracts/meta/errors.go` so the
//! same observability + recovery patterns work cross-language.

use thiserror::Error;

/// `MetaError` mirrors the Go `errors.go` constants.
///
/// All errors are derived from this enum so callers can `match` on the variant
/// (which is more idiomatic Rust than `errors.Is`) while still preserving the
/// underlying `source` chain.
#[derive(Debug, Error)]
pub enum MetaError {
    /// CAS UPDATE matched 0 rows — another writer won the race.
    /// Caller must refresh state and retry.
    #[error("meta: concurrent state transition")]
    ConcurrentStateTransition,

    /// `(from, to)` not in the resource's transition graph.
    /// Logic bug; do NOT retry.
    #[error("meta: invalid state transition: {from} -> {to}")]
    InvalidTransition {
        /// The state the resource was in.
        from: String,
        /// The state the caller requested.
        to: String,
    },

    /// Resource is in a mutex-blocked state for the requested transition.
    #[error("meta: mutual-exclusion conflict")]
    MutualExclusion,

    /// Domain precondition unmet (e.g., archive verification missing).
    #[error("meta: precondition failed: {0}")]
    PreconditionFailed(String),

    /// Library is in degraded mode and rejected the request.
    #[error("meta: degraded mode")]
    DegradedMode,

    /// Intent or request failed input validation.
    #[error("meta: bad intent: {0}")]
    BadIntent(String),

    /// Reading a sensitive path that wasn't registered in meta-sensitive-read-paths.yml.
    /// Defense-in-depth: callers MUST use a registered id.
    #[error("meta: sensitive path not registered: {0}")]
    SensitivePathNotRegistered(String),

    /// Resource type unknown to the loaded transition graph.
    #[error("meta: unknown resource type: {0}")]
    UnknownResource(String),

    /// Backend Postgres / connection error.
    #[error("meta: backend error: {0}")]
    Backend(#[source] Box<dyn std::error::Error + Send + Sync>),

    /// YAML parse / sanity-check failure.
    #[error("meta: config invalid: {0}")]
    ConfigInvalid(String),
}

impl MetaError {
    /// Reports whether the error signals a CAS lost race (cross-language
    /// idiom matching Go's `meta.IsConcurrent`).
    pub fn is_concurrent(&self) -> bool {
        matches!(self, MetaError::ConcurrentStateTransition)
    }
}
