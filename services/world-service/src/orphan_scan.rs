//! W5 — orphan classification: what a half-finished provision leaves behind.
//!
//! Provisioning is not one write. It is a registry row, then `CREATE DATABASE`,
//! then migrations, then two lifecycle transitions — across two servers, with no
//! transaction spanning them. Every gap between those steps is a state a crash
//! can leave the platform in, and until `W3` shipped there was no producer to
//! leave one: the sole caller was a drill that cleaned up after itself.
//!
//! `orphan_scanner` was specified for this in cycle 5 and shipped as a scaffold
//! whose dry run classified `let scanned = 0u32` — an empty set, forever. This
//! module is the part that actually decides something, kept **pure** (rows in,
//! findings out) so its behaviour is testable without a database and so a bite
//! can prove each rule fires.
//!
//! ## The four classes, and why the third is the dangerous one
//!
//! | class | shape | why it matters |
//! |---|---|---|
//! | [`Finding::StalledProvision`] | registry row stuck in `provisioning`/`seeding` past the stall window | the provision died mid-flight; a human must decide resume-or-reap |
//! | [`Finding::MissingDatabase`] | registry row points at a database that is not there | reads against it fail at connect; the row lies about what exists |
//! | [`Finding::UntrackedDatabase`] | a `lw_reality_*` database no registry row claims | **capacity silently over-reports.** Occupancy is counted from `reality_registry` (`capacity_glue`), so a database nothing references consumes disk and a real slot while the planner believes the slot is free |
//! | [`Finding::DropEligible`] | `soft_deleted` past the grace period | the reaper's actual work — reported here, acted on elsewhere |
//!
//! `UntrackedDatabase` is the one no other mechanism can see. `capacity_glue`
//! counts registry rows by design (the metrics job that would count databases is
//! unbuilt), so an untracked database is invisible to the one component whose
//! job is knowing how full a shard is.

use serde::Serialize;
use uuid::Uuid;

/// Registry statuses whose provision is still in flight. A row that sits in one
/// of these past the stall window did not finish.
pub const IN_FLIGHT_STATUSES: [&str; 2] = ["provisioning", "seeding"];

/// The status a reality rests in before its grace period expires.
pub const SOFT_DELETED_STATUS: &str = "soft_deleted";

/// Statuses whose per-reality database is expected to EXIST. A registry row in
/// one of these with no database is a [`Finding::MissingDatabase`].
///
/// `provisioning` is deliberately absent: a row is written *before*
/// `CREATE DATABASE` (provisioner step 3 precedes step 4), so a `provisioning`
/// row with no database is the normal state for a few hundred milliseconds and
/// is covered by the stall rule instead.
pub const DB_EXPECTED_STATUSES: [&str; 6] = [
    "seeding",
    "active",
    "migrating",
    "pending_close",
    "frozen",
    "soft_deleted",
];

/// One `reality_registry` row, reduced to what classification needs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegistryRow {
    /// The reality's id.
    pub reality_id: Uuid,
    /// The per-reality database name the row claims.
    pub db_name: String,
    /// The shard host the row is placed on.
    pub db_host: String,
    /// Lifecycle status.
    pub status: String,
    /// Hours since the row was created. Supplied by the caller (read from the
    /// DB) rather than computed here, so this module needs no clock and its
    /// tests need no time control.
    pub age_hours: i64,
}

/// A classified orphan.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "class")]
pub enum Finding {
    /// A provision that never finished.
    StalledProvision {
        /// The reality's id.
        reality_id: Uuid,
        /// The database the row claims.
        db_name: String,
        /// The status it is stuck in.
        status: String,
        /// How long it has been stuck.
        age_hours: i64,
        /// Whether the per-reality database was actually created.
        database_present: bool,
    },
    /// A registry row whose database does not exist.
    MissingDatabase {
        /// The reality's id.
        reality_id: Uuid,
        /// The database the row claims but which is absent.
        db_name: String,
        /// The status the row is in.
        status: String,
    },
    /// A per-reality database no registry row claims — invisible to capacity.
    UntrackedDatabase {
        /// The database found on the shard.
        db_name: String,
    },
    /// A soft-deleted reality whose grace period has expired.
    DropEligible {
        /// The reality's id.
        reality_id: Uuid,
        /// The database to reclaim.
        db_name: String,
        /// How long it has been soft-deleted.
        age_hours: i64,
    },
}

