//! `dp-kernel` — LoreWeave data-platform kernel.
//!
//! ## Module scope by RAID cycle
//!
//! ### Cycle 8 / L2.H + L2.I — schema-evolution + write-time validation
//! - [`upcaster`] — per-event `vN -> vN+1` transformation chain;
//!   IDEMPOTENT + REPLAY-SAFE; refuses backward upcasts.
//! - [`event_validator`] — schema validation on write (R03 §12C.4).
//!
//! ### Cycle 10 / L2.C — outbox
//! - [`outbox`] — transport-agnostic outbox writer; caller owns the TX.
//!
//! ### Cycle 12 / L3.B + L3.C — projections + snapshot read
//! - [`envelope`] — Rust mirror of `contracts/events/envelope.go::Envelope`.
//! - [`projection`] — sync `Projection` trait; one event ↦ `Vec<ProjectionUpdate>`
//!   (Q-L3B-1). Carries [`projection::VerificationMeta`] per Q-L3-4.
//! - [`load_aggregate`] + [`snapshot_cache`] — `load_aggregate<A: Aggregate>`
//!   reconstructs aggregate state from `aggregate_snapshots` (L2.E) + delta
//!   events. Bounded LRU snapshot cache.
//!
//! ### Cycle 17 / L4.A — Event + EventStore + Snapshot trait + Postgres backend
//! - [`event`] — domain-typed [`Event`] trait. Service code works in typed
//!   terms then converts to [`EventEnvelope`] at the EventStore boundary.
//! - [`metadata`] — typed [`EventMetadata`] view over the envelope's
//!   free-form `metadata` blob (additive only; flatten preserves unknown fields).
//! - [`aggregate`] — canonical re-export of cycle-12 [`Aggregate`] + the
//!   additive [`AggregateMeta`] trait (used by `#[derive(Aggregate)]`).
//! - [`snapshot`] — [`Snapshot`] trait (encoder/decoder + schema version);
//!   distinct from cycle-12 `SnapshotStore` (I/O abstraction).
//! - [`event_store`] — async [`EventStore`] trait + canonical errors +
//!   `shared_test_suite::run_event_store_tests` + `InMemoryEventStore`.
//! - [`event_store_pg`] — Postgres impl of [`EventStore`]; WRAPPED `PgPool`
//!   behind `pub(crate) pool: Arc<PgPool>` per Q-L4A-1.
//!
//! ### Cycle 21 / L4.D + L4.L — prompt SDK + WS envelope Rust mirrors
//! - [`prompt`] — Rust mirror of `contracts/prompt/` (S09 §12Y SKELETON):
//!   typed [`prompt::Intent`] (7-variant) + [`prompt::Section`] (8-variant,
//!   fixed order) + [`prompt::PromptContext`] + [`prompt::PromptBundle`]
//!   (body-never-stored) + [`prompt::Composer`] trait (Q-L6H-1 FAIL not
//!   best-effort) + no-op safety/consent/budget hooks (Q-L6L-1) + audit
//!   writer bridging cycle-4 `prompt_audit`. ProviderPayload OPAQUE
//!   (Q-L4D-1). Empty templates (Q-L6K-1 — foundation does not own copy).
//! - [`ws`] — Rust mirror of `contracts/ws/` (S12 §12AB SKELETON):
//!   typed [`ws::Ticket`] (60s TTL) + [`ws::Envelope`] (control vs data
//!   + 11 close codes) + [`ws::WSSession`] (15-min TTL, refresh, seq /
//!   nonce tracking) + ServiceMode integration (cycle 18 lifecycle:
//!   ReadOnly mode rejects WS writes). SERVER-only — no browser TS lib
//!   (Q-L6-3: frontend-game team owns browser lib).
//!
//! ### Cycle 20 / L4.C + L4.E + L4.K — entity_status + turn + errors Rust mirrors
//! - [`entity_status`] — Rust mirror of `contracts/entity_status/` (S10 §12Z):
//!   typed [`entity_status::GoneState`] + [`entity_status::Resolver`] 4-layer
//!   cascade (PIIKek → reality_registry → reality_ancestry → projections) +
//!   compound precedence + cache surface. Q-L4-1 parity.
//! - [`turn`] — Rust mirror of `contracts/turn/` (SR11 §12AN):
//!   typed [`turn::TurnState`] 8-variant enum + [`turn::TurnContext`] +
//!   turn lifecycle hooks (turn_start, turn_end) integrating with cycle-18
//!   lifecycle. Q-L4-1 parity.
//! - [`turn_errors`] — Rust mirror of `contracts/errors/` canonical error
//!   taxonomy ([`turn_errors::ErrorClass`] 4-variant: UserError, SystemError,
//!   Transient, Permanent) + [`turn_errors::ErrorEnvelope`] + exhaustive
//!   stable error codes (no "Other" catch-all).
//!
//! ### Cycle 19 / L4.H + L4.I + L4.J — observability + capacity + supply_chain Rust mirrors
//! - [`observability`] — Rust mirror of `contracts/observability/` (SR12 §12AO):
//!   typed [`observability::Inventory`] + [`observability::Admission`] +
//!   [`observability::TraceConvention`]. Q-L4-1 parity with the Go contracts.
//!   Same JSON-only architectural pattern as cycle-18 `dependencies` mirror.
//! - [`capacity`] — Rust mirror of `contracts/capacity/` (SR08 I17):
//!   typed [`capacity::Budgets`] + per-service replica/CPU/memory plan +
//!   admission check on service registration.
//! - [`supply_chain`] — Rust mirror of `contracts/supply_chain/` (SR10 I18):
//!   typed [`supply_chain::Policy`] + license allowlist + SBOM emit row +
//!   programmatic [`supply_chain::Provenance::verify`] helper (cosign stub).
//!
//! ### Cycle 18 / L4.F + L4.G + L4.N — resilience + lifecycle + dependencies Rust mirrors
//! - [`resilience`] — Rust mirror of `contracts/resilience/` (4 primitives:
//!   [`resilience::with_timeout`], [`resilience::CircuitBreaker`],
//!   [`resilience::retry`], [`resilience::Bulkhead`]). Q-L4-1 parity with
//!   the Go contracts.
//! - [`lifecycle`] — Rust mirror of `contracts/lifecycle/`. Re-exports the
//!   cycle-7 [`lifecycle::ServiceMode`] enum (kept in lockstep with the Go
//!   side) + cycle-18 additions: [`lifecycle::drain`] orchestrator and
//!   [`lifecycle::PresenceState`] 6-variant enum (SR11).
//! - [`dependencies`] — Rust mirror of `contracts/dependencies/`. The
//!   typed [`dependencies::Matrix`] + [`dependencies::ClientFactory`] +
//!   YAML loader with DAG cycle detection.
//!
//! ### Shared
//! - [`errors`] — typed [`EventError`] enum (schema / upcaster / etc.).
//!
//! The Go side of the legacy modules lives in `contracts/events/upcasters_go/`
//! and `contracts/events/validators_go/`. The L4.A EventStore is Rust-first
//! (no Go mirror in scope this cycle; cycle 19+ adds Go client per Q-L4-1).
//!
//! ## Stability contract
//!
//! Symbols exported at the root (`pub use`) are V1-stable. Sub-module paths
//! may be reshaped within `dp-kernel` between cycles — prefer the root
//! re-exports.

