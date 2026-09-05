-- 0021_turn_slot — DP-Ch51's advisory turn slot.
--
-- WHAT THIS IS, AND WHAT IT IS NOT
-- --------------------------------
-- `21_llm_turn_slot.md` is explicit: the slot is *"an advisory hint stored in
-- the channel's writer state… actor X is currently expected to act, until time
-- T"*. It is **NOT** an enforcement primitive — it does not block writes. That
-- is `channel_pause`'s job (DP-Ch35), which is unbuilt.
--
-- So nothing here has a constraint that would make it behave like a lock. All
-- four columns are nullable and default NULL = no slot held, exactly as the
-- document specifies. A NOT NULL or a partial unique index would quietly turn a
-- hint into a mutex and mislead the next reader about what the slot guarantees.
--
-- WHY NO `ActorId` TYPE (SF-6)
-- ----------------------------
-- DP-Ch51 types the occupant as `ActorId`, and no such type exists. Four
-- spellings of "who is acting" already do: `sim-core::EntityId(u64)`, the meta
-- audit tables' `actor_id UUID`, `meta_write_audit.actor_id TEXT`, and
-- `dp-kernel::pii_sdk`'s `actor_id: String`. A fifth, introduced at the data
-- plane, would be the vocabulary proliferation this track already documented
-- once (four things called a "turn").
--
-- The column is JSONB and DP does not interpret it — the same argument
-- `turn_data` rests on. Whoever occupies the slot owns its spelling.
--
-- IDEMPOTENT: every statement is `IF NOT EXISTS`.

BEGIN;

ALTER TABLE channel_writer_state
    ADD COLUMN IF NOT EXISTS current_turn_actor  JSONB,
    ADD COLUMN IF NOT EXISTS turn_started_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS turn_expected_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS turn_slot_reason    TEXT;

COMMENT ON COLUMN channel_writer_state.current_turn_actor IS
    'DP-Ch51 advisory slot occupant, serialized. NULL = no slot held. DP does not interpret it (SF-6: no ActorId type is introduced).';
COMMENT ON COLUMN channel_writer_state.turn_expected_until IS
    'DP-Ch51 SOFT deadline. Advisory: passing it does not block writes — that is channel_pause (DP-Ch35), unbuilt.';

COMMIT;
