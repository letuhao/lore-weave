//! L3.B.3 — PC + pc_inventory + pc_relationship projection skeletons.
//!
//! ## Scope (RAID cycle 13)
//!
//! This crate ships **skeleton** implementations of the [`Projection`] trait
//! (cycle-12 contract from `dp-kernel`) for the three PC-side projection
//! tables shipped in cycle-13 L3.A migration:
//!   - `pc_projection`            (L3.A.1)
//!   - `pc_inventory_projection`  (L3.A.2)
//!   - `pc_relationship_projection` (L3.A.3)
//!
//! Each projection handles **1-2 representative events** and TODOs the rest.
//! Full event coverage lands with the L4-L7 domain cycles (when the
//! corresponding domain services author their `pc.*` event handlers).
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3-4** (OPEN_QUESTIONS_LOCKED §5): every emitted [`ProjectionUpdate`]
//!   carries [`VerificationMeta`] (event_id, aggregate_version, applied_at).
//!   The migration tables have matching columns.
//! - **Q-L3B-1** (§5): trait returns `Vec<ProjectionUpdate>` — `PcProjection`
//!   demonstrates the multi-update path (`pc.spawned` writes a row to BOTH
//!   `pc_projection` AND a placeholder inventory row).
//!
//! ## What is NOT in this crate
//!
//! - Full event coverage — only `pc.spawned`, `pc.moved`, `pc.item_acquired`
//!   are sketched. The remaining `pc.*` events are TODO comments at the
//!   match arms.
//! - DB write side (sqlx EXECUTE-ing the [`ProjectionUpdate`]) — that's
//!   `services/world-service` runtime work in cycle 14+.
//! - Macros — no `#[derive(Projection)]` yet (L4 work).
//! - Async — sync only per Q-L3-2.

use dp_kernel::{EventEnvelope, Projection, ProjectionUpdate, VerificationMeta};
use serde_json::json;

// ───────────────────────────────────────────────────────────────────────────
// pc_projection (L3.A.1)
// ───────────────────────────────────────────────────────────────────────────

/// Skeleton projection for `pc_projection`.
pub struct PcProjection;

impl Projection for PcProjection {
    fn name(&self) -> &str {
        "pc_state"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.aggregate_type == "pc"
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        if env.aggregate_type != "pc" {
            return vec![];
        }
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            // ── pc.spawned: Insert into pc_projection + placeholder inventory
            //               row demonstrates Q-L3B-1 multi-update fan-out.
            "pc.spawned" => {
                vec![
                    ProjectionUpdate::Insert {
                        table: "pc_projection".into(),
                        row: json!({
                            "pc_id":               env.aggregate_id,
                            "user_id":             env.payload.get("user_id"),
                            "name":                env.payload.get("name"),
                            "current_region_id":   env.payload.get("spawn_region_id"),
                            "status":              "active",
                            "stats":               env.payload.get("stats").cloned().unwrap_or(json!({})),
                            "last_event_version":  env.aggregate_version,
                        }),
                        meta: meta.clone(),
                    },
                    // Demonstrates Q-L3B-1: one event → multiple updates.
                    // Placeholder inventory row keyed by sentinel item_code.
                    ProjectionUpdate::Insert {
                        table: "pc_inventory_projection".into(),
                        row: json!({
                            "pc_id":       env.aggregate_id,
                            "item_code":   "__sentinel_initial__",
                            "quantity":    0,
                            "metadata":    {},
                        }),
                        meta,
                    },
                ]
            }
            // ── pc.moved: Update current_region_id.
            "pc.moved" => vec![ProjectionUpdate::Update {
                table: "pc_projection".into(),
                pk: json!({ "pc_id": env.aggregate_id }),
                fields: json!({
                    "current_region_id":   env.payload.get("to_region_id"),
                    "last_event_version":  env.aggregate_version,
                }),
                meta,
            }],
            // TODO(cycle 17+ L4): pc.died, pc.stats_changed, pc.renamed, ...
            _ => vec![],
        }
    }
}

// ───────────────────────────────────────────────────────────────────────────
// pc_inventory_projection (L3.A.2)
// ───────────────────────────────────────────────────────────────────────────

pub struct PcInventoryProjection;

