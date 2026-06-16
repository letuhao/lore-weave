-- L5.J down migration — RAID cycle 27.
--
-- Drops the canon_change_history table + triggers + function. SAFE to
-- run repeatedly (IF EXISTS guards everywhere). Drops the trigger
-- function as well so the namespace stays clean.
--
-- WARNING: this drops APPEND-ONLY history. Only run in fresh dev/test
-- environments. Production rollback is via PITR snapshot per L1.B PITR
-- runbook.

BEGIN;

DROP TRIGGER IF EXISTS canon_change_history_no_delete ON canon_change_history;
DROP TRIGGER IF EXISTS canon_change_history_no_update ON canon_change_history;
DROP FUNCTION IF EXISTS canon_change_history_block_update_delete();

DROP INDEX IF EXISTS canon_change_history_source_event_idx;
DROP INDEX IF EXISTS canon_change_history_reality_recorded_idx;
DROP INDEX IF EXISTS canon_change_history_book_path_recorded_idx;
DROP INDEX IF EXISTS canon_change_history_entry_recorded_idx;

DROP TABLE IF EXISTS canon_change_history;

COMMIT;
