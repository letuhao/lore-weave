//! W4.6 / D-C2-REFERENCE-PROJECTOR — the independent projection oracle.
//!
//! The C2 golden battery is a same-author regression-lock: its fixtures are
//! authored from the same design the arms implement, so they pin the contract
//! but cannot DISAGREE with the arms on a real bug. This crate is the independent
//! oracle that can — built from TWO sources that are NOT `crates/projections/*`:
//!
//!   1. the **event contract** — payload field names (mirrors
//!      `tests/workload-gen/internal/schema` Specs / `contracts/events`).
//!   2. the **table DDL** — projection columns + PKs
//!      (`contracts/migrations/per_reality/0006_projections.up.sql`,
//!      `0009_canon_projection.up.sql`).
//!
//! It has two layers:
//!
//! * [`check_conformance`] — a CONFORMANCE oracle over EVERY production update for
//!   all 20 events: the target table exists + is a contract-allowed target for the
//!   event with the right KIND; every written column EXISTS in the DDL; the `pk`
//!   is EXACTLY the table's PRIMARY KEY; and every payload field whose name is a
//!   real column carries the payload VALUE (the direct-field check — the wrong-key
//!   bug class). This is grounded in the DDL+contract, not the arms, so it does NOT
//!   agree-by-construction.
//! * [`reference_project`] — a from-DESIGN REPRODUCTION reference for the highest
//!   -value arms (npc/pc relationship + canon), used as a deeper differential vs
//!   the production output.
//!
//! ## Honest scope (plan-review)
//! The conformance oracle does NOT verify literal / renamed / envelope-derived
//! VALUES (e.g. `spawn_region_id`→`current_region_id`, `status:"active"`,
//! `reality_id` from the envelope) — those need the design intent the arm encodes,
//! so they are out of the independent surface. The reproduction reference covers a
//! few arms fully; first-run agreement there is (like C2) a regression-lock, and
//! the independent VALUE is a FUTURE arm change (or a present mismatch) it catches.
//!
//! ## Coverage boundaries (impl /review-impl)
//! * **Dropped field** — the direct-field check fires only when production WROTE a
//!   same-named column; an arm that OMITS a required column passes (Update writes
//!   subsets by design, so the oracle cannot require all fields). Not covered.
//! * **Column-set DDL drift** — `table_schema` is hand-mirrored from the DDL. A new
//!   column/table fails LOUD (production writes it → `unknown-column`/`unknown-table`
//!   → the conformance test fails, forcing an update). The [`KNOWN_TABLES`] drift
//!   guard catches a stale *table*. A column REMOVAL/rename not mirrored here is a
//!   silent residual (would need DDL parsing or a shared schema source) →
//!   `D-PROJREF-COLUMN-DDL-DRIFT`.
//! * **Arm-set completeness** — the differential harness runs a fixed production
//!   arm-set over the golden fixtures; a new arm+event with no fixture is unchecked
//!   (shared with the C2 `full_delta` battery).

use dp_kernel::{EventEnvelope, ProjectionUpdate, VerificationMeta};
use serde_json::{Value, json};
use std::collections::BTreeSet;

// ───────────────────────────── schema model (from the DDL) ─────────────────────

/// VerificationMeta columns the writer stamps on every L3.A row (Q-L3-4). Valid
/// on every projection table in addition to its projection-specific columns.
const META_COLS: &[&str] = &[
    "event_id",
    "aggregate_version",
    "applied_at",
    "last_verified_event_version",
    "last_verified_at",
];

/// The 11 L3.A projection tables the schema model knows. The differential harness
/// asserts this set equals the tables production actually emits across the golden
/// fixtures (the table-set drift guard — catches a stale or missing table).
pub const KNOWN_TABLES: &[&str] = &[
    "pc_projection",
    "pc_inventory_projection",
    "pc_relationship_projection",
    "npc_projection",
    "npc_session_memory_projection",
    "npc_pc_relationship_projection",
    "npc_session_memory_embedding",
    "region_projection",
    "session_participants",
    "world_kv_projection",
    "canon_projection",
];

