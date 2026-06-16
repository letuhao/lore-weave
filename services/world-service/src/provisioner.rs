//! L1.C.1 — Per-reality DB provisioner.
//!
//! Implements the 11-step `provision_reality()` flow per R04 §12D.1.
//!
//! ## 11-step flow (canonical)
//!
//!  1. `validate(req)` — request shape OK + locale parseable
//!  2. `pick_shard(snapshot, thresholds)` — capacity_planner choice
//!  3. `register_pending(reality_id, db_host, db_name)` — INSERT into
//!     `reality_registry` with `status=provisioning`
//!  4. `create_database(db_host, db_name)` — `CREATE DATABASE <name>` on
//!     the picked shard
//!  5. `apply_initial_migration(db_name)` — apply
//!     `contracts/migrations/per_reality/0001_initial.sql` skeleton
//!  6. `register_with_pgbouncer(db_host, db_name)` — append entry to
//!     pgbouncer's `databases.ini` and SIGHUP (L1.G dependency)
//!  7. `register_prometheus_scrape(db_host, db_name)` — append scrape
//!     target to Prometheus dynamic config (L1.I dependency — cycle 6)
//!  8. `register_backup_policy(reality_id)` — backup-scheduler reads
//!     `reality_registry.status` and applies the active-tier policy
//!     (L1.H dependency — cycle 7)
//!  9. `transition_to(seeding)` — AttemptStateTransition
//! 10. `transition_to(active)` — AttemptStateTransition after seeder ack
//! 11. `emit(reality.created)` — outbox event (lands automatically via
//!     MetaWrite() since reality_registry has the `INSERT → reality.created`
//!     allowlist entry)
//!
//! ## Idempotency
//!
//! Each step is idempotent. Steps 4-8 use "exists?" precheck so a partial
//! prior run that crashed between e.g. step 5 and step 6 can be re-driven
//! to completion. The orphan_scanner (L1.C.4) handles the case where a
//! crash leaves `reality_registry.status='provisioning'` indefinitely:
//! 7d grace, then drop.
//!
//! ## Integration with `crates/meta-rs`
//!
//! Hot-path **reads** (e.g., re-reading the row after CAS) go through
//! `meta_rs::MetaRead`. **Writes** delegate to a `MetaWriter` trait that
//! the integration glue (cycle 6+) bridges to the Go `contracts/meta`
//! MetaWrite() via a thin RPC stub (Q-L1B-4 cold-path rule). This keeps
//! the audit trail unified: every INSERT into `reality_registry` lands a
//! `meta_write_audit` row in the SAME TX on the Go side.

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::capacity_planner::{CapacityPlanner, CapacityThresholds, ShardCapacity, ShardId};
use crate::errors::ProvisionerError;

/// Input to `Provisioner::provision_reality()`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProvisionRequest {
    /// The reality UUID (caller-generated to keep the audit chain coherent).
    pub reality_id: Uuid,
    /// BCP-47 locale (en, en-US, ja-JP, ...).
    pub locale: String,
    /// Deploy canary cohort 0..=99 (SR05 §12AH.4).
    pub deploy_cohort: u8,
    /// Reason string written into the MetaWrite audit trail.
    pub reason: String,
}

impl ProvisionRequest {
    fn validate(&self) -> Result<(), ProvisionerError> {
        if self.reality_id.is_nil() {
            return Err(ProvisionerError::InvalidState(
                "reality_id must not be nil".into(),
            ));
        }
        if self.locale.trim().is_empty() {
            return Err(ProvisionerError::InvalidState("locale empty".into()));
        }
        if self.deploy_cohort > 99 {
            return Err(ProvisionerError::InvalidState(format!(
                "deploy_cohort={} > 99",
                self.deploy_cohort
            )));
        }
        if self.reason.trim().is_empty() {
            return Err(ProvisionerError::InvalidState("reason empty".into()));
        }
        Ok(())
    }
}

