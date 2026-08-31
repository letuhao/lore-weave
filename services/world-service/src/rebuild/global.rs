//! Global-order rebuild for MULTI-AGGREGATE projection tables.
//!
//! The per-aggregate [`rebuilder::ParallelRebuilder`] replays each aggregate
//! independently, which is correct + fast for tables a single aggregate owns.
//! But a MULTI-AGGREGATE table is written from two aggregates — one creates
//! the row, another updates it — so per-aggregate replay races (the update can
//! run before the row exists). This path replays ALL the reality's events in
//! GLOBAL `(recorded_at, event_id)` order in a single sequential pass, so the
//! creating event always precedes the one that depends on it.
//!
//! **No shipped table has that shape today.** The seven `pc.*` / `npc.*`
//! projections that did were removed 2026-08-04 — vocabulary with no producer.
//! This path is kept because the SHAPE recurs the moment two aggregates share a
//! table, and its tests drive it through a neutral fixture pair rather than a
//! game noun.
//!
//! The caller TRUNCATEs the target table first (same contract as the
//! per-aggregate path). Sequential by design — global order is the whole point;
//! a multi-aggregate table is the rare case, so throughput is secondary.
//!
//! ## Trade-offs vs the per-aggregate path
//!
//! This path deliberately drops two features the parallel path has:
//!   - **No per-aggregate checkpoint/resume** — a killed global rebuild restarts
//!     from scratch (re-TRUNCATE + replay). Acceptable because the one
//!     multi-aggregate table this served was small; revisit if a large one
//!     ever appears.
//!   - **No dead-lettering** — any error aborts the whole table (the bin returns
//!     non-zero, the reality stays frozen), rather than dead-lettering one
//!     aggregate and continuing. Correct fail-loud posture for a single
//!     ordered pass; the error message names the failing event.

use dp_kernel::{EventEnvelope, Projection, ProjectionRunner, ProjectionUpdate};
use rebuilder::ProjectionWriter;

use super::event_source::{GlobalCursor, GlobalEventSource};

/// "Page the reality's events in global order" — abstracted so the
/// orchestration is unit-testable without a DB.
pub trait GlobalSource {
    fn events_after(
        &self,
        cursor: Option<&GlobalCursor>,
        batch_size: u64,
    ) -> Result<Vec<EventEnvelope>, String>;
}

impl GlobalSource for GlobalEventSource {
    fn events_after(
        &self,
        cursor: Option<&GlobalCursor>,
        batch_size: u64,
    ) -> Result<Vec<EventEnvelope>, String> {
        GlobalEventSource::events_after(self, cursor, batch_size)
    }
}

/// Summary of a global-order rebuild, mirroring the per-aggregate stats' counts.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct GlobalStats {
    pub events_replayed: u64,
    pub updates_applied: u64,
}

/// Replay all the reality's events in global order, fanning each through
/// `projections` and applying the target-table updates via `writer`. The caller
/// has already TRUNCATEd the target table.
pub fn rebuild_global_order(
    source: &dyn GlobalSource,
    projections: &[&dyn Projection],
    writer: &dyn ProjectionWriter,
    batch_size: u64,
) -> Result<GlobalStats, String> {
    let mut runner = ProjectionRunner::new();
    for p in projections {
        runner = runner.with_projection(*p);
    }

    let mut stats = GlobalStats::default();
    let mut cursor: Option<GlobalCursor> = None;
    loop {
        let batch = source.events_after(cursor.as_ref(), batch_size)?;
        if batch.is_empty() {
            break;
        }
        // Updates stay in event order within the batch; the writer applies them
        // sequentially in ONE tx, so an Insert (session.started) is visible to a
        // later update from a second aggregate in the same pass.
        let updates: Vec<ProjectionUpdate> =
            batch.iter().flat_map(|env| runner.apply_one(env)).collect();
        writer.apply_batch(&updates)?;

        stats.events_replayed += batch.len() as u64;
        stats.updates_applied += updates.len() as u64;

        let last = batch.last().expect("non-empty batch");
        cursor = Some(GlobalCursor {
            recorded_at: last.recorded_at.clone(),
            event_id: last.event_id,
        });
        if (batch.len() as u64) < batch_size {
            break; // short page ⇒ end of stream
        }
    }
    Ok(stats)
}

