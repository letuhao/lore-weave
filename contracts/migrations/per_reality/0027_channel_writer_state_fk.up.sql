-- 0027_channel_writer_state_fk.up.sql
--
-- FLOW-19, DISCHARGED BY A GATE THAT WATCHED FOR ITS OWN TRIGGER.
--
-- `FLOW-19` is "channel_writer_state.channel_id has no foreign key to
-- channels". It was called discharged in two artifacts and still-open in two
-- others, and `FLOW-*` appeared nowhere in the deferral gate -- so nothing would
-- have noticed if the key never landed.
--
-- `1b7gap-H4` replaced those four sentences with a MECHANISM. The recorded
-- reason for not adding the key was measurable rather than rhetorical (`1b.9`):
-- `dp-kernel::acquire_writer_lease` INSERTs into `channel_writer_state` on every
-- lease acquisition, and NOTHING ANYWHERE WROTE `channels`, so the key would
-- have made every lease acquisition fail against an empty table. The check
-- therefore reds "the moment `channels` gains a non-test writer".
--
-- It just did. `services/world-service/src/world_seed.rs` is the first, and the
-- gate refused the commit that introduced it. This file is the discharge.
--
-- WHY `NOT VALID`, AND IT IS MEASURED RATHER THAN CAUTIOUS.
--
--   A plain ADD CONSTRAINT scans the existing rows. Counted before choosing:
--
--     dp_kernel_test                          456 rows, 313 ORPHANS
--     ls_dp_kernel_channel_writer_pg_smoke      8 rows,   8 orphans
--     ls_dp_kernel_writer_lease_pg_smoke        6 rows,   6 orphans
--     lw_reality_58663ea66315                   0 rows,   0 orphans
--     lw_reality_cd0747d24b94                   0 rows,   0 orphans
--
--   That distribution is exactly what `1b.9` predicted: leases were acquired
--   against a table nothing populated, so the orphans are the DEFECT the key
--   exists to prevent, already present in every database with history. Live
--   realities are clean, because nothing has run there yet.
--
--   `0023_actors_entity_id_nonneg` faced the same fork and chose the strict
--   form, reasoning that "a failure here would mean the invariant was already
--   broken, which is worth knowing". That reasoning is right and it points the
--   OTHER WAY here, because the answer is already known: the invariant IS
--   broken, in 313 measured rows, and a strict ADD would not inform anyone --
--   it would refuse to migrate any database that has ever acquired a lease.
--
--   So `NOT VALID` enforces on EVERY NEW WRITE from this moment while leaving
--   the historical rows unscanned. It is a ratchet, not an amnesty: no new
--   orphan can be created.
--
-- WHAT IS OWED, and it is owed rather than assumed: `VALIDATE CONSTRAINT` after
-- the historical rows are reconciled. Until then the constraint is honest about
-- covering new writes only, which is strictly more than the nothing it replaces.
--
-- NO `ON DELETE` CLAUSE, DELIBERATELY. The default is `NO ACTION`, so a channel
-- carrying writer state cannot be hard-deleted. That is the wanted behaviour:
-- `current_epoch` is a FENCE, and dropping it while an id could be reused would
-- reset the fence -- the confused-deputy shape one tier down from the one
-- `0023` prevents. `channels` already models removal as `lifecycle='dissolved'`
-- plus `dissolved_at`, so hard deletion is not the normal path anyway.

BEGIN;

ALTER TABLE channel_writer_state
    DROP CONSTRAINT IF EXISTS channel_writer_state_channel_fk;

ALTER TABLE channel_writer_state
    ADD CONSTRAINT channel_writer_state_channel_fk
    FOREIGN KEY (reality_id, channel_id)
    REFERENCES channels (reality_id, id)
    NOT VALID;

COMMIT;
