-- 0014 — DP-Ch11/Ch13 channel ordering + writer fence (S3a, 2026-07-27).
--
-- ⚠ SPEC CORRECTION (plan D1 / REC-80 candidate): DP-Ch11 asks for
--   UNIQUE (reality_id, channel_id, channel_event_id) on the event log —
-- IMPOSSIBLE here: `events` is PARTITION BY RANGE (recorded_at), and PG
-- requires the partition key inside any parent unique constraint. Delivered
-- instead as:
--   (a) channel_writer_state — one row per (reality, channel); a single
--       atomic CAS UPDATE is BOTH the channel_event_id allocator AND the
--       DP-A16 epoch fence ("stale epoch fails at the DB layer");
--   (b) channel_event_index — non-partitioned, PK = the spec's unique
--       triple, written in the same tx as the event row: the hard
--       uniqueness + the channel-ordered lookup index DP-Ch11 wanted.
-- Reality-scoped events keep channel columns NULL (DP-Ch11 note).

ALTER TABLE events
    ADD COLUMN IF NOT EXISTS channel_id       BIGINT,
    ADD COLUMN IF NOT EXISTS channel_event_id BIGINT,
    ADD COLUMN IF NOT EXISTS writer_epoch     BIGINT,
    ADD COLUMN IF NOT EXISTS causal_refs      JSONB NOT NULL DEFAULT '[]'::jsonb;

-- (a) Writer state: DP-Ch13's channel_writer_state, plus last_event_id so
-- allocation is DB-authoritative (survives writer crash without gaps being
-- resurrected; in-memory counters are hints only).
CREATE TABLE IF NOT EXISTS channel_writer_state (
    reality_id     UUID   NOT NULL,
    channel_id     BIGINT NOT NULL,
    current_epoch  BIGINT NOT NULL DEFAULT 1,
    last_event_id  BIGINT NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (reality_id, channel_id)
);

-- (b) The uniqueness the spec asked for, on a non-partitioned side table.
CREATE TABLE IF NOT EXISTS channel_event_index (
    reality_id       UUID   NOT NULL,
    channel_id       BIGINT NOT NULL,
    channel_event_id BIGINT NOT NULL,
    event_id         UUID   NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (reality_id, channel_id, channel_event_id)
);

-- Channel-ordered scan support on the event rows themselves (non-unique —
-- uniqueness lives in channel_event_index).
CREATE INDEX IF NOT EXISTS events_channel_order_idx
    ON events (reality_id, channel_id, channel_event_id)
    WHERE channel_id IS NOT NULL;