impl Finding {
    /// Short stable slug, used as the `reality_close_audit.event_type` suffix
    /// and as the metric label.
    pub fn class(&self) -> &'static str {
        match self {
            Finding::StalledProvision { .. } => "orphan_partial_provision",
            Finding::MissingDatabase { .. } => "orphan_missing_database",
            Finding::UntrackedDatabase { .. } => "orphan_untracked_database",
            Finding::DropEligible { .. } => "orphan_drop_eligible",
        }
    }

    /// The database this finding is about. EVERY class names one — it is the
    /// only field common to all four, which is why the finding table is keyed
    /// by `(shard_host, db_name)` rather than by reality.
    pub fn db_name(&self) -> &str {
        match self {
            Finding::StalledProvision { db_name, .. }
            | Finding::MissingDatabase { db_name, .. }
            | Finding::UntrackedDatabase { db_name }
            | Finding::DropEligible { db_name, .. } => db_name,
        }
    }

    /// Operator-facing context for the finding. Human triage detail only —
    /// never a second source of truth for anything the columns carry.
    pub fn detail(&self) -> serde_json::Value {
        match self {
            Finding::StalledProvision { status, age_hours, database_present, .. } => {
                serde_json::json!({
                    "status": status,
                    "age_hours": age_hours,
                    "database_present": database_present,
                })
            }
            Finding::MissingDatabase { status, .. } => serde_json::json!({ "status": status }),
            Finding::UntrackedDatabase { .. } => serde_json::json!({
                "note": "no registry row claims this database; capacity counts registry rows, so it is invisible to the planner",
            }),
            Finding::DropEligible { age_hours, .. } => serde_json::json!({
                "age_hours": age_hours,
            }),
        }
    }

    /// The reality this finding concerns, when one is known. An untracked
    /// database has none — that is precisely what is wrong with it.
    pub fn reality_id(&self) -> Option<Uuid> {
        match self {
            Finding::StalledProvision { reality_id, .. }
            | Finding::MissingDatabase { reality_id, .. }
            | Finding::DropEligible { reality_id, .. } => Some(*reality_id),
            Finding::UntrackedDatabase { .. } => None,
        }
    }
}

/// Thresholds governing the scan.
#[derive(Debug, Clone, Copy)]
pub struct ScanThresholds {
    /// Hours a row may sit in an in-flight status before it is stalled.
    pub stall_hours: i64,
    /// Days a `soft_deleted` reality is retained before it may be reclaimed.
    pub grace_days: i64,
}

impl Default for ScanThresholds {
    fn default() -> Self {
        // Must match runbooks/provisioner/orphan_resolution.md and the constants
        // the cycle-5 scaffold published.
        Self { stall_hours: 24, grace_days: 7 }
    }
}

