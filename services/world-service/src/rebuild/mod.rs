//! 073 (L3.G/H) — projection rebuilder wiring.
//!
//! The per-reality WORKER the admin-cli `rebuild-projection` /
//! `catastrophic-rebuild` commands invoke (Q-L3-3): replay the per-reality
//! `events` log through the L3.B projection crates (`crates/projections/*`) into
//! a TRUNCATEd projection table, via:
//!
//! - [`event_source::SqlxEventSource`] — reads `events` per aggregate (sqlx).
//! - [`writer::SqlxProjectionWriter`] — applies the resulting
//!   [`dp_kernel::ProjectionUpdate`]s to the ONE target table generically via
//!   `jsonb_populate_record` (no per-table schema map; identifier-allowlisted).
//! - [`crate::rebuild::all_projections`] — the leaked `&'static` projection set.
//!
//! This is the FIRST live projection-apply path in the codebase (the rebuilder
//! crate doc's "wired in cycle 15+ when world-service consumes this crate").
//! Its end-to-end correctness against real events is validated by the L3.E/F
//! integrity checker, which does not exist yet — so the admin-cli destructive
//! commands that drive it stay fail-closed behind an explicit operator gate
//! (`ADMIN_CLI_ENABLE_UNPROVEN_REBUILD`). See
//! `docs/plans/2026-06-03-073-destructive-admin-commands.md`.

pub mod event_source;
pub mod writer;

use rebuilder::{AggregateOutcome, AggregateStatus, SendSyncProjection};
use serde::Serialize;

/// The 10 L3.A projection tables (`contracts/migrations/per_reality/
/// 0006_projections.up.sql` + `0009_canon_projection`). The target table the
/// rebuilder writes is validated against this allowlist — it is interpolated
/// into `jsonb_populate_record(NULL::<table>, …)`, so an un-allowlisted name
/// must never reach the SQL.
pub const PROJECTION_TABLES: &[&str] = &[
    "pc_projection",
    "pc_inventory_projection",
    "pc_relationship_projection",
    "npc_projection",
    "npc_session_memory_projection",
    "npc_pc_relationship_projection",
    "npc_session_memory_embedding",
    "region_projection",
    "world_kv_projection",
    "session_participants",
    "canon_projection",
];

/// Returns true if `table` is one of the known L3.A projection tables.
pub fn is_known_projection_table(table: &str) -> bool {
    PROJECTION_TABLES.contains(&table)
}

/// JSON-serializable rebuild summary — printed to stdout for the Go invoker
/// (`admin rebuild-projection`) to parse. Field names are the wire contract.
#[derive(Debug, Clone, Default, Serialize, PartialEq, Eq)]
pub struct RebuildStats {
    /// Aggregates fully replayed and flushed.
    pub aggregates_rebuilt: u64,
    /// Aggregates skipped because a prior run's checkpoint marked them done.
    pub aggregates_skipped: u64,
    /// Aggregates that failed after retries (dead-lettered) — NON-ZERO means
    /// the reality MUST stay frozen and an operator inspects the dead letter.
    pub aggregates_failed: u64,
    /// Total events replayed across all aggregates.
    pub events_replayed: u64,
    /// Total projection updates applied to the target table.
    pub updates_applied: u64,
}

impl RebuildStats {
    /// Fold per-aggregate outcomes into a single summary.
    pub fn from_outcomes(outcomes: &[AggregateOutcome]) -> Self {
        let mut s = RebuildStats::default();
        for o in outcomes {
            s.events_replayed += o.events_replayed;
            s.updates_applied += o.updates_applied;
            match o.status {
                AggregateStatus::Done => s.aggregates_rebuilt += 1,
                AggregateStatus::SkippedAlreadyDone => s.aggregates_skipped += 1,
                AggregateStatus::Failed { .. } => s.aggregates_failed += 1,
            }
        }
        s
    }
}

/// Build the full set of L3.B projections as leaked `&'static` trait objects
/// (the shape `rebuilder::ParallelRebuilder::new` requires). The projections
/// are stateless unit structs, so leaking one of each at process start is the
/// canonical pattern (a CLI process exits after one rebuild — the leak is the
/// process lifetime).
///
/// All projections run over every event; the writer applies ONLY the updates
/// targeting the requested table, so rebuilding e.g. `pc_projection` replays
/// `pc.*` through `PcProjection` and drops every other projection's output.
pub fn all_projections() -> Vec<&'static dyn SendSyncProjection> {
    fn leak<T: SendSyncProjection + 'static>(p: T) -> &'static dyn SendSyncProjection {
        &*Box::leak(Box::new(p))
    }
    vec![
        leak(projections_pc::PcProjection),
        leak(projections_pc::PcInventoryProjection),
        leak(projections_pc::PcRelationshipProjection),
        leak(projections_npc::NpcProjection),
        leak(projections_npc::NpcSessionMemoryProjection),
        leak(projections_npc::NpcPcRelationshipProjection),
        leak(projections_npc::NpcSessionMemoryEmbeddingProjection),
        leak(projections_region::RegionProjection),
        leak(projections_session::SessionParticipantsProjection),
        leak(projections_world_kv::WorldKvProjection),
        leak(projections_canon::CanonProjection),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use rebuilder::{AggregateRef, AggregateStatus};
    use std::time::Duration;
    use uuid::Uuid;

    fn outcome(status: AggregateStatus, events: u64, updates: u64) -> AggregateOutcome {
        AggregateOutcome {
            agg: AggregateRef {
                reality_id: Uuid::nil(),
                aggregate_type: "pc".into(),
                aggregate_id: "pc-1".into(),
            },
            events_replayed: events,
            updates_applied: updates,
            duration: Duration::from_millis(1),
            status,
        }
    }

    #[test]
    fn stats_fold_counts_each_status() {
        let outcomes = vec![
            outcome(AggregateStatus::Done, 10, 5),
            outcome(AggregateStatus::SkippedAlreadyDone, 0, 0),
            outcome(
                AggregateStatus::Failed {
                    error: "boom".into(),
                    retries: 2,
                },
                3,
                1,
            ),
        ];
        let s = RebuildStats::from_outcomes(&outcomes);
        assert_eq!(s.aggregates_rebuilt, 1);
        assert_eq!(s.aggregates_skipped, 1);
        assert_eq!(s.aggregates_failed, 1);
        assert_eq!(s.events_replayed, 13);
        assert_eq!(s.updates_applied, 6);
    }

    #[test]
    fn all_projections_present_and_named() {
        let ps = all_projections();
        assert_eq!(ps.len(), 11, "all L3.B projections registered");
    }

    #[test]
    fn projection_table_allowlist() {
        assert!(is_known_projection_table("pc_projection"));
        assert!(is_known_projection_table("canon_projection"));
        assert!(!is_known_projection_table("reality_registry"));
        assert!(!is_known_projection_table("pc_projection; DROP TABLE x"));
    }
}
