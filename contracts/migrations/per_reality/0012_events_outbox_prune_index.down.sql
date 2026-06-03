-- contracts/migrations/per_reality/0012_events_outbox_prune_index.down.sql
--
-- Reverse 0012 — drop the prune-supporting partial index. Idempotent
-- (DROP INDEX IF EXISTS).

BEGIN;

DROP INDEX IF EXISTS events_outbox_prune_idx;

COMMIT;
