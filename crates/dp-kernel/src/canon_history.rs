//! Cycle 27 L5.J — Rust mirror of `contracts/canon/timeline/`.
//!
//! # Purpose (Q-L4-1 parity)
//!
//! Rust services (world-service, future roleplay-service Rust shards)
//! emit + query the canon change-history via the same SDK surface as
//! the Go-side contracts/canon/timeline. APPEND-ONLY discipline is
//! enforced by the absence of update/delete methods on the trait.
//!
//! # LOCKED Q-IDs honored
//!
//! - **Q-L5-3**: `canon_layer` field carries `"L1_axiom"` | `"L2_seeded"`
//!   verbatim
//! - **Q-L1A-2**: change history conceptually lives in glossary DB; this
//!   crate ships SDK types only

use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Three LOCKED change kinds (mirrors Go contracts/events/canon_change_history.go).
pub const CHANGE_KIND_AUTHORED: &str = "authored";
pub const CHANGE_KIND_FORCE_PROPAGATE: &str = "force_propagate";
pub const CHANGE_KIND_PROPAGATION_COMPLETED: &str = "propagation_completed";

/// Returns true if `kind` is one of the LOCKED change kinds.
pub fn is_valid_change_kind(kind: &str) -> bool {
    matches!(
        kind,
        CHANGE_KIND_AUTHORED | CHANGE_KIND_FORCE_PROPAGATE | CHANGE_KIND_PROPAGATION_COMPLETED
    )
}

/// One change-history row. Mirrors `Entry` in contracts/canon/timeline.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChangeEntry {
    pub change_id: Uuid,
    pub canon_entry_id: Uuid,
    pub book_id: Uuid,
    pub attribute_path: String,
    #[serde(default)]
    pub reality_id: Option<Uuid>,
    pub kind: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub old_value: Vec<u8>,
    pub new_value: Vec<u8>,
    pub canon_layer: String,
    pub source_event_id: Uuid,
    pub source_event_type: String,
    /// Epoch seconds (UTC). Matches dp-kernel's i64-epoch convention.
    pub recorded_at_epoch: i64,
}

/// Query parameters for the timeline. Mirrors Go `Query`.
#[derive(Debug, Clone, Default)]
pub struct ChangeQuery {
    pub canon_entry_id: Option<Uuid>,
    pub book_id: Option<Uuid>,
    pub attribute_path: Option<String>,
    pub reality_id: Option<Uuid>,
    pub since_epoch: Option<i64>,
    pub limit: Option<usize>,
}

/// Validation outcomes for [`ChangeQuery`].
#[derive(Debug, thiserror::Error)]
pub enum ChangeQueryError {
    #[error("timeline: must specify canon_entry_id OR (book_id + attribute_path)")]
    MissingScope,
}

impl ChangeQuery {
    /// Returns Ok when the query has a usable scope.
    pub fn validate(&self) -> Result<(), ChangeQueryError> {
        let has_entry = self.canon_entry_id.is_some();
        let has_path = self.book_id.is_some() && self.attribute_path.is_some();
        if !has_entry && !has_path {
            return Err(ChangeQueryError::MissingScope);
        }
        Ok(())
    }
}

/// Errors from [`TimelineAppender`] / [`TimelineQueryer`].
#[derive(Debug, thiserror::Error)]
pub enum TimelineError {
    #[error("timeline: invalid entry: {0}")]
    Invalid(String),
    #[error("timeline: duplicate change_id (APPEND-ONLY)")]
    DuplicateChangeId,
    #[error("timeline: query: {0}")]
    Query(#[from] ChangeQueryError),
}

/// Write-side trait. APPEND-ONLY by design — no update/delete method.
pub trait TimelineAppender: Send + Sync {
    fn append(&self, entry: ChangeEntry) -> Result<(), TimelineError>;
}

/// Read-side trait.
pub trait TimelineQueryer: Send + Sync {
    fn query(&self, q: ChangeQuery) -> Result<Vec<ChangeEntry>, TimelineError>;
}

/// In-memory reference impl satisfying both traits.
pub struct InMemoryTimeline {
    rows: Mutex<Vec<ChangeEntry>>,
}

impl Default for InMemoryTimeline {
    fn default() -> Self {
        Self::new()
    }
}

impl InMemoryTimeline {
    pub fn new() -> Self {
        Self {
            rows: Mutex::new(Vec::new()),
        }
    }

