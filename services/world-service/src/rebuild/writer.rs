//! Generic sqlx [`ProjectionWriter`] that applies [`ProjectionUpdate`]s to ONE
//! target projection table.
//!
//! ## Why generic (no per-table schema map)
//!
//! Every variant is applied via `jsonb_populate_record(NULL::<table>, $json)`,
//! which casts each JSON field to its column's real type using the table's
//! implicit composite type. So a single code path handles all 10+ L3.A tables
//! with no hand-written column lists. The only static knowledge is the
//! table-NAME allowlist (`super::is_known_projection_table`) — the name is
//! interpolated into SQL, so it must be validated; column names taken from the
//! update's JSON keys are additionally identifier-checked (defense in depth).
//!
//! ## Apply semantics
//!
//! `apply_batch` runs all target-table updates for one envelope-batch in a
//! SINGLE TX (the trait contract). A failed batch rolls back atomically, and
//! the rebuilder does NOT advance its checkpoint, so a retry re-replays the
//! same batch cleanly against the rolled-back (empty) rows — no `ON CONFLICT`
//! needed for the TRUNCATE-then-full-replay model. A genuine duplicate-key
//! INSERT therefore fails loud (a projection/double-event bug), which is the
//! correct posture for a recovery tool.

use std::sync::Arc;

use dp_kernel::{ProjectionUpdate, VerificationMeta};
use rebuilder::ProjectionWriter;
use serde_json::{Map, Value};
use sqlx::PgPool;
use tokio::runtime::Handle;

use super::is_known_projection_table;

/// Applies projection updates for exactly one `target_table` via sqlx.
#[derive(Debug)]
pub struct SqlxProjectionWriter {
    pool: Arc<PgPool>,
    handle: Handle,
    target_table: String,
}

impl SqlxProjectionWriter {
    /// Bind the per-reality pool + DB runtime handle. `target_table` MUST be an
    /// allowlisted L3.A projection table; otherwise an error is returned (the
    /// name is interpolated into SQL).
    pub fn new(pool: Arc<PgPool>, handle: Handle, target_table: String) -> Result<Self, String> {
        if !is_known_projection_table(&target_table) {
            return Err(format!(
                "rebuilder: unknown projection table {target_table:?} (not in the L3.A allowlist)"
            ));
        }
        Ok(Self {
            pool,
            handle,
            target_table,
        })
    }
}

/// Build the (SQL, $1 payload) for one update targeting `target_table`. Pure —
/// no DB access — so a malformed update aborts the batch before any statement
/// runs, and the SQL shape is unit-testable without a pool. `target_table` is
/// assumed already allowlisted (the caller validated it).
fn build_stmt(target_table: &str, update: &ProjectionUpdate) -> Result<(String, Value), String> {
    let t = target_table; // allowlisted ⇒ safe to interpolate
    match update {
        ProjectionUpdate::Insert { row, meta, .. } => {
            let mut payload = as_object(row, "Insert.row")?;
            merge_meta(&mut payload, meta);
            let sql = format!(
                "INSERT INTO {t} SELECT * FROM jsonb_populate_record(NULL::{t}, $1::jsonb)"
            );
            Ok((sql, Value::Object(payload)))
        }
        ProjectionUpdate::Update {
            pk, fields, meta, ..
        } => {
            let pk_map = as_object(pk, "Update.pk")?;
            let field_map = as_object(fields, "Update.fields")?;
            if pk_map.is_empty() {
                return Err("rebuilder: Update.pk is empty".into());
            }
            let mut payload = pk_map.clone();
            for (k, v) in &field_map {
                payload.insert(k.clone(), v.clone());
            }
            merge_meta(&mut payload, meta);

            let mut set_cols: Vec<&str> = field_map.keys().map(String::as_str).collect();
            set_cols.extend(["event_id", "aggregate_version", "applied_at"]);
            let set_clause = build_assignment_list(&set_cols, ", ")?;
            let where_clause = build_pk_predicate(&pk_map)?;
            let sql = format!(
                "WITH r AS (SELECT * FROM jsonb_populate_record(NULL::{t}, $1::jsonb)) \
                     UPDATE {t} AS t SET {set_clause} FROM r WHERE {where_clause}"
            );
            Ok((sql, Value::Object(payload)))
        }
        ProjectionUpdate::Delete { pk, .. } => {
            let pk_map = as_object(pk, "Delete.pk")?;
            if pk_map.is_empty() {
                return Err("rebuilder: Delete.pk is empty".into());
            }
            let where_clause = build_pk_predicate(&pk_map)?;
            let sql = format!(
                "WITH r AS (SELECT * FROM jsonb_populate_record(NULL::{t}, $1::jsonb)) \
                     DELETE FROM {t} AS t USING r WHERE {where_clause}"
            );
            Ok((sql, Value::Object(pk_map)))
        }
        ProjectionUpdate::Tombstone { .. } => Err(
            "rebuilder: Tombstone updates are not supported by the generic writer \
                 (no V1 projection emits them; wire an explicit handler if one ever does)"
                .into(),
        ),
    }
}