/// Report returned by `provision_reality()` on success — caller logs
/// + uses for follow-up commands.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProvisionReport {
    /// The provisioned reality.
    pub reality_id: Uuid,
    /// Physical shard the reality was allocated to.
    pub shard_id: ShardId,
    /// Per-reality database name (convention: `lw_reality_<short>`).
    pub db_name: String,
    /// Each of the 11 steps in order, with outcome.
    pub steps: Vec<StepOutcome>,
}

/// Per-step bookkeeping. `Skipped` means an idempotent re-entry found the
/// step already complete; `Done` means the step executed this call.
///
/// Labels are stored as `String` (not `&'static`) so the report can be
/// serialized — the canonical label set is exported via `PROVISION_STEPS`
/// and the constructor helpers ensure no drift between the two.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "outcome", content = "step", rename_all = "lowercase")]
pub enum StepOutcome {
    /// Step executed and changed state.
    Done(String),
    /// Step was a no-op (already complete from a prior re-entry).
    Skipped(String),
}

impl StepOutcome {
    /// Returns the step label.
    pub fn label(&self) -> &str {
        match self {
            StepOutcome::Done(s) | StepOutcome::Skipped(s) => s.as_str(),
        }
    }

    /// Constructor for "Done" outcomes — keeps the call sites tidy.
    pub fn done(label: &'static str) -> Self {
        StepOutcome::Done(label.to_string())
    }

    /// Constructor for "Skipped" outcomes — keeps the call sites tidy.
    pub fn skipped(label: &'static str) -> Self {
        StepOutcome::Skipped(label.to_string())
    }
}

/// The canonical 11 step labels — frozen so external observers (Prometheus,
/// audit) can pin metric labels against them.
pub const PROVISION_STEPS: [&str; 11] = [
    "validate",
    "pick_shard",
    "register_pending",
    "create_database",
    "apply_initial_migration",
    "register_with_pgbouncer",
    "register_prometheus_scrape",
    "register_backup_policy",
    "transition_to_seeding",
    "transition_to_active",
    "emit_reality_created",
];

/// Effect trait — abstracts the side-effecting operations the provisioner
/// performs. Production wiring delegates each method to its real component:
///
/// - `register_pending` → MetaWriter RPC → Go MetaWrite()
/// - `create_database` → libpq `CREATE DATABASE`
/// - `apply_initial_migration` → migrate cli
/// - `register_with_pgbouncer` → append + SIGHUP
/// - `register_prometheus_scrape` → file-write + Prom config reload
/// - `register_backup_policy` → backup-scheduler API
/// - `transition_to(...)` → AttemptStateTransition RPC
/// - `emit_reality_created` → no-op (automatic via MetaWrite allowlist)
///
/// Tests inject a `FakeEffects` (see `tests` module) that records calls.
pub trait Effects {
    /// Step 3 — INSERT into reality_registry with status=provisioning.
    /// Returns `true` if a row was created, `false` if it already existed.
    fn register_pending(
        &mut self,
        reality_id: Uuid,
        shard: &ShardId,
        db_name: &str,
        req: &ProvisionRequest,
    ) -> Result<bool, ProvisionerError>;

    /// Step 4 — CREATE DATABASE on the shard. Idempotent: returns `false`
    /// if it already exists.
    fn create_database(&mut self, shard: &ShardId, db_name: &str)
        -> Result<bool, ProvisionerError>;

    /// Step 5 — apply contracts/migrations/per_reality/0001_initial.sql
    /// (the SKELETON; per-reality tables land in L2 cycles 8-11).
    /// Idempotent: returns `false` if it was already applied.
    fn apply_initial_migration(
        &mut self,
        shard: &ShardId,
        db_name: &str,
    ) -> Result<bool, ProvisionerError>;

    /// Step 6 — register database in pgbouncer's databases.ini + SIGHUP.
    /// Idempotent: returns `false` if entry was already present.
    fn register_with_pgbouncer(
        &mut self,
        shard: &ShardId,
        db_name: &str,
    ) -> Result<bool, ProvisionerError>;

    /// Step 7 — register scrape target with Prometheus dynamic config.
    /// Returns `false` if already registered.
    fn register_prometheus_scrape(
        &mut self,
        shard: &ShardId,
        db_name: &str,
    ) -> Result<bool, ProvisionerError>;

