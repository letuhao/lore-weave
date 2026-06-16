//! Cycle 20 / L4.K — `errors` Rust mirror of `contracts/errors/` (Go).
//!
//! ## Exhaustive taxonomy
//!
//! 4 [`ErrorClass`] variants + 28 [`ErrorCode`] variants. **NO** "Other" /
//! "Unknown" catch-all — forces every team to classify failures into the
//! right bucket so SLO + retry semantics stay correct.
//!
//! ## Q-L4-1 parity
//!
//! Wire format matches `contracts/errors/canonical.go` 1:1.

use serde::{Deserialize, Serialize};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

/// 4 SR11 error classes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorClass {
    /// Caller's fault. NEVER retry; never page.
    UserError,
    /// Server-side bug or unexpected state. Page at threshold.
    SystemError,
    /// Known-temporary failure. Retry with backoff.
    Transient,
    /// Terminal failure. Caller surfaces gracefully.
    Permanent,
}

impl ErrorClass {
    /// Canonical snake_case string.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::UserError => "user_error",
            Self::SystemError => "system_error",
            Self::Transient => "transient",
            Self::Permanent => "permanent",
        }
    }

    /// True iff the class permits retry by default.
    pub fn is_retryable(&self) -> bool {
        matches!(self, Self::Transient)
    }

    /// True iff the class warrants paging by default.
    pub fn is_pageable(&self) -> bool {
        matches!(self, Self::SystemError)
    }

    /// All 4 classes.
    pub fn all() -> &'static [ErrorClass] {
        &[
            Self::UserError,
            Self::SystemError,
            Self::Transient,
            Self::Permanent,
        ]
    }
}

/// 28 canonical V1 error codes. Adding a code requires:
///   1. New variant here.
///   2. New arm in [`ErrorCode::class`] (compile-time exhaustive enforced).
///   3. Unit test passes [`tests::all_codes_have_classes`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCode {
    // ── UserError (9) ──
    /// Missing or absent auth token.
    AuthRequired,
    /// Auth token expired.
    AuthExpired,
    /// Authenticated but not authorized.
    AuthForbidden,
    /// Input failed validation.
    ValidationFailed,
    /// User quota exceeded.
    QuotaExceeded,
    /// Per-actor rate limit exceeded.
    RateLimitExceeded,
    /// Malformed input (wrong encoding, bad JSON).
    BadInputFormat,
    /// Client version too old.
    UnsupportedClient,
    /// Required consent missing.
    ConsentRequired,

    // ── SystemError (6) ──
    /// Internal invariant violated.
    InternalAssertion,
    /// Projection row corrupted.
    ProjectionCorruption,
    /// MetaWrite failed unexpectedly.
    MetaWriteFailed,
    /// Outbox drained or in failure state.
    OutboxDrained,
    /// Upstream service misconfigured (broken endpoint, bad creds).
    UpstreamMisconfigured,
    /// Event payload violates registered schema.
    SchemaViolation,

    // ── Transient (8) ──
    /// Upstream call timed out.
    UpstreamTimeout,
    /// Upstream rate limit (retry with backoff).
    UpstreamRateLimit,
    /// Upstream temporarily unavailable.
    UpstreamUnavailable,
    /// Circuit breaker open.
    CircuitOpen,
    /// Bulkhead full.
    BulkheadFull,
    /// CAS race lost.
    ConcurrentStateChange,
    /// Service in degraded mode (Limited / FallbackOnly).
    DegradedMode,
    /// Cache unavailable (recoverable; falls through to source).
    CacheUnavailable,

    // ── Permanent (5) ──
    /// Entity is dropped.
    EntityDropped,
    /// Entity is archived.
    EntityArchived,
    /// Home reality frozen.
    RealityFrozen,
    /// User PII erased.
    UserErased,
    /// Feature retired.
    FeatureRetired,
}

impl ErrorCode {
    /// Returns the ErrorClass for this code. Exhaustive `match` — compile
    /// fails if a new variant is added without a class assignment.
    pub fn class(&self) -> ErrorClass {
        match self {
            // UserError
            Self::AuthRequired
            | Self::AuthExpired
            | Self::AuthForbidden
            | Self::ValidationFailed
            | Self::QuotaExceeded
            | Self::RateLimitExceeded
            | Self::BadInputFormat
            | Self::UnsupportedClient
            | Self::ConsentRequired => ErrorClass::UserError,
            // SystemError
            Self::InternalAssertion
            | Self::ProjectionCorruption
            | Self::MetaWriteFailed
            | Self::OutboxDrained
            | Self::UpstreamMisconfigured
            | Self::SchemaViolation => ErrorClass::SystemError,
            // Transient
            Self::UpstreamTimeout
            | Self::UpstreamRateLimit
            | Self::UpstreamUnavailable
            | Self::CircuitOpen
            | Self::BulkheadFull
            | Self::ConcurrentStateChange
            | Self::DegradedMode
            | Self::CacheUnavailable => ErrorClass::Transient,
            // Permanent
            Self::EntityDropped
            | Self::EntityArchived
            | Self::RealityFrozen
            | Self::UserErased
            | Self::FeatureRetired => ErrorClass::Permanent,
        }
    }

