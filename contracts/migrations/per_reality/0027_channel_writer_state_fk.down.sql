-- 0027_channel_writer_state_fk.down.sql
--
-- Reverting re-opens `FLOW-19`: a writer lease could again be acquired for a
-- channel that does not exist, which is the state 313 measured rows in
-- `dp_kernel_test` are already in.
--
-- The gate notices. `dp-channels-schema-gate`'s FLOW-19 check reds whenever
-- `channels` has a non-test writer and no such foreign key is declared in any
-- per-reality migration, so a revert that ships would fail the next commit
-- rather than fail silently. That is the difference between this deferral and
-- the four sentences it replaced.

BEGIN;

ALTER TABLE channel_writer_state
    DROP CONSTRAINT IF EXISTS channel_writer_state_channel_fk;

COMMIT;
