-- 002_instance_schema_migrations.up.sql
-- L1.A-1 (cycle 2) — per-reality schema migration tracker.
-- Source: L1A_meta_tables.md §1.2  (chunk R04-L2 §12D.2)
-- Retention: Operational (no expiry — historical record)
-- Written by: migration-orchestrator
-- Read by: migration-orchestrator (planning) + world-service (verification on reality boot)

CREATE TABLE IF NOT EXISTS instance_schema_migrations (
    reality_id      UUID            NOT NULL,
    migration_id    TEXT            NOT NULL,
    applied_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    applied_by      TEXT            NOT NULL,
    failure_reason  TEXT            NULL,
    PRIMARY KEY (reality_id, migration_id),
    CONSTRAINT instance_schema_migrations_migration_id_nonempty CHECK (
        length(migration_id) BETWEEN 1 AND 128
    ),
    CONSTRAINT instance_schema_migrations_applied_by_nonempty CHECK (
        length(applied_by) BETWEEN 1 AND 128
    )
);

CREATE INDEX IF NOT EXISTS idx_instance_schema_migrations_applied_at
    ON instance_schema_migrations (applied_at DESC);

-- Reference FK to reality_registry (cycle 2 §1.1) — soft-checked so out-of-order
-- migration apply during catastrophic restore doesn't break (R04 orphan scanner reconciles)
ALTER TABLE instance_schema_migrations
    DROP CONSTRAINT IF EXISTS instance_schema_migrations_reality_id_fk;
ALTER TABLE instance_schema_migrations
    ADD  CONSTRAINT instance_schema_migrations_reality_id_fk
    FOREIGN KEY (reality_id) REFERENCES reality_registry(reality_id)
    ON DELETE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

COMMENT ON TABLE instance_schema_migrations IS
    'L1.A-1 — per-reality schema migration tracker. Owned by migration-orchestrator.';
