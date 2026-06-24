//! L5.G.6 — Checkpointer: per-reality seed progress persistence.
//!
//! Acceptance criterion: "Resumable: kill seeder mid-flight, restart,
//! completes without duplication." The checkpointer persists progress
//! every N canon entries (default N=100 per layer plan; the seeder's
//! `with_checkpoint_every` overrides for tests).
//!
//! ## Storage location
//!
//! Production binds to a meta-table `reality_seed_checkpoint`
//! (`(reality_id, book_id)` composite PK + `cursor TEXT NULL +
//! entries_committed BIGINT + snapshot_at TIMESTAMPTZ`). The migration
//! lives outside this cycle (added when the seeder is wired into
//! meta-worker / world-service production binary). For foundation
//! scope, the trait + interface are sufficient — tests use an
//! in-memory HashMap.
//!
//! ## Idempotency
//!
//! `save` is an UPSERT (PK = (reality_id, book_id)). Re-saving the
//! same checkpoint is a no-op. The seeder writes the FINAL checkpoint
//! (cursor=None) even if no mid-flight checkpoints fired so that
//! a re-run detects completion.

use crate::reality_seeder::SeederError;
use uuid::Uuid;

/// Per-(reality, book) seed checkpoint row.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeedCheckpoint {
    /// Reality being seeded.
    pub reality_id: Uuid,
    /// Source book.
    pub book_id: Uuid,
    /// The cursor value to pass to the NEXT export_canon_for_seed call.
    /// `None` = seed is complete OR the canon stream was a single page.
    pub cursor: Option<String>,
    /// Total canon entries committed so far (monotonic; only increases).
    pub entries_committed: u64,
    /// RFC3339 snapshot timestamp from the server-side seed_export.
    pub snapshot_at: String,
}

impl SeedCheckpoint {
    /// True if this checkpoint indicates the seed is fully drained
    /// (no more pages + at least one entry committed). Used by the
    /// orchestrator's idempotent-rerun detection.
    pub fn is_complete(&self) -> bool {
        self.cursor.is_none() && self.entries_committed > 0
    }
}

/// L5.G.6 trait — production binds to a meta-table writer; tests use
/// an in-memory fake.
pub trait CheckpointStore {
    /// UPSERT a checkpoint row keyed on `(reality_id, book_id)`.
    fn save(&mut self, cp: SeedCheckpoint) -> Result<(), SeederError>;
    /// Read the latest checkpoint for `(reality_id, book_id)`. Returns
    /// `None` for first-run (no prior checkpoint).
    fn load(
        &self,
        reality_id: Uuid,
        book_id: Uuid,
    ) -> Result<Option<SeedCheckpoint>, SeederError>;
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::collections::HashMap;

    #[derive(Default)]
    struct Fake {
        store: RefCell<HashMap<(Uuid, Uuid), SeedCheckpoint>>,
    }
    impl CheckpointStore for Fake {
        fn save(&mut self, cp: SeedCheckpoint) -> Result<(), SeederError> {
            self.store
                .borrow_mut()
                .insert((cp.reality_id, cp.book_id), cp);
            Ok(())
        }
        fn load(
            &self,
            reality_id: Uuid,
            book_id: Uuid,
        ) -> Result<Option<SeedCheckpoint>, SeederError> {
            Ok(self.store.borrow().get(&(reality_id, book_id)).cloned())
        }
    }

    #[test]
    fn save_then_load_round_trip() {
        let mut f = Fake::default();
        let cp = SeedCheckpoint {
            reality_id: Uuid::from_u128(0x1),
            book_id: Uuid::from_u128(0x2),
            cursor: Some("page-3".into()),
            entries_committed: 300,
            snapshot_at: "2026-05-29T12:00:00Z".into(),
        };
        f.save(cp.clone()).unwrap();
        let got = f
            .load(Uuid::from_u128(0x1), Uuid::from_u128(0x2))
            .unwrap()
            .unwrap();
        assert_eq!(got, cp);
    }

    #[test]
    fn load_returns_none_when_no_prior() {
        let f = Fake::default();
        assert!(f
            .load(Uuid::from_u128(0x1), Uuid::from_u128(0x2))
            .unwrap()
            .is_none());
    }

    #[test]
    fn save_is_upsert_on_pk() {
        let mut f = Fake::default();
        let rid = Uuid::from_u128(0x1);
        let bid = Uuid::from_u128(0x2);
        f.save(SeedCheckpoint {
            reality_id: rid,
            book_id: bid,
            cursor: Some("page-1".into()),
            entries_committed: 100,
            snapshot_at: "t1".into(),
        })
        .unwrap();
        f.save(SeedCheckpoint {
            reality_id: rid,
            book_id: bid,
            cursor: Some("page-2".into()),
            entries_committed: 200,
            snapshot_at: "t2".into(),
        })
        .unwrap();
        let got = f.load(rid, bid).unwrap().unwrap();
        assert_eq!(got.entries_committed, 200);
        assert_eq!(got.cursor.as_deref(), Some("page-2"));
    }

    #[test]
    fn is_complete_when_cursor_none_and_entries_committed() {
        let cp = SeedCheckpoint {
            reality_id: Uuid::nil(),
            book_id: Uuid::nil(),
            cursor: None,
            entries_committed: 5,
            snapshot_at: String::new(),
        };
        assert!(cp.is_complete());
        let cp2 = SeedCheckpoint {
            cursor: Some("x".into()),
            ..cp.clone()
        };
        assert!(!cp2.is_complete());
        let cp3 = SeedCheckpoint {
            entries_committed: 0,
            ..cp
        };
        assert!(!cp3.is_complete());
    }
}
