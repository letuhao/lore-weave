-- 0020_turn_boundary — DP-Ch22's per-channel turn counter.
--
-- WHY THIS DID NOT EXIST UNTIL NOW, AND WHY IT DOES NOW
-- -----------------------------------------------------
-- `events.turn_number` has been specified since Phase 4 and was deliberately
-- NOT shipped. It is a registered deferral in
-- `crates/dp/tests/spec_oracle_channels.rs`'s `DEFERRED_EVENT_COLUMNS`, and the
-- recorded reason names this exact work:
--
--     "DP-A17 / DP-Ch22's per-channel turn counter — 15_turn_boundary.md's turn
--      machinery has no implementation and nothing would advance the counter,
--      so the column would be a NOT NULL DEFAULT 0 that never moves"
--
-- That was the right call: a column nothing writes is the orphan shape, and the
-- register's shrink arm exists to FAIL the day a migration adds the column. It
-- fires with this file, and the row is removed in the same change — which is
-- the whole difference between a register and a comment.
--
-- WHICH "TURN" THIS IS
-- --------------------
-- Four things in this repo are called a turn (see
-- `docs/plans/2026-08-11-turn-loop-RUN-STATE.md` §1.1). **This is DP-Ch21's: a
-- per-channel, monotonic page-flip counter shared by every member of a
-- channel.** It is NOT `contracts/turn/` + `crates/dp-kernel/src/turn.rs`,
-- which is one REQUEST's lifecycle (`pending → validating → … → completed`) and
-- carries `reality_id`/`session_id`/`actor_id` — the same scope keys, a
-- different subject.
--
-- THE INDEX SHAPE, AND WHY THIS ONE CAN BE CREATED
-- ------------------------------------------------
-- `events` is `PARTITION BY RANGE (recorded_at)`. DP-Ch22 originally specified
-- a **partial UNIQUE index** here, which Postgres cannot create on a
-- partitioned table at all — amended in the doc (`REC-99c`) after `DP-Ch11`'s
-- twin was caught by an implementer trying to run it. This file's index is
-- **non-unique**, which is supported, and `0014_channel_ordering` already ships
-- exactly this shape (`events_channel_order_idx … WHERE channel_id IS NOT
-- NULL`). Precedent verified in the tree, not assumed — and then executed,
-- because "a spec defect is found by execution or not at all".
--
-- `channel_turn_index` (the uniqueness side table DP-Ch22 sketches) is
-- deliberately NOT created — see `SF-3` in the run-state. The doc calls it
-- optional and says the anomaly it prevents violates no invariant.
--
-- IDEMPOTENT: every statement is `IF NOT EXISTS`, so a re-run is a no-op.

BEGIN;

-- DP-Ch22. Reality-scoped events (channel_id IS NULL) keep the default 0 and
-- never read it; turn_number is only meaningful for channel events.
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS turn_number BIGINT NOT NULL DEFAULT 0;

-- "What happened in turn N" — the query DP-Ch22 names. Non-unique and partial,
-- mirroring events_channel_order_idx.
CREATE INDEX IF NOT EXISTS events_turn_number_idx
    ON events (reality_id, channel_id, turn_number)
    WHERE channel_id IS NOT NULL;

-- DP-Ch22's writer state. Updated in the SAME transaction as the TurnBoundary
-- insert, so no partial state is observable; the writer reseeds it from
-- MAX(turn_number) on takeover.
ALTER TABLE channel_writer_state
    ADD COLUMN IF NOT EXISTS last_turn_number BIGINT NOT NULL DEFAULT 0;

COMMENT ON COLUMN events.turn_number IS
    'DP-Ch22 per-channel turn counter. 0 = channel never advanced a turn, or a reality-scoped event. NOT the dp-kernel TurnContext lifecycle state.';
COMMENT ON COLUMN channel_writer_state.last_turn_number IS
    'DP-Ch22 last turn allocated by this channel''s writer; reseeded from MAX(events.turn_number) on writer takeover.';

COMMIT;
