//! Global-order rebuild for MULTI-AGGREGATE projection tables.
//!
//! The per-aggregate [`rebuilder::ParallelRebuilder`] replays each aggregate
//! independently, which is correct + fast for tables a single aggregate owns.
//! But a table like `npc_session_memory_projection` is written from TWO
//! aggregates — the *session* aggregate's `session.started` creates the row, and
//! the *npc* aggregate's `npc.said` increments it — so per-aggregate replay
//! races (the increment can run before the row exists). This path replays ALL
//! the reality's events in GLOBAL `(recorded_at, event_id)` order in a single
//! sequential pass, so `session.started` always precedes the `npc.said` that
//! depends on it.
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
//!     multi-aggregate table (`npc_session_memory_projection`) is small; revisit
//!     if a large multi-aggregate table ever appears.
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
        // later increment (npc.said) in the same pass.
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

    fn session_started(sid: &str, npc: &str, secs: u32) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(secs as u128),
            event_type: "session.started".into(),
            event_version: 1,
            aggregate_id: sid.into(),
            aggregate_type: "session".into(),
            aggregate_version: 1,
            reality_id: Uuid::from_u128(0xBEEF),
            occurred_at: format!("2026-01-01T00:00:{secs:02}.000000Z"),
            recorded_at: format!("2026-01-01T00:00:{secs:02}.000000Z"),
            payload: serde_json::json!({ "npc_id": npc, "session_id": sid, "aggregate_id": sid }),
            metadata: None,
        }
    }

    fn npc_said(npc: &str, sid: &str, version: u64, secs: u32) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(100 + secs as u128),
            event_type: "npc.said".into(),
            event_version: 1,
            aggregate_id: npc.into(),
            aggregate_type: "npc".into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xBEEF),
            occurred_at: format!("2026-01-01T00:00:{secs:02}.000000Z"),
            recorded_at: format!("2026-01-01T00:00:{secs:02}.000000Z"),
            payload: serde_json::json!({ "text": "hi" }),
            metadata: Some(serde_json::json!({ "session_id": sid })),
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
        // (session.started) and the increment (npc.said) land in SEPARATE
        // batches/transactions — the cross-batch case the single-page test can't
        // reach. The earlier batch commits the row before the increment runs.
        let source = PagingSource {
            all: vec![
                session_started("sess-1", "npc-1", 1),
                npc_said("npc-1", "sess-1", 2, 2),
                npc_said("npc-1", "sess-1", 3, 3),
            ],
        };
        let proj_mem = projections_npc::NpcSessionMemoryProjection;
        let proj_npc = projections_npc::NpcProjection;
        let projections: Vec<&dyn Projection> = vec![&proj_mem, &proj_npc];
        let writer = RecordingWriter {
            applied: Mutex::new(vec![]),
        };

        let stats = rebuild_global_order(&source, &projections, &writer, 1).unwrap();
        // Every event replayed exactly once (no dup at a page boundary, no miss).
        assert_eq!(stats.events_replayed, 3);

        let applied = writer.applied.lock().unwrap();
        let mem: Vec<&ProjectionUpdate> = applied
            .iter()
            .filter(|u| u.table() == "npc_session_memory_projection")
            .collect();
        // Insert (session.started) then two increment Updates (the two npc.said).
        assert!(matches!(mem[0], ProjectionUpdate::Insert { .. }), "{:?}", mem[0]);
        assert_eq!(
            mem.iter()
                .filter(|u| matches!(u, ProjectionUpdate::Update { .. }))
                .count(),
            2,
            "two npc.said increments must be replayed"
        );
    }

    #[test]
    fn global_order_feeds_session_started_before_npc_said_increment() {
        // The cross-aggregate case: a session row created by the session
        // aggregate, then an increment from the npc aggregate. In global order
        // the Insert must reach the writer BEFORE the increment Update.
        let source = OnePageSource {
            events: vec![
                session_started("sess-1", "npc-1", 1),
                npc_said("npc-1", "sess-1", 2, 2),
            ],
        };
        let proj_mem = projections_npc::NpcSessionMemoryProjection;
        let proj_npc = projections_npc::NpcProjection;
        let projections: Vec<&dyn Projection> = vec![&proj_mem, &proj_npc];
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
            .filter(|u| u.table() == "npc_session_memory_projection")
            .collect();
        assert!(mem.len() >= 2, "expected an insert + an increment, got {mem:?}");
        assert!(
            matches!(mem[0], ProjectionUpdate::Insert { .. }),
            "session.started Insert must come first, got {:?}",
            mem[0]
        );
        assert!(
            matches!(mem[1], ProjectionUpdate::Update { .. }),
            "npc.said increment Update must follow, got {:?}",
            mem[1]
        );
    }
}
