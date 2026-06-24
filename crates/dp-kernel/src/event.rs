//! L4.A — `Event` trait. Domain-typed view that callers implement on their
//! own Rust enums / structs.
//!
//! ## Why both `EventEnvelope` AND `Event`?
//!
//! - [`crate::EventEnvelope`] is the **wire shape** — a single concrete
//!   struct that mirrors `contracts/events/envelope.go::Envelope` field-for-
//!   field. It is what the EventStore reads/writes.
//! - [`Event`] is the **domain trait** — implemented by service-side types
//!   like `enum WorldEvent { TickAdvanced { tick: u64 }, RegionDiscovered { ... } }`.
//!   Lets the service code work in typed terms then convert to an
//!   `EventEnvelope` once at the EventStore boundary via
//!   [`Event::to_envelope`].
//!
//! ## LOCKED decisions
//!
//! - **Q-L4A-1** (the EventStore wraps PgPool, not exposes it) — this trait
//!   is what the EventStore upstream sees; it lets a single
//!   `EventStore::append<E: Event>(...)` signature accept any domain type.
//! - Backward-compat: a service using the cycle-12 raw `EventEnvelope` path
//!   continues to work. `Event` is additive — there's a blanket impl for
//!   `EventEnvelope` itself so existing call sites are unaffected.

use uuid::Uuid;

use crate::envelope::{EventEnvelope, Rfc3339Timestamp};
use crate::metadata::EventMetadata;

/// Domain-event trait. Service-side enums/structs implement this to surface
/// the envelope-shaped fields without forcing every call site through
/// `serde_json::Value` payloads.
///
/// Implementors typically derive [`Serialize`] for the payload portion;
/// `payload()` returns a `serde_json::Value` so the trait stays
/// payload-agnostic.
pub trait Event {
    /// Stable dotted identifier — convention: `<aggregate>.<verb>` (snake/
    /// kebab inside segments allowed). Examples: `world.tick_advanced`,
    /// `npc.said`, `pc.moved`.
    fn event_type(&self) -> &str;

    /// Schema version of this event payload (>= 1). Bumped via L2.H upcaster
    /// when payload shape changes.
    fn event_version(&self) -> u32 {
        1
    }

    /// Aggregate this event applies to (1:1 with `Aggregate::id()`).
    fn aggregate_id(&self) -> &str;

    /// Aggregate type tag — convention matches `Aggregate::aggregate_type()`
    /// (e.g. `world`, `pc`, `npc`, `region`).
    fn aggregate_type(&self) -> &str;

    /// JSON payload. Implementors typically `serde_json::to_value(self)` and
    /// strip envelope-level fields, OR return a hand-rolled `serde_json::json!`
    /// blob.
    fn payload(&self) -> serde_json::Value;

    /// Optional typed metadata. Default: empty.
    fn metadata(&self) -> EventMetadata {
        EventMetadata::default()
    }

    /// Build an [`EventEnvelope`] from this domain event. The caller supplies
    /// the envelope-level fields (`event_id`, `reality_id`, server-side
    /// timestamps, monotonic `aggregate_version`) because those are
    /// allocated at the EventStore boundary, NOT inside the domain type.
    fn to_envelope(
        &self,
        event_id: Uuid,
        reality_id: Uuid,
        aggregate_version: u64,
        occurred_at: Rfc3339Timestamp,
        recorded_at: Rfc3339Timestamp,
    ) -> EventEnvelope {
        EventEnvelope {
            event_id,
            event_type: self.event_type().to_string(),
            event_version: self.event_version(),
            aggregate_id: self.aggregate_id().to_string(),
            aggregate_type: self.aggregate_type().to_string(),
            aggregate_version,
            reality_id,
            occurred_at,
            recorded_at,
            payload: self.payload(),
            metadata: self.metadata().into_value(),
        }
    }
}

/// Convenience: `EventEnvelope` itself implements `Event` so call sites that
/// hold a raw envelope (cycle 8-16 style) can pass it where an `&dyn Event`
/// is required. `to_envelope` is overridden to return a clone of self with
/// the new version bumps, but the field-extractors return the wire values.
impl Event for EventEnvelope {
    fn event_type(&self) -> &str {
        &self.event_type
    }
    fn event_version(&self) -> u32 {
        self.event_version
    }
    fn aggregate_id(&self) -> &str {
        &self.aggregate_id
    }
    fn aggregate_type(&self) -> &str {
        &self.aggregate_type
    }
    fn payload(&self) -> serde_json::Value {
        self.payload.clone()
    }
    fn metadata(&self) -> EventMetadata {
        EventMetadata::from_value(self.metadata.as_ref()).unwrap_or_default()
    }
    fn to_envelope(
        &self,
        _event_id: Uuid,
        _reality_id: Uuid,
        _aggregate_version: u64,
        _occurred_at: Rfc3339Timestamp,
        _recorded_at: Rfc3339Timestamp,
    ) -> EventEnvelope {
        // EventEnvelope's `to_envelope` is identity (the caller already has
        // the envelope they want). Versions/IDs supplied by the caller are
        // ignored to keep the envelope's intrinsic wire shape stable —
        // mutations should happen via direct field updates, not this method.
        self.clone()
    }
}

