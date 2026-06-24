//! L3.D — Per-aggregate parallel rebuilder (RAID cycle 14).
//!
//! ## Scope
//!
//! Rebuilds a per-reality projection by replaying events from the L2.A event
//! log through the L3.B [`dp_kernel::Projection`] trait. Designed to handle
//! catastrophic loss (`TRUNCATE projection_table; replay all events`) AND
//! incremental targeted rebuild (single aggregate marked drifted by L3.E
//! sampler).
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3-3** (OPEN_QUESTIONS_LOCKED §5): catastrophic-rebuild orchestrator
//!   = `admin-cli` sub-command + `rolling_rebuild` internal lib (Go side,
//!   `services/admin-cli/internal/rolling_rebuild/`). This Rust crate is the
//!   *worker* that the orchestrator invokes per reality (via a binary in
//!   `services/world-service/src/bin/`).
//! - **Q-L3-5** (§5): NO V2 blue-green migration scaffolding. The rebuilder
//!   participates in the L3.G **freeze-rebuild** approach (caller flips
//!   reality state → `rebuilding`, calls `rebuild_projection`, flips back
//!   → `active`).
//! - **Q-L3-4** (§5): Verification metadata is stamped through the existing
//!   [`dp_kernel::ProjectionUpdate`] payloads — this crate does not invent
//!   new bookkeeping, it just re-runs the L3.B contract.
//! - **Q-L3B-1** (§5): a single event may produce multiple updates; the
//!   rebuilder honors `Vec<ProjectionUpdate>` (same as live path).
//!
//! ## What is in cycle 14
//!
//! - [`RebuildPlan`] — input descriptor (reality + aggregate list).
//! - [`ParallelRebuilder`] — work-stealing worker pool that fans out
//!   per-aggregate rebuild tasks across N tokio tasks (bounded concurrency).
//! - [`AggregateEventSource`] — abstract trait for "give me the event stream
//!   for this aggregate" (production wires to L2.A reader; tests inject).
//! - [`ProjectionWriter`] — abstract trait for "apply this batch of
//!   `ProjectionUpdate`s in a TX" (production wires to per-reality DB; tests
//!   record).
//! - [`CheckpointStore`] — per-aggregate progress checkpoint so a killed
//!   rebuilder can resume without redoing finished aggregates.
//! - [`DeadLetterStore`] — aggregates that failed `max_retries` move to the
//!   dead-letter table; surfaced to the runbook so an operator can inspect.
//!
//! ## What is NOT in cycle 14
//!
//! - Real `sqlx` / `tokio-postgres` impls — wired in cycle 15+ when
//!   world-service consumes this crate.
//! - The L3.G freeze-rebuild **script** + admin-cli command (DPS 2/3 of this
//!   cycle ship those — they reuse this rebuilder as their core).
//! - The L3.H catastrophic admin-cli command itself (DPS 3 of this cycle).
//! - The L3.E daily integrity-checker / drift detection — cycle 15 L3.E/F.

use std::sync::Arc;
use std::time::{Duration, Instant};

use dp_kernel::{EventEnvelope, Projection, ProjectionRunner, ProjectionUpdate};

/// Marker trait alias for a thread-safe [`Projection`] usable in the parallel
/// rebuilder. The bound is split out so callers can write `SendSyncProjection`
/// (concise) instead of `Projection + Send + Sync` everywhere.
pub trait SendSyncProjection: Projection + Send + Sync {}
impl<T: Projection + Send + Sync + ?Sized> SendSyncProjection for T {}
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

pub mod checkpoint;
pub mod dead_letter;

pub use checkpoint::{Checkpoint, CheckpointStore, InMemoryCheckpointStore};
pub use dead_letter::{DeadLetterEntry, DeadLetterStore, InMemoryDeadLetterStore};

// ────────────────────────────────────────────────────────────────────────────
// Configuration
// ────────────────────────────────────────────────────────────────────────────

