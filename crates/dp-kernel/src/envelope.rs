//! `EventEnvelope` — Rust mirror of `contracts/events/envelope.go` (R03 §12C.1).
//!
//! Single canonical wire shape used by **upcasters**, **validators**,
//! **projections** (L3.B), the **snapshot loader** (L3.C), the EventStore
//! (L4+), and downstream consumers. Having one Rust shape that matches the
//! Go envelope field-for-field is the contract that lets Rust-side
//! projections consume events written by Go-side services without per-call
//! translation glue.
//!
//! ## Why this lives in dp-kernel
//!
//! Before cycle 12 the envelope was only spelled in Go (services were all Go +
//! Python; the only Rust crate was `dp-kernel`'s upcaster/validator which
//! worked on `serde_json::Value` payloads). Cycle 12 adds the L3.B
//! `Projection` trait — the FIRST Rust API that consumes whole envelopes (not
//! just payloads) — so this is the natural home for the type.
//!
//! Field semantics MATCH `contracts/events/envelope.go::Envelope` 1:1.
//! Adding/removing/renaming a field here REQUIRES a paired change to the Go
//! envelope (and a contractgen regeneration if the registry-driven code-gen
//! is in use — cycle 14+ L4.B scope).
//!
//! ## Stability contract
//!
//! V1-stable as of cycle 12. Field-shape changes go through R03 §12C.4 schema
//! evolution: add nullable fields without breaking; remove/rename fields only
//! with an upcaster path.

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use serde_json::Value;

/// Serializable timestamp surface that matches Go's `time.Time` JSON
/// marshaling (RFC 3339). We use a `String` here rather than pulling in
/// `chrono` because `dp-kernel` MUST stay dependency-light (matches the
/// outbox.rs design: no `sqlx`, no `tokio`). Callers that need typed time
/// handling can parse to `chrono::DateTime<Utc>` at the use site.
pub type Rfc3339Timestamp = String;

/// Cross-service event envelope.
///
/// Mirrors `contracts/events/envelope.go::Envelope` field-for-field. See
/// module docs for the stability + sync contract.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EventEnvelope {
    pub event_id: Uuid,
    pub event_type: String,
    pub event_version: u32,
    pub aggregate_id: String,
    pub aggregate_type: String,
    pub aggregate_version: u64,
    pub reality_id: Uuid,
    pub occurred_at: Rfc3339Timestamp,
    pub recorded_at: Rfc3339Timestamp,
    pub payload: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
}

impl EventEnvelope {
    /// Lightweight structural validation matching `Envelope.Validate()` in
    /// the Go side. Does NOT check the payload schema (that's L2.I).
    pub fn validate(&self) -> Result<(), String> {
        if self.event_id.is_nil() {
            return Err("event_id is zero".into());
        }
        if self.event_type.is_empty() {
            return Err("event_type is empty".into());
        }
        if self.event_version < 1 {
            return Err("event_version must be >= 1".into());
        }
        if self.aggregate_id.is_empty() {
            return Err("aggregate_id is empty".into());
        }
        if self.aggregate_type.is_empty() {
            return Err("aggregate_type is empty".into());
        }
        if self.reality_id.is_nil() {
            return Err("reality_id is zero".into());
        }
        if self.recorded_at.is_empty() {
            return Err("recorded_at is empty".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(1),
            event_type: "world.tick".into(),
            event_version: 1,
            aggregate_id: "world-1".into(),
            aggregate_type: "world".into(),
            aggregate_version: 1,
            reality_id: Uuid::from_u128(2),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: "2026-05-29T00:00:01Z".into(),
            payload: serde_json::json!({ "tick": 1 }),
            metadata: None,
        }
    }

    #[test]
    fn validate_accepts_fixture() {
        fixture().validate().expect("fixture is valid");
    }

    #[test]
    fn validate_rejects_zero_event_id() {
        let mut e = fixture();
        e.event_id = Uuid::nil();
        assert!(e.validate().is_err());
    }

    #[test]
    fn validate_rejects_zero_reality_id() {
        let mut e = fixture();
        e.reality_id = Uuid::nil();
        assert!(e.validate().is_err());
    }

    #[test]
    fn validate_rejects_empty_event_type() {
        let mut e = fixture();
        e.event_type = "".into();
        assert!(e.validate().is_err());
    }

    #[test]
    fn validate_rejects_zero_event_version() {
        let mut e = fixture();
        e.event_version = 0;
        assert!(e.validate().is_err());
    }

    #[test]
    fn roundtrip_json_matches_go_field_names() {
        let env = fixture();
        let v = serde_json::to_value(&env).unwrap();
        let obj = v.as_object().unwrap();
        // Snake-case names match Go json tags exactly.
        for key in [
            "event_id",
            "event_type",
            "event_version",
            "aggregate_id",
            "aggregate_type",
            "aggregate_version",
            "reality_id",
            "occurred_at",
            "recorded_at",
            "payload",
        ] {
            assert!(obj.contains_key(key), "missing key {key}");
        }
        // metadata is `skip_serializing_if = "Option::is_none"` → absent when None.
        assert!(!obj.contains_key("metadata"));
    }
}
