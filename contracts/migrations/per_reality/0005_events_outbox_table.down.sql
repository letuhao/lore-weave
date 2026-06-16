-- contracts/migrations/per_reality/0005_events_outbox_table.down.sql
--
-- L2.C.1 — down migration.
--
-- Drops indexes first (defensive — IF EXISTS makes it idempotent under
-- partial-apply recovery), then the table. Cycle 5 placeholder `outbox`
-- is NOT re-created here — that table was dropped by cycle 9's 0002
-- migration and is gone for good.

BEGIN;

DROP INDEX IF EXISTS events_outbox_dead_letter_idx;
DROP INDEX IF EXISTS events_outbox_pending_idx;
DROP TABLE IF EXISTS events_outbox;

COMMIT;