    /// Canonical snake_case string.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::AuthRequired => "auth_required",
            Self::AuthExpired => "auth_expired",
            Self::AuthForbidden => "auth_forbidden",
            Self::ValidationFailed => "validation_failed",
            Self::QuotaExceeded => "quota_exceeded",
            Self::RateLimitExceeded => "rate_limit_exceeded",
            Self::BadInputFormat => "bad_input_format",
            Self::UnsupportedClient => "unsupported_client",
            Self::ConsentRequired => "consent_required",
            Self::InternalAssertion => "internal_assertion",
            Self::ProjectionCorruption => "projection_corruption",
            Self::MetaWriteFailed => "meta_write_failed",
            Self::OutboxDrained => "outbox_drained",
            Self::UpstreamMisconfigured => "upstream_misconfigured",
            Self::SchemaViolation => "schema_violation",
            Self::UpstreamTimeout => "upstream_timeout",
            Self::UpstreamRateLimit => "upstream_rate_limit",
            Self::UpstreamUnavailable => "upstream_unavailable",
            Self::CircuitOpen => "circuit_open",
            Self::BulkheadFull => "bulkhead_full",
            Self::ConcurrentStateChange => "concurrent_state_change",
            Self::DegradedMode => "degraded_mode",
            Self::CacheUnavailable => "cache_unavailable",
            Self::EntityDropped => "entity_dropped",
            Self::EntityArchived => "entity_archived",
            Self::RealityFrozen => "reality_frozen",
            Self::UserErased => "user_erased",
            Self::FeatureRetired => "feature_retired",
        }
    }

    /// Every canonical V1 code (28 total).
    pub fn all() -> &'static [ErrorCode] {
        &[
            // UserError
            Self::AuthRequired,
            Self::AuthExpired,
            Self::AuthForbidden,
            Self::ValidationFailed,
            Self::QuotaExceeded,
            Self::RateLimitExceeded,
            Self::BadInputFormat,
            Self::UnsupportedClient,
            Self::ConsentRequired,
            // SystemError
            Self::InternalAssertion,
            Self::ProjectionCorruption,
            Self::MetaWriteFailed,
            Self::OutboxDrained,
            Self::UpstreamMisconfigured,
            Self::SchemaViolation,
            // Transient
            Self::UpstreamTimeout,
            Self::UpstreamRateLimit,
            Self::UpstreamUnavailable,
            Self::CircuitOpen,
            Self::BulkheadFull,
            Self::ConcurrentStateChange,
            Self::DegradedMode,
            Self::CacheUnavailable,
            // Permanent
            Self::EntityDropped,
            Self::EntityArchived,
            Self::RealityFrozen,
            Self::UserErased,
            Self::FeatureRetired,
        ]
    }
}

/// Versioned error envelope. Mirrors Go `ErrorEnvelope`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ErrorEnvelope {
    /// 1 of 4 classes.
    pub class: ErrorClass,
    /// 1 of 28 V1 codes.
    pub code: ErrorCode,
    /// Human-readable; NEVER contains PII.
    pub message: String,
    /// Suggested HTTP status (0 = none).
    #[serde(default, skip_serializing_if = "is_zero_u32")]
    pub http_status: u32,
    /// Retry-After hint (transient only).
    #[serde(default, skip_serializing_if = "is_zero_duration")]
    #[serde(with = "duration_nanos")]
    pub retry_after: Duration,
    /// Trace id.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub trace_id: String,
    /// Wall clock at error generation (unix nanos).
    pub occurred_at_nanos: i64,
}

fn is_zero_u32(v: &u32) -> bool {
    *v == 0
}
fn is_zero_duration(v: &Duration) -> bool {
    v.is_zero()
}

mod duration_nanos {
    use super::Duration;
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S: Serializer>(v: &Duration, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_u64(v.as_nanos() as u64)
    }
    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<Duration, D::Error> {
        let nanos = u64::deserialize(d)?;
        Ok(Duration::from_nanos(nanos))
    }
}

impl ErrorEnvelope {
    /// Construct a validated envelope. `class` derived from `code` to prevent
    /// class+code desync.
    pub fn new(code: ErrorCode, message: impl Into<String>, occurred_at_nanos: i64) -> Self {
        Self {
            class: code.class(),
            code,
            message: message.into(),
            http_status: 0,
            retry_after: Duration::ZERO,
            trace_id: String::new(),
            occurred_at_nanos,
        }
    }

