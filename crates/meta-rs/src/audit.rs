//! L4.C — Audit-row + outbox-event types + supporting traits.
//!
//! Mirrors `contracts/meta/metawrite.go::MetaWriteAuditRow` +
//! `LifecycleTransitionAuditRow` + `OutboxEvent` and the small
//! `Clock` / `UUIDGen` / `OutboxAppender` collaborator interfaces.
//!
//! Kept in its own file so `metawrite.rs` and `transitions.rs` can share these
//! without cyclic imports.

use serde::{Deserialize, Serialize};
use std::cell::Cell;
use uuid::Uuid;

use crate::errors::MetaError;
use crate::metawrite::{ActorType, MetaWriteOp, RequestContext, TransactionExecutor, ValueMap};

/// One audit row written into `meta_write_audit` in the same TX as the data
/// write. Mirrors `MetaWriteAuditRow` in `contracts/meta/metawrite.go`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MetaWriteAuditRow {
    /// Audit row primary key (UUID v4).
    pub audit_id: Uuid,
    /// Table that was written to.
    pub table_name: String,
    /// SQL operation.
    pub operation: MetaWriteOp,
    /// Primary key columns of the affected row.
    pub row_pk: ValueMap,
    /// Before-image (CAS guard for UPDATE; row image for DELETE).
    pub before_values: ValueMap,
    /// After-image (final column values for INSERT/UPDATE).
    pub after_values: ValueMap,
    /// Actor kind.
    pub actor_type: ActorType,
    /// Actor id.
    pub actor_id: String,
    /// Human-readable reason (required for DELETE).
    pub reason: String,
    /// Trace + request envelope.
    pub request_context: RequestContext,
    /// `created_at` as unix nanos (codec-agnostic).
    pub created_at_nanos: i64,
}

/// One lifecycle audit row written by `AttemptStateTransition`. Mirrors
/// `LifecycleTransitionAuditRow` in `contracts/meta/metawrite.go`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LifecycleTransitionAuditRow {
    /// Audit row primary key (UUID v4).
    pub audit_id: Uuid,
    /// Resource id (e.g., reality_id, incident_id).
    pub resource_id: String,
    /// State the resource was in.
    pub from_status: String,
    /// State the caller requested.
    pub to_status: String,
    /// Actor id.
    pub actor_id: String,
    /// Actor kind.
    pub actor_type: ActorType,
    /// Did the transition succeed?
    pub succeeded: bool,
    /// Empty when `succeeded`; one of: `invalid_transition`,
    /// `mutual_exclusion`, `concurrent_modification`, `database_error`.
    pub failure_reason: String,
    /// Extra columns set in the same UPDATE (caller-supplied).
    #[serde(default)]
    pub payload: ValueMap,
    /// Attempted-at as unix nanos.
    pub attempted_at_nanos: i64,
}

/// One outbox event row appended by `MetaWrite` in the same TX.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OutboxEvent {
    /// Event id (UUID v4).
    pub event_id: Uuid,
    /// Outbox event_name (from allowlist binding).
    pub event_name: String,
    /// Aggregate id (stable string composed from PK).
    pub aggregate_id: String,
    /// Free-form payload (typically `{table, operation, pk, after}`).
    pub payload: serde_json::Value,
    /// Recorded-at as unix nanos.
    pub recorded_at_nanos: i64,
}

/// Lets `MetaWrite` write outbox rows without owning a driver. Implementors
/// typically `INSERT INTO events_outbox(...)` using the same TX handle.
pub trait OutboxAppender<Tx: TransactionExecutor> {
    /// Append one outbox row using the supplied TX.
    fn append(&self, tx: &mut Tx, event: OutboxEvent) -> Result<(), MetaError>;
}

/// Lets tests inject a deterministic time source.
pub trait AuditClock {
    /// Returns the current unix nanos.
    fn now_unix_nanos(&self) -> i64;
}

/// Lets tests inject a deterministic UUID source.
pub trait AuditUuidGen {
    /// Returns a new UUID (v4 in production; fixed in tests).
    fn new_uuid(&self) -> Uuid;
}

// ── Test fixtures (also usable by downstream Rust services for tests) ──────

/// Deterministic clock returning the configured nanos value.
#[derive(Debug, Clone, Copy)]
pub struct FixedClock(pub i64);
impl AuditClock for FixedClock {
    fn now_unix_nanos(&self) -> i64 {
        self.0
    }
}

/// Deterministic UUID source returning the same id on every call.
#[derive(Debug, Clone, Copy)]
pub struct FixedUuid(pub Uuid);
impl AuditUuidGen for FixedUuid {
    fn new_uuid(&self) -> Uuid {
        self.0
    }
}

/// Production clock — wraps `std::time::SystemTime`.
#[derive(Debug, Default, Clone, Copy)]
pub struct SystemClock;
impl AuditClock for SystemClock {
    fn now_unix_nanos(&self) -> i64 {
        use std::time::{SystemTime, UNIX_EPOCH};
        let d = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default();
        d.as_nanos() as i64
    }
}

/// Production UUID generator — wraps `uuid::Uuid::new_v4`.
#[derive(Debug, Default, Clone, Copy)]
pub struct V4UuidGen;
impl AuditUuidGen for V4UuidGen {
    fn new_uuid(&self) -> Uuid {
        Uuid::new_v4()
    }
}

/// No-op outbox that just counts appends. Used by tests that exercise the
/// MetaWrite flow without a real outbox table.
#[derive(Debug, Default)]
pub struct NoopOutbox {
    appended: Cell<usize>,
}

impl NoopOutbox {
    /// Returns the number of append calls observed.
    pub fn appended_count(&self) -> usize {
        self.appended.get()
    }
}

impl<Tx: TransactionExecutor> OutboxAppender<Tx> for NoopOutbox {
    fn append(&self, _tx: &mut Tx, _event: OutboxEvent) -> Result<(), MetaError> {
        self.appended.set(self.appended.get() + 1);
        Ok(())
    }
}
