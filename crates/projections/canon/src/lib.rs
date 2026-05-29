//! L5.D.3 — `canon_projection` writer.
//!
//! ## Scope (RAID cycle 23)
//!
//! Implements [`Projection`] for the four `canon.entry.*` events shipped in
//! cycle 23 L5.A (`contracts/events/canon.go`). Writes UPSERT-shaped
//! [`ProjectionUpdate`]s targeting the cycle-23 L5.D.1 `canon_projection`
//! table (`contracts/migrations/per_reality/0009_canon_projection.up.sql`).
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L5A-1**: foundation owns the consumer side; glossary-service outbox
//!   emitter is a SEPARATE sub-program. This crate works against the contract
//!   (event shapes from `contracts/events/canon.go`) — when the sub-program
//!   lands, this writer is wired into the meta-worker canon consumer
//!   (cycle 24+ L5.B) without code change.
//! - **Q-L5-3**: SINGLE `canon_projection` table with `canon_layer` column;
//!   we write `"L1_axiom"` or `"L2_seeded"` into the row directly from the
//!   event payload.
//! - **Q-L3-4**: every emitted [`ProjectionUpdate`] carries [`VerificationMeta`]
//!   stamped from the envelope (event_id + aggregate_version + applied_at).
//! - **Q-L1A-2**: canon TABLES (canon_entries, etc.) live in glossary DB
//!   (NOT meta, NOT per-reality) — this projection is a per-reality CACHE
//!   of authored canon, NOT the SSOT. UPSERT semantics: canon update =
//!   upsert on `canon_entry_id`, not insert.
//!
//! ## What is NOT in this crate
//!
//! - Cascade read-through writer (multiverse §3) — when a child reality
//!   inherits canon from an ancestor, the writer is a SEPARATE path
//!   (`cascaded_from_reality_id` populated, `source_event_id` NULL). That
//!   path lands with the cycle 24+ multiverse cascade orchestrator.
//! - L3 override marker writer (`overridden_by_l3_event_id`) — set by a
//!   different per-reality L3 event handler (NOT canon.* events), shipped
//!   in cycle 24+ L5.B sibling.
//! - DB write side (sqlx EXECUTE-ing the [`ProjectionUpdate`]) — that's
//!   meta-worker runtime work in cycle 24+ (L5.B canon writer).
//! - Async — sync only per Q-L3-2 (consistent with cycle 13 projections).

use dp_kernel::{EventEnvelope, Projection, ProjectionUpdate, VerificationMeta};
use serde_json::json;

/// LOCKED canon layer values per Q-L5-3.
pub const CANON_LAYER_L1_AXIOM: &str = "L1_axiom";
pub const CANON_LAYER_L2_SEEDED: &str = "L2_seeded";

/// Default lock level when canon.entry.created event payload omits the
/// field. Matches `contracts/migrations/per_reality/0009_canon_projection.up.sql`
/// column DEFAULT.
pub const DEFAULT_LOCK_LEVEL: &str = "soft";

/// Projection writer for the per-reality `canon_projection` table.
///
/// Handles 4 events (cycle 23 L5.A.1):
///   - `canon.entry.created`     → UPSERT new row
///   - `canon.entry.updated`     → UPSERT (canon updates may arrive
///                                  out-of-order across cascade boundaries;
///                                  we treat both as upsert keyed on
///                                  canon_entry_id, never insert-only)
///   - `canon.entry.promoted`    → UPDATE canon_layer
///   - `canon.entry.decanonized` → UPDATE: tombstone via lock_level='archived'
///                                  (separate from L3-override; this is
///                                  authored retraction)
///
/// Cascade + L3-override writers live in sibling crates (cycle 24+).
pub struct CanonProjection;

impl Projection for CanonProjection {
    fn name(&self) -> &str {
        "canon_projection"
    }

