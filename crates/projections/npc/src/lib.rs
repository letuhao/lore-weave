//! L3.B.4 — NPC + npc_session_memory + npc_pc_relationship + embedding
//! projection skeletons.
//!
//! ## Scope (RAID cycle 13)
//!
//! Skeleton implementations of [`Projection`] for the four NPC-side tables
//! shipped in cycle-13 L3.A migration:
//!   - `npc_projection`                 (L3.A.4)
//!   - `npc_session_memory_projection`  (L3.A.5)
//!   - `npc_pc_relationship_projection` (L3.A.6)
//!   - `npc_session_memory_embedding`   (L3.A.7) — Q-L3I-1 dim=1536 LOCKED
//!
//! Each handles 1-2 representative events; full coverage lands with L4-L7
//! domain cycles.
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3-4** (§5): VerificationMeta on every emitted [`ProjectionUpdate`].
//! - **Q-L3B-1** (§5): `npc.said` fans out — updates `npc_projection` AND
//!   increments `npc_session_memory_projection.interaction_count`.
//! - **Q-L3I-1** (§5): embedding dim 1536 hard-coded V1. The
//!   `NpcSessionMemoryEmbeddingProjection` here only WRITES bytes/vectors of
//!   that length; the actual embedding computation (LLM call via BYOK
//!   provider) is cycle-14 L3.I (`embedding_writer.rs`).

use dp_kernel::{EventEnvelope, Projection, ProjectionUpdate, VerificationMeta};
use serde_json::json;

/// Embedding dimension (Q-L3I-1 V1 lock).
pub const EMBEDDING_DIM: usize = 1536;

// ───────────────────────────────────────────────────────────────────────────
// npc_projection (L3.A.4)
// ───────────────────────────────────────────────────────────────────────────

pub struct NpcProjection;

impl Projection for NpcProjection {
    fn name(&self) -> &str {
        "npc_state"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.aggregate_type == "npc"
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        if env.aggregate_type != "npc" {
            return vec![];
        }
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            "npc.created" => vec![ProjectionUpdate::Insert {
                table: "npc_projection".into(),
                row: json!({
                    "npc_id":             env.aggregate_id,
                    "glossary_entity_id": env.payload.get("glossary_entity_id"),
                    "current_region_id":  env.payload.get("spawn_region_id"),
                    "mood":               env.payload.get("initial_mood"),
                    "core_beliefs":       env.payload.get("core_beliefs").cloned().unwrap_or(json!({})),
                    "flexible_state":     json!({}),
                    "last_event_version": env.aggregate_version,
                }),
                meta,
            }],
            // ── npc.said: Q-L3B-1 multi-update fan-out. Updates npc state
            //              + bumps session-memory interaction counter.
            "npc.said" => {
                let session_id = env
                    .metadata
                    .as_ref()
                    .and_then(|m| m.get("session_id"))
                    .cloned()
                    .unwrap_or(json!(null));
                vec![
                    ProjectionUpdate::Update {
                        table: "npc_projection".into(),
                        pk: json!({ "npc_id": env.aggregate_id }),
                        fields: json!({ "last_event_version": env.aggregate_version }),
                        meta: meta.clone(),
                    },
                    ProjectionUpdate::Update {
                        table: "npc_session_memory_projection".into(),
                        pk: json!({ "npc_id": env.aggregate_id, "session_id": session_id }),
                        fields: json!({ "interaction_count_increment": 1 }),
                        meta,
                    },
                ]
            }
            // TODO(cycle 17+ L4): npc.mood_changed, npc.belief_updated, npc.moved, ...
            _ => vec![],
        }
    }
}

// ───────────────────────────────────────────────────────────────────────────
// npc_session_memory_projection (L3.A.5)
// ───────────────────────────────────────────────────────────────────────────

pub struct NpcSessionMemoryProjection;

impl Projection for NpcSessionMemoryProjection {
    fn name(&self) -> &str {
        "npc_session_memory"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.event_type.starts_with("session.") || env.event_type == "npc.memory_updated"
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            "session.started" => vec![ProjectionUpdate::Insert {
                table: "npc_session_memory_projection".into(),
                row: json!({
                    "npc_id":              env.payload.get("npc_id"),
                    "session_id":          env.payload.get("session_id"),
                    "reality_id":          env.reality_id,
                    "aggregate_id":        env.payload.get("aggregate_id"),
                    "session_started_at":  env.occurred_at,
                    "interaction_count":   0,
                    "archive_status":      "active",
                }),
                meta,
            }],
            "session.ended" => vec![ProjectionUpdate::Update {
                table: "npc_session_memory_projection".into(),
                pk: json!({
                    "npc_id":     env.payload.get("npc_id"),
                    "session_id": env.payload.get("session_id"),
                }),
                fields: json!({
                    "session_ended_at": env.occurred_at,
                    "archive_status":   "faded",
                }),
                meta,
            }],
            // TODO(cycle 14+ L3.E): npc.memory_updated (summary regen by
            //                       background fader worker).
            _ => vec![],
        }
    }
}

// ───────────────────────────────────────────────────────────────────────────
// npc_pc_relationship_projection (L3.A.6)
// ───────────────────────────────────────────────────────────────────────────

pub struct NpcPcRelationshipProjection;

