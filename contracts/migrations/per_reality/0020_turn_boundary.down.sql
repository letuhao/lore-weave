-- 0020 down — remove DP-Ch22's turn counter.
--
-- The index is dropped explicitly rather than left to fall with the column. It
-- would fall either way, but a down migration that relies on a cascade is one
-- rename away from leaving an orphan behind — the reason `0019`'s down names
-- its indexes too.
--
-- DATA LOSS, stated rather than discovered: dropping `events.turn_number`
-- discards every channel's turn history, which is not reconstructible from the
-- remaining columns (a TurnBoundary event's payload carries its own number, so
-- a rebuild is *possible* from the event log, but this migration does not do
-- it). There is no guard here, unlike `036`'s in the meta tree, because at the
-- time of writing nothing produces a non-zero value — the producer arrives in
-- `T3`. **When it does, revisit this file**: a down migration that silently
-- discards live game state needs the same refuse-if-populated guard `036` has.
--
-- IDEMPOTENT: every statement is `IF EXISTS`, so a re-run is a no-op.

BEGIN;

DROP INDEX IF EXISTS events_turn_number_idx;

ALTER TABLE channel_writer_state
    DROP COLUMN IF EXISTS last_turn_number;

ALTER TABLE events
    DROP COLUMN IF EXISTS turn_number;

COMMIT;