/// Classify the shard's state.
///
/// `rows` must be EVERY `reality_registry` row for the shard being scanned, not
/// just the transient ones: an `active` row is what proves a database is
/// tracked, so filtering to transient statuses first would report every healthy
/// database as untracked. (That inversion is the reason this takes the full set
/// and does its own filtering.)
///
/// `shard_databases` is every `lw_reality_*` database present on the shard.
pub fn classify(
    rows: &[RegistryRow],
    shard_databases: &[String],
    thresholds: ScanThresholds,
) -> Vec<Finding> {
    let mut findings = Vec::new();

    let present = |name: &str| shard_databases.iter().any(|d| d == name);

    for row in rows {
        let in_flight = IN_FLIGHT_STATUSES.contains(&row.status.as_str());
        let db_present = present(&row.db_name);

        if in_flight && row.age_hours >= thresholds.stall_hours {
            findings.push(Finding::StalledProvision {
                reality_id: row.reality_id,
                db_name: row.db_name.clone(),
                status: row.status.clone(),
                age_hours: row.age_hours,
                database_present: db_present,
            });
            // A stalled row is already reported; do not also report its absent
            // database as a separate finding — one broken provision is one
            // problem, and duplicate findings inflate the alert.
            continue;
        }

        if !db_present && DB_EXPECTED_STATUSES.contains(&row.status.as_str()) {
            findings.push(Finding::MissingDatabase {
                reality_id: row.reality_id,
                db_name: row.db_name.clone(),
                status: row.status.clone(),
            });
            continue;
        }

        if row.status == SOFT_DELETED_STATUS && row.age_hours >= thresholds.grace_days * 24 {
            findings.push(Finding::DropEligible {
                reality_id: row.reality_id,
                db_name: row.db_name.clone(),
                age_hours: row.age_hours,
            });
        }
    }

    // Anything on the shard that no row claims — in ANY status.
    for db in shard_databases {
        if !rows.iter().any(|r| &r.db_name == db) {
            findings.push(Finding::UntrackedDatabase { db_name: db.clone() });
        }
    }

    findings
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(status: &str, age_hours: i64, db: &str) -> RegistryRow {
        RegistryRow {
            reality_id: Uuid::new_v4(),
            db_name: db.to_string(),
            db_host: "pg-shard-0.internal".to_string(),
            status: status.to_string(),
            age_hours,
        }
    }

    fn dbs(names: &[&str]) -> Vec<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn healthy_shard_yields_nothing() {
        let rows = vec![row("active", 500, "lw_reality_a"), row("active", 2, "lw_reality_b")];
        let found = classify(&rows, &dbs(&["lw_reality_a", "lw_reality_b"]), ScanThresholds::default());
        assert!(found.is_empty(), "healthy shard produced {found:?}");
    }

    #[test]
    fn stalled_provision_is_flagged_past_the_window() {
        let rows = vec![row("provisioning", 25, "lw_reality_a")];
        let found = classify(&rows, &dbs(&[]), ScanThresholds::default());
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].class(), "orphan_partial_provision");
    }

    #[test]
    fn a_provision_inside_the_window_is_not_an_orphan() {
        // The normal case: a row written seconds ago, database not yet created.
        let rows = vec![row("provisioning", 0, "lw_reality_a")];
        let found = classify(&rows, &dbs(&[]), ScanThresholds::default());
        assert!(found.is_empty(), "a fresh provision must not be reported: {found:?}");
    }

    #[test]
    fn stall_boundary_is_inclusive() {
        let rows = vec![row("seeding", 24, "lw_reality_a")];
        assert_eq!(classify(&rows, &dbs(&["lw_reality_a"]), ScanThresholds::default()).len(), 1);
        let rows = vec![row("seeding", 23, "lw_reality_a")];
        assert!(classify(&rows, &dbs(&["lw_reality_a"]), ScanThresholds::default()).is_empty());
    }

    #[test]
    fn stalled_finding_records_whether_the_database_exists() {
        // The two halves of a broken provision need different remediation, so
        // the finding must distinguish them.
        let rows = vec![row("seeding", 48, "lw_reality_a")];
        let with_db = classify(&rows, &dbs(&["lw_reality_a"]), ScanThresholds::default());
        let without = classify(&rows, &dbs(&[]), ScanThresholds::default());
        match (&with_db[0], &without[0]) {
            (
                Finding::StalledProvision { database_present: true, .. },
                Finding::StalledProvision { database_present: false, .. },
            ) => {}
            other => panic!("database_present not tracked: {other:?}"),
        }
    }

    #[test]
    fn active_row_without_a_database_is_missing_not_stalled() {
        let rows = vec![row("active", 900, "lw_reality_gone")];
        let found = classify(&rows, &dbs(&[]), ScanThresholds::default());
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].class(), "orphan_missing_database");
    }

    #[test]
    fn untracked_database_is_flagged() {
        let found = classify(&[], &dbs(&["lw_reality_ghost"]), ScanThresholds::default());
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].class(), "orphan_untracked_database");
        assert_eq!(found[0].reality_id(), None, "an untracked db has no reality");
    }

    // The inversion this guards: classify() must see NON-transient rows too, or
    // every healthy active database reads as untracked.
    #[test]
    fn active_databases_are_not_reported_as_untracked() {
        let rows = vec![row("active", 100, "lw_reality_a")];
        let found = classify(&rows, &dbs(&["lw_reality_a"]), ScanThresholds::default());
        assert!(
            !found.iter().any(|f| f.class() == "orphan_untracked_database"),
            "a tracked, active database was reported untracked: {found:?}"
        );
    }

    #[test]
    fn soft_deleted_past_grace_is_drop_eligible() {
        let rows = vec![row("soft_deleted", 7 * 24, "lw_reality_a")];
        let found = classify(&rows, &dbs(&["lw_reality_a"]), ScanThresholds::default());
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].class(), "orphan_drop_eligible");
    }

    #[test]
    fn soft_deleted_inside_grace_is_left_alone() {
        let rows = vec![row("soft_deleted", 7 * 24 - 1, "lw_reality_a")];
        let found = classify(&rows, &dbs(&["lw_reality_a"]), ScanThresholds::default());
        assert!(found.is_empty(), "inside grace should be untouched: {found:?}");
    }

    #[test]
    fn one_broken_provision_produces_one_finding() {
        // A stalled row with no database must not ALSO report MissingDatabase.
        let rows = vec![row("seeding", 100, "lw_reality_a")];
        let found = classify(&rows, &dbs(&[]), ScanThresholds::default());
        assert_eq!(found.len(), 1, "duplicate findings for one problem: {found:?}");
    }

    #[test]
    fn thresholds_are_honoured_not_hardcoded() {
        let rows = vec![row("provisioning", 2, "lw_reality_a")];
        let tight = ScanThresholds { stall_hours: 1, grace_days: 7 };
        assert_eq!(classify(&rows, &dbs(&[]), tight).len(), 1);
        let loose = ScanThresholds { stall_hours: 100, grace_days: 7 };
        assert!(classify(&rows, &dbs(&[]), loose).is_empty());
    }

    #[test]
    fn mixed_shard_reports_each_class_once() {
        let rows = vec![
            row("active", 100, "lw_reality_ok"),
            row("provisioning", 99, "lw_reality_stalled"),
            row("active", 100, "lw_reality_vanished"),
            row("soft_deleted", 200, "lw_reality_expired"),
        ];
        let found = classify(
            &rows,
            &dbs(&["lw_reality_ok", "lw_reality_stalled", "lw_reality_expired", "lw_reality_ghost"]),
            ScanThresholds::default(),
        );
        let mut classes: Vec<&str> = found.iter().map(|f| f.class()).collect();
        classes.sort_unstable();
        assert_eq!(
            classes,
            vec![
                "orphan_drop_eligible",
                "orphan_missing_database",
                "orphan_partial_provision",
                "orphan_untracked_database",
            ]
        );
    }
}
