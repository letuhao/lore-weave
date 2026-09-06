-- 0025_entity_binding.down.sql
--
-- Reverting forgets where everything is. The entities survive -- `actors` is a
-- different table and holds identity, not location -- so a revert leaves a
-- reality whose beings exist and are NOWHERE, which is precisely the state that
-- made this migration necessary in the first place.
--
-- That is the honest cost of the revert rather than a defect in it. A down that
-- also removed the actors would destroy identity in order to undo a location
-- schema, and identity is the thing `actor_control_binding` still points at
-- from another database this file cannot reach.

BEGIN;

DROP INDEX IF EXISTS entity_binding_by_cell;
DROP TABLE IF EXISTS entity_binding;

COMMIT;