/// (pk columns, projection-specific columns) for a projection table — authored
/// from the per-reality DDL. Returns None for a non-projection / unknown table.
fn table_schema(table: &str) -> Option<(&'static [&'static str], &'static [&'static str])> {
    Some(match table {
        "pc_projection" => (
            &["pc_id"],
            &[
                "pc_id",
                "user_id",
                "name",
                "current_region_id",
                "status",
                "stats",
                "last_event_version",
            ],
        ),
        "pc_inventory_projection" => (
            &["pc_id", "item_code"],
            &[
                "pc_id",
                "item_code",
                "quantity",
                "metadata",
                "origin_reality_id",
            ],
        ),
        "pc_relationship_projection" => (
            &["pc_id", "other_entity_type", "other_entity_id"],
            &[
                "pc_id",
                "other_entity_type",
                "other_entity_id",
                "score",
                "labels",
            ],
        ),
        "npc_projection" => (
            &["npc_id"],
            &[
                "npc_id",
                "glossary_entity_id",
                "current_region_id",
                "mood",
                "core_beliefs",
                "flexible_state",
                "last_event_version",
            ],
        ),
        "npc_session_memory_projection" => (
            &["npc_id", "session_id"],
            &[
                "npc_id",
                "session_id",
                "reality_id",
                "aggregate_id",
                "summary",
                "facts",
                "session_started_at",
                "session_ended_at",
                "interaction_count",
                "archive_status",
            ],
        ),
        "npc_pc_relationship_projection" => (
            &["npc_id", "other_entity_id"],
            &[
                "npc_id",
                "other_entity_id",
                "other_entity_type",
                "reality_id",
                "trust_level",
                "familiarity_count",
                "last_session_id",
                "relationship_labels",
            ],
        ),
        "npc_session_memory_embedding" => (
            &["npc_id", "session_id"],
            &["npc_id", "session_id", "embedding", "content_hash"],
        ),
        "region_projection" => (
            &["region_id"],
            &[
                "region_id",
                "code",
                "display_name",
                "description",
                "parent_region_id",
                "exits",
                "floor_items",
                "ambient_state",
                "last_event_version",
            ],
        ),
        "session_participants" => (
            &["session_id", "participant_type", "participant_id"],
            &[
                "session_id",
                "participant_type",
                "participant_id",
                "reality_id",
                "joined_at",
                "left_at",
            ],
        ),
        "world_kv_projection" => (
            &["key"],
            &["key", "value", "last_event_version", "updated_at"],
        ),
        "canon_projection" => (
            &["canon_entry_id"],
            &[
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
            ],
        ),
        _ => return None,
    })
}

// ───────────────────────── event contract (target table + kind) ────────────────

/// The update KIND an event's projection emits, by design.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Kind {
    Insert,
    Update,
    Upsert,
    Delete,
}

impl Kind {
    fn of(u: &ProjectionUpdate) -> Kind {
        match u {
            ProjectionUpdate::Insert { .. } => Kind::Insert,
            ProjectionUpdate::Update { .. } => Kind::Update,
            ProjectionUpdate::Upsert { .. } => Kind::Upsert,
            ProjectionUpdate::Delete { .. } => Kind::Delete,
            ProjectionUpdate::Tombstone { .. } => Kind::Delete, // no projection emits this
        }
    }
}

