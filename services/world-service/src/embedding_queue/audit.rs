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
//! [`AuditEvent`] here (it includes a surrogate audit_id, recorded_at
//! timestamp, calling-service field, etc — see cycle-7 contracts/meta).
//! The [`AuditWriter`] adapter is responsible for populating those:
//! production wiring binds [`AuditWriter`] to a `meta-rs::MetaWrite` call
//! that lands the row in the SAME TX as the embedding column UPDATE
//! (Q-L1B-3 multi-table TX support).
//!
//! ## Why we keep `AuditEvent` POD
//!
//! Mirroring the [`crate::embedding_queue::EmbeddingWriter`] split: the
//! audit recorder is a trait so unit tests can use an in-memory counter
//! without needing meta-rs + sqlx + a running Postgres. The
//! [`CountingAuditWriter`] in this module is the test-time impl;
//! production binds a `MetaWriteAuditAdapter` (deferred to
//! D-EMBEDDING-QUEUE-LIVE-WIRING).

use uuid::Uuid;

/// Outcome enum surfaced into the audit row's `outcome` text column.
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

/// One audit-row payload. Production wiring lands this into
/// `service_to_service_audit` via meta-rs::MetaWrite (Q-L1A-3 full audit).
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
/// MetaWrite adapter; tests use [`CountingAuditWriter`].
pub trait AuditWriter {
    /// Record one audit event. MUST NOT block on a long-running operation
    /// — production wiring uses a same-TX MetaWrite call (sub-ms when the
    /// meta DB is healthy); during meta DB degraded-mode (cycle-3) the
    /// queue WILL stall as designed (calls are degraded-mode-essential
    /// reads/writes per the audit invariant).
    fn record(&mut self, event: AuditEvent);
}

/// Test-time + integration-test [`AuditWriter`] that collects events in
/// memory. Reused by `tests/integration/embedding_retrieval_test.rs`
/// (L3.I.5) for end-to-end assertions on the audit trail.
#[derive(Default)]
pub struct CountingAuditWriter {
    /// All events recorded, in order.
    pub events: Vec<AuditEvent>,
}

impl CountingAuditWriter {
    /// Total token count across all OK events — useful for cost-budget
    /// assertions in tests.
    pub fn total_ok_tokens(&self) -> u32 {
        self.events
            .iter()
            .filter(|e| matches!(e.outcome, AuditOutcome::Ok))
            .map(|e| e.tokens)
            .sum()
    }

    /// Count events matching a given outcome discriminator. Test helper.
    pub fn count_by_outcome_kind(&self, kind: &str) -> usize {
        self.events
            .iter()
            .filter(|e| match (&e.outcome, kind) {
                (AuditOutcome::Ok, "ok") => true,
                (AuditOutcome::DimMismatch { .. }, "dim_mismatch") => true,
                (AuditOutcome::ProviderError(_), "provider_error") => true,
                (AuditOutcome::WriteError(_), "write_error") => true,
                _ => false,
            })
            .count()
    }
}

impl AuditWriter for CountingAuditWriter {
    fn record(&mut self, event: AuditEvent) {
        self.events.push(event);
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

    #[test]
    fn counting_writer_total_ok_tokens_sums_only_ok() {
        let mut w = CountingAuditWriter::default();
        w.record(evt(AuditOutcome::Ok, 100));
        w.record(evt(AuditOutcome::ProviderError("nope".into()), 0));
        w.record(evt(AuditOutcome::Ok, 50));
        w.record(evt(AuditOutcome::DimMismatch { returned_dim: 768 }, 0));
        assert_eq!(w.total_ok_tokens(), 150);
    }

    #[test]
    fn counting_writer_count_by_outcome_kind() {
        let mut w = CountingAuditWriter::default();
        w.record(evt(AuditOutcome::Ok, 10));
        w.record(evt(AuditOutcome::Ok, 20));
        w.record(evt(AuditOutcome::DimMismatch { returned_dim: 768 }, 0));
        w.record(evt(AuditOutcome::ProviderError("x".into()), 0));
        w.record(evt(AuditOutcome::WriteError("y".into()), 0));
        assert_eq!(w.count_by_outcome_kind("ok"), 2);
        assert_eq!(w.count_by_outcome_kind("dim_mismatch"), 1);
        assert_eq!(w.count_by_outcome_kind("provider_error"), 1);
        assert_eq!(w.count_by_outcome_kind("write_error"), 1);
    }
}
