-- 020_user_queue_metrics.up.sql
-- L1.A-4 (cycle 7) — NPC queue abuse counters (S07).
-- Source: L1A_meta_tables.md §4.4; Owning kernel chunk: S07 §12W.4
--
-- @pii_sensitivity: low (counters only)
-- @retention_class: ops_metrics
-- @retention_hot: 90d
-- @erasure_method: hard_delete
-- @legal_basis: legitimate_interest

CREATE TABLE IF NOT EXISTS user_queue_metrics (
    user_ref_id              UUID            PRIMARY KEY,
    total_queues_joined      BIGINT          NOT NULL DEFAULT 0,
    total_accepted           BIGINT          NOT NULL DEFAULT 0,
    total_abandoned          BIGINT          NOT NULL DEFAULT 0,
    total_declined           BIGINT          NOT NULL DEFAULT 0,
    last_abandoned_at        TIMESTAMPTZ     NULL,
    updated_at               TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT user_queue_metrics_counters_nonneg CHECK (
        total_queues_joined >= 0 AND total_accepted >= 0
        AND total_abandoned >= 0 AND total_declined >= 0
    )
);

-- ops dashboard: top-N abusers by abandonment rate
CREATE INDEX IF NOT EXISTS idx_user_queue_metrics_abandoned_at
    ON user_queue_metrics (last_abandoned_at DESC)
    WHERE last_abandoned_at IS NOT NULL;

COMMENT ON TABLE user_queue_metrics IS
    'L1.A-4 §4.4 — NPC queue abuse counters; 90d rolling retention (ops_metrics tier).';
