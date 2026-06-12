//! L3.C — bounded in-memory snapshot cache.
//!
//! Holds reconstructed aggregate state keyed by `(reality_id, aggregate_type,
//! aggregate_id)`. Used by [`crate::load_aggregate`] to short-circuit repeat
//! loads of hot aggregates (e.g. an NPC currently in dialogue → load cycle
//! per tick).
//!
//! ## Design constraints
//!
//! - **Bounded.** Configurable max entries — when full, LRU eviction. No
//!   unbounded growth (foundation invariant I9: bounded memory).
//! - **In-memory only.** Process-local. The L3.C acceptance criterion is
//!   "cache hit rate ≥ 80% in steady-state" — that is a single-process
//!   metric. Cross-process / cross-host caching is a separate concern
//!   (Redis tier, deferred to L4+ integration).
//! - **Type-erased payload.** Values stored as `serde_json::Value` so a
//!   single cache instance can host PC / NPC / region / world_kv aggregates.
//!   The caller deserializes into the concrete `A: Aggregate` type at read.
//! - **No async.** Q-L3-2 — sync only.
//!
//! ## What is NOT in cycle 12
//!
//! - **Write-through invalidation tied to L2.D publisher** — cycle 14+ will
//!   wire the publisher to call `invalidate()` on event emit. For cycle 12
//!   we expose [`SnapshotCache::invalidate`] + [`SnapshotCache::insert`] so
//!   callers can manage coherence by hand.
//! - **TTL-based expiry** — keep it simple; LRU is enough for the L3.C
//!   acceptance bar.

use std::collections::HashMap;

use serde_json::Value;
use uuid::Uuid;

/// Cache key — process-stable identity of an aggregate inside a reality.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CacheKey {
    pub reality_id: Uuid,
    pub aggregate_type: String,
    pub aggregate_id: String,
}

impl CacheKey {
    pub fn new(reality_id: Uuid, aggregate_type: impl Into<String>, aggregate_id: impl Into<String>) -> Self {
        Self {
            reality_id,
            aggregate_type: aggregate_type.into(),
            aggregate_id: aggregate_id.into(),
        }
    }
}

/// Cache entry — the cached aggregate snapshot + its version high-water
/// mark (so the load path can ask the event reader for events strictly
/// after this version).
#[derive(Debug, Clone, PartialEq)]
pub struct CacheEntry {
    pub snapshot_data: Value,
    pub aggregate_version: u64,
}

/// Bounded LRU snapshot cache.
///
/// Note: the LRU bookkeeping uses an insertion-order `Vec<CacheKey>`. For
/// the cache sizes we ship (process-local; bound typically 64-1024 entries)
/// this is fine — O(n) on eviction but n is tiny. If we ever need a larger
/// cache, swap the order-vec for the `lru` crate without changing the
/// public surface.
pub struct SnapshotCache {
    capacity: usize,
    entries: HashMap<CacheKey, CacheEntry>,
    /// Insertion / access order — most-recently-used at the back.
    order: Vec<CacheKey>,
    hits: u64,
    misses: u64,
}

impl SnapshotCache {
    /// Create a bounded cache with the given capacity. Panics if capacity
    /// is 0 (a 0-capacity cache would always miss).
    pub fn new(capacity: usize) -> Self {
        assert!(capacity > 0, "SnapshotCache capacity must be > 0");
        Self {
            capacity,
            entries: HashMap::with_capacity(capacity),
            order: Vec::with_capacity(capacity),
            hits: 0,
            misses: 0,
        }
    }

    /// Look up the cached snapshot. On hit, the key is bumped to MRU and
    /// `hits` is incremented; on miss, `misses` is incremented.
    pub fn get(&mut self, key: &CacheKey) -> Option<CacheEntry> {
        if self.entries.contains_key(key) {
            self.bump_lru(key);
            self.hits += 1;
            return self.entries.get(key).cloned();
        }
        self.misses += 1;
        None
    }

    /// Insert / overwrite an entry. Evicts the LRU entry if at capacity.
    pub fn insert(&mut self, key: CacheKey, entry: CacheEntry) {
        if self.entries.contains_key(&key) {
            self.entries.insert(key.clone(), entry);
            self.bump_lru(&key);
            return;
        }
        if self.entries.len() >= self.capacity {
            // Evict LRU (front of order vec).
            if let Some(evict) = self.order.first().cloned() {
                self.order.remove(0);
                self.entries.remove(&evict);
            }
        }
        self.order.push(key.clone());
        self.entries.insert(key, entry);
    }