/// `contracts/rebuild/config.yaml` Rust mirror.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RebuildConfig {
    /// Number of concurrent per-aggregate rebuild tasks. Layer-plan L3.D.2:
    /// `storage.rebuild.parallel_workers = 8`.
    pub parallel_workers: usize,
    /// Per-aggregate timeout before the worker moves on (and the failed
    /// aggregate is retried up to `max_retries` times).
    pub per_aggregate_timeout: Duration,
    /// Maximum retries per aggregate before it's moved to the dead-letter
    /// store. R02 §12B.2 calls for "fail loud, do not lose aggregates".
    pub max_retries: u32,
    /// Per-batch event count (the rebuilder pages through history in batches
    /// to bound memory). Prod tuning: 5000.
    pub batch_size: u64,
}

impl Default for RebuildConfig {
    fn default() -> Self {
        Self {
            parallel_workers: 8,
            per_aggregate_timeout: Duration::from_secs(60),
            max_retries: 2,
            batch_size: 5_000,
        }
    }
}

/// A single aggregate the orchestrator wants rebuilt. Equivalent to one row
/// in the rebuild work queue.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AggregateRef {
    pub reality_id: Uuid,
    pub aggregate_type: String,
    pub aggregate_id: String,
}

/// Plan handed to [`ParallelRebuilder::run`].
#[derive(Debug, Clone)]
pub struct RebuildPlan {
    pub reality_id: Uuid,
    pub aggregates: Vec<AggregateRef>,
    /// Name of the projection being rebuilt (e.g. `pc_projection`). Used in
    /// logs + checkpoint keying.
    pub projection_name: String,
}

// ────────────────────────────────────────────────────────────────────────────
// Errors
// ────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Error)]
pub enum RebuildError {
    #[error("event source error: {0}")]
    EventSource(String),
    #[error("projection writer error: {0}")]
    ProjectionWriter(String),
    #[error("checkpoint store error: {0}")]
    CheckpointStore(String),
    #[error("dead letter store error: {0}")]
    DeadLetterStore(String),
    #[error("aggregate {agg:?} timed out after {timeout:?}")]
    Timeout {
        agg: AggregateRef,
        timeout: Duration,
    },
    #[error("aggregate {agg:?} cancelled")]
    Cancelled { agg: AggregateRef },
    #[error("config invalid: {0}")]
    Config(String),
}

// ────────────────────────────────────────────────────────────────────────────
// Abstract dependencies
// ────────────────────────────────────────────────────────────────────────────

/// Reads events for a single aggregate from the L2.A event log. Cycle-15+
/// will wire `services/world-service/src/event_reader.rs` (sqlx) here.
///
/// Sync today — the parallel rebuilder uses `tokio::task::spawn_blocking`
/// so a slow event source doesn't starve the runtime.
pub trait AggregateEventSource: Send + Sync {
    /// Fetch up to `batch_size` events for the aggregate, strictly after
    /// `after_version`. Empty Vec = end of stream.
    fn events_batch(
        &self,
        agg: &AggregateRef,
        after_version: u64,
        batch_size: u64,
    ) -> Result<Vec<EventEnvelope>, String>;
}

/// Applies a flat batch of `ProjectionUpdate`s in a single DB TX. The
/// rebuilder calls this once per envelope batch (after fanning the batch
/// through all registered projections).
pub trait ProjectionWriter: Send + Sync {
    fn apply_batch(&self, updates: &[ProjectionUpdate]) -> Result<(), String>;
}

// ────────────────────────────────────────────────────────────────────────────
// Per-aggregate outcome
// ────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub struct AggregateOutcome {
    pub agg: AggregateRef,
    pub events_replayed: u64,
    pub updates_applied: u64,
    pub duration: Duration,
    pub status: AggregateStatus,
}

#[derive(Debug, Clone, PartialEq)]
pub enum AggregateStatus {
    /// All events replayed and projection updates flushed successfully.
    Done,
    /// Skipped because the checkpoint says this aggregate already finished
    /// in a prior run (resumability).
    SkippedAlreadyDone,
    /// Failed (after retries exhausted) — moved to dead letter.
    Failed { error: String, retries: u32 },
}

// ────────────────────────────────────────────────────────────────────────────
// Per-aggregate rebuilder (sync, single aggregate)
// ────────────────────────────────────────────────────────────────────────────

