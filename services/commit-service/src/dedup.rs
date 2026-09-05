//! `EVT-L3` idempotency bookkeeping — a TTL map, not an admission stage.
//!
//! Split out of `admission.rs` alongside `proposal.rs` when `SEALED-SUBJECT`
//! pushed that file past its `IMP-D3` ceiling. Admission USES this the way it
//! uses the vocabulary and the verb table, neither of which lives there either:
//! the file runs STAGES, and remembering what it has already seen is a
//! collaborator with its own eviction rule.

use std::collections::BTreeMap;
use std::time::{Duration, Instant};

/// EVT-L3 dedup cache — commit-service-owned, 60 s TTL (bus layer; the
/// kernel seen-set stays the second, step-time layer).
pub struct DedupCache {
    ttl: Duration,
    seen: BTreeMap<(String, String, i64), Instant>,
}

impl DedupCache {
    pub fn new(ttl: Duration) -> Self {
        Self { ttl, seen: BTreeMap::new() }
    }

    /// Returns false iff the triple is a live duplicate.
    pub fn insert(&mut self, key: (String, String, i64)) -> bool {
        let now = Instant::now();
        self.seen.retain(|_, t| now.duration_since(*t) < self.ttl);
        match self.seen.get(&key) {
            Some(_) => false,
            None => {
                self.seen.insert(key, now);
                true
            }
        }
    }

    pub fn len(&self) -> usize {
        self.seen.len()
    }

    pub fn is_empty(&self) -> bool {
        self.seen.is_empty()
    }
}