    /// Drop an entry (e.g. on event emit — call from publisher write-through).
    pub fn invalidate(&mut self, key: &CacheKey) {
        if self.entries.remove(key).is_some() {
            self.order.retain(|k| k != key);
        }
    }

    /// Hit / miss counters for observability + the L3.C cache-hit-rate test.
    pub fn hits(&self) -> u64 {
        self.hits
    }
    pub fn misses(&self) -> u64 {
        self.misses
    }
    pub fn len(&self) -> usize {
        self.entries.len()
    }
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Hit rate as a float in [0.0, 1.0]. Returns 0.0 if no accesses yet.
    pub fn hit_rate(&self) -> f64 {
        let total = self.hits + self.misses;
        if total == 0 {
            return 0.0;
        }
        self.hits as f64 / total as f64
    }

    fn bump_lru(&mut self, key: &CacheKey) {
        if let Some(pos) = self.order.iter().position(|k| k == key) {
            self.order.remove(pos);
            self.order.push(key.clone());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn key(id: u128) -> CacheKey {
        CacheKey::new(Uuid::from_u128(0xDEAD), "counter", format!("c-{id}"))
    }

    fn entry(v: u64) -> CacheEntry {
        CacheEntry {
            snapshot_data: json!({ "value": v }),
            aggregate_version: v,
        }
    }

    #[test]
    #[should_panic]
    fn zero_capacity_panics() {
        SnapshotCache::new(0);
    }

    #[test]
    fn miss_then_hit() {
        let mut c = SnapshotCache::new(8);
        assert!(c.get(&key(1)).is_none());
        assert_eq!(c.misses(), 1);
        c.insert(key(1), entry(10));
        let hit = c.get(&key(1));
        assert!(hit.is_some());
        assert_eq!(hit.unwrap().aggregate_version, 10);
        assert_eq!(c.hits(), 1);
    }

    #[test]
    fn lru_eviction_at_capacity() {
        let mut c = SnapshotCache::new(2);
        c.insert(key(1), entry(1));
        c.insert(key(2), entry(2));
        c.insert(key(3), entry(3)); // evicts key 1
        assert!(c.get(&key(1)).is_none(), "key 1 should be evicted");
        assert!(c.get(&key(2)).is_some());
        assert!(c.get(&key(3)).is_some());
        assert_eq!(c.len(), 2);
    }

    #[test]
    fn lru_get_bumps_to_mru() {
        let mut c = SnapshotCache::new(2);
        c.insert(key(1), entry(1));
        c.insert(key(2), entry(2));
        // Touch key 1 so it becomes MRU.
        let _ = c.get(&key(1));
        c.insert(key(3), entry(3)); // should evict key 2 (LRU), not key 1
        assert!(c.get(&key(1)).is_some(), "key 1 was bumped to MRU");
        assert!(c.get(&key(2)).is_none(), "key 2 was LRU");
    }

    #[test]
    fn invalidate_removes_entry() {
        let mut c = SnapshotCache::new(4);
        c.insert(key(1), entry(1));
        c.invalidate(&key(1));
        assert!(c.get(&key(1)).is_none());
        assert_eq!(c.len(), 0);
    }

    #[test]
    fn hit_rate_meets_l3c_acceptance_bar() {
        // L3.C acceptance: hit rate >= 80% in steady-state.
        // Simulate: 1 cold miss + 9 warm hits → 90% hit rate.
        let mut c = SnapshotCache::new(8);
        let k = key(1);
        assert!(c.get(&k).is_none()); // miss (cold)
        c.insert(k.clone(), entry(1));
        for _ in 0..9 {
            assert!(c.get(&k).is_some());
        }
        assert_eq!(c.hits(), 9);
        assert_eq!(c.misses(), 1);
        assert!(c.hit_rate() >= 0.8, "hit_rate={} should be >= 0.8", c.hit_rate());
    }

    #[test]
    fn insert_overwrite_updates_value_keeps_lru_bump() {
        let mut c = SnapshotCache::new(2);
        c.insert(key(1), entry(1));
        c.insert(key(2), entry(2));
        // Overwrite key 1 (bumps to MRU).
        c.insert(key(1), entry(100));
        c.insert(key(3), entry(3)); // evicts key 2 (LRU)
        let v = c.get(&key(1)).unwrap();
        assert_eq!(v.aggregate_version, 100, "overwrite value visible");
        assert!(c.get(&key(2)).is_none());
    }
}