    pub fn len(&self) -> usize {
        self.rows.lock().unwrap().len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl TimelineAppender for InMemoryTimeline {
    fn append(&self, entry: ChangeEntry) -> Result<(), TimelineError> {
        if entry.change_id.is_nil() {
            return Err(TimelineError::Invalid("change_id required".into()));
        }
        if !is_valid_change_kind(&entry.kind) {
            return Err(TimelineError::Invalid(format!("invalid kind {:?}", entry.kind)));
        }
        if entry.recorded_at_epoch <= 0 {
            return Err(TimelineError::Invalid("recorded_at_epoch must be positive".into()));
        }
        let mut g = self.rows.lock().unwrap();
        if g.iter().any(|r| r.change_id == entry.change_id) {
            return Err(TimelineError::DuplicateChangeId);
        }
        g.push(entry);
        Ok(())
    }
}

impl TimelineQueryer for InMemoryTimeline {
    fn query(&self, q: ChangeQuery) -> Result<Vec<ChangeEntry>, TimelineError> {
        q.validate()?;
        let g = self.rows.lock().unwrap();
        let mut out: Vec<ChangeEntry> = g
            .iter()
            .filter(|r| matches(r, &q))
            .cloned()
            .collect();
        out.sort_by_key(|r| r.recorded_at_epoch);
        if let Some(limit) = q.limit {
            if out.len() > limit {
                out.truncate(limit);
            }
        }
        Ok(out)
    }
}

fn matches(r: &ChangeEntry, q: &ChangeQuery) -> bool {
    if let Some(ce) = q.canon_entry_id {
        if r.canon_entry_id != ce {
            return false;
        }
    } else {
        if let Some(b) = q.book_id {
            if r.book_id != b {
                return false;
            }
        }
        if let Some(ap) = &q.attribute_path {
            if &r.attribute_path != ap {
                return false;
            }
        }
    }
    if let Some(rid) = q.reality_id {
        if r.reality_id != Some(rid) {
            return false;
        }
    }
    if let Some(since) = q.since_epoch {
        if r.recorded_at_epoch < since {
            return false;
        }
    }
    true
}

// ─────────────────────────────────────────────────────────────────────────
// Tests.
// ─────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(kind: &str, recorded_at: i64) -> ChangeEntry {
        ChangeEntry {
            change_id: Uuid::new_v4(),
            canon_entry_id: Uuid::new_v4(),
            book_id: Uuid::new_v4(),
            attribute_path: "world.climate".to_string(),
            reality_id: None,
            kind: kind.to_string(),
            old_value: vec![],
            new_value: b"\"arid\"".to_vec(),
            canon_layer: "L2_seeded".to_string(),
            source_event_id: Uuid::new_v4(),
            source_event_type: "canon.entry.updated".to_string(),
            recorded_at_epoch: recorded_at,
        }
    }

    #[test]
    fn change_kind_strings_match_go() {
        assert!(is_valid_change_kind(CHANGE_KIND_AUTHORED));
        assert!(is_valid_change_kind(CHANGE_KIND_FORCE_PROPAGATE));
        assert!(is_valid_change_kind(CHANGE_KIND_PROPAGATION_COMPLETED));
        assert!(!is_valid_change_kind("bogus"));
    }

    #[test]
    fn cross_language_change_kind_parity_with_go() {
        // Go contracts/events/canon_change_history.go LOCKS these exact
        // strings.
        assert_eq!(CHANGE_KIND_AUTHORED, "authored");
        assert_eq!(CHANGE_KIND_FORCE_PROPAGATE, "force_propagate");
        assert_eq!(CHANGE_KIND_PROPAGATION_COMPLETED, "propagation_completed");
    }

    #[test]
    fn append_rejects_invalid() {
        let store = InMemoryTimeline::new();
        let bad_kind = ChangeEntry {
            kind: "bogus".into(),
            ..sample(CHANGE_KIND_AUTHORED, 1)
        };
        match store.append(bad_kind) {
            Err(TimelineError::Invalid(_)) => {}
            other => panic!("expected Invalid, got {other:?}"),
        }

        let zero_recorded = sample(CHANGE_KIND_AUTHORED, 0);
        match store.append(zero_recorded) {
            Err(TimelineError::Invalid(_)) => {}
            other => panic!("expected Invalid for zero recorded_at, got {other:?}"),
        }

        let zero_id = ChangeEntry {
            change_id: Uuid::nil(),
            ..sample(CHANGE_KIND_AUTHORED, 100)
        };
        match store.append(zero_id) {
            Err(TimelineError::Invalid(_)) => {}
            other => panic!("expected Invalid for nil change_id, got {other:?}"),
        }
    }

