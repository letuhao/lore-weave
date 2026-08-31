-- 0021 down — remove DP-Ch51's advisory turn slot.
--
-- No data-loss guard, and unlike `0020`'s down that is not a deferral: the slot
-- is an ADVISORY HINT about who is expected to act right now. Dropping it loses
-- at most one in-flight "NPC X is thinking…" indicator per channel, which the
-- next claim replaces. There is no history here to destroy — the durable record
-- of what happened is the event log, not this row.
--
-- IDEMPOTENT: every statement is `IF EXISTS`.

BEGIN;

ALTER TABLE channel_writer_state
    DROP COLUMN IF EXISTS turn_slot_reason,
    DROP COLUMN IF EXISTS turn_expected_until,
    DROP COLUMN IF EXISTS turn_started_at,
    DROP COLUMN IF EXISTS current_turn_actor;

COMMIT;
