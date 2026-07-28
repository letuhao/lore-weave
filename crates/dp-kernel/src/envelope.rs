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
    /// RLS-A13 — the content digest (BLAKE3, 64 lowercase hex) of the resolved
    /// `RealityRuleset` the producing island was running.
    ///
    /// **`None` when the event did not come from a ruleset-pinned simulation**
    /// — canon writes, Forge edits, admin actions. That is a real category, not
    /// a gap, which is why the shared envelope validates the FORMAT and not the
    /// PRESENCE: this shape belongs to the whole platform, and a required field
    /// would break every existing producer (I14 additive rule). The game writer
    /// stamps it unconditionally; that obligation is enforced where it lives,
    /// in `commit-service`, not here.
    ///
    /// Rows written before migration `0016` carry SQL `NULL`, and NULL is the
    /// honest value: *"written before pinning existed"*. A 64-zero string would
    /// instead claim *"pinned to the empty ruleset"* — a lie, and precisely what
    /// `scripts/zero-digest-gate.py` was added to outlaw.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ruleset_digest: Option<String>,
}

impl EventEnvelope {
    /// Lightweight structural validation matching `Envelope.Validate()` in
    /// the Go side. Does NOT check the payload schema (that's L2.I).
    pub fn validate(&self) -> Result<(), String> {
        // PRESENCE is not required (see the field docs); FORMAT is, when
        // present. A mixed-case or truncated digest silently fails to equal the
        // same digest written by another producer — RLS-D5's "worse than no
        // digest, because it fails loudly and WRONGLY".
        if let Some(d) = &self.ruleset_digest
            && !(d.len() == 64 && d.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)))
        {
            return Err("ruleset_digest must be 64 lowercase hex characters".into());
        }
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
    /// RLS-A13 — the pin is OPTIONAL by presence and STRICT by format, and the
    /// Rust mirror must agree with `contracts/events/envelope.go` on both.
    ///
    /// Presence is optional because this envelope is the whole platform's wire
    /// shape (canon writes, Forge edits and admin actions have no ruleset), and
    /// a required field would break every existing producer. Format is strict
    /// because the digest is compared as TEXT: an uppercase or truncated value
    /// silently fails to equal the same digest written by another producer,
    /// which is RLS-D5's "worse than no digest — it fails loudly and WRONGLY".
    #[test]
    fn ruleset_digest_is_optional_by_presence_and_strict_by_format() {
        let valid = "807d5b5213f0707ff1e0f2e359d1b22463ce074d914ab98646440a4f62f4fe01";
        let mut e = fixture();

        e.ruleset_digest = None;
        assert!(e.validate().is_ok(), "an unpinned event is legal, not a gap");

        e.ruleset_digest = Some(valid.to_string());
        assert!(e.validate().is_ok());

        for bad in [
            valid.to_uppercase(),
            valid[..63].to_string(),
            format!("{valid}0"),
            "z".repeat(64),
            String::new(),
        ] {
            e.ruleset_digest = Some(bad.clone());
            assert!(
                e.validate().is_err(),
                "`{bad}` must be rejected: it can never equal the same digest \
                 written correctly by another producer"
            );
        }
    }

    /// The field must SURVIVE a round trip, and be ABSENT rather than null when
    /// unpinned — a `"ruleset_digest": null` on the wire is a third state the
    /// Go side does not have (`omitempty`), and three states where the contract
    /// declares two is how polyglot consumers start disagreeing.
    #[test]
    fn ruleset_digest_round_trips_and_omits_when_absent() {
        let mut e = fixture();
        e.ruleset_digest = Some("00ff".repeat(16));
        let json = serde_json::to_string(&e).unwrap();
        assert!(json.contains("ruleset_digest"));
        let back: EventEnvelope = serde_json::from_str(&json).unwrap();
        assert_eq!(back.ruleset_digest, e.ruleset_digest);

        e.ruleset_digest = None;
        let json = serde_json::to_string(&e).unwrap();
        assert!(!json.contains("ruleset_digest"), "absent, not null (Go omitempty)");
        let back: EventEnvelope = serde_json::from_str(&json).unwrap();
        assert_eq!(back.ruleset_digest, None, "a missing field deserializes as None");
    }

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
            ruleset_digest: None,
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
