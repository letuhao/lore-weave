//! L3.I / Q-L1A-3 — Audit emitter for embedding-queue provider calls.
//!
//! Every call from the embedding queue to an [`EmbeddingProvider`]
//! (whether successful, dim-mismatched, or errored) emits ONE row into
//! the `service_to_service_audit` table (cycle-7 L1.A-4 meta DB). This is
//! the Q-L1A-3 "full audit, no sampling" decision applied to embedding
//! cost tracking: even rejected provider responses cost tokens.
//!
//! ## Audit row shape
//!
//! The on-the-wire row in `service_to_service_audit` is wider than the
//! [`AuditEvent`] here (it includes a surrogate audit_id, created_at_nanos,
//! caller/callee/rpc fields, etc — see cycle-7 `migrations/meta/016`). The
//! [`AuditWriter`] adapter is responsible for populating those: production
//! wiring binds [`AuditWriter`] to a sqlx INSERT
//! (`crate::embedding_queue::live::MetaAuditWriter`).
//!
//! ## Why we keep `AuditEvent` POD
//!
//! Mirroring the [`crate::embedding_queue::EmbeddingWriter`] split: the
//! audit recorder is a trait so unit tests can use an in-memory counter
//! without needing sqlx + a running Postgres. The [`CountingAuditWriter`]
//! in this module is the test-time impl; production binds
//! [`crate::embedding_queue::live::MetaAuditWriter`].

use std::sync::Mutex;

use async_trait::async_trait;
use uuid::Uuid;

/// Outcome enum surfaced into the audit row's `outcome` mapping.
/// Stays SMALL so cardinality of `lw_embedding_audit_outcome_total{outcome=...}`
/// (V1+30d obs counter) is bounded.
#[derive(Debug, Clone, PartialEq)]
pub enum AuditOutcome {
    /// Provider returned a correctly-dimensioned vector + write succeeded.
    Ok,
    /// Provider returned a vector of the wrong dimension. The cost of the
    /// call was still incurred (we paid for the tokens), so it MUST be
    /// audited.
    DimMismatch {
        /// What the provider actually returned.
        returned_dim: usize,
    },
    /// Provider call failed (network, 5xx, timeout, rate-limit). Token
    /// count is recorded as 0 in the audit row (no successful billing).
    ProviderError(String),
    /// Provider call succeeded but the subsequent DB write failed. This
    /// is the most expensive failure — the BYOK provider has billed the
    /// caller but the embedding column is still NULL. Daily integrity
    /// checker re-enqueues; the audit row is the evidence trail.
    WriteError(String),
}

impl AuditOutcome {
    /// Stable lowercase discriminator string. Used by the metrics counter
    /// label AND folded into the `service_to_service_audit.result` mapping
    /// (`ok` → "ok"; everything else → "error" per the table's CHECK enum,
    /// with this finer-grained kind carried in correlation fields).
    pub fn kind(&self) -> &'static str {
        match self {
            AuditOutcome::Ok => "ok",
            AuditOutcome::DimMismatch { .. } => "dim_mismatch",
            AuditOutcome::ProviderError(_) => "provider_error",
            AuditOutcome::WriteError(_) => "write_error",
        }
    }
}

/// One audit-row payload. Production wiring lands this into
/// `service_to_service_audit` via a sqlx INSERT (Q-L1A-3 full audit).
#[derive(Debug, Clone, PartialEq)]
pub struct AuditEvent {
    /// Reality the embedding belongs to. Audit DB partitions on this.
    pub reality_id: Uuid,
    /// NPC the embedding belongs to.
    pub npc_id: Uuid,
    /// Session the embedding belongs to.
    pub session_id: Uuid,
    /// BYOK provider name (audit anchor — e.g. "openai", "cohere",
    /// "local-bge"). MUST come from the provider gateway, not be hardcoded
    /// in the queue.
    pub provider: String,
    /// Concrete model identifier from the provider response (e.g.
    /// "text-embedding-ada-002"). This is what the user's bill itemizes
    /// against.
    pub model: String,
    /// Token count for cost tracking. 0 for failure outcomes.
    pub tokens: u32,
    /// Discriminator + reason for the call.
    pub outcome: AuditOutcome,
}

