//! L5.G.7 — Lifecycle transitioner: wraps cycle-5 AttemptStateTransition.
//!
//! The provisioner (cycle 5, `src/provisioner.rs`) uses an `Effects`
//! trait with `transition_to(reality_id, from, to, reason)`. The
//! seeder uses the SAME RPC under the hood but exposes a stricter
//! enum-typed surface (`RealityStatus::{Seeding, Active, FailedSeeding}`)
//! so the orchestrator can't accidentally transition to an
//! out-of-flow state.
//!
//! ## State flow
//!
//! ```text
//!  provisioner step 9 → status=seeding
//!                            │
//!                            │  L5.G run() drives here
//!                            ▼
//!         ┌──────────────────────────────────────┐
//!         │  seeding ──happy─→ active            │ ← seeder success
//!         │  seeding ──fail──→ failed_seeding    │ ← seeder fatal error
//!         └──────────────────────────────────────┘
//!                            │
//!                            │  SRE retry path
//!                            ▼
//!                  failed_seeding → seeding (manual)
//! ```
//!
//! The `failed_seeding → seeding` transition is owned by the SRE
//! runbook (L5.G.10); the seeder never performs it itself (defense vs
//! infinite-loop bug).
//!
//! ## Q-IDs honored
//!
//! - Cycle-5 contract: the underlying transition call routes through
//!   `MetaWrite` → `state_transitions_audit` so every change is
//!   audit-trailed.

use crate::reality_seeder::SeederError;
use uuid::Uuid;

/// L5.G allowed reality statuses. Subset of the full
/// `reality_registry.status` enum — the seeder only ever sees these
/// three values.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RealityStatus {
    /// Provisioner step 9 → seeding in flight.
    Seeding,
    /// Seed completed; reality open for gameplay.
    Active,
    /// Fatal seed failure; SRE intervention required (L5.G.10 runbook).
    FailedSeeding,
}

impl RealityStatus {
    /// String form matching `reality_registry.status` text values.
    pub fn as_str(&self) -> &'static str {
        match self {
            RealityStatus::Seeding => "seeding",
            RealityStatus::Active => "active",
            RealityStatus::FailedSeeding => "failed_seeding",
        }
    }
}

/// L5.G.7 trait. Production binds to the meta-worker MetaWrite path
/// (`AttemptStateTransition` RPC) — same as cycle-5 provisioner's
/// `Effects::transition_to`. Tests inject in-memory fakes that record
/// the transition tuple.
pub trait LifecycleTransitioner {
    /// Transition `reality_id` from `from` to `to` with audit reason.
    /// Returns `SeederError::Lifecycle` on disallowed transitions or
    /// CAS failure (someone else moved the reality first).
    fn transition(
        &mut self,
        reality_id: Uuid,
        from: RealityStatus,
        to: RealityStatus,
        reason: &str,
    ) -> Result<(), SeederError>;
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    #[derive(Default)]
    struct Recorder {
        calls: RefCell<Vec<(Uuid, RealityStatus, RealityStatus, String)>>,
        reject_next: RefCell<bool>,
    }
    impl LifecycleTransitioner for Recorder {
        fn transition(
            &mut self,
            reality_id: Uuid,
            from: RealityStatus,
            to: RealityStatus,
            reason: &str,
        ) -> Result<(), SeederError> {
            if *self.reject_next.borrow() {
                *self.reject_next.borrow_mut() = false;
                return Err(SeederError::Lifecycle(format!(
                    "rejected: {:?} → {:?}",
                    from, to
                )));
            }
            self.calls
                .borrow_mut()
                .push((reality_id, from, to, reason.into()));
            Ok(())
        }
    }

    #[test]
    fn status_as_str_matches_registry_enum() {
        assert_eq!(RealityStatus::Seeding.as_str(), "seeding");
        assert_eq!(RealityStatus::Active.as_str(), "active");
        assert_eq!(RealityStatus::FailedSeeding.as_str(), "failed_seeding");
    }

    #[test]
    fn happy_transition_recorded() {
        let mut r = Recorder::default();
        r.transition(
            Uuid::from_u128(0x1),
            RealityStatus::Seeding,
            RealityStatus::Active,
            "test",
        )
        .unwrap();
        let calls = r.calls.borrow();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].1, RealityStatus::Seeding);
        assert_eq!(calls[0].2, RealityStatus::Active);
    }

    #[test]
    fn rejected_transition_returns_error() {
        let mut r = Recorder::default();
        *r.reject_next.borrow_mut() = true;
        let err = r
            .transition(
                Uuid::from_u128(0x1),
                RealityStatus::Seeding,
                RealityStatus::Active,
                "test",
            )
            .unwrap_err();
        assert!(matches!(err, SeederError::Lifecycle(_)));
    }
}
