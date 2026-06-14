//! A minimal keyed projection table-store + canonical JSON, shared by the
//! convergence oracle. Models what the DB write side does with a
//! [`ProjectionUpdate`]: apply Insert/Update/Delete/Tombstone to a row keyed by
//! its primary key. A `BTreeMap` + canonical (sorted-key) JSON make the final
//! state byte-comparable independent of insertion order.

use std::collections::BTreeMap;

use serde_json::{Value, json};

use dp_kernel::ProjectionUpdate;

/// `(table, canonical-pk-json)` → row value.
#[derive(Default, Clone, PartialEq, Eq)]
pub struct TableStore {
    rows: BTreeMap<(String, String), Value>,
}

impl TableStore {
    pub fn new() -> Self {
        Self::default()
    }

    /// Apply one update. Mirrors the DB semantics the runtime composes into a TX.
    /// `PcProjection` (the convergence oracle's subject) emits only Insert/Update
    /// today; the Delete/Tombstone arms are defensive — they keep this faithful
    /// if a future `pc.*` event deletes a row.
    pub fn apply(&mut self, u: &ProjectionUpdate) {
        match u {
            ProjectionUpdate::Insert { table, row, .. } => {
                let key = (table.clone(), canon(&insert_pk(table, row)));
                self.rows.insert(key, row.clone());
            }
            ProjectionUpdate::Update {
                table, pk, fields, ..
            } => {
                let key = (table.clone(), canon(pk));
                // Update-before-insert: materialize from `fields` (matches an
                // UPSERT-on-update DB path); else merge into the existing row.
                let entry = self.rows.entry(key).or_insert_with(|| json!({}));
                merge(entry, fields);
            }
            ProjectionUpdate::Delete { table, pk } => {
                self.rows.remove(&(table.clone(), canon(pk)));
            }
            ProjectionUpdate::Tombstone { table, pk, .. } => {
                let key = (table.clone(), canon(pk));
                self.rows.insert(key, json!({ "__tombstone": true }));
            }
        }
    }

    /// Canonical serialization of the entire store — the byte-comparable
    /// projection state.
    pub fn snapshot(&self) -> String {
        let mut out = String::new();
        for ((table, pk), row) in &self.rows {
            out.push_str(table);
            out.push('|');
            out.push_str(pk);
            out.push('=');
            out.push_str(&canon(row));
            out.push('\n');
        }
        out
    }
}

/// Derive the primary key of an `Insert` row per table (mirrors the migration
/// PKs). Update/Delete/Tombstone carry their pk explicitly.
fn insert_pk(table: &str, row: &Value) -> Value {
    match table {
        "pc_projection" => json!({ "pc_id": row.get("pc_id") }),
        "pc_inventory_projection" => {
            json!({ "pc_id": row.get("pc_id"), "item_code": row.get("item_code") })
        }
        _ => row.clone(),
    }
}

/// Shallow field merge (Update semantics): copy each field of `fields` onto the
/// target object.
fn merge(target: &mut Value, fields: &Value) {
    if let (Some(t), Some(f)) = (target.as_object_mut(), fields.as_object()) {
        for (k, v) in f {
            t.insert(k.clone(), v.clone());
        }
    } else {
        *target = fields.clone();
    }
}

/// Canonical JSON: objects serialized with keys sorted recursively, so two
/// values that differ only in key order compare equal.
pub fn canon(v: &Value) -> String {
    let mut s = String::new();
    canon_into(v, &mut s);
    s
}

fn canon_into(v: &Value, out: &mut String) {
    match v {
        Value::Object(m) => {
            let sorted: BTreeMap<&String, &Value> = m.iter().collect();
            out.push('{');
            for (i, (k, val)) in sorted.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                out.push_str(&serde_json::to_string(k).unwrap());
                out.push(':');
                canon_into(val, out);
            }
            out.push('}');
        }
        Value::Array(a) => {
            out.push('[');
            for (i, val) in a.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                canon_into(val, out);
            }
            out.push(']');
        }
        other => out.push_str(&other.to_string()),
    }
}
