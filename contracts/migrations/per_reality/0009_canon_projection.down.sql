-- contracts/migrations/per_reality/0009_canon_projection.down.sql
--
-- Reverse L5.D.1 canon_projection table.
-- Idempotent (DROP TABLE IF EXISTS).

BEGIN;

DROP TABLE IF EXISTS canon_projection;

COMMIT;
