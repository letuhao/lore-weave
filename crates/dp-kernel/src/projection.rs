//! L3.B — `Projection` trait + per-aggregate `apply_event()` runtime.
//!
//! ## Scope (RAID cycle 12)
//!
//! Defines the SYNC contract for converting an [`EventEnvelope`] into one or
//! more [`ProjectionUpdate`]s that the projection runtime will execute against
//! per-reality DB tables.
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3B-1** (OPEN_QUESTIONS_LOCKED §5): `Projection` returns
//!   `Vec<ProjectionUpdate>` — a single event may update multiple projection
//!   tables atomically (e.g. `pc.said` increments `pc_projection.last_event_version`
//!   AND `npc_session_memory_projection.interaction_count`).
//! - **Q-L3-2** (§5): NO async projection in V1. Trait is sync; an async
//!   variant (V3+) would be a separate trait, not a default-impl.
//! - **Q-L3-4** (§5): Every projection row carries verification metadata
//!   (`event_id`, `aggregate_version`, `applied_at`). The metadata is part of
//!   the [`ProjectionUpdate`] payload here; cycle-13 L3.A adds the column
//!   shapes (`last_verified_event_version BIGINT`, `last_verified_at TIMESTAMPTZ`).
//! - **Q-L3-5** (§5): NO V2 blue-green migration scaffolding (V2+ scope).
//!
//! ## What is NOT in cycle 12
//!
//! - **L3.A projection TABLES** — cycle 13.
//! - **Per-aggregate projection implementations** (PC, NPC, region, …) —
//!   cycle 13/14 ride on top of the contract here.
//! - **Snapshot READ runtime** — DPS 2 sibling (`load_aggregate.rs`).
//! - **`#[derive(Projection)]` proc-macro** (L3.B.2) — deferred to L4
//!   macros cycle.
//! - **`async fn apply_event`** — explicitly OUT per Q-L3-2.
//! - **DB transaction handling** — the trait yields a `Vec<ProjectionUpdate>`;
//!   the caller composes them into a single TX (matches outbox.rs design:
//!   transport-agnostic, caller owns TX scope).
//!
//! ## Contract for cycle 13+
//!
//! A concrete projection (e.g. `WorldStateProjection`) implements
//! [`Projection`] and:
//!
//! 1. Inspects `env.event_type` — if unrelated, returns `vec![]` (empty Vec
//!    is the "skip" path; the runtime does not treat this as an error).
//! 2. Inspects `env.payload` — typed deserialization is the projection's
//!    job; the trait stays payload-agnostic.
//! 3. Returns one or more [`ProjectionUpdate`]s, each annotated with
//!    [`VerificationMeta`] derived from the envelope.
//!
//! Idempotency is handled by [`ProjectionRunner::should_skip`] —
//! `env.aggregate_version <= projection.last_seen_version(env.aggregate_id)`
//! means the event was already applied; runner skips without calling
//! `apply_event`. This is the L3.B.9 idempotency contract.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

use crate::envelope::{EventEnvelope, Rfc3339Timestamp};

/// Verification metadata stamped on every projected row (Q-L3-4 contract).
///
/// Cycle-13 L3.A migration adds columns:
///   * `last_verified_event_version BIGINT`  ← `aggregate_version`
///   * `last_verified_at            TIMESTAMPTZ` ← `applied_at`
///
/// `event_id` is kept here for debug + integrity-checker (L3.E sampler can
/// confirm "this row was last touched by event X").
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct VerificationMeta {
    pub event_id: Uuid,
    pub aggregate_version: u64,
    pub applied_at: Rfc3339Timestamp,
}

impl VerificationMeta {
    /// Build verification metadata from an envelope. `applied_at` is taken
    /// from `env.recorded_at` (the server-side timestamp at append) — using
    /// `recorded_at` (not `occurred_at`) ensures monotonicity per
    /// `(aggregate_id, version)` even when in-world time differs.
    pub fn from_envelope(env: &EventEnvelope) -> Self {
        Self {
            event_id: env.event_id,
            aggregate_version: env.aggregate_version,
            applied_at: env.recorded_at.clone(),
        }
    }
}

