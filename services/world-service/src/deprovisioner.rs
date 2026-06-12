//! L1.C.2 — Per-reality DB deprovisioner.
//!
//! Implements the 6-step `deprovision_reality()` flow per R04 §12D.1.
//!
//! ## 6-step flow (canonical)
//!
//!  1. `transition_to(soft_deleted)` — `reality_registry.status` flip with
//!     CAS on (active|frozen|archived_verified). Out-of-state input is a
//!     no-op (idempotent re-entry returns Skipped).
//!  2. `unregister_with_pgbouncer(db_host, db_name)` — remove databases.ini
//!     entry + SIGHUP. Idempotent: missing entry returns Skipped.
//!  3. `unregister_prometheus_scrape(db_host, db_name)` — remove scrape
//!     target.
//!  4. `unregister_backup_policy(reality_id)` — backup-scheduler stops
//!     scheduling new backups; existing snapshots retained per backup tier.
//!  5. `drop_database(db_host, db_name)` — `DROP DATABASE IF EXISTS` on
//!     the shard. Pre-condition: orphan_scanner grace expired
//!     (`soft_deleted_at` >= 7d ago) UNLESS `force=true`.
//!  6. `transition_to(dropped)` — terminal state. After this, the row
//!     stays in `reality_registry` forever (as audit record) but is
//!     never picked up again by any router or backup.
//!
//! ## Idempotency
//!
//! The deprovisioner is safe to call multiple times. Step 1 uses
//! AttemptStateTransition with CAS — a second call sees the reality
//! already `soft_deleted` and returns `Skipped`. Subsequent steps query
//! "is the entry/policy/database present?" before acting.

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::errors::ProvisionerError;
use crate::provisioner::{Effects, StepOutcome};

/// Input to `Deprovisioner::deprovision_reality()`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DeprovisionRequest {
    /// Target reality.
    pub reality_id: Uuid,
    /// Physical shard the reality lives on (looked up via MetaRead).
    pub shard_host: String,
    /// Per-reality database name.
    pub db_name: String,
    /// Audit reason.
    pub reason: String,
    /// Bypass the 7-day soft-delete grace. ADMIN ONLY — only use after
    /// explicit operator confirmation (S5 Tier 2 audited path).
    pub force: bool,
}

impl DeprovisionRequest {
    fn validate(&self) -> Result<(), ProvisionerError> {
        if self.reality_id.is_nil() {
            return Err(ProvisionerError::InvalidState("reality_id nil".into()));
        }
        if self.shard_host.trim().is_empty() {
            return Err(ProvisionerError::InvalidState("shard_host empty".into()));
        }
        if self.db_name.trim().is_empty() {
            return Err(ProvisionerError::InvalidState("db_name empty".into()));
        }
        if self.reason.trim().is_empty() {
            return Err(ProvisionerError::InvalidState("reason empty".into()));
        }
        Ok(())
    }
}

/// Report returned by `deprovision_reality()`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DeprovisionReport {
    /// The reality this report describes.
    pub reality_id: Uuid,
    /// Each of the 6 steps in order, with outcome.
    pub steps: Vec<StepOutcome>,
}

/// The canonical 6 step labels — frozen so the Prometheus + audit labels
/// stay stable as the impl evolves.
pub const DEPROVISION_STEPS: [&str; 6] = [
    "transition_to_soft_deleted",
    "unregister_with_pgbouncer",
    "unregister_prometheus_scrape",
    "unregister_backup_policy",
    "drop_database",
    "transition_to_dropped",
];

/// Extra side-effects beyond the shared `Effects` (provisioner) trait.
/// Tests inject a fake; production wiring delegates to the same RPC stubs
/// the provisioner uses.
pub trait DeprovisionEffects {
    /// Step 2 — remove pgbouncer entry; returns false if entry already absent.
    fn unregister_with_pgbouncer(
        &mut self,
        shard_host: &str,
        db_name: &str,
    ) -> Result<bool, ProvisionerError>;

    /// Step 3 — remove Prometheus scrape target; returns false if absent.
    fn unregister_prometheus_scrape(
        &mut self,
        shard_host: &str,
        db_name: &str,
    ) -> Result<bool, ProvisionerError>;

    /// Step 4 — unregister from backup-scheduler; returns false if not
    /// registered. (Existing snapshots are NOT deleted here — retention
    /// is governed by `contracts/backup/policy.yaml` in L1.H.)
    fn unregister_backup_policy(
        &mut self,
        reality_id: Uuid,
    ) -> Result<bool, ProvisionerError>;