impl Projection for PcInventoryProjection {
    fn name(&self) -> &str {
        "pc_inventory"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.aggregate_type == "pc" && env.event_type.starts_with("pc.item_")
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            "pc.item_acquired" => vec![ProjectionUpdate::Insert {
                table: "pc_inventory_projection".into(),
                row: json!({
                    "pc_id":             env.aggregate_id,
                    "item_code":         env.payload.get("item_code"),
                    "quantity":          env.payload.get("quantity").cloned().unwrap_or(json!(1)),
                    "metadata":          env.payload.get("metadata").cloned().unwrap_or(json!({})),
                    "origin_reality_id": env.payload.get("origin_reality_id"),
                }),
                meta,
            }],
            // TODO(cycle 17+ L4): pc.item_consumed, pc.item_dropped, ...
            _ => vec![],
        }
    }
}

// ───────────────────────────────────────────────────────────────────────────
// pc_relationship_projection (L3.A.3)
// ───────────────────────────────────────────────────────────────────────────

pub struct PcRelationshipProjection;

impl Projection for PcRelationshipProjection {
    fn name(&self) -> &str {
        "pc_relationship"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.aggregate_type == "pc" && env.event_type.starts_with("pc.relationship_")
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            "pc.relationship_changed" => vec![ProjectionUpdate::Update {
                table: "pc_relationship_projection".into(),
                pk: json!({
                    "pc_id":             env.aggregate_id,
                    "other_entity_type": env.payload.get("other_entity_type"),
                    "other_entity_id":   env.payload.get("other_entity_id"),
                }),
                fields: json!({
                    "score":  env.payload.get("score"),
                    "labels": env.payload.get("labels"),
                }),
                meta,
            }],
            // TODO(cycle 17+ L4): pc.relationship_created, pc.relationship_severed, ...
            _ => vec![],
        }
    }
}

// ───────────────────────────────────────────────────────────────────────────
// Tests
// ───────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use uuid::Uuid;

    fn env(event_type: &str, agg_id: &str, version: u64, payload: serde_json::Value) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(version as u128),
            event_type: event_type.into(),
            event_version: 1,
            aggregate_id: agg_id.into(),
            aggregate_type: "pc".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", version % 60),
            payload,
            metadata: None,
        }
    }

    #[test]
    fn pc_projection_spawned_emits_two_updates_q_l3b_1() {
        let p = PcProjection;
        let e = env(
            "pc.spawned",
            "pc-1",
            1,
            json!({
                "user_id":         "user-1",
                "name":            "Alice",
                "spawn_region_id": "region-1",
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 2, "Q-L3B-1: pc.spawned fans out to pc_projection + pc_inventory_projection");
        assert_eq!(updates[0].table(), "pc_projection");
        assert_eq!(updates[1].table(), "pc_inventory_projection");
    }

    #[test]
    fn pc_projection_moved_updates_region() {
        let p = PcProjection;
        let e = env("pc.moved", "pc-1", 2, json!({ "to_region_id": "region-2" }));
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "pc_projection");
    }

    #[test]
    fn pc_projection_unknown_event_returns_empty() {
        let p = PcProjection;
        let e = env("pc.future_event", "pc-1", 3, json!({}));
        assert!(p.apply_event(&e).is_empty());
    }

    #[test]
    fn pc_projection_skips_non_pc_aggregate() {
        let p = PcProjection;
        let mut e = env("pc.spawned", "npc-1", 1, json!({}));
        e.aggregate_type = "npc".into();
        assert!(p.apply_event(&e).is_empty());
    }

    #[test]
    fn pc_inventory_projection_item_acquired() {
        let p = PcInventoryProjection;
        let e = env(
            "pc.item_acquired",
            "pc-1",
            5,
            json!({ "item_code": "sword_iron", "quantity": 1 }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "pc_inventory_projection");
    }

    #[test]
    fn pc_relationship_projection_changed() {
        let p = PcRelationshipProjection;
        let e = env(
            "pc.relationship_changed",
            "pc-1",
            10,
            json!({
                "other_entity_type": "npc",
                "other_entity_id":   "npc-7",
                "score":             42,
                "labels":            ["friendly"],
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "pc_relationship_projection");
    }

    #[test]
    fn verification_meta_stamped_on_every_update() {
        let p = PcProjection;
        let e = env("pc.spawned", "pc-1", 1, json!({}));
        let updates = p.apply_event(&e);
        for u in &updates {
            match u {
                ProjectionUpdate::Insert { meta, .. } | ProjectionUpdate::Update { meta, .. } => {
                    assert_eq!(meta.aggregate_version, 1);
                    assert_eq!(meta.event_id, Uuid::from_u128(1));
                }
                _ => unreachable!(),
            }
        }
    }
}