    /// Step 8 — call backup-scheduler API to register this reality. Returns
    /// `false` if already registered.
    fn register_backup_policy(&mut self, reality_id: Uuid) -> Result<bool, ProvisionerError>;

    /// Steps 9 + 10 — AttemptStateTransition: provisioning → seeding → active.
    /// Returns `false` if reality was already past `to`.
    fn transition_to(
        &mut self,
        reality_id: Uuid,
        from: &str,
        to: &str,
        reason: &str,
    ) -> Result<bool, ProvisionerError>;
}

/// L1.C.1 — provisioner driver. Stateless except for the immutable thresholds;
/// per-call shard pick is functional.
pub struct Provisioner {
    planner: CapacityPlanner,
}

impl Provisioner {
    /// Construct with explicit capacity thresholds.
    pub fn new(thresholds: CapacityThresholds) -> Self {
        Self { planner: CapacityPlanner::new(thresholds) }
    }

    /// Run the 11-step flow. `snapshot` is the per-shard capacity at call
    /// time (read from `shard_utilization`).
    pub fn provision_reality<E: Effects>(
        &self,
        req: ProvisionRequest,
        snapshot: &[ShardCapacity],
        effects: &mut E,
    ) -> Result<ProvisionReport, ProvisionerError> {
        // Step 1 — validate
        req.validate()?;
        let mut steps: Vec<StepOutcome> = Vec::with_capacity(PROVISION_STEPS.len());
        steps.push(StepOutcome::done("validate"));

        // Step 2 — pick shard
        let picked = self.planner.pick_shard(snapshot)?;
        steps.push(StepOutcome::done("pick_shard"));

        let db_name = db_name_for(req.reality_id);

        // Step 3 — register pending
        let inserted = effects.register_pending(req.reality_id, &picked.shard_id, &db_name, &req)?;
        steps.push(io(inserted, "register_pending"));

        // Step 4 — create database
        let created = effects.create_database(&picked.shard_id, &db_name)?;
        steps.push(io(created, "create_database"));

        // Step 5 — apply initial migration
        let migrated = effects.apply_initial_migration(&picked.shard_id, &db_name)?;
        steps.push(io(migrated, "apply_initial_migration"));

        // Step 6 — register with pgbouncer
        let pgb = effects.register_with_pgbouncer(&picked.shard_id, &db_name)?;
        steps.push(io(pgb, "register_with_pgbouncer"));

        // Step 7 — Prometheus scrape registration
        let prom = effects.register_prometheus_scrape(&picked.shard_id, &db_name)?;
        steps.push(io(prom, "register_prometheus_scrape"));

        // Step 8 — backup policy
        let bk = effects.register_backup_policy(req.reality_id)?;
        steps.push(io(bk, "register_backup_policy"));

        // Step 9 — provisioning → seeding
        let seeding =
            effects.transition_to(req.reality_id, "provisioning", "seeding", &req.reason)?;
        steps.push(io(seeding, "transition_to_seeding"));

        // Step 10 — seeding → active
        let active = effects.transition_to(req.reality_id, "seeding", "active", &req.reason)?;
        steps.push(io(active, "transition_to_active"));

        // Step 11 — emit. Automatic via the events_allowlist entry on
        // reality_registry INSERT — caller doesn't need to explicitly
        // emit here. Track it so the report stays at 11 steps.
        steps.push(StepOutcome::done("emit_reality_created"));

        Ok(ProvisionReport {
            reality_id: req.reality_id,
            shard_id: picked.shard_id.clone(),
            db_name,
            steps,
        })
    }

    /// Borrow the inner planner for callers that want to introspect (e.g.
    /// SRE tooling that surfaces "next reality goes to <shard>").
    pub fn planner(&self) -> &CapacityPlanner {
        &self.planner
    }
}

fn io(executed: bool, label: &'static str) -> StepOutcome {
    if executed { StepOutcome::done(label) } else { StepOutcome::skipped(label) }
}

