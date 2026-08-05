-- contracts/migrations/per_reality/0018_drop_region_session_world_kv_projections.down.sql
--
-- **This down-migration does NOT recreate the three tables, for the same reason
-- `0017`'s did not recreate its seven.**
--
-- A rollback would restore tables no production code can fill — nothing emitted
-- `region.*`, `session.participant_*` or `world.kv_*` when they were dropped — and
-- `session_participants` would bring back a `CHECK (participant_type IN
-- ('pc','npc'))` that puts game vocabulary in an engine table. It would also
-- re-establish a membership model built on a world/map feature that is being
-- redesigned, which is the thing the PO asked to stop building on.
--
-- What this DOES undo is the allowlist repoint, so a reality rolled back to 0017
-- is not left with a CHECK that a re-applied 0006/0007 would violate. The
-- allowlist returns to the three names 0017 left; the tables themselves are
-- 0006's to create.
--
-- If a later slice needs any of these projections, it authors them forward —
-- with a producer.

ALTER TABLE projection_drift_state
    DROP CONSTRAINT IF EXISTS projection_drift_table_name_allowlist;

ALTER TABLE projection_drift_state
    ADD CONSTRAINT projection_drift_table_name_allowlist
    CHECK (table_name IN (
        'region_projection',
        'world_kv_projection',
        'session_participants'
    ));
