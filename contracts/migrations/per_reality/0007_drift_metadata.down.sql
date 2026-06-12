-- contracts/migrations/per_reality/0007_drift_metadata.down.sql
--
-- Reverse L3.K drift metadata migration. Idempotent.

BEGIN;

DROP VIEW IF EXISTS stale_projections;
DROP TABLE IF EXISTS projection_drift_state;

COMMIT;
