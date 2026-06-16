//! [`AuditWriter`] bound to the meta `service_to_service_audit` table
//! (migration `migrations/meta/016`).
//!
//! Q-L1A-3 (full audit, no sampling): every embedding provider call lands one
//! row recording the **service-to-service edge + outcome**:
//! `world-service → provider-registry-service / Embed`.
//!
//! ## Column-mapping note (honest scope)
//!
//! `service_to_service_audit` is a generic *edge* audit (caller / callee /
//! rpc / principal / result / latency / correlation). It has **no** column for
//! reality / npc / session / model / tokens. So the embedding-specific cost
//! detail (model, token count) is NOT persisted here — it is surfaced via the
//! prometheus counters ([`super::metrics::Metrics`]) and belongs, structurally,
//! in a usage/billing table (V1+30d, out of foundation scope — see row 080).
//! What this row faithfully captures is "world-service called the provider, and
//! the call's outcome was ok/error" — which is exactly the Q-L1A-3 audit edge.
//!
//! `latency_ms` is recorded as 0 because [`AuditEvent`] carries no timing;
//! threading per-call latency into the event is a small follow-up.

use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use async_trait::async_trait;
use sqlx::postgres::PgPool;
use uuid::Uuid;

use crate::embedding_queue::{AuditEvent, AuditOutcome, AuditWriter};

const CALLER_SERVICE: &str = "world-service";
const CALLEE_SERVICE: &str = "provider-registry-service";
const RPC_NAME: &str = "Embed";
/// The embedding worker is a background system process (no user request in the
/// call path), so the s2s principal mode is `system_only` per the table's
/// CHECK enum. `user_ref_id` stays NULL (allowed for `system_only`).
const PRINCIPAL_MODE: &str = "system_only";

/// Production [`AuditWriter`]. Clone-cheap (`Arc<PgPool>`).
#[derive(Clone)]
pub struct MetaAuditWriter {
    pool: Arc<PgPool>,
}

impl MetaAuditWriter {
    /// Wrap a pre-built meta pool.
    pub fn new(pool: PgPool) -> Self {
        Self {
            pool: Arc::new(pool),
        }
    }

    /// Construct from an already-shared pool.
    pub fn from_arc(pool: Arc<PgPool>) -> Self {
        Self { pool }
    }

    /// Map the queue outcome onto the table's `result` CHECK enum
    /// (`ok|deny|error|timeout`). This row audits the **provider-call edge**
    /// (`world-service → Embed`), so the mapping reflects whether the *provider
    /// call itself* succeeded:
    /// - `Ok` → `ok`.
    /// - `DimMismatch` and `ProviderError` → `error` (provider-side failure).
    ///
    /// `WriteError` never reaches here — it is filtered in [`Self::record`]
    /// because it is NOT a provider-edge event (see the comment there). The
    /// arm is kept for exhaustiveness only.
    fn result_for(outcome: &AuditOutcome) -> &'static str {
        match outcome {
            AuditOutcome::Ok | AuditOutcome::WriteError(_) => "ok",
            AuditOutcome::DimMismatch { .. } | AuditOutcome::ProviderError(_) => "error",
        }
    }
}

#[async_trait]
impl AuditWriter for MetaAuditWriter {
    async fn record(&self, event: AuditEvent) {
        // `WriteError` is NOT a provider-edge event: the provider call already
        // succeeded and was recorded by the preceding `Ok` row (see
        // `Worker::handle_one`). Persisting a second edge row for the downstream
        // DB-write failure would double-count the Embed call AND — since this
        // table has no outcome column — be indistinguishable from a real
        // success. The write-failure signal lives in
        // `lw_embedding_queue_failures_total` +
        // `lw_embedding_audit_outcome_total{outcome="write_error"}` (the
        // MetricsAuditWriter decorator already counted it before this call).
        // So skip the row — one provider call yields exactly one edge row.
        if matches!(event.outcome, AuditOutcome::WriteError(_)) {
            return;
        }

        let created_at_nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos() as i64)
            // Pre-epoch clock is implausible; fall back to the CHECK floor + 1
            // so the INSERT still satisfies `created_at_nanos > 2020-01-01`.
            .unwrap_or(1_577_836_800_000_000_001);

        let result = Self::result_for(&event.outcome);

        let res = sqlx::query(
            r#"
            INSERT INTO service_to_service_audit
                (audit_id, caller_service, callee_service, rpc_name,
                 principal_mode, user_ref_id, result, latency_ms, created_at_nanos)
            VALUES ($1, $2, $3, $4, $5, NULL, $6, 0, $7)
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(CALLER_SERVICE)
        .bind(CALLEE_SERVICE)
        .bind(RPC_NAME)
        .bind(PRINCIPAL_MODE)
        .bind(result)
        .bind(created_at_nanos)
        .execute(&*self.pool)
        .await;

        if let Err(e) = res {
            // An audit-write failure must NOT panic the worker (it would lose
            // the whole batch). Q-L1A-3 audit is degraded-mode-essential, so we
            // surface it loudly via tracing for the SRE alert path; the missing
            // row is acceptable degraded behaviour (vs crashing the drain).
            tracing::error!(
                error = %e,
                outcome = event.outcome.kind(),
                "service_to_service_audit INSERT failed (embedding provider call)"
            );
        }
    }
}