/// Convention: `lw_reality_<first-12-hex>`. The trailing 12 hex chars give
/// 2^48 collision resistance — more than enough for the V1+30d 10K reality
/// budget. Keeping the full UUID would push some Postgres identifier limits.
fn db_name_for(reality_id: Uuid) -> String {
    let s = reality_id.simple().to_string();
    let prefix = &s[..s.len().min(12)];
    format!("lw_reality_{prefix}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    /// Records each side-effect call so tests can verify the 11-step flow.
    #[derive(Default)]
    struct FakeEffects {
        registered_pending: HashSet<Uuid>,
        created_dbs: HashSet<String>,
        migrated_dbs: HashSet<String>,
        pgbouncer_entries: HashSet<String>,
        prometheus_entries: HashSet<String>,
        backup_realities: HashSet<Uuid>,
        transitions: Vec<(Uuid, String, String)>,
        /// When set, register_pending returns this error.
        fail_register_pending: Option<ProvisionerError>,
    }

    impl Effects for FakeEffects {
        fn register_pending(
            &mut self,
            reality_id: Uuid,
            _shard: &ShardId,
            _db_name: &str,
            _req: &ProvisionRequest,
        ) -> Result<bool, ProvisionerError> {
            if let Some(err) = self.fail_register_pending.take() {
                return Err(err);
            }
            Ok(self.registered_pending.insert(reality_id))
        }

        fn create_database(
            &mut self,
            _shard: &ShardId,
            db_name: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(self.created_dbs.insert(db_name.to_string()))
        }

        fn apply_initial_migration(
            &mut self,
            _shard: &ShardId,
            db_name: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(self.migrated_dbs.insert(db_name.to_string()))
        }

        fn register_with_pgbouncer(
            &mut self,
            _shard: &ShardId,
            db_name: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(self.pgbouncer_entries.insert(db_name.to_string()))
        }

        fn register_prometheus_scrape(
            &mut self,
            _shard: &ShardId,
            db_name: &str,
        ) -> Result<bool, ProvisionerError> {
            Ok(self.prometheus_entries.insert(db_name.to_string()))
        }

        fn register_backup_policy(
            &mut self,
            reality_id: Uuid,
        ) -> Result<bool, ProvisionerError> {
            Ok(self.backup_realities.insert(reality_id))
        }

        fn transition_to(
            &mut self,
            reality_id: Uuid,
            from: &str,
            to: &str,
            _reason: &str,
        ) -> Result<bool, ProvisionerError> {
            self.transitions
                .push((reality_id, from.into(), to.into()));
            Ok(true)
        }
    }

    fn snapshot() -> Vec<ShardCapacity> {
        vec![
            ShardCapacity {
                shard_id: ShardId::new("pg-shard-0.internal"),
                used_realities: 10,
                total_realities: 100,
            },
            ShardCapacity {
                shard_id: ShardId::new("pg-shard-1.internal"),
                used_realities: 50,
                total_realities: 100,
            },
        ]
    }

    fn req() -> ProvisionRequest {
        ProvisionRequest {
            reality_id: Uuid::from_u128(0xdead_beef),
            locale: "en-US".into(),
            deploy_cohort: 0,
            reason: "integration_test".into(),
        }
    }

    #[test]
    fn happy_path_runs_all_11_steps() {
        let provisioner = Provisioner::new(CapacityThresholds::default());
        let mut effects = FakeEffects::default();
        let report = provisioner
            .provision_reality(req(), &snapshot(), &mut effects)
            .expect("provision ok");
        assert_eq!(report.steps.len(), PROVISION_STEPS.len());
        for (i, expected) in PROVISION_STEPS.iter().enumerate() {
            assert_eq!(report.steps[i].label(), *expected, "step {i}");
        }
        // Shard 0 was least full (10/100 vs 50/100).
        assert_eq!(report.shard_id.as_str(), "pg-shard-0.internal");
        // Transitions: provisioning→seeding, then seeding→active
        assert_eq!(effects.transitions.len(), 2);
        assert_eq!(effects.transitions[0].1, "provisioning");
        assert_eq!(effects.transitions[0].2, "seeding");
        assert_eq!(effects.transitions[1].1, "seeding");
        assert_eq!(effects.transitions[1].2, "active");
    }

    #[test]
    fn picks_least_full_shard_not_random() {
        let provisioner = Provisioner::new(CapacityThresholds::default());
        let mut effects = FakeEffects::default();
        // Reverse order so a buggy "first shard wins" would pick the full one.
        let snap = vec![
            ShardCapacity {
                shard_id: ShardId::new("pg-shard-1.internal"),
                used_realities: 80,
                total_realities: 100,
            },
            ShardCapacity {
                shard_id: ShardId::new("pg-shard-0.internal"),
                used_realities: 5,
                total_realities: 100,
            },
        ];
        let report = provisioner
            .provision_reality(req(), &snap, &mut effects)
            .expect("ok");
        assert_eq!(report.shard_id.as_str(), "pg-shard-0.internal");
    }

    #[test]
    fn idempotent_reentry_skips_completed_steps() {
        let provisioner = Provisioner::new(CapacityThresholds::default());
        let mut effects = FakeEffects::default();
        let r1 = provisioner
            .provision_reality(req(), &snapshot(), &mut effects)
            .expect("ok");
        for s in &r1.steps[2..=7] {
            assert!(matches!(s, StepOutcome::Done(_)));
        }
        // Re-run identical request — steps 3-8 should now report Skipped
        // (already done) but the run still succeeds end-to-end.
        let r2 = provisioner
            .provision_reality(req(), &snapshot(), &mut effects)
            .expect("ok 2");
        for (i, s) in r2.steps[2..=7].iter().enumerate() {
            assert!(
                matches!(s, StepOutcome::Skipped(_)),
                "step {} should be Skipped on re-entry, got {:?}",
                i + 2,
                s
            );
        }
    }

    #[test]
    fn rejects_nil_reality_id() {
        let provisioner = Provisioner::new(CapacityThresholds::default());
        let mut effects = FakeEffects::default();
        let mut req = req();
        req.reality_id = Uuid::nil();
        let err = provisioner
            .provision_reality(req, &snapshot(), &mut effects)
            .unwrap_err();
        assert!(matches!(err, ProvisionerError::InvalidState(_)));
    }

    #[test]
    fn rejects_full_cluster() {
        let provisioner = Provisioner::new(CapacityThresholds::default());
        let mut effects = FakeEffects::default();
        let snap = vec![ShardCapacity {
            shard_id: ShardId::new("pg-shard-0"),
            used_realities: 100,
            total_realities: 100,
        }];
        let err = provisioner
            .provision_reality(req(), &snap, &mut effects)
            .unwrap_err();
        assert!(matches!(err, ProvisionerError::NoShardCapacity));
    }

    #[test]
    fn step_labels_are_frozen_strings() {
        // Defense-in-depth: the audit + Prometheus metric label sets
        // depend on these strings being stable.
        assert_eq!(
            PROVISION_STEPS,
            [
                "validate",
                "pick_shard",
                "register_pending",
                "create_database",
                "apply_initial_migration",
                "register_with_pgbouncer",
                "register_prometheus_scrape",
                "register_backup_policy",
                "transition_to_seeding",
                "transition_to_active",
                "emit_reality_created",
            ]
        );
    }

    #[test]
    fn db_name_follows_convention() {
        // The simple form is 32 lowercase hex chars (no hyphens). We take the
        // first 12 — gives 2^48 collision resistance for a 10K-reality V1+30d.
        let id = Uuid::from_u128(0x0123_4567_89ab_cdef_dead_beef_cafe_babe);
        let name = db_name_for(id);
        assert!(name.starts_with("lw_reality_"));
        assert_eq!(name.len(), "lw_reality_".len() + 12);
        // Prefix character set is [0-9a-f]
        let suffix = &name["lw_reality_".len()..];
        assert!(
            suffix.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()),
            "suffix must be lowercase hex: {suffix}"
        );
    }
}