    /// Set the suggested HTTP status.
    pub fn with_http_status(mut self, status: u32) -> Self {
        self.http_status = status;
        self
    }

    /// Set Retry-After (only honored for transient).
    pub fn with_retry_after(mut self, d: Duration) -> Self {
        if self.class == ErrorClass::Transient {
            self.retry_after = d;
        }
        self
    }

    /// Set trace id.
    pub fn with_trace_id(mut self, id: impl Into<String>) -> Self {
        self.trace_id = id.into();
        self
    }
}

impl std::fmt::Display for ErrorEnvelope {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}/{}: {}", self.class.as_str(), self.code.as_str(), self.message)
    }
}

impl std::error::Error for ErrorEnvelope {}

/// Production now-nanos helper.
pub fn now_nanos() -> i64 {
    let d = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    d.as_nanos() as i64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn class_count_is_four() {
        assert_eq!(ErrorClass::all().len(), 4);
    }

    #[test]
    fn class_retryable_pageable_defaults() {
        assert!(ErrorClass::Transient.is_retryable());
        for c in [ErrorClass::UserError, ErrorClass::SystemError, ErrorClass::Permanent] {
            assert!(!c.is_retryable(), "{c:?}");
        }
        assert!(ErrorClass::SystemError.is_pageable());
        for c in [ErrorClass::UserError, ErrorClass::Transient, ErrorClass::Permanent] {
            assert!(!c.is_pageable(), "{c:?}");
        }
    }

    #[test]
    fn class_serializes_as_snake_case() {
        let s = serde_json::to_string(&ErrorClass::UserError).unwrap();
        assert_eq!(s, "\"user_error\"");
    }

    #[test]
    fn all_codes_count_is_28() {
        assert_eq!(ErrorCode::all().len(), 28);
    }

    #[test]
    fn all_codes_have_classes() {
        // Trivially true via the exhaustive match in code.class(), but we
        // also count per-class to ensure the distribution matches Go.
        let mut counts = [0usize; 4];
        for c in ErrorCode::all() {
            counts[match c.class() {
                ErrorClass::UserError => 0,
                ErrorClass::SystemError => 1,
                ErrorClass::Transient => 2,
                ErrorClass::Permanent => 3,
            }] += 1;
        }
        assert_eq!(counts, [9, 6, 8, 5]);
    }

    #[test]
    fn code_strings_match_go() {
        for code in ErrorCode::all() {
            let s = serde_json::to_string(code).unwrap();
            assert!(s.starts_with('"') && s.ends_with('"'));
            let inner = &s[1..s.len() - 1];
            assert_eq!(inner, code.as_str());
        }
    }

    #[test]
    fn envelope_new_validates_class_from_code() {
        let env = ErrorEnvelope::new(ErrorCode::AuthRequired, "missing auth", 0);
        assert_eq!(env.class, ErrorClass::UserError);
        assert_eq!(env.code, ErrorCode::AuthRequired);
    }

    #[test]
    fn envelope_display_format() {
        let env = ErrorEnvelope::new(ErrorCode::UpstreamTimeout, "openai 504", 0);
        assert_eq!(env.to_string(), "transient/upstream_timeout: openai 504");
    }

    #[test]
    fn retry_after_only_honored_for_transient() {
        let transient = ErrorEnvelope::new(ErrorCode::UpstreamTimeout, "x", 0)
            .with_retry_after(Duration::from_secs(5));
        assert_eq!(transient.retry_after, Duration::from_secs(5));
        let user_err = ErrorEnvelope::new(ErrorCode::AuthRequired, "x", 0)
            .with_retry_after(Duration::from_secs(5));
        assert_eq!(user_err.retry_after, Duration::ZERO);
    }

    #[test]
    fn envelope_with_modifiers() {
        let env = ErrorEnvelope::new(ErrorCode::AuthExpired, "expired", 0)
            .with_http_status(401)
            .with_trace_id("trace-abc");
        assert_eq!(env.http_status, 401);
        assert_eq!(env.trace_id, "trace-abc");
    }

    #[test]
    fn envelope_roundtrip_json() {
        let env = ErrorEnvelope::new(ErrorCode::UpstreamTimeout, "x", 1234)
            .with_retry_after(Duration::from_millis(500))
            .with_http_status(503);
        let s = serde_json::to_string(&env).unwrap();
        let back: ErrorEnvelope = serde_json::from_str(&s).unwrap();
        assert_eq!(back, env);
    }

    #[test]
    fn errors_implement_std_error_trait() {
        fn takes_err(_: Box<dyn std::error::Error>) {}
        let env = ErrorEnvelope::new(ErrorCode::InternalAssertion, "bug", 0);
        takes_err(Box::new(env));
    }
}