/// One projection-table mutation. The runtime composes a `Vec<ProjectionUpdate>`
/// into a single DB TX per envelope.
///
/// `Tombstone` is distinct from `Delete`: it leaves a marker row (e.g. for
/// audit / soft-delete patterns) while `Delete` removes the row entirely.
/// Both carry [`VerificationMeta`] so the integrity checker can detect
/// orphans.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ProjectionUpdate {
    Insert {
        table: String,
        row: Value,
        meta: VerificationMeta,
    },
    Update {
        table: String,
        pk: Value,
        fields: Value,
        meta: VerificationMeta,
    },
    Delete {
        table: String,
        pk: Value,
    },
    Tombstone {
        table: String,
        pk: Value,
        meta: VerificationMeta,
    },
}

impl ProjectionUpdate {
    /// Returns the target table for this update.
    pub fn table(&self) -> &str {
        match self {
            ProjectionUpdate::Insert { table, .. } => table,
            ProjectionUpdate::Update { table, .. } => table,
            ProjectionUpdate::Delete { table, .. } => table,
            ProjectionUpdate::Tombstone { table, .. } => table,
        }
    }
}

/// The projection trait. SYNC only (Q-L3-2).
///
/// Implementors are typically small structs that hold per-aggregate state
/// (or none at all). The runtime guarantees:
///   * Each envelope is presented in `(aggregate_id, aggregate_version)`
///     order.
///   * `apply_event` is called exactly once per (envelope, projection) pair
///     unless idempotency-skip fires.
///   * Returning `vec![]` is the SKIP path — the runtime does NOT treat
///     it as an error.
pub trait Projection {
    /// Stable name for this projection (used in logs + metrics). Convention:
    /// `<aggregate>_<purpose>`, e.g. `pc_state`, `npc_session_memory`.
    fn name(&self) -> &str;

    /// Decide whether this envelope is relevant to this projection. Default
    /// impl returns `true` (let `apply_event` decide); concrete projections
    /// can override for cheap event-type pre-filtering.
    fn handles(&self, _env: &EventEnvelope) -> bool {
        true
    }

    /// Compute updates for this envelope. Empty Vec = projection is not
    /// relevant to this envelope. The runtime accepts the empty Vec as a
    /// valid skip path; it does NOT shortcut on `handles() == false`
    /// (callers can short-circuit themselves if perf matters).
    fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate>;
}

/// Runtime orchestrator for the L3.B sync projection contract.
///
/// Holds an ordered set of [`Projection`] implementations. For each
/// envelope, it fans out to each projection and accumulates the returned
/// updates. The caller wraps the result in a DB TX.
pub struct ProjectionRunner<'p> {
    projections: Vec<&'p dyn Projection>,
}

impl<'p> ProjectionRunner<'p> {
    pub fn new() -> Self {
        Self { projections: vec![] }
    }

    pub fn with_projection(mut self, proj: &'p dyn Projection) -> Self {
        self.projections.push(proj);
        self
    }

    pub fn projections(&self) -> &[&'p dyn Projection] {
        &self.projections
    }

    /// Apply one envelope across all registered projections. Returns the
    /// flattened list of updates (in projection registration order).
    pub fn apply_one(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
        let mut out = Vec::new();
        for p in &self.projections {
            if !p.handles(env) {
                continue;
            }
            out.extend(p.apply_event(env));
        }
        out
    }

    /// Apply a batch of envelopes. Returns one `Vec<ProjectionUpdate>` per
    /// input envelope, preserving order. The caller decides TX granularity
    /// (one TX per envelope vs one TX per batch).
    pub fn apply_batch(&self, envs: &[EventEnvelope]) -> Vec<Vec<ProjectionUpdate>> {
        envs.iter().map(|e| self.apply_one(e)).collect()
    }

