//! L3.B.7 — session_participants projection skeleton (S2 capability binding).
//!
//! ## Scope (RAID cycle 13)
//!
//! Skeleton implementation of [`Projection`] for `session_participants`
//! (L3.A.10). S2 capability-scoped membership: which entities are bound
//! to which session. `left_at IS NULL` = currently in-session.
//!
//! Handles `session.participant_joined` + `session.participant_left`. Other
//! `session.*` events (started/ended) update the NPC session memory
//! projection (handled by `projections-npc::NpcSessionMemoryProjection`),
//! not the participants table.
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3-4** (§5): VerificationMeta on every emitted [`ProjectionUpdate`].

use dp_kernel::{EventEnvelope, Projection, ProjectionUpdate, VerificationMeta};
use serde_json::json;

pub struct SessionParticipantsProjection;

impl Projection for SessionParticipantsProjection {
    fn name(&self) -> &str {
        "session_participants"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.event_type == "session.participant_joined" || env.event_type == "session.participant_left"
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            "session.participant_joined" => vec![ProjectionUpdate::Insert {
                table: "session_participants".into(),
                row: json!({
                    "session_id":       env.payload.get("session_id"),
                    "participant_type": env.payload.get("participant_type"),
                    "participant_id":   env.payload.get("participant_id"),
                    "reality_id":       env.reality_id,
                    "joined_at":        env.occurred_at,
                }),
                meta,
            }],
            "session.participant_left" => vec![ProjectionUpdate::Update {
                table: "session_participants".into(),
                pk: json!({
                    "session_id":       env.payload.get("session_id"),
                    "participant_type": env.payload.get("participant_type"),
                    "participant_id":   env.payload.get("participant_id"),
                }),
                fields: json!({ "left_at": env.occurred_at }),
                meta,
            }],
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
            aggregate_id: "sess-1".into(),
            aggregate_type: "session".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", version % 60),
            payload,
            metadata: None,
        }
    }

    #[test]
    fn participant_joined_inserts() {
        let p = SessionParticipantsProjection;
        let e = env(
            "session.participant_joined",
            1,
            json!({
                "session_id":       "sess-1",
                "participant_type": "pc",
                "participant_id":   "pc-1",
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "session_participants");
        match &updates[0] {
            ProjectionUpdate::Insert { .. } => {}
            _ => panic!("expected Insert"),
        }
    }

    #[test]
    fn participant_left_updates_left_at() {
        let p = SessionParticipantsProjection;
        let e = env(
            "session.participant_left",
            5,
            json!({
                "session_id":       "sess-1",
                "participant_type": "pc",
                "participant_id":   "pc-1",
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        match &updates[0] {
            ProjectionUpdate::Update { fields, .. } => {
                assert!(fields.get("left_at").is_some(), "left_at must be set");
            }
            _ => panic!("expected Update"),
        }
    }

    #[test]
    fn unrelated_session_event_returns_empty() {
        let p = SessionParticipantsProjection;
        let e = env("session.started", 1, json!({}));
        assert!(p.apply_event(&e).is_empty());
    }
}