    #[test]
    fn append_only_rejects_duplicate_change_id() {
        let store = InMemoryTimeline::new();
        let e = sample(CHANGE_KIND_AUTHORED, 100);
        store.append(e.clone()).unwrap();
        match store.append(e) {
            Err(TimelineError::DuplicateChangeId) => {}
            other => panic!("expected DuplicateChangeId, got {other:?}"),
        }
    }

    #[test]
    fn query_entry_scoped() {
        let store = InMemoryTimeline::new();
        let entry = Uuid::new_v4();
        let mut e1 = sample(CHANGE_KIND_AUTHORED, 100);
        e1.canon_entry_id = entry;
        let mut e2 = sample(CHANGE_KIND_FORCE_PROPAGATE, 200);
        e2.canon_entry_id = entry;
        let e3 = sample(CHANGE_KIND_AUTHORED, 300); // different entry
        store.append(e1).unwrap();
        store.append(e2).unwrap();
        store.append(e3).unwrap();

        let rows = store
            .query(ChangeQuery {
                canon_entry_id: Some(entry),
                ..Default::default()
            })
            .unwrap();
        assert_eq!(rows.len(), 2);
        assert!(rows[0].recorded_at_epoch <= rows[1].recorded_at_epoch);
    }

    #[test]
    fn query_requires_scope() {
        let store = InMemoryTimeline::new();
        match store.query(ChangeQuery::default()) {
            Err(TimelineError::Query(ChangeQueryError::MissingScope)) => {}
            other => panic!("expected MissingScope, got {other:?}"),
        }
    }

    #[test]
    fn query_reality_filter() {
        let store = InMemoryTimeline::new();
        let entry = Uuid::new_v4();
        let r1 = Uuid::new_v4();
        let mut e1 = sample(CHANGE_KIND_FORCE_PROPAGATE, 100);
        e1.canon_entry_id = entry;
        e1.reality_id = Some(r1);
        let mut e2 = sample(CHANGE_KIND_FORCE_PROPAGATE, 200);
        e2.canon_entry_id = entry;
        e2.reality_id = Some(Uuid::new_v4());
        store.append(e1).unwrap();
        store.append(e2).unwrap();

        let rows = store
            .query(ChangeQuery {
                canon_entry_id: Some(entry),
                reality_id: Some(r1),
                ..Default::default()
            })
            .unwrap();
        assert_eq!(rows.len(), 1);
    }

    #[test]
    fn query_limit_caps_results() {
        let store = InMemoryTimeline::new();
        let entry = Uuid::new_v4();
        for i in 0..10 {
            let mut e = sample(CHANGE_KIND_AUTHORED, 100 + i);
            e.canon_entry_id = entry;
            store.append(e).unwrap();
        }
        let rows = store
            .query(ChangeQuery {
                canon_entry_id: Some(entry),
                limit: Some(3),
                ..Default::default()
            })
            .unwrap();
        assert_eq!(rows.len(), 3);
    }

    #[test]
    fn query_since_filter() {
        let store = InMemoryTimeline::new();
        let entry = Uuid::new_v4();
        for i in 0..5 {
            let mut e = sample(CHANGE_KIND_AUTHORED, 100 + i);
            e.canon_entry_id = entry;
            store.append(e).unwrap();
        }
        let rows = store
            .query(ChangeQuery {
                canon_entry_id: Some(entry),
                since_epoch: Some(102),
                ..Default::default()
            })
            .unwrap();
        assert_eq!(rows.len(), 3); // 102, 103, 104
    }

    #[test]
    fn json_round_trip_wire_stable() {
        let e = ChangeEntry {
            change_id: Uuid::new_v4(),
            canon_entry_id: Uuid::new_v4(),
            book_id: Uuid::new_v4(),
            attribute_path: "world.climate".into(),
            reality_id: Some(Uuid::new_v4()),
            kind: CHANGE_KIND_FORCE_PROPAGATE.into(),
            old_value: b"\"temperate\"".to_vec(),
            new_value: b"\"arid\"".to_vec(),
            canon_layer: "L2_seeded".into(),
            source_event_id: Uuid::new_v4(),
            source_event_type: "admin.canon.override.compensating".into(),
            recorded_at_epoch: 1_780_000_000,
        };
        let raw = serde_json::to_string(&e).unwrap();
        let dec: ChangeEntry = serde_json::from_str(&raw).unwrap();
        assert_eq!(dec, e);

        // Pin a few JSON tag names.
        for key in ["change_id", "canon_entry_id", "kind", "source_event_type", "recorded_at_epoch"] {
            assert!(raw.contains(key), "wire-stable {key} missing");
        }
    }
}
