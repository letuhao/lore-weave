//! L4.C — Allowlist mirror of `contracts/meta/allowlist.go`.
//!
//! Loads + queries `events_allowlist.yaml` so Rust hot-path writers can
//! enforce the same defense-in-depth gate as the Go library. Defense-in-depth:
//! a MetaWrite intent that targets a table NOT in this file is rejected before
//! any SQL runs.
//!
//! The YAML schema is shared with Go (`contracts/meta/events_allowlist.yaml`)
//! and version-pinned at `version: 1`.

use serde::Deserialize;
use std::collections::HashMap;
use std::path::Path;

use crate::errors::MetaError;
use crate::metawrite::MetaWriteOp;

/// One outbox-event binding for a `(table, op)` pair.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct EventBinding {
    /// SQL operation (INSERT | UPDATE | DELETE).
    pub op: MetaWriteOp,
    /// Outbox event name emitted on successful write.
    pub event_name: String,
}

/// One entry in the allowlist YAML.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct AllowlistEntry {
    /// Meta table name (matches a real `migrations/meta/*` table).
    pub table: String,
    /// Outbox event bindings for this table; empty = no events emitted.
    #[serde(default)]
    pub events: Vec<EventBinding>,
    /// Owning service (informational; not enforced).
    #[serde(default)]
    pub owner: String,
    /// Notes (informational).
    #[serde(default)]
    pub notes: String,
}

#[derive(Debug, Deserialize)]
struct AllowlistFile {
    version: u32,
    entries: Vec<AllowlistEntry>,
}

/// Parsed `events_allowlist.yaml`. Cheap to clone (uses `Arc`-free maps so
/// callers usually wrap the whole struct in `Arc<Allowlist>`).
#[derive(Debug, Clone)]
pub struct Allowlist {
    tables: HashMap<String, AllowlistEntry>,
    /// `(table, op) -> event_name` for O(1) lookup at MetaWrite emission time.
    events: HashMap<(String, MetaWriteOp), String>,
}

impl Allowlist {
    /// Load + parse the allowlist YAML file at `path`.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, MetaError> {
        let raw = std::fs::read(path.as_ref()).map_err(|e| {
            MetaError::ConfigInvalid(format!(
                "read allowlist {}: {e}",
                path.as_ref().display()
            ))
        })?;
        Self::parse(&raw)
    }

    /// Parse + validate an in-memory YAML payload.
    pub fn parse(raw: &[u8]) -> Result<Self, MetaError> {
        let f: AllowlistFile = serde_yaml::from_slice(raw)
            .map_err(|e| MetaError::ConfigInvalid(format!("unmarshal allowlist: {e}")))?;
        if f.version != 1 {
            return Err(MetaError::ConfigInvalid(format!(
                "allowlist version={} unsupported (want 1)",
                f.version
            )));
        }
        let mut tables = HashMap::with_capacity(f.entries.len());
        let mut events = HashMap::new();
        for entry in f.entries {
            let table = entry.table.trim();
            if table.is_empty() {
                return Err(MetaError::ConfigInvalid("empty table".into()));
            }
            if tables.contains_key(table) {
                return Err(MetaError::ConfigInvalid(format!(
                    "duplicate table {table}"
                )));
            }
            for b in &entry.events {
                if b.event_name.trim().is_empty() {
                    return Err(MetaError::ConfigInvalid(format!(
                        "table {table} op {:?} missing event_name",
                        b.op
                    )));
                }
                let key = (table.to_string(), b.op);
                if events.contains_key(&key) {
                    return Err(MetaError::ConfigInvalid(format!(
                        "table {table} op {:?} duplicated",
                        b.op
                    )));
                }
                events.insert(key, b.event_name.clone());
            }
            tables.insert(table.to_string(), entry);
        }
        Ok(Self { tables, events })
    }

    /// True if `table` is registered.
    pub fn allows_table(&self, table: &str) -> bool {
        self.tables.contains_key(table)
    }

    /// Returns the outbox event name for a `(table, op)` pair, if any.
    pub fn emits_event(&self, table: &str, op: MetaWriteOp) -> Option<&str> {
        self.events
            .get(&(table.to_string(), op))
            .map(String::as_str)
    }

    /// List registered table names (unsorted; tests sort if needed).
    pub fn tables(&self) -> Vec<&str> {
        self.tables.keys().map(String::as_str).collect()
    }

    /// Fast in-tests constructor — accepts a simple list of (table, events) pairs.
    /// Bypasses YAML loading; used by unit tests that don't want a fixture file.
    pub fn from_entries(entries: Vec<AllowlistEntry>) -> Result<Self, MetaError> {
        // Re-use parse logic via a synthetic doc to keep validation centralized.
        let f = AllowlistFile { version: 1, entries };
        let raw = serde_yaml::to_string(&serde_json::json!({
            "version": f.version,
            "entries": f.entries.iter().map(|e| {
                serde_json::json!({
                    "table": e.table,
                    "owner": e.owner,
                    "notes": e.notes,
                    "events": e.events.iter().map(|b| serde_json::json!({
                        "op": b.op.as_str(),
                        "event_name": b.event_name,
                    })).collect::<Vec<_>>(),
                })
            }).collect::<Vec<_>>(),
        }))
        .map_err(|e| MetaError::ConfigInvalid(format!("synthesize entries: {e}")))?;
        Self::parse(raw.as_bytes())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SHIPPED: &str = "../../contracts/meta/events_allowlist.yaml";

    #[test]
    fn shipped_yaml_parses() {
        let al = Allowlist::load(SHIPPED).expect("load shipped");
        // reality_registry MUST be present (cycle 2 seed).
        assert!(al.allows_table("reality_registry"));
        // INSERT emits reality.created.
        assert_eq!(
            al.emits_event("reality_registry", MetaWriteOp::Insert),
            Some("reality.created")
        );
        // UPDATE emits reality.status.changed.
        assert_eq!(
            al.emits_event("reality_registry", MetaWriteOp::Update),
            Some("reality.status.changed")
        );
        // Unknown table is rejected.
        assert!(!al.allows_table("does_not_exist"));
    }

    #[test]
    fn duplicate_table_rejected() {
        let doc = br#"
version: 1
entries:
  - table: a
    events: []
  - table: a
    events: []
"#;
        let err = Allowlist::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("duplicate")));
    }

    #[test]
    fn empty_event_name_rejected() {
        let doc = br#"
version: 1
entries:
  - table: a
    events:
      - op: INSERT
        event_name: ""
"#;
        let err = Allowlist::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("missing event_name")));
    }

    #[test]
    fn duplicate_op_rejected() {
        let doc = br#"
version: 1
entries:
  - table: a
    events:
      - op: INSERT
        event_name: foo
      - op: INSERT
        event_name: bar
"#;
        let err = Allowlist::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("duplicated")));
    }

    #[test]
    fn version_mismatch_rejected() {
        let doc = br#"
version: 99
entries:
  - table: a
    events: []
"#;
        let err = Allowlist::parse(doc).unwrap_err();
        assert!(matches!(err, MetaError::ConfigInvalid(ref m) if m.contains("unsupported")));
    }
}