/// Trait the queue speaks to for audit emission. Production binds to a
/// sqlx INSERT adapter; tests use [`CountingAuditWriter`].
#[async_trait]
pub trait AuditWriter: Send + Sync {
    /// Record one audit event. Production wiring INSERTs one row into
    /// `service_to_service_audit`; during meta-DB degraded mode the call
    /// (and thus the queue tick) WILL stall as designed — audit writes are
    /// degraded-mode-essential per the Q-L1A-3 audit invariant.
    async fn record(&self, event: AuditEvent);
}

/// Test-time + integration-test [`AuditWriter`] that collects events in
/// memory. Interior-mutable (`&self`) via `Mutex` so it matches the
/// production adapter's shared-handle shape.
#[derive(Default)]
pub struct CountingAuditWriter {
    events: Mutex<Vec<AuditEvent>>,
}

impl CountingAuditWriter {
    /// Snapshot of all events recorded so far, in order.
    pub fn events(&self) -> Vec<AuditEvent> {
        self.events.lock().unwrap().clone()
    }

    /// Number of events recorded.
    pub fn len(&self) -> usize {
        self.events.lock().unwrap().len()
    }

    /// True if no events recorded yet.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Total token count across all OK events — useful for cost-budget
    /// assertions in tests.
    pub fn total_ok_tokens(&self) -> u32 {
        self.events
            .lock()
            .unwrap()
            .iter()
            .filter(|e| matches!(e.outcome, AuditOutcome::Ok))
            .map(|e| e.tokens)
            .sum()
    }

    /// Count events matching a given outcome discriminator. Test helper.
    pub fn count_by_outcome_kind(&self, kind: &str) -> usize {
        self.events
            .lock()
            .unwrap()
            .iter()
            .filter(|e| e.outcome.kind() == kind)
            .count()
    }
}

#[async_trait]
impl AuditWriter for CountingAuditWriter {
    async fn record(&self, event: AuditEvent) {
        self.events.lock().unwrap().push(event);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn evt(outcome: AuditOutcome, tokens: u32) -> AuditEvent {
        AuditEvent {
            reality_id: Uuid::from_u128(1),
            npc_id: Uuid::from_u128(2),
            session_id: Uuid::from_u128(3),
            provider: "openai".into(),
            model: "text-embedding-ada-002".into(),
            tokens,
            outcome,
        }
    }

    #[tokio::test]
    async fn counting_writer_total_ok_tokens_sums_only_ok() {
        let w = CountingAuditWriter::default();
        w.record(evt(AuditOutcome::Ok, 100)).await;
        w.record(evt(AuditOutcome::ProviderError("nope".into()), 0))
            .await;
        w.record(evt(AuditOutcome::Ok, 50)).await;
        w.record(evt(AuditOutcome::DimMismatch { returned_dim: 768 }, 0))
            .await;
        assert_eq!(w.total_ok_tokens(), 150);
    }

    #[tokio::test]
    async fn counting_writer_count_by_outcome_kind() {
        let w = CountingAuditWriter::default();
        w.record(evt(AuditOutcome::Ok, 10)).await;
        w.record(evt(AuditOutcome::Ok, 20)).await;
        w.record(evt(AuditOutcome::DimMismatch { returned_dim: 768 }, 0))
            .await;
        w.record(evt(AuditOutcome::ProviderError("x".into()), 0))
            .await;
        w.record(evt(AuditOutcome::WriteError("y".into()), 0)).await;
        assert_eq!(w.count_by_outcome_kind("ok"), 2);
        assert_eq!(w.count_by_outcome_kind("dim_mismatch"), 1);
        assert_eq!(w.count_by_outcome_kind("provider_error"), 1);
        assert_eq!(w.count_by_outcome_kind("write_error"), 1);
    }
}
