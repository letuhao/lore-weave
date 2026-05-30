//! Prometheus ops surface for the embedding worker + a [`MetricsAuditWriter`]
//! decorator that derives counters from the audit stream.
//!
//! Metrics (DEFERRED-059 part 5):
//! - `lw_embedding_queue_depth` (gauge) — current in-process queue depth.
//! - `lw_embedding_queue_failures_total` (counter) — items that did NOT result
//!   in a stored vector (dim mismatch / provider error / write error).
//! - `lw_embedding_provider_tokens_total` (counter) — provider tokens billed
//!   (Ok outcomes; cost obs since the audit table has no token column).
//! - `lw_embedding_audit_outcome_total{outcome}` (counter vec) — bounded-
//!   cardinality outcome breakdown.

use std::sync::Arc;

use async_trait::async_trait;
use prometheus::{Encoder, IntCounter, IntCounterVec, IntGauge, Opts, Registry, TextEncoder};

use crate::embedding_queue::{AuditEvent, AuditOutcome, AuditWriter};

/// Owns the prometheus registry + the embedding-worker collectors.
pub struct Metrics {
    registry: Registry,
    /// Current depth of the in-process queue (set each tick).
    pub queue_depth: IntGauge,
    /// Items that did not yield a stored vector.
    pub failures_total: IntCounter,
    /// Provider tokens billed across Ok outcomes.
    pub provider_tokens_total: IntCounter,
    /// Outcome breakdown by `AuditOutcome::kind()`.
    pub outcome_total: IntCounterVec,
}

impl Metrics {
    /// Build + register all collectors on a fresh registry.
    pub fn new() -> Self {
        let registry = Registry::new();
        let queue_depth = IntGauge::new(
            "lw_embedding_queue_depth",
            "Current depth of the in-process embedding queue.",
        )
        .expect("static metric opts");
        let failures_total = IntCounter::new(
            "lw_embedding_queue_failures_total",
            "Embedding items that did not result in a stored vector (dim mismatch / provider error / write error).",
        )
        .expect("static metric opts");
        let provider_tokens_total = IntCounter::new(
            "lw_embedding_provider_tokens_total",
            "Total embedding provider tokens billed (Ok outcomes).",
        )
        .expect("static metric opts");
        let outcome_total = IntCounterVec::new(
            Opts::new(
                "lw_embedding_audit_outcome_total",
                "Embedding provider call outcomes by kind.",
            ),
            &["outcome"],
        )
        .expect("static metric opts");

        registry
            .register(Box::new(queue_depth.clone()))
            .expect("register queue_depth");
        registry
            .register(Box::new(failures_total.clone()))
            .expect("register failures_total");
        registry
            .register(Box::new(provider_tokens_total.clone()))
            .expect("register provider_tokens_total");
        registry
            .register(Box::new(outcome_total.clone()))
            .expect("register outcome_total");

        Self {
            registry,
            queue_depth,
            failures_total,
            provider_tokens_total,
            outcome_total,
        }
    }

    /// Encode the registry in the prometheus text exposition format.
    pub fn encode(&self) -> String {
        let mut buf = Vec::new();
        let encoder = TextEncoder::new();
        let families = self.registry.gather();
        if encoder.encode(&families, &mut buf).is_err() {
            return String::new();
        }
        String::from_utf8(buf).unwrap_or_default()
    }
}

impl Default for Metrics {
    fn default() -> Self {
        Self::new()
    }
}

/// [`AuditWriter`] decorator: derives metrics from every audit event, then
/// forwards to the wrapped writer. Keeps metric bumping out of the persistence
/// adapter (single-responsibility) while giving the worker per-event visibility
/// that `process_batch`'s count alone can't provide.
pub struct MetricsAuditWriter {
    inner: Arc<dyn AuditWriter>,
    metrics: Arc<Metrics>,
}

impl MetricsAuditWriter {
    /// Wrap an inner audit writer with metric derivation.
    pub fn new(inner: Arc<dyn AuditWriter>, metrics: Arc<Metrics>) -> Self {
        Self { inner, metrics }
    }
}

#[async_trait]
impl AuditWriter for MetricsAuditWriter {
    async fn record(&self, event: AuditEvent) {
        self.metrics
            .outcome_total
            .with_label_values(&[event.outcome.kind()])
            .inc();
        match &event.outcome {
            AuditOutcome::Ok => {
                self.metrics
                    .provider_tokens_total
                    .inc_by(event.tokens as u64);
            }
            _ => {
                self.metrics.failures_total.inc();
            }
        }
        self.inner.record(event).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::embedding_queue::CountingAuditWriter;
    use uuid::Uuid;

    fn evt(outcome: AuditOutcome, tokens: u32) -> AuditEvent {
        AuditEvent {
            reality_id: Uuid::from_u128(1),
            npc_id: Uuid::from_u128(2),
            session_id: Uuid::from_u128(3),
            provider: "openai".into(),
            model: "m".into(),
            tokens,
            outcome,
        }
    }

    #[tokio::test]
    async fn decorator_bumps_counters_and_forwards() {
        let inner = Arc::new(CountingAuditWriter::default());
        let metrics = Arc::new(Metrics::new());
        let w = MetricsAuditWriter::new(inner.clone(), metrics.clone());

        w.record(evt(AuditOutcome::Ok, 100)).await;
        w.record(evt(AuditOutcome::ProviderError("x".into()), 0))
            .await;

        assert_eq!(metrics.provider_tokens_total.get(), 100);
        assert_eq!(metrics.failures_total.get(), 1);
        assert_eq!(metrics.outcome_total.with_label_values(&["ok"]).get(), 1);
        assert_eq!(
            metrics
                .outcome_total
                .with_label_values(&["provider_error"])
                .get(),
            1
        );
        // Forwarded to the inner writer (Q-L1A-3 audit still lands).
        assert_eq!(inner.len(), 2);
    }
}