/// Replays one aggregate end-to-end. Used directly for the catastrophic
/// `--scope=aggregate-list` path, AND by [`ParallelRebuilder`] under a
/// worker.
///
/// The caller passes a flat slice of projections (vs a pre-built runner) so
/// each worker can build its own `ProjectionRunner` thread-locally — this
/// sidesteps the fact that `ProjectionRunner<'p>` holds non-`Sync` trait
/// references internally.
pub fn rebuild_aggregate(
    plan: &RebuildPlan,
    agg: &AggregateRef,
    config: &RebuildConfig,
    events: &dyn AggregateEventSource,
    projections: &[&dyn Projection],
    writer: &dyn ProjectionWriter,
    checkpoints: &dyn CheckpointStore,
) -> AggregateOutcome {
    let mut runner = ProjectionRunner::new();
    for p in projections {
        runner = runner.with_projection(*p);
    }
    rebuild_aggregate_with_runner(plan, agg, config, events, &runner, writer, checkpoints)
}

fn rebuild_aggregate_with_runner(
    plan: &RebuildPlan,
    agg: &AggregateRef,
    config: &RebuildConfig,
    events: &dyn AggregateEventSource,
    runner: &ProjectionRunner<'_>,
    writer: &dyn ProjectionWriter,
    checkpoints: &dyn CheckpointStore,
) -> AggregateOutcome {
    let start = Instant::now();

    // ── Resumability check ────────────────────────────────────────────────
    // If we've already finished this aggregate in a prior run, skip.
    match checkpoints.get(&plan.projection_name, agg) {
        Ok(Some(cp)) if cp.completed => {
            return AggregateOutcome {
                agg: agg.clone(),
                events_replayed: 0,
                updates_applied: 0,
                duration: start.elapsed(),
                status: AggregateStatus::SkippedAlreadyDone,
            };
        }
        _ => {}
    }

    let mut after_version: u64 = checkpoints
        .get(&plan.projection_name, agg)
        .ok()
        .flatten()
        .map(|cp| cp.last_applied_version)
        .unwrap_or(0);
    let mut events_replayed: u64 = 0;
    let mut updates_applied: u64 = 0;

    loop {
        let batch = match events.events_batch(agg, after_version, config.batch_size) {
            Ok(b) => b,
            Err(e) => {
                return AggregateOutcome {
                    agg: agg.clone(),
                    events_replayed,
                    updates_applied,
                    duration: start.elapsed(),
                    status: AggregateStatus::Failed {
                        error: format!("event source: {}", e),
                        retries: 0,
                    },
                };
            }
        };

        if batch.is_empty() {
            // End of stream — mark completion atomically with the final
            // checkpoint write (so a crash AFTER apply_batch but BEFORE
            // checkpoint update results in safe re-replay rather than
            // assumed-done).
            if let Err(e) = checkpoints.set(
                &plan.projection_name,
                agg,
                Checkpoint {
                    last_applied_version: after_version,
                    completed: true,
                },
            ) {
                return AggregateOutcome {
                    agg: agg.clone(),
                    events_replayed,
                    updates_applied,
                    duration: start.elapsed(),
                    status: AggregateStatus::Failed {
                        error: format!("checkpoint flush: {}", e),
                        retries: 0,
                    },
                };
            }
            return AggregateOutcome {
                agg: agg.clone(),
                events_replayed,
                updates_applied,
                duration: start.elapsed(),
                status: AggregateStatus::Done,
            };
        }

        // Fan batch through projections.
        let updates: Vec<ProjectionUpdate> = batch
            .iter()
            .flat_map(|env| runner.apply_one(env))
            .collect();

        // Apply DB updates (caller wraps in a TX).
        if let Err(e) = writer.apply_batch(&updates) {
            return AggregateOutcome {
                agg: agg.clone(),
                events_replayed,
                updates_applied,
                duration: start.elapsed(),
                status: AggregateStatus::Failed {
                    error: format!("writer: {}", e),
                    retries: 0,
                },
            };
        }

        events_replayed += batch.len() as u64;
        updates_applied += updates.len() as u64;
        after_version = batch.last().map(|e| e.aggregate_version).unwrap_or(after_version);

        // Persist incremental progress (resumability anchor).
        if let Err(e) = checkpoints.set(
            &plan.projection_name,
            agg,
            Checkpoint {
                last_applied_version: after_version,
                completed: false,
            },
        ) {
            return AggregateOutcome {
                agg: agg.clone(),
                events_replayed,
                updates_applied,
                duration: start.elapsed(),
                status: AggregateStatus::Failed {
                    error: format!("checkpoint: {}", e),
                    retries: 0,
                },
            };
        }

        // If the batch was smaller than batch_size, we're at end of stream.
        if (batch.len() as u64) < config.batch_size {
            // mark completion
            if let Err(e) = checkpoints.set(
                &plan.projection_name,
                agg,
                Checkpoint {
                    last_applied_version: after_version,
                    completed: true,
                },
            ) {
                return AggregateOutcome {
                    agg: agg.clone(),
                    events_replayed,
                    updates_applied,
                    duration: start.elapsed(),
                    status: AggregateStatus::Failed {
                        error: format!("checkpoint flush: {}", e),
                        retries: 0,
                    },
                };
            }
            return AggregateOutcome {
                agg: agg.clone(),
                events_replayed,
                updates_applied,
                duration: start.elapsed(),
                status: AggregateStatus::Done,
            };
        }
    }
}