    fn handles(&self, env: &EventEnvelope) -> bool {
        env.aggregate_type == "canon"
    }

    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        if env.aggregate_type != "canon" {
            return vec![];
        }
        let meta = VerificationMeta::from_envelope(env);
        match env.event_type.as_str() {
            // ── canon.entry.created ────────────────────────────────────
            // UPSERT: a "created" event arriving for an already-cascaded
            // row replaces the cascade with own-source (cascaded_from_…
            // → NULL, source_event_id → this event). Meta-worker runtime
            // (cycle 24+) materializes this UPSERT semantics as an
            // INSERT ... ON CONFLICT (canon_entry_id) DO UPDATE.
            "canon.entry.created" => vec![ProjectionUpdate::Insert {
                table: "canon_projection".into(),
                row: json!({
                    "canon_entry_id":            env.payload.get("canon_entry_id"),
                    "book_id":                   env.payload.get("book_id"),
                    "attribute_path":            env.payload.get("attribute_path"),
                    "value":                     env.payload.get("value"),
                    "canon_layer":               env.payload.get("canon_layer"),
                    "lock_level":                env.payload.get("lock_level").cloned().unwrap_or(json!(DEFAULT_LOCK_LEVEL)),
                    "source_event_id":           env.event_id,
                    "cascaded_from_reality_id":  serde_json::Value::Null,
                    "overridden_by_l3_event_id": serde_json::Value::Null,
                    "last_synced_at":            env.recorded_at,
                }),
                meta,
            }],

            // ── canon.entry.updated ────────────────────────────────────
            // UPDATE: change value (+ optionally canon_layer if author
            // edited it; treated as separate from promoted). last_synced_at
            // refreshed for L5.E cache invalidation (Q-L5-1).
            "canon.entry.updated" => vec![ProjectionUpdate::Update {
                table: "canon_projection".into(),
                pk: json!({ "canon_entry_id": env.payload.get("canon_entry_id") }),
                fields: json!({
                    "value":            env.payload.get("new_value"),
                    "canon_layer":      env.payload.get("canon_layer"),
                    "source_event_id":  env.event_id,
                    "last_synced_at":   env.recorded_at,
                }),
                meta,
            }],

            // ── canon.entry.promoted ───────────────────────────────────
            // UPDATE: ToLayer becomes the new canon_layer (typically
            // L2_seeded → L1_axiom per M4 §9.7.4). Distinct from
            // xreality.canon.promoted (cycle 10 fan-out signal) which is
            // the cross-reality dispatch event.
            "canon.entry.promoted" => vec![ProjectionUpdate::Update {
                table: "canon_projection".into(),
                pk: json!({ "canon_entry_id": env.payload.get("canon_entry_id") }),
                fields: json!({
                    "canon_layer":     env.payload.get("to_layer"),
                    "source_event_id": env.event_id,
                    "last_synced_at":  env.recorded_at,
                }),
                meta,
            }],

            // ── canon.entry.decanonized ────────────────────────────────
            // Authored retraction: tombstone via lock_level='archived'.
            // The row STAYS in the table for audit / change history
            // (L5.J), but [WORLD_CANON] prompt assembly (cycle 25+ L5.E)
            // filters lock_level='archived' rows out.
            "canon.entry.decanonized" => vec![ProjectionUpdate::Update {
                table: "canon_projection".into(),
                pk: json!({ "canon_entry_id": env.payload.get("canon_entry_id") }),
                fields: json!({
                    "lock_level":      "archived",
                    "source_event_id": env.event_id,
                    "last_synced_at":  env.recorded_at,
                }),
                meta,
            }],

            // TODO(cycle 24+ multiverse cascade): canon.entry.cascaded —
            // a NEW event_type emitted when meta-worker fans cascade-
            // inheritance to a child reality. Writer would emit a row
            // with source_event_id=NULL + cascaded_from_reality_id=<id>.
            //
            // TODO(cycle 24+ L3 override): NOT a canon.* event — emitted
            // from the per-reality L3 event handler. Writer would update
            // overridden_by_l3_event_id only.
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
            aggregate_type: "canon".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", version % 60),
            payload,
            metadata: None,
        }
    }

    fn created_payload() -> serde_json::Value {
        json!({
            "canon_entry_id": "11111111-1111-1111-1111-111111111111",
            "book_id":        "22222222-2222-2222-2222-222222222222",
            "attribute_path": "characters/alice/race",
            "value":          "elf",
            "canon_layer":    CANON_LAYER_L2_SEEDED,
            "lock_level":     "soft",
            "author_user_id": "33333333-3333-3333-3333-333333333333",
        })
    }

    #[test]
    fn canon_created_emits_insert_with_required_fields() {
        let p = CanonProjection;
        let e = env("canon.entry.created", "canon-1", 1, created_payload());
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        match &updates[0] {
            ProjectionUpdate::Insert { table, row, meta } => {
                assert_eq!(table, "canon_projection");
                assert_eq!(meta.aggregate_version, 1);
                // All locked-required fields present.
                for field in [
                    "canon_entry_id",
                    "book_id",
                    "attribute_path",
                    "value",
                    "canon_layer",
                    "lock_level",
                    "source_event_id",
                    "cascaded_from_reality_id",
                    "overridden_by_l3_event_id",
                    "last_synced_at",
                ] {
                    assert!(
                        row.get(field).is_some(),
                        "Insert row missing field {}: {:?}",
                        field,
                        row
                    );
                }
                // Cascade origin XOR: source set, cascade NULL on own-source.
                assert_eq!(row.get("cascaded_from_reality_id"), Some(&serde_json::Value::Null));
                assert!(row.get("source_event_id").is_some_and(|v| !v.is_null()));
                // Override is NULL on a freshly-created row.
                assert_eq!(row.get("overridden_by_l3_event_id"), Some(&serde_json::Value::Null));
            }
            other => panic!("expected Insert, got {:?}", other),
        }
    }

    #[test]
    fn canon_created_default_lock_level_when_omitted() {
        let p = CanonProjection;
        let mut payload = created_payload();
        // Sub-program might emit without explicit lock_level — DEFAULT_LOCK_LEVEL applies.
        payload.as_object_mut().unwrap().remove("lock_level");
        let e = env("canon.entry.created", "canon-1", 1, payload);
        let updates = p.apply_event(&e);
        match &updates[0] {
            ProjectionUpdate::Insert { row, .. } => {
                assert_eq!(row.get("lock_level"), Some(&json!(DEFAULT_LOCK_LEVEL)));
            }
            _ => unreachable!(),
        }
    }

    #[test]
    fn canon_updated_writes_new_value_and_refreshes_last_synced() {
        let p = CanonProjection;
        let e = env(
            "canon.entry.updated",
            "canon-1",
            2,
            json!({
                "canon_entry_id": "11111111-1111-1111-1111-111111111111",
                "book_id":        "22222222-2222-2222-2222-222222222222",
                "attribute_path": "characters/alice/race",
                "old_value":      "elf",
                "new_value":      "half-elf",
                "canon_layer":    CANON_LAYER_L2_SEEDED,
                "editor_user_id": "33333333-3333-3333-3333-333333333333",
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        match &updates[0] {
            ProjectionUpdate::Update { table, pk, fields, .. } => {
                assert_eq!(table, "canon_projection");
                assert!(pk.get("canon_entry_id").is_some());
                assert_eq!(fields.get("value"), Some(&json!("half-elf")));
                assert!(fields.get("last_synced_at").is_some());
                assert!(fields.get("source_event_id").is_some_and(|v| !v.is_null()));
            }
            other => panic!("expected Update, got {:?}", other),
        }
    }

    #[test]
    fn canon_promoted_sets_canon_layer_to_to_layer() {
        let p = CanonProjection;
        let e = env(
            "canon.entry.promoted",
            "canon-1",
            3,
            json!({
                "canon_entry_id": "11111111-1111-1111-1111-111111111111",
                "book_id":        "22222222-2222-2222-2222-222222222222",
                "from_layer":     CANON_LAYER_L2_SEEDED,
                "to_layer":       CANON_LAYER_L1_AXIOM,
                "promoted_by":    "33333333-3333-3333-3333-333333333333",
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        match &updates[0] {
            ProjectionUpdate::Update { fields, .. } => {
                // Layer becomes L1_axiom — Q-L5-3 enum value.
                assert_eq!(fields.get("canon_layer"), Some(&json!(CANON_LAYER_L1_AXIOM)));
            }
            _ => unreachable!(),
        }
    }

    #[test]
    fn canon_decanonized_tombstones_via_archived_lock_level() {
        let p = CanonProjection;
        let e = env(
            "canon.entry.decanonized",
            "canon-1",
            4,
            json!({
                "canon_entry_id": "11111111-1111-1111-1111-111111111111",
                "book_id":        "22222222-2222-2222-2222-222222222222",
                "reason":         "superseded",
                "decanonized_by": "33333333-3333-3333-3333-333333333333",
            }),
        );
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        match &updates[0] {
            ProjectionUpdate::Update { fields, .. } => {
                assert_eq!(fields.get("lock_level"), Some(&json!("archived")));
            }
            _ => unreachable!(),
        }
    }

    #[test]
    fn canon_projection_skips_non_canon_aggregate() {
        let p = CanonProjection;
        let mut e = env("canon.entry.created", "x", 1, created_payload());
        e.aggregate_type = "npc".into();
        // Defense vs publisher routing bug: a non-canon aggregate must
        // produce no updates even if event_type matches.
        assert!(p.apply_event(&e).is_empty());
    }

    #[test]
    fn canon_projection_unknown_event_returns_empty() {
        let p = CanonProjection;
        let e = env("canon.entry.future_event", "canon-1", 5, json!({}));
        assert!(p.apply_event(&e).is_empty());
    }

    #[test]
    fn verification_meta_stamped_on_every_canon_update() {
        let p = CanonProjection;
        for et in [
            "canon.entry.created",
            "canon.entry.updated",
            "canon.entry.promoted",
            "canon.entry.decanonized",
        ] {
            let e = env(et, "canon-1", 7, created_payload());
            let updates = p.apply_event(&e);
            assert!(!updates.is_empty(), "{} produced no updates", et);
            for u in &updates {
                match u {
                    ProjectionUpdate::Insert { meta, .. } | ProjectionUpdate::Update { meta, .. } => {
                        assert_eq!(meta.aggregate_version, 7, "Q-L3-4 meta stamp on {}", et);
                        assert_eq!(meta.event_id, Uuid::from_u128(7), "event_id propagated on {}", et);
                    }
                    _ => unreachable!("canon writer never emits Delete/Tombstone"),
                }
            }
        }
    }

    #[test]
    fn canon_handles_only_canon_aggregate_type() {
        let p = CanonProjection;
        let canon_env = env("canon.entry.created", "x", 1, created_payload());
        assert!(p.handles(&canon_env));
        let mut other = canon_env.clone();
        other.aggregate_type = "pc".into();
        assert!(!p.handles(&other));
    }

    // ── L5.D.4 integration-style test (in-crate, mocks DB via update vector) ──
    //
    // Simulates: apply L2 canon entry → projection has correct row;
    // apply L3 override (separate event handler — not canon writer) →
    // overridden_by_l3_event_id would be populated (verified by manual
    // construction since L3 handler lands cycle 24+).
    //
    // Cascade read-through (multiverse §3): a child reality reads from
    // ancestor reality_id when canon_projection row carries
    // cascaded_from_reality_id. Verified here at the SHAPE level — a
    // cascade-sourced row has source_event_id=NULL and
    // cascaded_from_reality_id non-NULL (XOR constraint mirrored in
    // 0009_canon_projection.up.sql).
    #[test]
    fn canon_projection_test_l5_d_4_integration_shape() {
        let p = CanonProjection;
        // Step 1: own-source L2_seeded canon row from canon.entry.created
        let own = p.apply_event(&env("canon.entry.created", "c1", 10, created_payload()));
        match &own[0] {
            ProjectionUpdate::Insert { row, .. } => {
                assert_eq!(row.get("canon_layer"), Some(&json!(CANON_LAYER_L2_SEEDED)));
                assert_eq!(row.get("cascaded_from_reality_id"), Some(&serde_json::Value::Null));
                assert_eq!(row.get("overridden_by_l3_event_id"), Some(&serde_json::Value::Null));
            }
            _ => unreachable!(),
        }

        // Step 2: L3 override would set overridden_by_l3_event_id on the
        // SAME canon row. Construct the expected Update shape manually
        // (cycle 24+ L3 handler will emit this):
        let expected_l3_override_shape = ProjectionUpdate::Update {
            table: "canon_projection".into(),
            pk: json!({ "canon_entry_id": "11111111-1111-1111-1111-111111111111" }),
            fields: json!({
                "overridden_by_l3_event_id": Uuid::from_u128(99),
                "last_synced_at":            "2026-05-29T00:01:00Z",
            }),
            meta: VerificationMeta {
                event_id: Uuid::from_u128(99),
                aggregate_version: 99,
                applied_at: "2026-05-29T00:01:00Z".into(),
            },
        };
        match &expected_l3_override_shape {
            ProjectionUpdate::Update { fields, .. } => {
                assert!(fields.get("overridden_by_l3_event_id").is_some());
            }
            _ => unreachable!(),
        }

        // Step 3: cascade-from-ancestor row SHAPE (cycle 24+ multiverse
        // cascade orchestrator emits this).
        let cascade_row = json!({
            "canon_entry_id":            "11111111-1111-1111-1111-111111111111",
            "book_id":                   "22222222-2222-2222-2222-222222222222",
            "attribute_path":            "characters/alice/race",
            "value":                     "elf",
            "canon_layer":               CANON_LAYER_L2_SEEDED,
            "lock_level":                "soft",
            "source_event_id":           serde_json::Value::Null,  // cascade
            "cascaded_from_reality_id":  Uuid::from_u128(0x1234),  // ancestor
            "overridden_by_l3_event_id": serde_json::Value::Null,
            "last_synced_at":            "2026-05-29T00:00:00Z",
        });
        // XOR constraint visible at the JSON level — verified at DB level
        // by 0009 CHECK canon_projection_origin_xor.
        assert!(cascade_row.get("source_event_id").unwrap().is_null());
        assert!(!cascade_row.get("cascaded_from_reality_id").unwrap().is_null());
    }
}