/// Reverse direction: parse a domain type out of an envelope. Implementors
/// typically `serde_json::from_value(env.payload)` after dispatching on
/// `env.event_type`. Default impl returns `Err` to force the implementor to
/// opt in explicitly.
pub trait EventFromEnvelope: Sized + Event {
    /// Try to parse `Self` from an envelope. Returns `Err` if the envelope
    /// is for a different event type, or the payload cannot be decoded.
    fn try_from_envelope(env: &EventEnvelope) -> Result<Self, String>;
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::{Deserialize, Serialize};
    use serde_json::json;

    #[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
    struct WorldTickAdvanced {
        tick: u64,
        world_id: String,
    }

    impl Event for WorldTickAdvanced {
        fn event_type(&self) -> &str {
            "world.tick_advanced"
        }
        fn aggregate_id(&self) -> &str {
            &self.world_id
        }
        fn aggregate_type(&self) -> &str {
            "world"
        }
        fn payload(&self) -> serde_json::Value {
            json!({ "tick": self.tick })
        }
    }

    #[test]
    fn event_to_envelope_populates_all_fields() {
        let e = WorldTickAdvanced { tick: 42, world_id: "world-1".into() };
        let env = e.to_envelope(
            Uuid::from_u128(7),
            Uuid::from_u128(99),
            1,
            "2026-05-29T00:00:00Z".into(),
            "2026-05-29T00:00:01Z".into(),
        );
        assert_eq!(env.event_id, Uuid::from_u128(7));
        assert_eq!(env.event_type, "world.tick_advanced");
        assert_eq!(env.event_version, 1);
        assert_eq!(env.aggregate_id, "world-1");
        assert_eq!(env.aggregate_type, "world");
        assert_eq!(env.aggregate_version, 1);
        assert_eq!(env.reality_id, Uuid::from_u128(99));
        assert_eq!(env.payload, json!({ "tick": 42 }));
        assert!(env.metadata.is_none(), "default metadata is empty -> None");
        env.validate().unwrap();
    }

    #[test]
    fn envelope_self_impl_returns_intrinsic_fields() {
        let env = EventEnvelope {
            event_id: Uuid::from_u128(1),
            event_type: "x.y".into(),
            event_version: 3,
            aggregate_id: "a-1".into(),
            aggregate_type: "a".into(),
            aggregate_version: 5,
            reality_id: Uuid::from_u128(2),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: "2026-05-29T00:00:00Z".into(),
            payload: json!({"k": 1}),
            metadata: None,
        };
        let e: &dyn Event = &env;
        assert_eq!(e.event_type(), "x.y");
        assert_eq!(e.event_version(), 3);
        assert_eq!(e.aggregate_id(), "a-1");
        assert_eq!(e.aggregate_type(), "a");
        assert_eq!(e.payload(), json!({"k": 1}));
    }

    #[test]
    fn envelope_to_envelope_is_identity() {
        let env = EventEnvelope {
            event_id: Uuid::from_u128(1),
            event_type: "x.y".into(),
            event_version: 1,
            aggregate_id: "a-1".into(),
            aggregate_type: "a".into(),
            aggregate_version: 1,
            reality_id: Uuid::from_u128(2),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: "2026-05-29T00:00:00Z".into(),
            payload: json!({}),
            metadata: None,
        };
        let other = env.to_envelope(
            Uuid::from_u128(99),
            Uuid::from_u128(99),
            99,
            "2026-05-30T00:00:00Z".into(),
            "2026-05-30T00:00:00Z".into(),
        );
        assert_eq!(env, other, "EventEnvelope::to_envelope is identity");
    }

    #[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
    struct NpcSaid {
        npc_id: String,
        text: String,
    }
    impl Event for NpcSaid {
        fn event_type(&self) -> &str {
            "npc.said"
        }
        fn aggregate_id(&self) -> &str {
            &self.npc_id
        }
        fn aggregate_type(&self) -> &str {
            "npc"
        }
        fn payload(&self) -> serde_json::Value {
            json!({ "text": self.text })
        }
    }
    impl EventFromEnvelope for NpcSaid {
        fn try_from_envelope(env: &EventEnvelope) -> Result<Self, String> {
            if env.event_type != "npc.said" {
                return Err(format!("not npc.said: {}", env.event_type));
            }
            let text = env
                .payload
                .get("text")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "missing 'text' in payload".to_string())?
                .to_string();
            Ok(NpcSaid {
                npc_id: env.aggregate_id.clone(),
                text,
            })
        }
    }

    #[test]
    fn event_from_envelope_roundtrips() {
        let e = NpcSaid { npc_id: "npc-1".into(), text: "hello".into() };
        let env = e.to_envelope(
            Uuid::from_u128(1),
            Uuid::from_u128(2),
            1,
            "2026-05-29T00:00:00Z".into(),
            "2026-05-29T00:00:00Z".into(),
        );
        let back = NpcSaid::try_from_envelope(&env).unwrap();
        assert_eq!(e, back);
    }
}