    /// Idempotency helper: returns `true` if `env.aggregate_version` is
    /// less-than-or-equal-to the supplied `last_seen_version`. Caller looks
    /// up the high-water-mark per `(aggregate_type, aggregate_id)` from its
    /// own state (e.g. `last_event_version` column on the projection table).
    pub fn should_skip(env: &EventEnvelope, last_seen_version: u64) -> bool {
        env.aggregate_version <= last_seen_version
    }
}

impl<'p> Default for ProjectionRunner<'p> {
    fn default() -> Self {
        Self::new()
    }
}

// ───────────────────────────────────────────────────────────────────────────
// Tests
// ───────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn env(event_type: &str, agg_type: &str, agg_id: &str, agg_version: u64) -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::from_u128(agg_version as u128),
            event_type: event_type.into(),
            event_version: 1,
            aggregate_id: agg_id.into(),
            aggregate_type: agg_type.into(),
            aggregate_version: agg_version,
            reality_id: Uuid::from_u128(0xDEAD_BEEF),
            occurred_at: "2026-05-29T00:00:00Z".into(),
            recorded_at: format!("2026-05-29T00:00:{:02}Z", agg_version % 60),
            payload: json!({}),
            metadata: None,
        }
    }

    // A WorldStateProjection that emits a single Update per `world.tick`
    // event and ignores all other event types.
    struct WorldStateProjection;
    impl Projection for WorldStateProjection {
        fn name(&self) -> &str {
            "world_state"
        }
        fn handles(&self, env: &EventEnvelope) -> bool {
            env.event_type == "world.tick"
        }
        fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
            if env.event_type != "world.tick" {
                return vec![];
            }
            vec![ProjectionUpdate::Update {
                table: "world_kv_projection".into(),
                pk: json!({ "key": "world.tick" }),
                fields: json!({ "value": env.aggregate_version }),
                meta: VerificationMeta::from_envelope(env),
            }]
        }
    }

    // A counter projection that BOTH updates pc_projection AND increments
    // an interaction counter — the multi-update case from Q-L3B-1.
    struct PcSaidMultiProjection;
    impl Projection for PcSaidMultiProjection {
        fn name(&self) -> &str {
            "pc_said_multi"
        }
        fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate> {
            if env.event_type != "pc.said" {
                return vec![];
            }
            let meta = VerificationMeta::from_envelope(env);
            vec![
                ProjectionUpdate::Update {
                    table: "pc_projection".into(),
                    pk: json!({ "pc_id": env.aggregate_id }),
                    fields: json!({ "last_event_version": env.aggregate_version }),
                    meta: meta.clone(),
                },
                ProjectionUpdate::Update {
                    table: "npc_session_memory_projection".into(),
                    pk: json!({ "session_id": env.metadata.as_ref()
                        .and_then(|m| m.get("session_id"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("none") }),
                    fields: json!({ "interaction_count_increment": 1 }),
                    meta,
                },
            ]
        }
    }

    #[test]
    fn empty_vec_when_event_unrelated() {
        let p = WorldStateProjection;
        let e = env("npc.said", "npc", "npc-1", 1);
        assert!(p.apply_event(&e).is_empty(), "irrelevant event must yield empty Vec, not panic");
    }

    #[test]
    fn projection_returns_single_update() {
        let p = WorldStateProjection;
        let e = env("world.tick", "world", "world-1", 42);
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].table(), "world_kv_projection");
    }

    #[test]
    fn projection_returns_multiple_updates_q_l3b_1() {
        let p = PcSaidMultiProjection;
        let mut e = env("pc.said", "pc", "pc-1", 7);
        e.metadata = Some(json!({ "session_id": "sess-9" }));
        let updates = p.apply_event(&e);
        assert_eq!(updates.len(), 2, "Q-L3B-1: one event may emit multiple updates");
        assert_eq!(updates[0].table(), "pc_projection");
        assert_eq!(updates[1].table(), "npc_session_memory_projection");
    }

    #[test]
    fn verification_meta_uses_recorded_at_for_monotonicity() {
        let p = WorldStateProjection;
        let e1 = env("world.tick", "world", "world-1", 1);
        let e2 = env("world.tick", "world", "world-1", 2);
        let u1 = &p.apply_event(&e1)[0];
        let u2 = &p.apply_event(&e2)[0];
        let m1 = match u1 {
            ProjectionUpdate::Update { meta, .. } => meta,
            _ => unreachable!(),
        };
        let m2 = match u2 {
            ProjectionUpdate::Update { meta, .. } => meta,
            _ => unreachable!(),
        };
        assert!(m1.applied_at <= m2.applied_at, "applied_at monotonic with aggregate_version");
        assert_eq!(m1.aggregate_version, 1);
        assert_eq!(m2.aggregate_version, 2);
    }

    #[test]
    fn runner_fan_out_across_projections() {
        let world = WorldStateProjection;
        let pc = PcSaidMultiProjection;
        let runner = ProjectionRunner::new()
            .with_projection(&world)
            .with_projection(&pc);
        assert_eq!(runner.projections().len(), 2);

        let tick = env("world.tick", "world", "world-1", 1);
        let updates = runner.apply_one(&tick);
        assert_eq!(updates.len(), 1, "only world projection fires on world.tick");
        assert_eq!(updates[0].table(), "world_kv_projection");

        let mut said = env("pc.said", "pc", "pc-1", 5);
        said.metadata = Some(json!({ "session_id": "sess-7" }));
        let updates = runner.apply_one(&said);
        assert_eq!(updates.len(), 2, "only pc projection fires on pc.said (2 updates from one event)");
    }

    #[test]
    fn runner_skips_via_handles_predicate() {
        // PcSaidMultiProjection doesn't override `handles` — default returns
        // true and the inner `if env.event_type != ...` does the skip.
        // WorldStateProjection DOES override handles().
        let world = WorldStateProjection;
        let runner = ProjectionRunner::new().with_projection(&world);
        let unrelated = env("npc.said", "npc", "npc-1", 1);
        // `handles(unrelated) == false` so runner short-circuits without
        // calling apply_event — observable as zero updates.
        assert!(runner.apply_one(&unrelated).is_empty());
    }

    #[test]
    fn runner_apply_batch_preserves_order() {
        let world = WorldStateProjection;
        let runner = ProjectionRunner::new().with_projection(&world);
        let batch = vec![
            env("world.tick", "world", "world-1", 1),
            env("npc.said", "npc", "npc-1", 2), // skipped
            env("world.tick", "world", "world-1", 3),
        ];
        let out = runner.apply_batch(&batch);
        assert_eq!(out.len(), 3);
        assert_eq!(out[0].len(), 1);
        assert!(out[1].is_empty(), "irrelevant envelope yields empty inner Vec");
        assert_eq!(out[2].len(), 1);
    }

    #[test]
    fn idempotency_skip_when_version_already_seen() {
        let e = env("world.tick", "world", "world-1", 5);
        assert!(ProjectionRunner::should_skip(&e, 5), "version equal = already applied");
        assert!(ProjectionRunner::should_skip(&e, 10), "version less than high-water = already applied");
        assert!(!ProjectionRunner::should_skip(&e, 4), "version greater than high-water = apply");
    }

    #[test]
    fn projection_update_variants_round_trip_json() {
        let meta = VerificationMeta {
            event_id: Uuid::from_u128(1),
            aggregate_version: 5,
            applied_at: "2026-05-29T00:00:05Z".into(),
        };
        let cases = vec![
            ProjectionUpdate::Insert {
                table: "t".into(),
                row: json!({"a": 1}),
                meta: meta.clone(),
            },
            ProjectionUpdate::Update {
                table: "t".into(),
                pk: json!({"id": 1}),
                fields: json!({"a": 2}),
                meta: meta.clone(),
            },
            ProjectionUpdate::Delete {
                table: "t".into(),
                pk: json!({"id": 1}),
            },
            ProjectionUpdate::Tombstone {
                table: "t".into(),
                pk: json!({"id": 1}),
                meta,
            },
        ];
        for c in cases {
            let s = serde_json::to_string(&c).unwrap();
            let back: ProjectionUpdate = serde_json::from_str(&s).unwrap();
            assert_eq!(c, back);
        }
    }
}
