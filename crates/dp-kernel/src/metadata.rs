//! L4.A — `EventMetadata`: typed shape for the `metadata` blob carried on
//! every [`EventEnvelope`].
//!
//! ## Scope (RAID cycle 17)
//!
//! Cycles 8-16 modeled `EventEnvelope.metadata` as a free-form
//! `Option<serde_json::Value>` so the on-the-wire shape could evolve without
//! breaking already-written events. L4.A introduces a **typed** struct that
//! callers can construct + read with field accessors instead of `json!` blobs.
//!
//! ## Wire compatibility contract
//!
//! `EventMetadata` is INTENTIONALLY a strict subset of fields seen in
//! production:
//!   * `actor`              — who triggered the event (player id, system, …)
//!   * `causation_id`       — the event id that immediately caused this one
//!   * `correlation_id`     — the request id tying a fan-out together
//!   * `source`             — emitting service name (e.g. `world-service`)
//!   * `occurred_at`        — in-world time (RFC3339; distinct from
//!     `EventEnvelope.recorded_at` which is server append time)
//!   * `instance_clock_tick` — monotonic per-service tick counter (SR06 I16)
//!
//! Any field NOT in this list is preserved in the round-trip via
//! `#[serde(flatten)] extra: Map<String, Value>` so older / experimental keys
//! never get silently dropped. This matches the cycle 8 envelope's
//! `skip_serializing_if = "Option::is_none"` design — additive evolution only.
//!
//! ## Why a separate module
//!
//! `envelope.rs` is the wire-shape mirror of `contracts/events/envelope.go`
//! and must stay byte-for-byte stable. Typed metadata is a Rust-side
//! affordance on top of it; callers can ignore [`EventMetadata`] entirely
//! and continue to write `serde_json::Value` blobs into
//! `EventEnvelope.metadata` without breakage.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use uuid::Uuid;

use crate::envelope::Rfc3339Timestamp;

/// Typed view of the `EventEnvelope.metadata` blob.
///
/// All fields are optional; an event with no metadata at all serializes as
/// the empty object `{}` (NOT `null`), so the round-trip stays deterministic.
///
/// Convert in/out of `serde_json::Value` via [`EventMetadata::from_value`] +
/// [`EventMetadata::into_value`].
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct EventMetadata {
    /// Player ID, system actor, or service name that originated the action.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub actor: Option<String>,

    /// Event ID of the immediately-preceding event in the same causal chain.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub causation_id: Option<Uuid>,

    /// Request / trace ID that ties together a fan-out (1 request -> many events).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<Uuid>,

    /// Emitting service name. Convention: kebab-case service name as in
    /// `services/<name>/` (e.g. `world-service`, `chat-service`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,

    /// In-world time the action occurred. Distinct from
    /// `EventEnvelope.recorded_at` which is server append time.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub occurred_at: Option<Rfc3339Timestamp>,

    /// Monotonic per-service tick counter (SR06 I16). Lets the integrity
    /// checker spot dropped events from a single emitter.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub instance_clock_tick: Option<u64>,

    /// Forward-compat: any field NOT named above is preserved here verbatim.
    /// This keeps old/experimental keys alive through the typed boundary.
    #[serde(flatten, default, skip_serializing_if = "Map::is_empty")]
    pub extra: Map<String, Value>,
}

impl EventMetadata {
    /// Construct a typed view from the raw `Option<serde_json::Value>` field
    /// of [`crate::EventEnvelope`]. `None` and empty objects both yield an
    /// empty typed struct (lossless).
    pub fn from_value(v: Option<&Value>) -> Result<Self, String> {
        match v {
            None => Ok(Self::default()),
            Some(val) => serde_json::from_value(val.clone()).map_err(|e| e.to_string()),
        }
    }

    /// Render to the raw `serde_json::Value` shape that
    /// `EventEnvelope.metadata` carries. Returns `None` when the struct has
    /// no fields set — so an envelope with no metadata still serializes
    /// without an empty `"metadata": {}` blob (matches cycle 8 envelope's
    /// `skip_serializing_if = "Option::is_none"` rule).
    pub fn into_value(self) -> Option<Value> {
        if self.is_empty() {
            return None;
        }
        Some(serde_json::to_value(self).expect("EventMetadata always serializes"))
    }

    /// `true` iff no field is set. Used by [`Self::into_value`] to decide
    /// whether to emit a `metadata` blob.
    pub fn is_empty(&self) -> bool {
        self.actor.is_none()
            && self.causation_id.is_none()
            && self.correlation_id.is_none()
            && self.source.is_none()
            && self.occurred_at.is_none()
            && self.instance_clock_tick.is_none()
            && self.extra.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn default_is_empty() {
        assert!(EventMetadata::default().is_empty());
    }

    #[test]
    fn empty_round_trips_as_none() {
        let m = EventMetadata::default();
        assert!(m.into_value().is_none());
    }

    #[test]
    fn populated_round_trip_preserves_fields() {
        let m = EventMetadata {
            actor: Some("player-1".into()),
            causation_id: Some(Uuid::from_u128(1)),
            correlation_id: Some(Uuid::from_u128(2)),
            source: Some("world-service".into()),
            occurred_at: Some("2026-05-29T00:00:00Z".into()),
            instance_clock_tick: Some(42),
            extra: Map::new(),
        };
        let v = m.clone().into_value().unwrap();
        let back = EventMetadata::from_value(Some(&v)).unwrap();
        assert_eq!(m, back);
    }

    #[test]
    fn extra_fields_round_trip_via_flatten() {
        let raw = json!({
            "actor": "system",
            "experimental_replay_token": "abc-123",
            "unrelated_nested": {"k": 1},
        });
        let m = EventMetadata::from_value(Some(&raw)).unwrap();
        assert_eq!(m.actor.as_deref(), Some("system"));
        assert_eq!(m.extra.len(), 2, "two unknown fields preserved");
        let v = m.into_value().unwrap();
        assert_eq!(
            v.get("experimental_replay_token").and_then(|x| x.as_str()),
            Some("abc-123")
        );
        assert!(v.get("unrelated_nested").is_some());
    }

    #[test]
    fn from_value_none_yields_empty() {
        let m = EventMetadata::from_value(None).unwrap();
        assert!(m.is_empty());
    }

    #[test]
    fn from_value_rejects_non_object() {
        let v = json!("not an object");
        let res = EventMetadata::from_value(Some(&v));
        assert!(res.is_err());
    }
}
