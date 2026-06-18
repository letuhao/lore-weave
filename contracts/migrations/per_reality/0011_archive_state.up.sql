-- contracts/migrations/per_reality/0011_archive_state.up.sql
--
-- L2.K — Per-reality `archive_state` table (DEFERRED 056).
--
-- The archive-worker's idempotency ledger: one row per `events` monthly
-- partition that has been Parquet-encoded, uploaded to MinIO, verified, and
-- DROPped. Written by archive-worker ONLY (pkg/state.RecordArchived), AFTER a
-- verified upload + BEFORE the partition DROP — that ordering guarantees a
-- re-run after a mid-flight crash skips the already-archived partition rather
-- than re-uploading + double-DROPping. Read by:
--   * archive-worker partition_picker (filter already-archived from the catalog)
--   * cmd/archive-restore (enumerate restorable months)
--
-- LOCKED decisions consumed:
--   * Q-L2-2 / R01 §12A.4: monthly partitions, 90d archive cutoff.
--   * Idempotency contract (pkg/state): INSERT ... ON CONFLICT DO NOTHING on
--     (reality_id, partition_name).
--
-- ⚠️  Per-reality INFRA table (not a domain table, not a meta table).

BEGIN;

CREATE TABLE IF NOT EXISTS archive_state (
    -- Tenant — denormalized (this IS the per-reality DB, but kept for parity
    -- with events_outbox + cross-checking the restore CLI).
    reality_id      UUID        NOT NULL,
    -- Postgres relation name of the archived partition, e.g. events_p_2025_11.
    partition_name  TEXT        NOT NULL,
    -- MinIO object key, e.g. events/<reality_id>/2025-11.parquet.
    object_key      TEXT        NOT NULL,
    -- Encoded blob size in bytes (the LWP1-wrapped Parquet+ZSTD blob).
    byte_size       BIGINT      NOT NULL,
    -- Number of event rows in the partition (matches the LWP1 footer rowcount).
    row_count       BIGINT      NOT NULL,
    -- LWP1 format marker (4 bytes) — verify-after-upload + restore use it.
    format_header   BYTEA       NOT NULL,
    archived_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (reality_id, partition_name),

    CONSTRAINT archive_state_byte_size_nonneg CHECK (byte_size >= 0),
    CONSTRAINT archive_state_row_count_nonneg CHECK (row_count >= 0),
    CONSTRAINT archive_state_format_header_len CHECK (octet_length(format_header) = 4)
);

-- Restore + dashboarding: list a reality's archived months newest-first.
CREATE INDEX IF NOT EXISTS idx_archive_state_reality_archived
    ON archive_state (reality_id, archived_at DESC);

COMMENT ON TABLE archive_state IS
    'L2.K archive-worker idempotency ledger: one row per archived+DROPped events partition. Written by archive-worker only (after verified upload, before DROP).';

COMMIT;