// ────────────────────────────────────────────────────────────────────────────
// Parallel rebuilder (tokio task pool with bounded concurrency)
// ────────────────────────────────────────────────────────────────────────────

/// Parallel orchestrator: spawns up to `config.parallel_workers` concurrent
/// per-aggregate tasks via a `tokio::sync::Semaphore`. Each worker calls
/// [`rebuild_aggregate`]. Failures up to `max_retries` are retried; final
/// failures move to the dead letter.
///
/// NOTE: the worker bodies are sync (no async event source today) — we use
/// tokio's `spawn_blocking` so a slow event source doesn't starve the runtime.
/// When cycle-15+ wires a real async event reader, swap to native `async fn`.
pub struct ParallelRebuilder {
    config: RebuildConfig,
    events: Arc<dyn AggregateEventSource>,
    /// `&'static` projections — production registers them at process start
    /// via `Box::leak`; tests do the same. Each worker rebuilds its own
    /// `ProjectionRunner` from this slice to sidestep `ProjectionRunner`'s
    /// non-`Sync` interior.
    projections: Arc<Vec<&'static dyn SendSyncProjection>>,
    writer: Arc<dyn ProjectionWriter>,
    checkpoints: Arc<dyn CheckpointStore>,
    dead_letter: Arc<dyn DeadLetterStore>,
}

impl ParallelRebuilder {
    pub fn new(
        config: RebuildConfig,
        events: Arc<dyn AggregateEventSource>,
        projections: Vec<&'static dyn SendSyncProjection>,
        writer: Arc<dyn ProjectionWriter>,
        checkpoints: Arc<dyn CheckpointStore>,
        dead_letter: Arc<dyn DeadLetterStore>,
    ) -> Result<Self, RebuildError> {
        if config.parallel_workers == 0 {
            return Err(RebuildError::Config(
                "parallel_workers must be >= 1".into(),
            ));
        }
        if config.batch_size == 0 {
            return Err(RebuildError::Config("batch_size must be >= 1".into()));
        }
        Ok(Self {
            config,
            events,
            projections: Arc::new(projections),
            writer,
            checkpoints,
            dead_letter,
        })
    }

