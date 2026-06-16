//! L5.G audit hook — Q-L1A-3 full audit V1 (no sampling).
//!
//! Per OPEN_QUESTIONS_LOCKED §2 Q-L1A-3:
//!
//! > Full audit from V1, no sampling — ~10 TB / 5y storage; dedicated
//! > audit DB cluster at V2+.
//!
//! The seeder records THREE event classes:
//!
//! 1. **Phase** — milestone within the seed run (validate,
//!    fetch_book_meta, load_checkpoint, transition_active).
//! 2. **CanonUpsert** — one per canon entry written to projection
//!    (carries canon_entry_id + book_id for the audit join).
//! 3. **Failure** — fatal error captured before mark_failed transitions
//!    the reality to `failed_seeding`. Carries the error string for SRE
//!    triage.
//!
//! Production binds [`AuditSink`] to the meta-worker MetaWrite audit
//! chain (same path cycle-4 / cycle-24 use). Tests use an in-memory
//! recorder.

use crate::reality_seeder::SeederError;
use uuid::Uuid;

/// One audit record emitted by the seeder. Variant determines the
/// shape; the production sink translates each into a
/// `meta_write_audit` row (or seeder-specific table, TBD by the
/// downstream wiring cycle).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AuditEvent {
    /// Phase milestone (validate / fetch_book_meta / load_checkpoint /
    /// transition_active).
    Phase {
        /// Reality being seeded.
        reality_id: Uuid,
        /// Phase name (`"validate"`, `"fetch_book_meta"`, etc).
        phase: String,
        /// Audit reason string from the SeedRequest.
        reason: String,
    },
    /// One canon entry upserted to per-reality canon_projection.
    CanonUpsert {
        /// Reality being seeded.
        reality_id: Uuid,
        /// Canon entry UUID upserted.
        canon_entry_id: Uuid,
        /// Owning book UUID (audit-join convenience).
        book_id: Uuid,
    },
    /// Fatal seed failure — recorded immediately before
    /// `mark_failed` issues the seeding → failed_seeding transition.
    Failure {
        /// Reality being seeded.
        reality_id: Uuid,
        /// Audit reason from the SeedRequest.
        reason: String,
        /// `SeederError` string for SRE triage.
        error: String,
    },
}

impl AuditEvent {
    /// Constructor for [`AuditEvent::Phase`].
    pub fn phase(reality_id: Uuid, phase: &str, reason: &str) -> Self {
        AuditEvent::Phase {
            reality_id,
            phase: phase.to_string(),
            reason: reason.to_string(),
        }
    }

    /// Constructor for [`AuditEvent::CanonUpsert`].
    pub fn canon_upsert(reality_id: Uuid, canon_entry_id: Uuid, book_id: Uuid) -> Self {
        AuditEvent::CanonUpsert {
            reality_id,
            canon_entry_id,
            book_id,
        }
    }

    /// Constructor for [`AuditEvent::Failure`].
    pub fn failure(reality_id: Uuid, reason: &str, error: String) -> Self {
        AuditEvent::Failure {
            reality_id,
            reason: reason.to_string(),
            error,
        }
    }

    /// True iff this is a Phase event (used by audit assertions in tests).
    pub fn is_phase(&self) -> bool {
        matches!(self, AuditEvent::Phase { .. })
    }

    /// True iff this is a CanonUpsert event.
    pub fn is_canon_upsert(&self) -> bool {
        matches!(self, AuditEvent::CanonUpsert { .. })
    }

    /// True iff this is a Failure event.
    pub fn is_failure(&self) -> bool {
        matches!(self, AuditEvent::Failure { .. })
    }
}

/// Audit sink — production binds to the meta-worker MetaWrite audit
/// chain. Failure to record is FATAL per Q-L1A-3 (no sampling) — the
/// seeder bubbles up via [`SeederError::Audit`] and marks the reality
/// failed.
pub trait AuditSink {
    /// Record one audit event. Failure returns
    /// [`SeederError::Audit`] which the orchestrator treats as fatal
    /// (Q-L1A-3 no sampling — every write must be audited).
    fn record(&mut self, event: AuditEvent) -> Result<(), SeederError>;
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    #[derive(Default)]
    struct Recorder {
        events: RefCell<Vec<AuditEvent>>,
    }
    impl AuditSink for Recorder {
        fn record(&mut self, event: AuditEvent) -> Result<(), SeederError> {
            self.events.borrow_mut().push(event);
            Ok(())
        }
    }

    #[test]
    fn variants_constructible_and_classifiable() {
        let p = AuditEvent::phase(Uuid::from_u128(0x1), "validate", "r");
        let c = AuditEvent::canon_upsert(
            Uuid::from_u128(0x1),
            Uuid::from_u128(0x2),
            Uuid::from_u128(0x3),
        );
        let f = AuditEvent::failure(Uuid::from_u128(0x1), "r", "boom".into());
        assert!(p.is_phase());
        assert!(c.is_canon_upsert());
        assert!(f.is_failure());
        assert!(!p.is_canon_upsert());
        assert!(!c.is_failure());
        assert!(!f.is_phase());
    }

    #[test]
    fn recorder_captures_events() {
        let mut r = Recorder::default();
        r.record(AuditEvent::phase(Uuid::from_u128(0x1), "validate", "r"))
            .unwrap();
        r.record(AuditEvent::canon_upsert(
            Uuid::from_u128(0x1),
            Uuid::from_u128(0x2),
            Uuid::from_u128(0x3),
        ))
        .unwrap();
        assert_eq!(r.events.borrow().len(), 2);
    }
}
