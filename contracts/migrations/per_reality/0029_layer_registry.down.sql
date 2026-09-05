-- 0029_layer_registry.down.sql
--
-- Reverting removes the declaration of what a layer IS. No layer DATA is stored
-- here -- the sidecars are `T5` and are not created by this migration -- so a
-- revert does not destroy a value. It destroys the ability to READ one: without
-- the registry, a `layer_<name>` sidecar is bytes with no owner, no storage
-- class, no home kinds and no schema version.
--
-- That is worse than it sounds, and `SDF-A12` is why. A retired layer is kept
-- decodable precisely so an old event log still replays; dropping the registry
-- drops the tombstones with it, and "deleting the decoder makes the log
-- un-replayable, and for an event-sourced world that means the world is gone."
--
-- So this down is safe ONLY while no sidecar exists. Once `T5` ships, reverting
-- past this point needs the sidecars dropped first, and that ordering belongs in
-- the migration that creates them rather than in a comment here.

BEGIN;

DROP INDEX IF EXISTS layer_registry_live;
DROP INDEX IF EXISTS layer_registry_by_home_kind;
DROP TABLE IF EXISTS layer_registry;

COMMIT;