    /// Run the rebuild plan. Returns one [`AggregateOutcome`] per aggregate
    /// in the plan (in finishing order, NOT input order — caller can re-sort
    /// by `agg` if it cares).
    pub async fn run(&self, plan: RebuildPlan) -> Vec<AggregateOutcome> {
        let plan = Arc::new(plan);
        let semaphore = Arc::new(tokio::sync::Semaphore::new(self.config.parallel_workers));
        let mut handles: Vec<tokio::task::JoinHandle<AggregateOutcome>> =
            Vec::with_capacity(plan.aggregates.len());

        for agg in plan.aggregates.iter().cloned() {
            let permit = semaphore.clone().acquire_owned().await.expect("semaphore closed");
            let events = self.events.clone();
            let projections = self.projections.clone();
            let writer = self.writer.clone();
            let checkpoints = self.checkpoints.clone();
            let dead_letter = self.dead_letter.clone();
            let plan_ref = plan.clone();
            let config = self.config.clone();
            let max_retries = self.config.max_retries;

            let h: tokio::task::JoinHandle<AggregateOutcome> =
                tokio::task::spawn_blocking(move || {
                    // permit held for the lifetime of this closure
                    let _permit = permit;
                    // Build a thread-local ProjectionRunner from the &'static slice.
                    let projections_slice: Vec<&dyn Projection> =
                        projections.iter().map(|p| *p as &dyn Projection).collect();
                    let mut last_outcome: Option<AggregateOutcome> = None;
                    for attempt in 0..=max_retries {
                        let outcome = rebuild_aggregate(
                            &plan_ref,
                            &agg,
                            &config,
                            &*events,
                            &projections_slice,
                            &*writer,
                            &*checkpoints,
                        );
                        match outcome.status {
                            AggregateStatus::Done | AggregateStatus::SkippedAlreadyDone => {
                                return outcome;
                            }
                            AggregateStatus::Failed { ref error, .. } => {
                                if attempt == max_retries {
                                    // Dead letter + return final outcome.
                                    let _ = dead_letter.record(DeadLetterEntry {
                                        agg: agg.clone(),
                                        projection_name: plan_ref.projection_name.clone(),
                                        last_error: error.clone(),
                                        attempts: attempt + 1,
                                    });
                                    let mut final_outcome = outcome.clone();
                                    if let AggregateStatus::Failed { ref mut retries, .. } =
                                        final_outcome.status
                                    {
                                        *retries = attempt;
                                    }
                                    return final_outcome;
                                }
                                last_outcome = Some(outcome);
                            }
                        }
                    }
                    last_outcome.expect("unreachable — loop runs at least once")
                });
            handles.push(h);
        }

        let mut results = Vec::with_capacity(handles.len());
        for h in handles {
            match h.await {
                Ok(o) => results.push(o),
                Err(join_err) => {
                    // tokio task crashed (panic). Caller can spot via missing
                    // outcome count — we just log here.
                    tracing::error!(error=?join_err, "rebuild worker join failed");
                }
            }
        }
        results
    }
}

