-- Reverse of 0019_channels.
--
-- The indexes go with the table, so `DROP TABLE` is sufficient — they are named
-- explicitly anyway, because a down migration that relies on a cascade is one
-- rename away from leaving an orphan behind.
--
-- No `CASCADE`. If something references `channels` by the time this runs, the
-- drop must FAIL and say so: the only intended reference is
-- `channel_writer_state`, whose foreign key `FLOW-19` says has never existed,
-- and a silent cascade would take real lease rows with it.
DROP INDEX IF EXISTS channels_lifecycle_idx;
DROP INDEX IF EXISTS channels_level_idx;
DROP INDEX IF EXISTS channels_parent_idx;
DROP INDEX IF EXISTS channels_root_single;
DROP TABLE IF EXISTS channels;
