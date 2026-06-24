//! L3.B.6 — world_kv projection skeleton.
//!
//! ## Scope (RAID cycle 13)
//!
//! Skeleton implementation of [`Projection`] for `world_kv_projection`
//! (L3.A.9). Handles the canonical `world.kv_set` and `world.kv_unset`
//! events; domain-specific quest-flag / global-event handlers land in
//! L4-L7 cycles.
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3-4** (§5): VerificationMeta on every emitted [`ProjectionUpdate`].

use dp_kernel::{EventEnvelope, Projection, ProjectionUpdate, VerificationMeta};
use serde_json::json;

pub struct WorldKvProjection;

impl Projection for WorldKvProjection {
    fn name(&self) -> &str {
        "world_kv"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.event_type.starts_with("world.kv_")
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            "world.kv_set" => {
                let Some(key) = env.payload.get("key").and_then(|v| v.as_str()) else {
                    return vec![]; // malformed payload — skip; integrity checker will flag
                };
                vec![ProjectionUpdate::Insert {
                    table: "world_kv_projection".into(),
                    row: json!({
                        "key":                key,
                        "value":              env.payload.get("value"),
                        "last_event_version": env.aggregate_version,
                        "updated_at":         env.recorded_at,
                    }),
                    meta,
                }]
            }
            "world.kv_unset" => {
                let Some(key) = env.payload.get("key").and_then(|v| v.as_str()) else {
                    return vec![];
                };
                vec![ProjectionUpdate::Delete {
                    table: "world_kv_projection".into(),
                    pk: json!({ "key": key }),
                }]
            }
            // TODO(cycle 17+ L4): quest-flag specialized writers.
            _ => vec![],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    fn env(event_type: &str, version: u64, payload: serde_json::Value) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(version as u128),
            event_type: event_type.into(),
            event_version: 1,
            aggregate_id: "world".into(),
            aggregate_type: "world".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", version % 60),
            payload,
            metadata: None,
        }
    }

    #[test]
    fn world_kv_set() {
        let p = WorldKvProjection;
        let e = env("world.kv_set", 1, json!({ "key": "quest.epic_started", "value": true }));
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "world_kv_projection");
    }

    #[test]
    fn world_kv_unset_emits_delete() {
        let p = WorldKvProjection;
        let e = env("world.kv_unset", 2, json!({ "key": "quest.epic_started" }));
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        match &updates[0] {
            ProjectionUpdate::Delete { .. } => {}
            _ => panic!("expected Delete variant for kv_unset"),
        }
    }

    #[test]
    fn world_kv_malformed_payload_returns_empty() {
        let p = WorldKvProjection;
        let e = env("world.kv_set", 3, json!({})); // no key
        assert!(p.apply_event(&e).is_empty());
    }
}