impl Projection for NpcPcRelationshipProjection {
    fn name(&self) -> &str {
        "npc_pc_relationship"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.aggregate_type == "npc" && env.event_type.starts_with("npc.relationship_")
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            // Upsert: the relationship row is created on the FIRST
            // relationship_changed (no preceding Insert) and updated thereafter.
            "npc.relationship_changed" => vec![ProjectionUpdate::Upsert {
                table: "npc_pc_relationship_projection".into(),
                pk: json!({
                    "npc_id":          env.aggregate_id,
                    "other_entity_id": env.payload.get("other_entity_id"),
                }),
                fields: json!({
                    "other_entity_type":    env.payload.get("other_entity_type"),
                    "reality_id":           env.reality_id,
                    "trust_level":          env.payload.get("trust_level"),
                    "familiarity_count":    env.payload.get("familiarity_count"),
                    "last_session_id":      env.payload.get("session_id"),
                    "relationship_labels":  env.payload.get("labels"),
                }),
                meta,
            }],
            _ => vec![],
        }
    }
}

// ───────────────────────────────────────────────────────────────────────────
// npc_session_memory_embedding (L3.A.7) — Q-L3I-1 dim=1536 V1
// ───────────────────────────────────────────────────────────────────────────

pub struct NpcSessionMemoryEmbeddingProjection;

impl Projection for NpcSessionMemoryEmbeddingProjection {
    fn name(&self) -> &str {
        "npc_session_memory_embedding"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.event_type == "npc.memory_embedded"
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        if env.event_type != "npc.memory_embedded" {
            return vec![];
        }
        // Q-L3I-1 V1 enforcement: payload MUST declare dim=1536 or we skip
        // (treat as malformed — the embedding writer will retry).
        let declared_dim = env
            .payload
            .get("dim")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as usize;
        if declared_dim != EMBEDDING_DIM {
            return vec![]; // skip — wrong dim, will be flagged by integrity checker
        }
        let meta = VerificationMeta::from_envelope(env);
        vec![ProjectionUpdate::Insert {
            table: "npc_session_memory_embedding".into(),
            row: json!({
                "npc_id":       env.payload.get("npc_id"),
                "session_id":   env.payload.get("session_id"),
                "embedding":    env.payload.get("embedding"),
                "content_hash": env.payload.get("content_hash"),
            }),
            meta,
        }]
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

    fn env(event_type: &str, agg_type: &str, agg_id: &str, version: u64, payload: serde_json::Value) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(version as u128),
            event_type: event_type.into(),
            event_version: 1,
            aggregate_id: agg_id.into(),
            aggregate_type: agg_type.into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", version % 60),
            payload,
            metadata: None,
        }
    }

    #[test]
    fn npc_projection_created() {
        let p = NpcProjection;
        let e = env(
            "npc.created",
            "npc",
            "npc-1",
            1,
            json!({ "glossary_entity_id": "g-1", "initial_mood": "neutral" }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "npc_projection");
    }

    #[test]
    fn npc_projection_said_emits_two_updates_q_l3b_1() {
        let p = NpcProjection;
        let mut e = env("npc.said", "npc", "npc-1", 5, json!({}));
        e.metadata = Some(json!({ "session_id": "sess-9" }));
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 2, "Q-L3B-1: npc.said fans out across two tables");
        assert_eq!(updates[0].table(), "npc_projection");
        assert_eq!(updates[1].table(), "npc_session_memory_projection");
    }

    #[test]
    fn npc_session_memory_session_started() {
        let p = NpcSessionMemoryProjection;
        let e = env(
            "session.started",
            "session",
            "sess-1",
            1,
            json!({ "npc_id": "npc-1", "session_id": "sess-1", "aggregate_id": "agg-1" }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "npc_session_memory_projection");
    }

    #[test]
    fn npc_pc_relationship_changed() {
        let p = NpcPcRelationshipProjection;
        let e = env(
            "npc.relationship_changed",
            "npc",
            "npc-1",
            7,
            json!({
                "other_entity_type": "pc",
                "other_entity_id":   "pc-1",
                "trust_level":       50,
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "npc_pc_relationship_projection");
        // MUST be an Upsert (create-or-update): the row is created on the first
        // relationship_changed with no preceding Insert. A regression to Update
        // would silently fail to materialize the row on rebuild
        // (D-W3-NPC-REL-PROJECTION-UPSERT).
        assert!(
            matches!(updates[0], ProjectionUpdate::Upsert { .. }),
            "npc.relationship_changed must Upsert, got {:?}",
            updates[0]
        );
    }

    #[test]
    fn embedding_projection_writes_when_dim_matches() {
        let p = NpcSessionMemoryEmbeddingProjection;
        let e = env(
            "npc.memory_embedded",
            "npc",
            "npc-1",
            1,
            json!({
                "npc_id":       "npc-1",
                "session_id":   "sess-1",
                "embedding":    vec![0.0_f32; EMBEDDING_DIM],
                "content_hash": "abc",
                "dim":          EMBEDDING_DIM,
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1, "matching dim writes a row");
    }

    #[test]
    fn embedding_projection_skips_when_dim_mismatches_q_l3i_1() {
        let p = NpcSessionMemoryEmbeddingProjection;
        let e = env(
            "npc.memory_embedded",
            "npc",
            "npc-1",
            1,
            json!({ "dim": 768 }), // wrong dim — Q-L3I-1 V1 LOCKED at 1536
        );
        assert!(p.apply_event(&e).is_empty(), "Q-L3I-1: V1 rejects dim != 1536");
    }

    #[test]
    fn embedding_dim_constant_locked_at_1536_q_l3i_1() {
        assert_eq!(EMBEDDING_DIM, 1536, "Q-L3I-1 LOCKED V1");
    }
}
