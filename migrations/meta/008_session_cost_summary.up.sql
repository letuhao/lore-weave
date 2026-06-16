-- 008_session_cost_summary.up.sql
-- L1.A-1 (cycle 2) — Q-L1A-1 hybrid: per-reality DB owns live writes;
-- meta has this `session_cost_summary` (60s rollup by NEW session-cost-rollup-worker service).
-- The rollup worker SHIPS LATER. This cycle creates the TABLE only so meta layout is stable.
-- Source: L1A_meta_tables.md Q-L1A-1 hybrid resolution
-- Retention: per billing rollup needs; deferred to L1.A-4 billing layer

CREATE TABLE IF NOT EXISTS session_cost_summary (
    summary_id           UUID            PRIMARY KEY,
    reality_id           UUID            NOT NULL,
    user_ref_id          UUID            NOT NULL,
    session_id           UUID            NOT NULL,
    window_start         TIMESTAMPTZ     NOT NULL,
    window_end           TIMESTAMPTZ     NOT NULL,
    rollup_interval_sec  INT             NOT NULL,
    request_count        BIGINT          NOT NULL DEFAULT 0,
    prompt_tokens        BIGINT          NOT NULL DEFAULT 0,
    completion_tokens    BIGINT          NOT NULL DEFAULT 0,
    cost_micro_usd       BIGINT          NOT NULL DEFAULT 0,
    rolled_up_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT session_cost_summary_window_order CHECK (window_end >= window_start),
    CONSTRAINT session_cost_summary_interval_sec_range CHECK (
        rollup_interval_sec BETWEEN 1 AND 3600
    ),
    CONSTRAINT session_cost_summary_counters_nonneg CHECK (
        request_count >= 0 AND prompt_tokens >= 0
        AND completion_tokens >= 0 AND cost_micro_usd >= 0
    )
);

-- Composite for billing dashboards (user × window) + reality breakdown
CREATE INDEX IF NOT EXISTS idx_session_cost_summary_user_window
    ON session_cost_summary (user_ref_id, window_start DESC);

CREATE INDEX IF NOT EXISTS idx_session_cost_summary_reality_window
    ON session_cost_summary (reality_id, window_start DESC);

CREATE INDEX IF NOT EXISTS idx_session_cost_summary_session_window
    ON session_cost_summary (session_id, window_start DESC);

COMMENT ON TABLE session_cost_summary IS
    'L1.A-1 / Q-L1A-1 — meta-side 60s rollup of per-reality session_cost_tracking. Written by session-cost-rollup-worker (ships LATER cycle).';