    /// Step 5 — DROP DATABASE on the shard; returns false if DB absent.
    /// Implementations MUST gate on `force || grace_expired`.
    fn drop_database(
        &mut self,
        shard_host: &str,
        db_name: &str,
        force: bool,
    ) -> Result<bool, ProvisionerError>;
}

/// L1.C.2 — deprovisioner driver. Stateless.
pub struct Deprovisioner;

impl Deprovisioner {
    /// Run the 6-step flow. Idempotent: re-entry after partial completion
    /// drives any incomplete steps to completion and returns Skipped for
    /// the ones already done.
    pub fn deprovision_reality<E, D>(
        req: DeprovisionRequest,
        provisioner_effects: &mut E,
        deprov_effects: &mut D,
    ) -> Result<DeprovisionReport, ProvisionerError>
    where
        E: Effects,
        D: DeprovisionEffects,
    {
        req.validate()?;
        let mut steps: Vec<StepOutcome> = Vec::with_capacity(DEPROVISION_STEPS.len());

        // Step 1 — flip to soft_deleted (CAS via AttemptStateTransition).
        // The previous state can be active / frozen / archived_verified.
        // We try each in turn until one succeeds; any other reply is a
        // no-op (likely already soft_deleted from a prior call).
        let mut flipped = false;
        for from in ["active", "frozen", "archived_verified"] {
            match provisioner_effects.transition_to(
                req.reality_id,
                from,
                "soft_deleted",
                &req.reason,
            ) {
                Ok(true) => {
                    flipped = true;
                    break;
                }
                Ok(false) => continue,
                // Mutual-exclusion / invalid transition just means the
                // reality wasn't in `from`; try the next valid pre-state.
                Err(ProvisionerError::Meta(meta_rs::MetaError::InvalidTransition { .. })) => {
                    continue
                }
                Err(ProvisionerError::Meta(meta_rs::MetaError::MutualExclusion)) => continue,
                Err(other) => return Err(other),
            }
        }
        steps.push(io(flipped, "transition_to_soft_deleted"));

        // Step 2 — remove pgbouncer entry
        let pgb = deprov_effects
            .unregister_with_pgbouncer(&req.shard_host, &req.db_name)?;
        steps.push(io(pgb, "unregister_with_pgbouncer"));

        // Step 3 — remove Prometheus scrape
        let prom = deprov_effects
            .unregister_prometheus_scrape(&req.shard_host, &req.db_name)?;
        steps.push(io(prom, "unregister_prometheus_scrape"));

        // Step 4 — unregister backup
        let bk = deprov_effects.unregister_backup_policy(req.reality_id)?;
        steps.push(io(bk, "unregister_backup_policy"));

        // Step 5 — DROP DATABASE (gated on grace || force)
        let dropped =
            deprov_effects.drop_database(&req.shard_host, &req.db_name, req.force)?;
        steps.push(io(dropped, "drop_database"));

        // Step 6 — terminal transition
        let term = provisioner_effects
            .transition_to(req.reality_id, "soft_deleted", "dropped", &req.reason)?;
        steps.push(io(term, "transition_to_dropped"));

        Ok(DeprovisionReport { reality_id: req.reality_id, steps })
    }
}

