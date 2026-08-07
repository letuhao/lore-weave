-- Reverse of 0019_channels.
--
-- The indexes go with the table, so `DROP TABLE` is sufficient — they are named
-- explicitly anyway, because a down migration that relies on a cascade is one
-- rename away from leaving an orphan behind.
--
-- No `CASCADE` -- and the reason stated here until `1b.5` was REC-104's own
-- defect, in the file written to fix REC-104.
--
-- It read: *"if something references `channels` by the time this runs, the drop
-- must FAIL and say so."* **It cannot fail. NOTHING references `channels`** --
-- that is `FLOW-19`, still open: `channel_writer_state.channel_id` has no
-- foreign key, so a lease can outlive the registry and this DROP will not
-- notice. A guard whose subject does not exist.
--
-- The `CASCADE` omission is still correct, for the reason that will apply once
-- the FK lands. Until then it guards nothing, and says so. (`channels` does now
-- reference ITSELF -- `channels_parent_fk`, `REC-106` -- and a self-reference
-- drops with the table, so that is not the subject either.)
DROP INDEX IF EXISTS channels_lifecycle_idx;
DROP INDEX IF EXISTS channels_level_idx;
DROP INDEX IF EXISTS channels_parent_idx;
DROP INDEX IF EXISTS channels_root_single;
DROP TABLE IF EXISTS channels;

-- The TRIGGER drops with the table; the FUNCTION does not, and a down migration
-- that leaves a `channels_lifecycle_guard()` behind makes the next forward
-- migration's `CREATE OR REPLACE` silently inherit an older body.
DROP FUNCTION IF EXISTS channels_lifecycle_guard();
