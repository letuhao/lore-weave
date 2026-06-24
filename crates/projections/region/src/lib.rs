//! L3.B.5 — region projection skeleton.
//!
//! ## Scope (RAID cycle 13)
//!
//! Skeleton implementation of [`Projection`] for `region_projection`
//! (L3.A.8). Handles `region.created` + `region.ambient_changed`; the rest
//! TODO until L4-L7 cycles author the full `region.*` event taxonomy.
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3-4** (§5): VerificationMeta on every emitted [`ProjectionUpdate`].

use dp_kernel::{EventEnvelope, Projection, ProjectionUpdate, VerificationMeta};
use serde_json::json;

pub struct RegionProjection;

impl Projection for RegionProjection {
    fn name(&self) -> &str {
        "region_state"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.aggregate_type == "region"
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        if env.aggregate_type != "region" {
            return vec![];
        }
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            "region.created" => vec![ProjectionUpdate::Insert {
                table: "region_projection".into(),
                row: json!({
                    "region_id":          env.aggregate_id,
                    "code":               env.payload.get("code"),
                    "display_name":       env.payload.get("display_name"),
                    "description":        env.payload.get("description").cloned().unwrap_or(json!("")),
                    "parent_region_id":   env.payload.get("parent_region_id"),
                    "exits":              env.payload.get("exits").cloned().unwrap_or(json!([])),
                    "floor_items":        json!([]),
                    "ambient_state":      env.payload.get("ambient_state").cloned().unwrap_or(json!({})),
                    "last_event_version": env.aggregate_version,
                }),
                meta,
            }],
            "region.ambient_changed" => vec![ProjectionUpdate::Update {
                table: "region_projection".into(),
                pk: json!({ "region_id": env.aggregate_id }),
                fields: json!({
                    "ambient_state":      env.payload.get("ambient_state"),
                    "last_event_version": env.aggregate_version,
                }),
                meta,
            }],
            // TODO(cycle 17+ L4): region.exit_added, region.item_dropped, region.merged, ...
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
            aggregate_id: "region-1".into(),
            aggregate_type: "region".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", version % 60),
            payload,
            metadata: None,
        }
    }

    #[test]
    fn region_created() {
        let p = RegionProjection;
        let e = env("region.created", 1, json!({ "code": "r1", "display_name": "Forest" }));
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "region_projection");
    }

    #[test]
    fn region_ambient_changed() {
        let p = RegionProjection;
        let e = env(
            "region.ambient_changed",
            5,
            json!({ "ambient_state": { "weather": "rain", "time_of_day": "dusk" } }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
    }

    #[test]
    fn region_unknown_event_returns_empty() {
        let p = RegionProjection;
        let e = env("region.future_event", 2, json!({}));
        assert!(p.apply_event(&e).is_empty());
    }
}
