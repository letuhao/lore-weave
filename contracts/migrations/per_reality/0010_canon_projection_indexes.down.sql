-- contracts/migrations/per_reality/0010_canon_projection_indexes.down.sql
--
-- Reverse L5.D.2 canon_projection indexes.
-- Idempotent (DROP INDEX IF EXISTS).

BEGIN;

DROP INDEX IF EXISTS canon_projection_cascade_source_idx;
DROP INDEX IF EXISTS canon_projection_event_id_idx;
DROP INDEX IF EXISTS canon_projection_applied_at_idx;
DROP INDEX IF EXISTS canon_projection_last_synced_idx;
DROP INDEX IF EXISTS canon_projection_attribute_path_active_idx;
DROP INDEX IF EXISTS canon_projection_book_layer_idx;

COMMIT;
