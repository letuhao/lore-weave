-- contracts/migrations/per_reality/0017_drop_pc_npc_projections.down.sql
--
-- **This down-migration does NOT recreate the seven tables, and that is
-- deliberate.**
--
-- A down-migration exists to undo a STRUCTURAL change safely. Recreating these
-- would restore a vocabulary model the actor-hub round sealed against (`D-2`,
-- `D-3`) and re-open the `pc.stats_changed` road that 0017's up-migration
-- exists to close. It would also restore tables no production code can fill:
-- nothing emitted `pc.*` or `npc.*` when they were dropped, so a rollback would
-- recreate seven permanently empty tables plus their drift rows.
--
-- What this DOES undo is the allowlist narrowing, so that a reality rolled back
-- to 0016 is not left with a CHECK that a re-applied 0006 would violate. The
-- allowlist is restored to the ten names 0007 shipped; the tables themselves
-- are 0006's to create.
--
-- If a future feature genuinely needs a player-character projection, it authors
-- it forward — with a producer, and with quantities that come from the fold.

ALTER TABLE projection_drift_state
    DROP CONSTRAINT IF EXISTS projection_drift_table_name_allowlist;

ALTER TABLE projection_drift_state
    ADD CONSTRAINT projection_drift_table_name_allowlist
    CHECK (table_name IN (
        'pc_projection',
        'pc_inventory_projection',
        'pc_relationship_projection',
        'npc_projection',
        'npc_session_memory_projection',
        'npc_pc_relationship_projection',
        'npc_session_memory_embedding',
        'region_projection',
        'world_kv_projection',
        'session_participants'
    ));