#[cfg(test)]
mod tests {
    use super::*;
    use dp_kernel::ProjectionUpdate;
    use std::sync::Mutex;
    use uuid::Uuid;

    /// Returns the whole event list on the first (cursor=None) call, then empty.
    struct OnePageSource {
        events: Vec<EventEnvelope>,
    }
    impl GlobalSource for OnePageSource {
        fn events_after(
            &self,
            cursor: Option<&GlobalCursor>,
            _batch_size: u64,
        ) -> Result<Vec<EventEnvelope>, String> {
            Ok(if cursor.is_none() {
                self.events.clone()
            } else {
                vec![]
            })
        }
    }

    struct RecordingWriter {
        applied: Mutex<Vec<ProjectionUpdate>>,
    }
    impl ProjectionWriter for RecordingWriter {
        fn apply_batch(&self, updates: &[ProjectionUpdate]) -> Result<(), String> {
            self.applied.lock().unwrap().extend(updates.iter().cloned());
            Ok(())
        }
    }

    /// **A test-only projector pair, deliberately carrying no game noun.**
    ///
    /// The property these tests exist for is one table written by TWO
    /// aggregate types, so the Insert from one must precede the Update from
    /// the other in global order. That shape used to be supplied by the
    /// `npc` projections; they were removed 2026-08-04 as vocabulary with no
    /// producer. **The property is foundation and the vocabulary was
    /// incidental**, so the fixture is replaced rather than the test deleted.
    struct ProbeAlpha;
    impl Projection for ProbeAlpha {
        fn name(&self) -> &str {
            "probe_alpha"
        }
        fn handles(&self, env: &EventEnvelope) -> bool {
            env.aggregate_type == "alpha"
        }
        fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
            match env.event_type.as_str() {
                "alpha.opened" => vec![ProjectionUpdate::Insert {
                    table: "probe_projection".into(),
                    row: serde_json::json!({ "id": env.aggregate_id }),
                    meta: dp_kernel::VerificationMeta::from_envelope(env),
                }],
                _ => vec![],
            }
        }
    }

    struct ProbeBeta;
    impl Projection for ProbeBeta {
        fn name(&self) -> &str {
            "probe_beta"
        }
        fn handles(&self, env: &EventEnvelope) -> bool {
            env.aggregate_type == "beta"
        }
        fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
            match env.event_type.as_str() {
                "beta.touched" => vec![ProjectionUpdate::Update {
                    table: "probe_projection".into(),
                    pk: serde_json::json!({ "id": env.aggregate_id }),
                    fields: serde_json::json!({ "touched": true }),
                    meta: dp_kernel::VerificationMeta::from_envelope(env),
                }],
                _ => vec![],
            }
        }
    }

    fn alpha_opened(row: &str, other: &str, secs: u32) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(secs as u128),
            event_type: "alpha.opened".into(),
            event_version: 1,
            aggregate_id: row.into(),
            aggregate_type: "alpha".into(),
            aggregate_version: 1,
            reality_id: Uuid::from_u128(0xBEEF),
            occurred_at: format!("2026-01-01T00:00:{secs:02}.000000Z"),
            recorded_at: format!("2026-01-01T00:00:{secs:02}.000000Z"),
            payload: serde_json::json!({ "other_id": other, "aggregate_id": row }),
            metadata: None,
            ruleset_digest: None,
        }
    }

    fn beta_touched(actor: &str, row: &str, version: u64, secs: u32) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(100 + secs as u128),
            event_type: "beta.touched".into(),
            event_version: 1,
            aggregate_id: actor.into(),
            aggregate_type: "beta".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xBEEF),
            occurred_at: format!("2026-01-01T00:00:{secs:02}.000000Z"),
            recorded_at: format!("2026-01-01T00:00:{secs:02}.000000Z"),
            payload: serde_json::json!({ "text": "hi" }),
            metadata: Some(serde_json::json!({ "row_id": row })),
            ruleset_digest: None,
        }
    }

    /// Pages `batch_size` events per call, advancing by the (recorded_at,
    /// event_id) cursor — emulates the real SQL reader so the paging loop is
    /// exercised. `all` MUST be pre-sorted in global order.
    struct PagingSource {
        all: Vec<EventEnvelope>,
    }
    impl GlobalSource for PagingSource {
        fn events_after(
            &self,
            cursor: Option<&GlobalCursor>,
            batch_size: u64,
        ) -> Result<Vec<EventEnvelope>, String> {
            let start = match cursor {
                None => 0,
                Some(c) => self
                    .all
                    .iter()
                    .position(|e| e.recorded_at == c.recorded_at && e.event_id == c.event_id)
                    .map(|i| i + 1)
                    .unwrap_or(self.all.len()),
            };
            Ok(self
                .all
                .iter()
                .skip(start)
                .take(batch_size as usize)
                .cloned()
                .collect())
        }
    }

    #[test]
    fn global_order_pages_across_batches_no_dup_no_miss() {
        // batch_size = 1 forces one event per page, so the Insert
        // (alpha.opened) and the update (beta.touched) land in SEPARATE
        // batches/transactions — the cross-batch case the single-page test can't
        // reach. The earlier batch commits the row before the increment runs.
        let source = PagingSource {
            all: vec![
                alpha_opened("row-1", "agg-2", 1),
                beta_touched("agg-2", "row-1", 2, 2),
                beta_touched("agg-2", "row-1", 3, 3),
            ],
        };
        let proj_a = ProbeAlpha;
        let proj_b = ProbeBeta;
        let projections: Vec<&dyn Projection> = vec![&proj_a, &proj_b];
        let writer = RecordingWriter {
            applied: Mutex::new(vec![]),
        };

        let stats = rebuild_global_order(&source, &projections, &writer, 1).unwrap();
        // Every event replayed exactly once (no dup at a page boundary, no miss).
        assert_eq!(stats.events_replayed, 3);

        let applied = writer.applied.lock().unwrap();
        let mem: Vec<&ProjectionUpdate> = applied
            .iter()
            .filter(|u| u.table() == "probe_projection")
            .collect();
        // Insert (alpha.opened) then two Updates (the two beta.touched).
        assert!(matches!(mem[0], ProjectionUpdate::Insert { .. }), "{:?}", mem[0]);
        assert_eq!(
            mem.iter()
                .filter(|u| matches!(u, ProjectionUpdate::Update { .. }))
                .count(),
            2,
            "two beta.touched updates must be replayed"
        );
    }

    #[test]
    fn global_order_feeds_one_aggregates_insert_before_anothers_update() {
        // The cross-aggregate case: a row created by one aggregate,
        // aggregate, then an update from a SECOND aggregate. In global order
        // the Insert must reach the writer BEFORE the increment Update.
        let source = OnePageSource {
            events: vec![
                alpha_opened("row-1", "agg-2", 1),
                beta_touched("agg-2", "row-1", 2, 2),
            ],
        };
        let proj_a = ProbeAlpha;
        let proj_b = ProbeBeta;
        let projections: Vec<&dyn Projection> = vec![&proj_a, &proj_b];
        let writer = RecordingWriter {
            applied: Mutex::new(vec![]),
        };

        let stats = rebuild_global_order(&source, &projections, &writer, 100).unwrap();
        assert_eq!(stats.events_replayed, 2);

        // Filter the recorded updates to the multi-aggregate table and assert
        // the Insert precedes the increment Update.
        let applied = writer.applied.lock().unwrap();
        let mem: Vec<&ProjectionUpdate> = applied
            .iter()
            .filter(|u| u.table() == "probe_projection")
            .collect();
        assert!(mem.len() >= 2, "expected an insert + an increment, got {mem:?}");
        assert!(
            matches!(mem[0], ProjectionUpdate::Insert { .. }),
            "the alpha Insert must come first, got {:?}",
            mem[0]
        );
        assert!(
            matches!(mem[1], ProjectionUpdate::Update { .. }),
            "the beta Update must follow, got {:?}",
            mem[1]
        );
    }
}
