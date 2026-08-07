-- 0019_channels — the channel registry (DP-Ch1 / DP-Ch2 / DP-Ch11 / DP-Ch13).
--
-- WHY THIS DID NOT EXIST UNTIL NOW
-- --------------------------------
-- `FLOW-9`, measured 2026-08-07: `06_data_plane/` has specified this table since
-- Phase 4 and no migration ever shipped. `FLOW-19` is the consequence —
-- `0014_channel_ordering` declares `channel_writer_state.channel_id BIGINT` with
-- **no foreign key**, which it could not have had, because there was nothing to
-- reference. `DP-Ch13` locks that column as `UUID PRIMARY KEY REFERENCES
-- channels(id)`; the shipped table is neither.
--
-- THREE AMENDMENTS THIS FILE IS WRITTEN AGAINST, ALL FOUND BEFORE IT EXISTED
-- --------------------------------------------------------------------------
-- `REC-103` — `id` is **BIGINT**, not `UUID`. `REC-102a` (PO-approved
--   2026-08-07) settled `ChannelId`'s payload as `i64`: the shipped
--   `crates/dp-kernel/src/channel.rs` says `ChannelId(pub(crate) i64)`, the
--   client wire contract says `Uint64String`, and `DP-Ch11`'s allocator is a
--   monotonic counter seeded from `MAX()` — which is what a BIGINT is for and
--   which a UUID cannot do. That decision reached the newtype and the code and
--   never reached the schema thirty lines below it.
--
-- `REC-104` — `CONSTRAINT channels_root_single UNIQUE (id)` was **vacuous**.
--   `id` is the primary key, so uniqueness on it is already total: it could not
--   reject a row. Its NAME states `DP-Ch1`'s real invariant — *a strict tree has
--   exactly one root* — and nothing enforced it. `channels_no_orphan` is
--   adjacent and weaker: it forbids a root at `depth != 0`, and permits any
--   number of roots. Here it is a partial unique index, which is the only shape
--   Postgres offers for "at most one row satisfying a predicate".
--
-- `1bF-4` — **`reality_id` is present, and `DP-Ch2` does not have it.** Every
--   other table in this directory carries `reality_id UUID NOT NULL` inside its
--   primary key (`events`, `channel_writer_state`, `channel_event_seq`, …), and
--   the README states no reason — but `channel_writer_state` is
--   `PRIMARY KEY (reality_id, channel_id)`, so a foreign key from it to a
--   single-column `channels(id)` is **not expressible**. Following the spec
--   literally would have re-created `FLOW-19` in the migration that exists to
--   discharge it. The composite key is derived from the shipped tables, not
--   chosen; `DP-Ch2` needs the matching amendment and does not have it yet.
--   ⚠ If the intent is genuinely one database per reality with `reality_id`
--   redundant, this is the wrong shape and it is cheap to change NOW — nothing
--   has been applied to a real database.

CREATE TABLE IF NOT EXISTS channels (
    reality_id    UUID     NOT NULL,
    id            BIGINT   NOT NULL,
    parent        BIGINT,
    level_name    TEXT     NOT NULL,
    display_name  TEXT,
    depth         SMALLINT NOT NULL,
    lifecycle     TEXT     NOT NULL,
    metadata      JSONB    NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    dissolved_at  TIMESTAMPTZ,

    PRIMARY KEY (reality_id, id),

    -- `DP-Ch1`: the tree is per-reality, so a parent is resolved WITHIN the
    -- reality. A self-referencing composite FK is what stops a channel in
    -- reality A claiming a parent in reality B.
    CONSTRAINT channels_parent_fk FOREIGN KEY (reality_id, parent)
        REFERENCES channels (reality_id, id),

    -- `DP-Ch2` verbatim: depth is bounded and the tree has no orphans.
    CONSTRAINT channels_depth_bounded CHECK (depth >= 0 AND depth <= 16),
    CONSTRAINT channels_lifecycle_known
        CHECK (lifecycle IN ('active', 'dormant', 'dissolved')),
    CONSTRAINT channels_no_orphan CHECK (
        (parent IS NULL AND depth = 0) OR (parent IS NOT NULL AND depth > 0)
    ),

    -- A channel cannot be its own parent. `channels_no_orphan` does not forbid
    -- it (a self-parented row at depth > 0 satisfies both halves), and a
    -- one-node cycle is the cheapest way to turn the tree into a graph.
    CONSTRAINT channels_no_self_parent CHECK (parent IS NULL OR parent <> id),

    -- `DP-Ch31`..`DP-Ch37` (17_channel_lifecycle.md): a dissolved channel has a
    -- dissolution time and a
    -- live one does not. Stated as a biconditional so neither direction can rot.
    -- (This cited `DP-Ch17` until 1b.5. DP-Ch17 is *Hybrid backing store*,
    -- 14_durable_subscribe.md:76 -- I had read the FILE NUMBER as a stable ID.)
    CONSTRAINT channels_dissolved_at_iff_dissolved CHECK (
        (lifecycle = 'dissolved') = (dissolved_at IS NOT NULL)
    )
);

-- `REC-104`, made able to fail: ONE root per reality. `parent IS NULL` is the
-- predicate; the index key is `reality_id`, so a second root in the same reality
-- collides and a root in a different reality does not.
CREATE UNIQUE INDEX IF NOT EXISTS channels_root_single
    ON channels (reality_id)
    WHERE parent IS NULL;

CREATE INDEX IF NOT EXISTS channels_parent_idx
    ON channels (reality_id, parent);
CREATE INDEX IF NOT EXISTS channels_level_idx
    ON channels (reality_id, level_name)
    WHERE lifecycle = 'active';
CREATE INDEX IF NOT EXISTS channels_lifecycle_idx
    ON channels (reality_id, lifecycle);

COMMENT ON TABLE channels IS
    'DP-Ch2 channel registry, per reality. id is BIGINT (REC-103): DP-Ch11 allocates it as a '
    'monotonic counter seeded from MAX(), which a UUID cannot do.';
