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

/// One prepared statement: its SQL, the `$1` jsonb payload, and any positional
/// increment values bound as `$2..`. A `<col>_increment` pseudo-field cannot
/// ride in the jsonb record (it is not a real column), so its value is bound
/// separately and the SET clause becomes `col = COALESCE(t.col, 0) + $N`.
#[derive(Debug)]
struct Stmt {
    sql: String,
    payload: Value,
    increments: Vec<i64>,
}

impl Stmt {
    /// True when this statement is an increment that MUST hit an existing row —
    /// a 0-rows result then means a cross-aggregate ordering bug or a data gap.
    fn expect_row(&self) -> bool {
        !self.increments.is_empty()
    }
}

/// Build the statement for one update targeting `target_table`. Pure — no DB
/// access — so a malformed update aborts the batch before any statement runs,
/// and the SQL shape is unit-testable without a pool. `target_table` is assumed
/// already allowlisted (the caller validated it).
fn build_stmt(target_table: &str, update: &ProjectionUpdate) -> Result<Stmt, String> {
    let t = target_table; // allowlisted ⇒ safe to interpolate
    match update {
        ProjectionUpdate::Insert { row, meta, .. } => {
            let mut payload = as_object(row, "Insert.row")?;
            merge_meta(&mut payload, meta);
            // INSERT only the columns the projection actually set, so columns
            // it OMITS fall to their schema DEFAULT. A bare `SELECT *` over
            // `jsonb_populate_record(NULL::t, …)` writes an explicit NULL into
            // every unlisted column, which fails for `NOT NULL DEFAULT` columns
            // the projection does not populate (e.g. npc_session_memory_projection
            // .summary / .facts, which session.started omits) — surfaced by the
            // L3.E/F live-smoke (147). The keys are now interpolated into SQL,
            // so each is identifier-validated (mirrors the Update SET path).
            let cols = build_column_list(&payload)?;
            let sql = format!(
                "INSERT INTO {t} ({cols}) SELECT {cols} FROM jsonb_populate_record(NULL::{t}, $1::jsonb)"
            );
            Ok(Stmt {
                sql,
                payload: Value::Object(payload),
                increments: vec![],
            })
        }
        ProjectionUpdate::Update {
            pk, fields, meta, ..
        } => {
            let pk_map = as_object(pk, "Update.pk")?;
            let field_map = as_object(fields, "Update.fields")?;
            if pk_map.is_empty() {
                return Err("rebuilder: Update.pk is empty".into());
            }

            // Split normal fields from `<col>_increment` pseudo-fields. The
            // latter mean `SET col = col + value` (e.g. npc.said bumps
            // npc_session_memory_projection.interaction_count) — the generic
            // `jsonb_populate_record` path can only `SET col = value`, so the
            // increment is applied via COALESCE + a separately-bound value.
            let mut normal: Vec<(String, Value)> = Vec::new();
            let mut increments: Vec<(String, i64)> = Vec::new();
            for (k, v) in &field_map {
                if let Some(base) = k.strip_suffix("_increment") {
                    let n = v.as_i64().ok_or_else(|| {
                        format!(
                            "rebuilder: increment field {k:?} must be an integer, got {}",
                            kind_of(v)
                        )
                    })?;
                    increments.push((base.to_string(), n));
                } else {
                    normal.push((k.clone(), v.clone()));
                }
            }

            // jsonb payload carries pk + normal fields + meta — NOT the
            // pseudo-fields (they are not columns; jsonb_populate_record drops
            // them, and their value rides as a bound param instead).
            let mut payload = pk_map.clone();
            for (k, v) in &normal {
                payload.insert(k.clone(), v.clone());
            }
            merge_meta(&mut payload, meta);

            let mut set_parts: Vec<String> = Vec::new();
            let mut set_cols: Vec<&str> = normal.iter().map(|(k, _)| k.as_str()).collect();
            set_cols.extend(["event_id", "aggregate_version", "applied_at"]);
            for c in &set_cols {
                ensure_ident(c)?;
                set_parts.push(format!("{c} = r.{c}"));
            }
            let mut inc_values: Vec<i64> = Vec::with_capacity(increments.len());
            for (base, val) in &increments {
                ensure_ident(base)?;
                let param = inc_values.len() + 2; // $1 is the jsonb payload
                set_parts.push(format!("{base} = COALESCE(t.{base}, 0) + ${param}"));
                inc_values.push(*val);
            }
            let set_clause = set_parts.join(", ");
            let where_clause = build_pk_predicate(&pk_map)?;
            let sql = format!(
                "WITH r AS (SELECT * FROM jsonb_populate_record(NULL::{t}, $1::jsonb)) \
                     UPDATE {t} AS t SET {set_clause} FROM r WHERE {where_clause}"
            );
            Ok(Stmt {
                sql,
                payload: Value::Object(payload),
                increments: inc_values,
            })
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
            Ok(Stmt {
                sql,
                payload: Value::Object(pk_map),
                increments: vec![],
            })
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
        let mut stmts: Vec<Stmt> = Vec::new();
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
            for stmt in &stmts {
                let mut q = sqlx::query(&stmt.sql).bind(&stmt.payload);
                for inc in &stmt.increments {
                    q = q.bind(inc);
                }
                let res = q
                    .execute(&mut *tx)
                    .await
                    .map_err(|e| format!("rebuilder: apply [{}]: {e}", stmt.sql))?;
                // An increment that hit no row means the target row was never
                // created — a cross-aggregate ordering bug (the global-order
                // path exists to prevent this) or a genuine data gap. Fail loud.
                if stmt.expect_row() && res.rows_affected() == 0 {
                    return Err(format!(
                        "rebuilder: increment update affected 0 rows — target row absent \
                         (cross-aggregate ordering or data gap): [{}]",
                        stmt.sql
                    ));
                }
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

/// `col1, col2, ...` for an INSERT column list, in the payload's key order.
/// Validates every identifier (the names are interpolated into SQL) and the
/// SAME string is reused for both the `INSERT (…)` target list and the
/// `SELECT …` source list, so the two are positionally consistent by
/// construction. Errors on an empty payload (an Insert with no columns is a
/// projection bug).
fn build_column_list(payload: &Map<String, Value>) -> Result<String, String> {
    if payload.is_empty() {
        return Err("rebuilder: Insert.row produced no columns".into());
    }
    let mut parts = Vec::with_capacity(payload.len());
    for c in payload.keys() {
        ensure_ident(c)?;
        parts.push(c.as_str());
    }
    Ok(parts.join(", "))
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
    fn insert_sql_lists_columns_so_omitted_ones_take_their_default() {
        let u = ProjectionUpdate::Insert {
            table: "pc_projection".into(),
            row: json!({"pc_id": Uuid::from_u128(2).to_string(), "name": "Aria"}),
            meta: meta(),
        };
        let stmt = build_stmt("pc_projection", &u).unwrap();
        let (sql, payload) = (&stmt.sql, &stmt.payload);
        // Column-list INSERT (NOT `SELECT *`): unlisted columns fall to their
        // schema DEFAULT instead of an explicit NULL. The (…) target list and
        // the SELECT source list are the identical column string.
        let prefix = "INSERT INTO pc_projection (";
        assert!(sql.starts_with(prefix), "{sql}");
        let cols = &sql[prefix.len()..sql.find(')').unwrap()];
        assert!(
            sql.contains(&format!(
                ") SELECT {cols} FROM jsonb_populate_record(NULL::pc_projection, $1::jsonb)"
            )),
            "target + source column lists must match: {sql}"
        );
        // Every set column (projection fields + the 3 meta cols) is present.
        for c in [
            "pc_id",
            "name",
            "event_id",
            "aggregate_version",
            "applied_at",
        ] {
            assert!(
                cols.split(", ").any(|x| x == c),
                "missing column {c}: {cols}"
            );
        }
        // meta stamped into payload
        assert_eq!(payload["event_id"], json!(Uuid::from_u128(1).to_string()));
        assert_eq!(payload["aggregate_version"], json!(7));
        assert_eq!(payload["name"], json!("Aria"));
    }

    #[test]
    fn insert_rejects_unsafe_row_key_identifier() {
        // Insert.row keys are now interpolated into the column list, so an
        // unsafe key must be rejected (defense in depth — keys come from
        // trusted projection code, but the writer validates regardless).
        let u = ProjectionUpdate::Insert {
            table: "pc_projection".into(),
            row: json!({"pc_id; DROP TABLE x": "1"}),
            meta: meta(),
        };
        assert!(build_stmt("pc_projection", &u).is_err());
    }

    #[test]
    fn update_sql_sets_fields_plus_meta_and_pk_where() {
        let u = ProjectionUpdate::Update {
            table: "pc_projection".into(),
            pk: json!({"pc_id": Uuid::from_u128(2).to_string()}),
            fields: json!({"last_event_version": 9}),
            meta: meta(),
        };
        let stmt = build_stmt("pc_projection", &u).unwrap();
        let (sql, payload) = (&stmt.sql, &stmt.payload);
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
        let sql = build_stmt("session_participants", &u).unwrap().sql;
        assert!(sql.starts_with("WITH r AS"), "{sql}");
        assert!(
            sql.contains("DELETE FROM session_participants AS t USING r WHERE"),
            "{sql}"
        );
        assert!(sql.contains("t.session_id = r.session_id"), "{sql}");
    }

    #[test]
    fn update_increment_field_uses_coalesce_and_bound_value() {
        // npc.said → npc_session_memory_projection.interaction_count += 1.
        let u = ProjectionUpdate::Update {
            table: "npc_session_memory_projection".into(),
            pk: json!({"npc_id": Uuid::from_u128(1).to_string(), "session_id": Uuid::from_u128(2).to_string()}),
            fields: json!({"interaction_count_increment": 1}),
            meta: meta(),
        };
        let stmt = build_stmt("npc_session_memory_projection", &u).unwrap();
        assert!(
            stmt.sql
                .contains("interaction_count = COALESCE(t.interaction_count, 0) + $2"),
            "{}",
            stmt.sql
        );
        assert_eq!(stmt.increments, vec![1]);
        assert!(
            stmt.expect_row(),
            "an increment update must expect an existing row"
        );
        // the pseudo-field must NOT be a column in the jsonb payload
        assert!(stmt.payload.get("interaction_count_increment").is_none());
    }

    #[test]
    fn update_multiple_increments_get_ordered_params() {
        // Two increment fields → $2 / $3 in sorted-key order, matching the
        // increments vec the binder walks.
        let u = ProjectionUpdate::Update {
            table: "npc_session_memory_projection".into(),
            pk: json!({"npc_id": "x"}),
            fields: json!({"a_increment": 1, "b_increment": 2}),
            meta: meta(),
        };
        let stmt = build_stmt("npc_session_memory_projection", &u).unwrap();
        assert!(stmt.sql.contains("a = COALESCE(t.a, 0) + $2"), "{}", stmt.sql);
        assert!(stmt.sql.contains("b = COALESCE(t.b, 0) + $3"), "{}", stmt.sql);
        assert_eq!(stmt.increments, vec![1, 2]); // same order as $2, $3
    }

    #[test]
    fn update_increment_rejects_non_integer() {
        let u = ProjectionUpdate::Update {
            table: "npc_session_memory_projection".into(),
            pk: json!({"npc_id": "x"}),
            fields: json!({"interaction_count_increment": "notanint"}),
            meta: meta(),
        };
        assert!(build_stmt("npc_session_memory_projection", &u).is_err());
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