/// The (table, kind) pairs an event legitimately projects to, authored from the
/// L3 design (which arm fans out where). The conformance check asserts production
/// emits EXACTLY this set (catching a wrong/extra/missing target or wrong kind).
fn event_targets(event_type: &str) -> Option<&'static [(&'static str, Kind)]> {
    Some(match event_type {
        "npc.created" => &[("npc_projection", Kind::Insert)],
        "npc.said" => &[
            ("npc_projection", Kind::Update),
            ("npc_session_memory_projection", Kind::Update),
        ],
        "npc.relationship_changed" => &[("npc_pc_relationship_projection", Kind::Upsert)],
        "npc.memory_embedded" => &[("npc_session_memory_embedding", Kind::Insert)],
        "session.started" => &[("npc_session_memory_projection", Kind::Insert)],
        "session.ended" => &[("npc_session_memory_projection", Kind::Update)],
        "session.participant_joined" => &[("session_participants", Kind::Insert)],
        "session.participant_left" => &[("session_participants", Kind::Update)],
        "pc.spawned" => &[
            ("pc_projection", Kind::Insert),
            ("pc_inventory_projection", Kind::Insert),
        ],
        "pc.moved" => &[("pc_projection", Kind::Update)],
        "pc.item_acquired" => &[("pc_inventory_projection", Kind::Insert)],
        "pc.relationship_changed" => &[("pc_relationship_projection", Kind::Upsert)],
        "region.created" => &[("region_projection", Kind::Insert)],
        "region.ambient_changed" => &[("region_projection", Kind::Update)],
        "world.kv_set" => &[("world_kv_projection", Kind::Insert)],
        "world.kv_unset" => &[("world_kv_projection", Kind::Delete)],
        "canon.entry.created" => &[("canon_projection", Kind::Insert)],
        "canon.entry.updated" => &[("canon_projection", Kind::Update)],
        "canon.entry.promoted" => &[("canon_projection", Kind::Update)],
        "canon.entry.decanonized" => &[("canon_projection", Kind::Update)],
        _ => return None,
    })
}

// ──────────────────────────── conformance oracle ───────────────────────────────

/// One conformance violation found in a production update.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Violation {
    pub rule: &'static str,
    pub detail: String,
}

fn v(rule: &'static str, detail: String) -> Violation {
    Violation { rule, detail }
}

/// Pull (pk, written-columns) out of an update. Insert writes `row`; Update/Upsert
/// write `fields` (+ the pk columns it also targets, carried in `pk`); Delete only
/// names the pk. The written-column keys strip a trailing `_increment` (a
/// pseudo-field whose base column is what's mutated, e.g. interaction_count).
fn obj_keys(v: &Value) -> BTreeSet<String> {
    match v {
        Value::Object(m) => m.keys().cloned().collect(),
        _ => BTreeSet::new(),
    }
}

fn base_col(k: &str) -> &str {
    k.strip_suffix("_increment").unwrap_or(k)
}