impl ProjectionWriter for SqlxProjectionWriter {
    fn apply_batch(&self, updates: &[ProjectionUpdate]) -> Result<(), String> {
        // Build every statement first so a malformed update aborts before the TX.
        let mut stmts: Vec<(String, Value)> = Vec::new();
        for u in updates {
            if u.table() != self.target_table {
                continue; // rebuilding ONE table: drop other projections' output
            }
            stmts.push(build_stmt(&self.target_table, u)?);
        }
        if stmts.is_empty() {
            return Ok(());
        }
        let pool = self.pool.clone();
        self.handle.block_on(async move {
            let mut tx = pool
                .begin()
                .await
                .map_err(|e| format!("rebuilder: begin tx: {e}"))?;
            for (sql, payload) in &stmts {
                sqlx::query(sql)
                    .bind(payload)
                    .execute(&mut *tx)
                    .await
                    .map_err(|e| format!("rebuilder: apply [{sql}]: {e}"))?;
            }
            tx.commit()
                .await
                .map_err(|e| format!("rebuilder: commit: {e}"))
        })
    }
}

/// Require a JSON object; project name into the error for diagnosis.
fn as_object(v: &Value, what: &str) -> Result<Map<String, Value>, String> {
    match v {
        Value::Object(m) => Ok(m.clone()),
        other => Err(format!(
            "rebuilder: {what} must be a JSON object, got {}",
            kind_of(other)
        )),
    }
}

