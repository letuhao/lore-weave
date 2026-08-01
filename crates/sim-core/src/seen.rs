//! Windowed idempotency set (SC-D3). The window is part of the CONTRACT:
//! "a retry within the window is deduplicated; after it, it may be
//! reprocessed." Encounter islands use `Unbounded` (the set dies with the
//! island); cell islands use a TTL — platform-wide 5 minutes per REC-69,
//! expressed here in ticks because the kernel never reads a clock.

use std::collections::BTreeMap;

use crate::types::{InputId, Tick};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SeenWindow {
    /// No eviction — bounded by island lifetime (encounter islands).
    Unbounded,
    /// Entries older than `ttl_ticks` MAY be reprocessed (cell islands).
    TtlTicks(u64),
}

/// Deterministic seen-set. `BTreeMap`, not `HashMap` — iteration order enters
/// eviction order, and hash order must never enter replay-observable state.
#[derive(Debug, Clone)]
pub struct SeenSet {
    window: SeenWindow,
    map: BTreeMap<InputId, Tick>,
}

impl SeenSet {
    pub fn new(window: SeenWindow) -> Self {
        Self {
            window,
            map: BTreeMap::new(),
        }
    }

    /// Record `id` at logical time `now`. Returns `false` iff `id` is a live
    /// duplicate (present and inside the window) — the caller records
    /// `Discarded { Duplicate }` and does NOT apply.
    pub fn insert(&mut self, id: InputId, now: Tick) -> bool {
        if let Some(&t) = self.map.get(&id) {
            match self.window {
                SeenWindow::Unbounded => return false,
                SeenWindow::TtlTicks(ttl) => {
                    if now.0.saturating_sub(t.0) <= ttl {
                        return false;
                    }
                    // Expired — fall through and re-record at `now`.
                }
            }
        }
        self.map.insert(id, now);
        true
    }

    /// Remove `id` — used when an input is BUFFERED (it will be re-offered,
    /// and must not collide with itself).
    pub fn forget(&mut self, id: &InputId) {
        self.map.remove(id);
    }

    /// Evict expired entries. Called from `tick()`, never from `step()` —
    /// eviction cost stays off the per-item path.
    pub fn evict_expired(&mut self, now: Tick) -> u64 {
        if let SeenWindow::TtlTicks(ttl) = self.window {
            let before = self.map.len();
            self.map.retain(|_, t| now.0.saturating_sub(t.0) <= ttl);
            (before - self.map.len()) as u64
        } else {
            0
        }
    }

    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn duplicate_inside_window_rejected() {
        let mut s = SeenSet::new(SeenWindow::TtlTicks(100));
        assert!(s.insert(InputId(1), Tick(0)));
        assert!(!s.insert(InputId(1), Tick(50)));
    }

    #[test]
    fn duplicate_after_window_reprocessed() {
        // The CONTRACT half most tests forget: after the window it MAY be
        // reprocessed. Mutation that must kill this test: dropping the TTL
        // check (making the set unbounded).
        let mut s = SeenSet::new(SeenWindow::TtlTicks(100));
        assert!(s.insert(InputId(1), Tick(0)));
        assert!(s.insert(InputId(1), Tick(101)));
    }

    #[test]
    fn unbounded_never_expires() {
        let mut s = SeenSet::new(SeenWindow::Unbounded);
        assert!(s.insert(InputId(1), Tick(0)));
        assert!(!s.insert(InputId(1), Tick(u64::MAX / 2)));
    }

    #[test]
    fn evict_prunes_only_expired() {
        let mut s = SeenSet::new(SeenWindow::TtlTicks(10));
        s.insert(InputId(1), Tick(0));
        s.insert(InputId(2), Tick(95));
        s.evict_expired(Tick(100));
        assert_eq!(s.len(), 1);
        assert!(!s.insert(InputId(2), Tick(100)));
    }
}