/// check_conformance validates EVERY production update against the DDL + contract.
/// Returns the (possibly empty) list of violations. An empty list means the update
/// set is schema- and contract-conformant; it does NOT assert value-correctness of
/// renamed / literal / envelope-derived fields (out of the independent surface).
pub fn check_conformance(env: &EventEnvelope, updates: &[ProjectionUpdate]) -> Vec<Violation> {
    let mut out = Vec::new();

    // 1. (table, kind) set must equal the contract's targets for this event.
    let Some(expected) = event_targets(&env.event_type) else {
        out.push(v(
            "unknown-event",
            format!("no contract target for event_type {:?}", env.event_type),
        ));
        return out;
    };
    let got: BTreeSet<(String, Kind)> = updates
        .iter()
        .map(|u| (u.table().to_string(), Kind::of(u)))
        .collect();
    let want: BTreeSet<(String, Kind)> =
        expected.iter().map(|(t, k)| (t.to_string(), *k)).collect();
    for g in &got {
        if !want.contains(g) {
            out.push(v(
                "unexpected-target",
                format!(
                    "{} emitted ({}, {:?}) which is not a contract target",
                    env.event_type, g.0, g.1
                ),
            ));
        }
    }
    for w in &want {
        if !got.contains(w) {
            out.push(v(
                "missing-target",
                format!(
                    "{} did NOT emit the contract target ({}, {:?})",
                    env.event_type, w.0, w.1
                ),
            ));
        }
    }

    // 2-4. Per-update structural checks (table exists, columns ∈ DDL, pk == PK).
    let payload = env.payload.as_object();
    for u in updates {
        let table = u.table();
        let Some((pk, cols)) = table_schema(table) else {
            out.push(v(
                "unknown-table",
                format!("{table:?} is not a projection table"),
            ));
            continue;
        };
        let allowed: BTreeSet<&str> = cols
            .iter()
            .copied()
            .chain(META_COLS.iter().copied())
            .collect();

        // Written columns must all be real DDL columns (base, sans _increment).
        let (written, pk_obj): (BTreeSet<String>, Option<&Value>) = match u {
            ProjectionUpdate::Insert { row, .. } => (obj_keys(row), None),
            ProjectionUpdate::Update { fields, pk, .. }
            | ProjectionUpdate::Upsert { fields, pk, .. } => (obj_keys(fields), Some(pk)),
            ProjectionUpdate::Delete { pk, .. } => (BTreeSet::new(), Some(pk)),
            ProjectionUpdate::Tombstone { pk, .. } => (BTreeSet::new(), Some(pk)),
        };
        for w in &written {
            if !allowed.contains(base_col(w)) {
                out.push(v(
                    "unknown-column",
                    format!("{table}.{w} is not a column of {table} (DDL)"),
                ));
            }
        }

        // pk must be EXACTLY the table's primary key. Insert carries the pk
        // columns INSIDE its row (no separate pk), so check presence there.
        let pk_set: BTreeSet<&str> = pk.iter().copied().collect();
        match u {
            ProjectionUpdate::Insert { row, .. } => {
                let rk = obj_keys(row);
                for c in &pk_set {
                    if !rk.contains(*c) {
                        out.push(v(
                            "insert-missing-pk-column",
                            format!("{table} Insert row is missing pk column {c}"),
                        ));
                    }
                }
            }
            _ => {
                if let Some(p) = pk_obj {
                    let got_pk: BTreeSet<&str> = match p {
                        Value::Object(m) => m.keys().map(|s| s.as_str()).collect(),
                        _ => BTreeSet::new(),
                    };
                    if got_pk != pk_set {
                        out.push(v(
                            "wrong-pk",
                            format!("{table} pk {:?} != table PRIMARY KEY {:?}", got_pk, pk_set),
                        ));
                    }
                }
            }
        }

        // 5. Direct-field value check (the wrong-key bug class): for any payload
        // key that IS a column of this table and that production wrote, the written
        // value MUST equal the payload value. Renamed/literal/envelope fields are
        // NOT checked (out of the independent surface).
        if let Some(pl) = payload {
            let body = match u {
                ProjectionUpdate::Insert { row, .. } => row.as_object(),
                ProjectionUpdate::Update { fields, .. }
                | ProjectionUpdate::Upsert { fields, .. } => fields.as_object(),
                _ => None,
            };
            if let Some(body) = body {
                for (k, pv) in pl {
                    if allowed.contains(k.as_str()) {
                        if let Some(wrote) = body.get(k) {
                            if wrote != pv {
                                out.push(v(
                                    "direct-field-mismatch",
                                    format!(
                                        "{table}.{k}: wrote {wrote} but payload.{k} = {pv} (wrong-key read?)"
                                    ),
                                ));
                            }
                        }
                    }
                }
            }
        }
    }

    out
}

// ──────────────────── reproduction reference (relationship + canon) ─────────────