fn kind_of(v: &Value) -> &'static str {
    match v {
        Value::Null => "null",
        Value::Bool(_) => "bool",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

/// Stamp the VerificationMeta columns (Q-L3-4 set a) into the payload.
fn merge_meta(map: &mut Map<String, Value>, meta: &VerificationMeta) {
    map.insert("event_id".into(), Value::String(meta.event_id.to_string()));
    map.insert(
        "aggregate_version".into(),
        Value::Number(meta.aggregate_version.into()),
    );
    map.insert("applied_at".into(), Value::String(meta.applied_at.clone()));
}

/// `col = r.col, ...` for an UPDATE SET list. Validates every identifier.
fn build_assignment_list(cols: &[&str], sep: &str) -> Result<String, String> {
    let mut parts = Vec::with_capacity(cols.len());
    for c in cols {
        ensure_ident(c)?;
        parts.push(format!("{c} = r.{c}"));
    }
    Ok(parts.join(sep))
}

/// `t.pk = r.pk AND ...` for the PK match. Validates every identifier.
fn build_pk_predicate(pk: &Map<String, Value>) -> Result<String, String> {
    let mut parts = Vec::with_capacity(pk.len());
    for c in pk.keys() {
        ensure_ident(c)?;
        parts.push(format!("t.{c} = r.{c}"));
    }
    Ok(parts.join(" AND "))
}

/// Reject anything that is not a lowercase snake_case SQL identifier. Column
/// names originate from trusted projection code, but the rebuilder interpolates
/// them into DDL-adjacent SQL, so we validate defensively.
fn ensure_ident(s: &str) -> Result<(), String> {
    let ok = !s.is_empty()
        && s.len() <= 63
        && s.bytes()
            .enumerate()
            .all(|(i, b)| b == b'_' || b.is_ascii_lowercase() || (i > 0 && b.is_ascii_digit()));
    if ok {
        Ok(())
    } else {
        Err(format!("rebuilder: unsafe column identifier {s:?}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use uuid::Uuid;

    fn meta() -> VerificationMeta {
        VerificationMeta {
            event_id: Uuid::from_u128(1),
            aggregate_version: 7,
            applied_at: "2026-06-03T10:00:00.000000Z".into(),
        }
    }

    #[test]
    fn insert_sql_uses_jsonb_populate_record() {
        let u = ProjectionUpdate::Insert {
            table: "pc_projection".into(),
            row: json!({"pc_id": Uuid::from_u128(2).to_string(), "name": "Aria"}),
            meta: meta(),
        };
        let (sql, payload) = build_stmt("pc_projection", &u).unwrap();
        assert_eq!(
            sql,
            "INSERT INTO pc_projection SELECT * FROM jsonb_populate_record(NULL::pc_projection, $1::jsonb)"
        );
        // meta stamped into payload
        assert_eq!(payload["event_id"], json!(Uuid::from_u128(1).to_string()));
        assert_eq!(payload["aggregate_version"], json!(7));
        assert_eq!(payload["name"], json!("Aria"));
    }

    #[test]
    fn update_sql_sets_fields_plus_meta_and_pk_where() {
        let u = ProjectionUpdate::Update {
            table: "pc_projection".into(),
            pk: json!({"pc_id": Uuid::from_u128(2).to_string()}),
            fields: json!({"last_event_version": 9}),
            meta: meta(),
        };
        let (sql, payload) = build_stmt("pc_projection", &u).unwrap();
        assert!(sql.contains("UPDATE pc_projection AS t SET"), "{sql}");
        assert!(
            sql.contains("last_event_version = r.last_event_version"),
            "{sql}"
        );
        assert!(sql.contains("event_id = r.event_id"), "{sql}");
        assert!(sql.contains("WHERE t.pc_id = r.pc_id"), "{sql}");
        assert_eq!(payload["last_event_version"], json!(9));
        assert_eq!(payload["pc_id"], json!(Uuid::from_u128(2).to_string()));
    }

    #[test]
    fn delete_sql_uses_pk_predicate() {
        let u = ProjectionUpdate::Delete {
            table: "session_participants".into(),
            pk: json!({"session_id": Uuid::from_u128(3).to_string(), "participant_type": "pc", "participant_id": Uuid::from_u128(4).to_string()}),
        };
        let (sql, _) = build_stmt("session_participants", &u).unwrap();
        assert!(sql.starts_with("WITH r AS"), "{sql}");
        assert!(
            sql.contains("DELETE FROM session_participants AS t USING r WHERE"),
            "{sql}"
        );
        assert!(sql.contains("t.session_id = r.session_id"), "{sql}");
    }

    #[test]
    fn tombstone_is_unsupported() {
        let u = ProjectionUpdate::Tombstone {
            table: "pc_projection".into(),
            pk: json!({"pc_id": "x"}),
            meta: meta(),
        };
        assert!(
            build_stmt("pc_projection", &u)
                .unwrap_err()
                .contains("Tombstone")
        );
    }

    #[test]
    fn rejects_non_object_row() {
        let u = ProjectionUpdate::Insert {
            table: "pc_projection".into(),
            row: json!([1, 2, 3]),
            meta: meta(),
        };
        assert!(
            build_stmt("pc_projection", &u)
                .unwrap_err()
                .contains("must be a JSON object")
        );
    }

    #[test]
    fn rejects_unsafe_pk_identifier() {
        let mut pk = Map::new();
        pk.insert("pc_id; DROP TABLE x".into(), json!("1"));
        assert!(build_pk_predicate(&pk).is_err());
    }
}