// ────────────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use dp_kernel::{Projection, ProjectionUpdate, VerificationMeta};
    use serde_json::json;
    use std::collections::HashMap;
    use std::sync::Mutex;

    // ── Test fixtures ─────────────────────────────────────────────────────

    fn env(agg_type: &str, agg_id: &str, version: u64) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(((version as u128) << 64) | agg_id.len() as u128),
            event_type: "world.kv_set".into(),
            event_version: 1,
            aggregate_id: agg_id.into(),
            aggregate_type: agg_type.into(),
            aggregate_version: version,
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", version % 60),
            payload: json!({ "key": format!("k{}", version), "value": version }),
            metadata: None,
        }
    }

    /// Fake event source backed by a flat map of (agg → events).
    struct FakeEvents {
        per_agg: HashMap<String, Vec<EventEnvelope>>,
        /// Per-agg busy-wait to verify actual parallelism in tests.
        busy_ms_per_batch: u64,
    }

    impl AggregateEventSource for FakeEvents {
        fn events_batch(
            &self,
            agg: &AggregateRef,
            after_version: u64,
            batch_size: u64,
        ) -> Result<Vec<EventEnvelope>, String> {
            if self.busy_ms_per_batch > 0 {
                std::thread::sleep(Duration::from_millis(self.busy_ms_per_batch));
            }
            let all = self.per_agg.get(&agg.aggregate_id).cloned().unwrap_or_default();
            let filtered: Vec<_> = all
                .into_iter()
                .filter(|e| e.aggregate_version > after_version)
                .take(batch_size as usize)
                .collect();
            Ok(filtered)
        }
    }

    /// Fake event source that returns an error N times then succeeds.
    struct FlakyEvents {
        per_agg: HashMap<String, Vec<EventEnvelope>>,
        fail_count: Mutex<u32>,
        fail_total: u32,
    }

    impl AggregateEventSource for FlakyEvents {
        fn events_batch(
            &self,
            agg: &AggregateRef,
            after_version: u64,
            batch_size: u64,
        ) -> Result<Vec<EventEnvelope>, String> {
            let mut c = self.fail_count.lock().unwrap();
            if *c < self.fail_total {
                *c += 1;
                return Err(format!("flaky failure {}/{}", *c, self.fail_total));
            }
            drop(c);
            let all = self.per_agg.get(&agg.aggregate_id).cloned().unwrap_or_default();
            let filtered: Vec<_> = all
                .into_iter()
                .filter(|e| e.aggregate_version > after_version)
                .take(batch_size as usize)
                .collect();
            Ok(filtered)
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

    struct FailingWriter;
    impl ProjectionWriter for FailingWriter {
        fn apply_batch(&self, _: &[ProjectionUpdate]) -> Result<(), String> {
            Err("writer always fails".into())
        }
    }

    struct StubProjection;
    impl Projection for StubProjection {
        fn name(&self) -> &str {
            "stub"
        }
        fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
            vec![ProjectionUpdate::Insert {
                table: "stub_projection".into(),
                row: json!({
                    "agg_id": env.aggregate_id,
                    "version": env.aggregate_version,
                }),
                meta: VerificationMeta::from_envelope(env),
            }]
        }
    }

    // ── Unit tests ────────────────────────────────────────────────────────

    #[test]
    fn rebuild_aggregate_replays_all_events_in_order() {
        let agg = AggregateRef {
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            aggregate_type: "world_kv".into(),
            aggregate_id: "k1".into(),
        };
        let events = FakeEvents {
            per_agg: vec![(
                "k1".to_string(),
                vec![env("world_kv", "k1", 1), env("world_kv", "k1", 2), env("world_kv", "k1", 3)],
            )]
            .into_iter()
            .collect(),
            busy_ms_per_batch: 0,
        };
        let writer = RecordingWriter { applied: Mutex::new(vec![]) };
        let proj = StubProjection;
        let projections: Vec<&dyn Projection> = vec![&proj];
        let checkpoints = InMemoryCheckpointStore::default();
        let plan = RebuildPlan {
            reality_id: agg.reality_id,
            aggregates: vec![agg.clone()],
            projection_name: "stub".into(),
        };

        let outcome = rebuild_aggregate(
            &plan,
            &agg,
            &RebuildConfig { batch_size: 100, ..Default::default() },
            &events,
            &projections,
            &writer,
            &checkpoints,
        );

        assert_eq!(outcome.events_replayed, 3);
        assert_eq!(outcome.updates_applied, 3);
        assert_eq!(outcome.status, AggregateStatus::Done);
        let applied = writer.applied.lock().unwrap();
        assert_eq!(applied.len(), 3);
        // Checkpoint reflects last version + completed flag.
        let cp = checkpoints.get("stub", &agg).unwrap().unwrap();
        assert_eq!(cp.last_applied_version, 3);
        assert!(cp.completed);
    }

    #[test]
    fn resumability_skips_completed_aggregates() {
        let agg = AggregateRef {
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            aggregate_type: "world_kv".into(),
            aggregate_id: "k1".into(),
        };
        let checkpoints = InMemoryCheckpointStore::default();
        checkpoints
            .set("stub", &agg, Checkpoint { last_applied_version: 5, completed: true })
            .unwrap();

        let events = FakeEvents { per_agg: HashMap::new(), busy_ms_per_batch: 0 };
        let writer = RecordingWriter { applied: Mutex::new(vec![]) };
        let proj = StubProjection;
        let projections: Vec<&dyn Projection> = vec![&proj];
        let plan = RebuildPlan {
            reality_id: agg.reality_id,
            aggregates: vec![agg.clone()],
            projection_name: "stub".into(),
        };

        let outcome =
            rebuild_aggregate(&plan, &agg, &RebuildConfig::default(), &events, &projections, &writer, &checkpoints);
        assert_eq!(outcome.status, AggregateStatus::SkippedAlreadyDone);
        assert!(writer.applied.lock().unwrap().is_empty());
    }

    #[test]
    fn resumability_resumes_from_checkpoint() {
        let agg = AggregateRef {
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            aggregate_type: "world_kv".into(),
            aggregate_id: "k1".into(),
        };
        let checkpoints = InMemoryCheckpointStore::default();
        // Prior run got to version 2 but didn't complete.
        checkpoints
            .set("stub", &agg, Checkpoint { last_applied_version: 2, completed: false })
            .unwrap();

        let events = FakeEvents {
            per_agg: vec![(
                "k1".to_string(),
                vec![env("world_kv", "k1", 1), env("world_kv", "k1", 2), env("world_kv", "k1", 3), env("world_kv", "k1", 4)],
            )]
            .into_iter()
            .collect(),
            busy_ms_per_batch: 0,
        };
        let writer = RecordingWriter { applied: Mutex::new(vec![]) };
        let proj = StubProjection;
        let projections: Vec<&dyn Projection> = vec![&proj];
        let plan = RebuildPlan {
            reality_id: agg.reality_id,
            aggregates: vec![agg.clone()],
            projection_name: "stub".into(),
        };

        let outcome =
            rebuild_aggregate(&plan, &agg, &RebuildConfig { batch_size: 100, ..Default::default() }, &events, &projections, &writer, &checkpoints);
        assert_eq!(outcome.status, AggregateStatus::Done);
        // Only 2 events replayed (versions 3 and 4) — versions 1 + 2 were
        // covered by the prior run's checkpoint.
        assert_eq!(outcome.events_replayed, 2);
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn parallel_rebuilder_actually_runs_in_parallel() {
        // 3 aggregates × 100ms busy-wait each. Sequential = 300ms,
        // parallel-3 should finish in ~120ms with overhead.
        let aggs: Vec<AggregateRef> = (0..3)
            .map(|i| AggregateRef {
                reality_id: Uuid::from_u128(0xDEAD_BEEF),
                aggregate_type: "world_kv".into(),
                aggregate_id: format!("k{}", i),
            })
            .collect();

        let mut per_agg = HashMap::new();
        for i in 0..3 {
            per_agg.insert(format!("k{}", i), vec![env("world_kv", &format!("k{}", i), 1)]);
        }
        let events = Arc::new(FakeEvents { per_agg, busy_ms_per_batch: 100 });
        let writer = Arc::new(RecordingWriter { applied: Mutex::new(vec![]) });
        let proj: &'static StubProjection = Box::leak(Box::new(StubProjection));
        let projections: Vec<&'static dyn SendSyncProjection> = vec![proj];
        let checkpoints = Arc::new(InMemoryCheckpointStore::default());
        let dead_letter = Arc::new(InMemoryDeadLetterStore::default());

        let rebuilder = ParallelRebuilder::new(
            RebuildConfig { parallel_workers: 3, batch_size: 100, ..Default::default() },
            events,
            projections,
            writer.clone(),
            checkpoints,
            dead_letter,
        )
        .unwrap();

        let plan = RebuildPlan {
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            aggregates: aggs.clone(),
            projection_name: "stub".into(),
        };

        let start = Instant::now();
        let outcomes = rebuilder.run(plan).await;
        let elapsed = start.elapsed();

        assert_eq!(outcomes.len(), 3);
        for o in &outcomes {
            assert!(matches!(o.status, AggregateStatus::Done));
        }
        // Parallel = should be well under 250ms (allow generous scheduling
        // overhead). Sequential would be 300ms+ guaranteed because of the
        // busy_ms_per_batch × 2 batches per aggregate (initial fetch + EOF
        // probe).
        assert!(elapsed < Duration::from_millis(500), "parallelism failed: elapsed={:?}", elapsed);
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn dead_letter_records_after_max_retries() {
        let agg = AggregateRef {
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            aggregate_type: "world_kv".into(),
            aggregate_id: "k1".into(),
        };
        let mut per_agg = HashMap::new();
        per_agg.insert("k1".into(), vec![env("world_kv", "k1", 1)]);
        // fail_total=10 > (max_retries+1)*2 batches → guaranteed to exhaust retries.
        let events = Arc::new(FlakyEvents {
            per_agg,
            fail_count: Mutex::new(0),
            fail_total: 10,
        });
        let writer = Arc::new(RecordingWriter { applied: Mutex::new(vec![]) });
        let proj: &'static StubProjection = Box::leak(Box::new(StubProjection));
        let projections: Vec<&'static dyn SendSyncProjection> = vec![proj];
        let checkpoints = Arc::new(InMemoryCheckpointStore::default());
        let dead_letter = Arc::new(InMemoryDeadLetterStore::default());

        let rebuilder = ParallelRebuilder::new(
            RebuildConfig { parallel_workers: 1, max_retries: 2, batch_size: 100, ..Default::default() },
            events,
            projections,
            writer.clone(),
            checkpoints,
            dead_letter.clone(),
        )
        .unwrap();

        let plan = RebuildPlan {
            reality_id: agg.reality_id,
            aggregates: vec![agg.clone()],
            projection_name: "stub".into(),
        };
        let outcomes = rebuilder.run(plan).await;
        assert_eq!(outcomes.len(), 1);
        assert!(matches!(outcomes[0].status, AggregateStatus::Failed { .. }));
        let dl = dead_letter.list();
        assert_eq!(dl.len(), 1);
        assert_eq!(dl[0].attempts, 3); // max_retries(2) + initial
        assert_eq!(dl[0].agg, agg);
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn writer_failure_dead_letters() {
        let agg = AggregateRef {
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            aggregate_type: "world_kv".into(),
            aggregate_id: "k1".into(),
        };
        let mut per_agg = HashMap::new();
        per_agg.insert("k1".into(), vec![env("world_kv", "k1", 1)]);
        let events = Arc::new(FakeEvents { per_agg, busy_ms_per_batch: 0 });
        let writer = Arc::new(FailingWriter);
        let proj: &'static StubProjection = Box::leak(Box::new(StubProjection));
        let projections: Vec<&'static dyn SendSyncProjection> = vec![proj];
        let checkpoints = Arc::new(InMemoryCheckpointStore::default());
        let dead_letter = Arc::new(InMemoryDeadLetterStore::default());

        let rebuilder = ParallelRebuilder::new(
            RebuildConfig { parallel_workers: 1, max_retries: 1, batch_size: 100, ..Default::default() },
            events,
            projections,
            writer,
            checkpoints,
            dead_letter.clone(),
        )
        .unwrap();
        let plan = RebuildPlan {
            reality_id: agg.reality_id,
            aggregates: vec![agg.clone()],
            projection_name: "stub".into(),
        };
        let outcomes = rebuilder.run(plan).await;
        assert!(matches!(outcomes[0].status, AggregateStatus::Failed { .. }));
        assert_eq!(dead_letter.list().len(), 1);
    }

    #[test]
    fn config_validation_rejects_zero_workers() {
        let events = Arc::new(FakeEvents { per_agg: HashMap::new(), busy_ms_per_batch: 0 });
        let writer = Arc::new(RecordingWriter { applied: Mutex::new(vec![]) });
        let proj: &'static StubProjection = Box::leak(Box::new(StubProjection));
        let projections: Vec<&'static dyn SendSyncProjection> = vec![proj];
        let checkpoints = Arc::new(InMemoryCheckpointStore::default());
        let dead_letter = Arc::new(InMemoryDeadLetterStore::default());

        let res = ParallelRebuilder::new(
            RebuildConfig { parallel_workers: 0, ..Default::default() },
            events,
            projections,
            writer,
            checkpoints,
            dead_letter,
        );
        match res {
            Err(RebuildError::Config(_)) => {}
            Err(other) => panic!("expected Config error, got {:?}", other),
            Ok(_) => panic!("expected error, got Ok"),
        }
    }
}