/// A from-DESIGN reproduction of the projection delta for the highest-value arms
/// (npc/pc relationship + canon). Returns `Some(updates)` for a covered event,
/// `None` for an event this reference does not reproduce (the differential harness
/// skips those — they are covered by the conformance oracle). Authored from the
/// event contract + table DDL + the documented L3 design, NOT the arm code.
pub fn reference_project(env: &EventEnvelope) -> Option<Vec<ProjectionUpdate>> {
    let meta = VerificationMeta::from_envelope(env);
    let p = env.payload.as_object()?;
    let get = |k: &str| p.get(k).cloned().unwrap_or(Value::Null);

    Some(match env.event_type.as_str() {
        // npc.relationship_changed → UPSERT npc_pc_relationship_projection. The row
        // is keyed (npc_id = the aggregate, other_entity_id). session_id maps to the
        // DDL column last_session_id ("the session it last changed in"); labels →
        // relationship_labels; reality_id comes from the envelope.
        "npc.relationship_changed" => vec![ProjectionUpdate::Upsert {
            table: "npc_pc_relationship_projection".into(),
            pk: json!({ "npc_id": env.aggregate_id, "other_entity_id": get("other_entity_id") }),
            fields: json!({
                "other_entity_type": get("other_entity_type"),
                "reality_id": env.reality_id,
                "trust_level": get("trust_level"),
                "familiarity_count": get("familiarity_count"),
                "last_session_id": get("session_id"),
                "relationship_labels": get("labels"),
            }),
            meta,
        }],
        // pc.relationship_changed → UPSERT pc_relationship_projection, keyed
        // (pc_id, other_entity_type, other_entity_id); score + labels direct.
        "pc.relationship_changed" => vec![ProjectionUpdate::Upsert {
            table: "pc_relationship_projection".into(),
            pk: json!({
                "pc_id": env.aggregate_id,
                "other_entity_type": get("other_entity_type"),
                "other_entity_id": get("other_entity_id"),
            }),
            fields: json!({ "score": get("score"), "labels": get("labels") }),
            meta,
        }],
        // canon.entry.created → INSERT canon_projection. source_event_id = the
        // writing event; cascaded_from_reality_id / overridden_by_l3_event_id are
        // null on a direct authored entry; last_synced_at = the sync time (applied).
        "canon.entry.created" => vec![ProjectionUpdate::Insert {
            table: "canon_projection".into(),
            row: json!({
                "canon_entry_id": get("canon_entry_id"),
                "book_id": get("book_id"),
                "attribute_path": get("attribute_path"),
                "value": get("value"),
                "canon_layer": get("canon_layer"),
                "lock_level": get("lock_level"),
                "source_event_id": env.event_id,
                "cascaded_from_reality_id": Value::Null,
                "overridden_by_l3_event_id": Value::Null,
                "last_synced_at": env.recorded_at,
            }),
            meta,
        }],
        // canon.entry.updated → UPDATE value + canon_layer; re-stamp source + sync.
        "canon.entry.updated" => vec![ProjectionUpdate::Update {
            table: "canon_projection".into(),
            pk: json!({ "canon_entry_id": get("canon_entry_id") }),
            fields: json!({
                "value": get("new_value"),
                "canon_layer": get("canon_layer"),
                "source_event_id": env.event_id,
                "last_synced_at": env.recorded_at,
            }),
            meta,
        }],
        // canon.entry.promoted → UPDATE canon_layer (to_layer); re-stamp.
        "canon.entry.promoted" => vec![ProjectionUpdate::Update {
            table: "canon_projection".into(),
            pk: json!({ "canon_entry_id": get("canon_entry_id") }),
            fields: json!({
                "canon_layer": get("to_layer"),
                "source_event_id": env.event_id,
                "last_synced_at": env.recorded_at,
            }),
            meta,
        }],
        // canon.entry.decanonized → UPDATE lock_level = archived; re-stamp.
        "canon.entry.decanonized" => vec![ProjectionUpdate::Update {
            table: "canon_projection".into(),
            pk: json!({ "canon_entry_id": get("canon_entry_id") }),
            fields: json!({
                "lock_level": "archived",
                "source_event_id": env.event_id,
                "last_synced_at": env.recorded_at,
            }),
            meta,
        }],
        _ => return None,
    })
}

/// The event types [`reference_project`] reproduces (for the anti-drift coverage
/// test in the differential harness).
pub const REPRODUCED_EVENTS: &[&str] = &[
    "npc.relationship_changed",
    "pc.relationship_changed",
    "canon.entry.created",
    "canon.entry.updated",
    "canon.entry.promoted",
    "canon.entry.decanonized",
];

/// Helper for tests: turn a serde_json object Value into a sorted key set.
pub fn columns_of(v: &Value) -> BTreeSet<String> {
    match v {
        Value::Object(m) => m.keys().cloned().collect(),
        _ => BTreeSet::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// KNOWN_TABLES and table_schema must agree: every known table resolves, an
    /// unknown one does not. (The table-set-vs-production drift guard lives in the
    /// differential harness, which has the production arms as a dev-dependency.)
    #[test]
    fn known_tables_resolve_and_unknowns_do_not() {
        for t in KNOWN_TABLES {
            assert!(
                table_schema(t).is_some(),
                "KNOWN_TABLES entry {t} has no schema"
            );
        }
        assert!(table_schema("not_a_projection").is_none());
        // The pk columns of each table are a subset of its column list.
        for t in KNOWN_TABLES {
            let (pk, cols) = table_schema(t).unwrap();
            for k in pk {
                assert!(
                    cols.contains(k),
                    "{t}: pk column {k} not in the column list"
                );
            }
        }
    }
}