fn io(executed: bool, label: &'static str) -> StepOutcome {
    if executed { StepOutcome::done(label) } else { StepOutcome::skipped(label) }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::provisioner::Effects as ProvEffects;
    use std::collections::HashSet;

    #[derive(Default)]
    struct FakeProvEffects {
        transitions: Vec<(Uuid, String, String)>,
        // returns Ok(false) for the "already past" path
        force_skip_first_n_transitions: usize,
    }

    impl ProvEffects for FakeProvEffects {
        fn register_pending(
            &mut self,
            _reality_id: Uuid,
            _shard: &crate::capacity_planner::ShardId,
            _db_name: &str,
            _req: &crate::provisioner::ProvisionRequest,
        ) -> Result<bool, ProvisionerError> {
            Ok(true)
        }
        fn create_database(
            &mut self,
            _: &crate::capacity_planner::ShardId,
            _: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(true)
        }
        fn apply_initial_migration(
            &mut self,
            _: &crate::capacity_planner::ShardId,
            _: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(true)
        }
        fn register_with_pgbouncer(
            &mut self,
            _: &crate::capacity_planner::ShardId,
            _: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(true)
        }
        fn register_prometheus_scrape(
            &mut self,
            _: &crate::capacity_planner::ShardId,
            _: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(true)
        }
        fn register_backup_policy(
            &mut self,
            _: Uuid,
        ) -> Result<bool, ProvisionerError> {
            Ok(true)
        }
        fn transition_to(
            &mut self,
            reality_id: Uuid,
            from: &str,
            to: &str,
            _reason: &str,
        ) -> Result<bool, ProvisionerError> {
            self.transitions.push((reality_id, from.into(), to.into()));
            if self.force_skip_first_n_transitions > 0 {
                self.force_skip_first_n_transitions -= 1;
                return Ok(false);
            }
            Ok(true)
        }
    }

    #[derive(Default)]
    struct FakeDeprov {
        pgbouncer_left: HashSet<String>, // populated with seed entries
        prom_left: HashSet<String>,
        backup_left: HashSet<Uuid>,
        databases_left: HashSet<String>,
        force_seen: Vec<bool>,
    }

    impl DeprovisionEffects for FakeDeprov {
        fn unregister_with_pgbouncer(
            &mut self,
            _shard: &str,
            db_name: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(self.pgbouncer_left.remove(db_name))
        }
        fn unregister_prometheus_scrape(
            &mut self,
            _shard: &str,
            db_name: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(self.prom_left.remove(db_name))
        }
        fn unregister_backup_policy(
            &mut self,
            reality_id: Uuid,
        ) -> Result<bool, ProvisionerError> {
            Ok(self.backup_left.remove(&reality_id))
        }
        fn drop_database(
            &mut self,
            _shard: &str,
            db_name: &str,
            force: bool,
        ) -> Result<bool, ProvisionerError> {
            self.force_seen.push(force);
            Ok(self.databases_left.remove(db_name))
        }
    }

    fn req() -> DeprovisionRequest {
        DeprovisionRequest {
            reality_id: Uuid::from_u128(0x42),
            shard_host: "pg-shard-0.internal".into(),
            db_name: "lw_reality_000000000042".into(),
            reason: "scheduled_close".into(),
            force: false,
        }
    }

    #[test]
    fn happy_path_runs_6_steps() {
        let mut prov = FakeProvEffects::default();
        let mut dep = FakeDeprov {
            pgbouncer_left: ["lw_reality_000000000042".to_string()].into(),
            prom_left: ["lw_reality_000000000042".to_string()].into(),
            backup_left: [Uuid::from_u128(0x42)].into(),
            databases_left: ["lw_reality_000000000042".to_string()].into(),
            ..Default::default()
        };
        let report = Deprovisioner::deprovision_reality(req(), &mut prov, &mut dep)
            .expect("ok");
        assert_eq!(report.steps.len(), 6);
        for (i, expected) in DEPROVISION_STEPS.iter().enumerate() {
            assert_eq!(report.steps[i].label(), *expected);
        }
        // Force was false (no override)
        assert_eq!(dep.force_seen, vec![false]);
    }

    #[test]
    fn idempotent_reentry_skips_completed_steps() {
        let mut prov = FakeProvEffects::default();
        let mut dep = FakeDeprov::default(); // empty: everything already cleaned
        let report =
            Deprovisioner::deprovision_reality(req(), &mut prov, &mut dep).expect("ok");
        // Step 1 still ran (transition_to returns true on first attempt).
        // Steps 2-5 are all Skipped because nothing left.
        assert!(matches!(report.steps[1], StepOutcome::Skipped(_)));
        assert!(matches!(report.steps[2], StepOutcome::Skipped(_)));
        assert!(matches!(report.steps[3], StepOutcome::Skipped(_)));
        assert!(matches!(report.steps[4], StepOutcome::Skipped(_)));
    }

    #[test]
    fn force_flag_propagates_to_drop() {
        let mut prov = FakeProvEffects::default();
        let mut dep = FakeDeprov::default();
        let mut r = req();
        r.force = true;
        let _ = Deprovisioner::deprovision_reality(r, &mut prov, &mut dep).expect("ok");
        assert_eq!(dep.force_seen, vec![true]);
    }

    #[test]
    fn rejects_nil_reality_id() {
        let mut prov = FakeProvEffects::default();
        let mut dep = FakeDeprov::default();
        let mut r = req();
        r.reality_id = Uuid::nil();
        let err = Deprovisioner::deprovision_reality(r, &mut prov, &mut dep).unwrap_err();
        assert!(matches!(err, ProvisionerError::InvalidState(_)));
    }

    #[test]
    fn step_labels_are_frozen() {
        assert_eq!(
            DEPROVISION_STEPS,
            [
                "transition_to_soft_deleted",
                "unregister_with_pgbouncer",
                "unregister_prometheus_scrape",
                "unregister_backup_policy",
                "drop_database",
                "transition_to_dropped",
            ]
        );
    }
}