pub mod aggregate;
pub mod capacity;
pub mod dependencies;
pub mod entity_status;
pub mod envelope;
pub mod errors;
pub mod event;
pub mod event_store;
pub mod event_store_pg;
pub mod event_validator;
pub mod lifecycle;
pub mod load_aggregate;
pub mod metadata;
pub mod observability;
pub mod outbox;
pub mod projection;
pub mod prompt;
pub mod resilience;
pub mod snapshot;
pub mod snapshot_cache;
pub mod supply_chain;
pub mod turn;
pub mod turn_errors;
pub mod upcaster;
pub mod ws;

// ── Cycle 8 + 10 + 12 re-exports (unchanged from prior cycles) ────────────
pub use envelope::{EventEnvelope, Rfc3339Timestamp};
pub use errors::EventError;
pub use event_validator::{EventValidator, SchemaDescriptor, ValidatorRegistry};
pub use load_aggregate::{load_aggregate, Aggregate, EventReader, LoadError, SnapshotRecord, SnapshotStore};
pub use outbox::{insert_sql as outbox_insert_sql, write as outbox_write, OutboxError, OutboxRow, OutboxWriter};
pub use projection::{Projection, ProjectionRunner, ProjectionUpdate, VerificationMeta};
pub use snapshot_cache::{CacheEntry, CacheKey, SnapshotCache};
pub use upcaster::{Upcaster, UpcasterChain, UpcasterRegistry};

// ── Cycle 17 / L4.A re-exports ────────────────────────────────────────────
pub use aggregate::AggregateMeta;
pub use event::{Event, EventFromEnvelope};
pub use event_store::{EventStore, EventStoreError, EventStoreResult};
pub use event_store_pg::PgEventStore;
pub use metadata::EventMetadata;
pub use snapshot::Snapshot;
