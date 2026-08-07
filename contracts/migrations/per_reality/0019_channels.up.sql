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
-- FOUR AMENDMENTS THIS FILE IS WRITTEN AGAINST, ALL FOUND BEFORE IT EXISTED
-- -------------------------------------------------------------------------
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
-- `REC-105` — **`reality_id` is present, and `DP-Ch2` does not have it.** Every
--   other table in this directory carries `reality_id UUID NOT NULL` inside its
--   primary key (`events`, `channel_writer_state`, `channel_event_seq`, …), and
--   the README states no reason — but `channel_writer_state` is
--   `PRIMARY KEY (reality_id, channel_id)`, so a foreign key from it to a
--   single-column `channels(id)` is **not expressible**. Following the spec
--   literally would have re-created `FLOW-19` in the migration that exists to
--   discharge it. The composite key is derived from the shipped tables, not
--   chosen; `DP-Ch2` needs the matching amendment and does not have it yet.
--
-- `REC-106` — **`DP-Ch1`'s anti-cycle mechanism, implemented instead of
--   asserted.** `12_channel_primitives.md:97` states it in full — *"No cycles.
--   Enforced by `depth` field (root = 0, children = parent.depth + 1) +
--   referential integrity on `parent`"* — and the first shipped schema
--   implemented the second half only. `depth` was a free-floating number: a
--   child of the root could declare `depth 16`, a hundred-node chain could sit
--   entirely at `depth 1`, and a two-row cycle took one `UPDATE`. The fix is
--   below and it is the spec's own sentence turned into SQL.

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

    -- `REC-106`. Not a fact about this channel — a fact about the one it claims
    -- as a parent, computed from this row so it CANNOT disagree with `depth`.
    -- The root's value is -1, which no row can ever match, and no row needs to:
    -- the root's `parent` is NULL and the foreign key below is `MATCH SIMPLE`.
    parent_depth  SMALLINT GENERATED ALWAYS AS ((depth - 1)::smallint) STORED,

    PRIMARY KEY (reality_id, id),

    -- The target of the foreign key below, and its ONLY purpose. `(reality_id,
    -- id)` is already unique; Postgres still requires a declared unique
    -- constraint on the exact referenced column list.
    CONSTRAINT channels_id_depth_uq UNIQUE (reality_id, id, depth),

    -- `DP-Ch1`, both halves (`REC-106`).
    --
    -- `reality_id` in the key is what stops a channel in reality A claiming a
    -- parent in reality B — structurally, not by a check.
    --
    -- `parent_depth` in the key is what stops CYCLES, and it is worth being
    -- precise about why, because "a check that looks strong" is this repo's
    -- most expensive defect. Along every parent edge, depth DECREASES BY
    -- EXACTLY ONE. Walk any cycle of length k and you return to your starting
    -- row having subtracted k > 0 from its own depth: `d = d - k` has no
    -- solution. A cycle is therefore not *rejected* — it is not
    -- *representable*. That includes the one-node case, which is why
    -- `channels_no_self_parent` is NOT in this table (see below).
    --
    -- DEFERRABLE INITIALLY IMMEDIATE, deliberately. Because a parent's `depth`
    -- is referenced by its children, moving a subtree cannot be done one row at
    -- a time; a transaction that re-parents a whole subtree must be able to
    -- pass through an inconsistent middle. The escape hatch does NOT weaken the
    -- guarantee above: the impossibility is arithmetic, so a deferred cycle is
    -- still refused — at COMMIT rather than at the statement. Measured on a live
    -- Postgres 18: `SET CONSTRAINTS channels_parent_fk DEFERRED` followed by a
    -- two-row cycle fails on `COMMIT`.
    CONSTRAINT channels_parent_fk FOREIGN KEY (reality_id, parent, parent_depth)
        REFERENCES channels (reality_id, id, depth)
        DEFERRABLE INITIALLY IMMEDIATE,

    -- `DP-Ch2` verbatim: depth is bounded and the tree has no orphans.
    CONSTRAINT channels_depth_bounded CHECK (depth >= 0 AND depth <= 16),
    CONSTRAINT channels_lifecycle_known
        CHECK (lifecycle IN ('active', 'dormant', 'dissolved')),
    CONSTRAINT channels_no_orphan CHECK (
        (parent IS NULL AND depth = 0) OR (parent IS NOT NULL AND depth > 0)
    ),

    -- `REC-106` also settles a question `channels_root_single` alone could not:
    -- that index gives AT MOST one root per reality, and this foreign key gives
    -- AT LEAST one for any non-empty reality — walk `parent` from any row and
    -- `depth` strictly decreases, so the walk terminates, and it can only
    -- terminate at `depth = 0`, which `channels_no_orphan` forces to be a root.
    -- Together: EXACTLY one root per non-empty reality, which is `DP-Ch1`.
    --
    -- NOT PRESENT, ON PURPOSE: `channels_no_self_parent CHECK (parent IS NULL OR
    -- parent <> id)`. It shipped in the first version of this file and
    -- `channels_parent_fk` now makes it unable to fail — a self-parented row
    -- would need a row with its own id at its own depth minus one, and `id` is
    -- unique per reality. A `CHECK` that cannot reject anything is `NV-1`, and
    -- `1bF-2` in this same table is what that costs when nobody notices for
    -- eight weeks. Verified by attack rather than by argument: with the foreign
    -- key in place, `INSERT (id 9, parent 9, depth 1)` is refused by
    -- `channels_parent_fk`; `scripts/dp-slice1b-constraint-bite.py` drops the
    -- foreign key and shows that same row INSERT.

    -- `1b5-M4`: `REC-103` cited the wire contract's unsigned `Uint64String` as a
    -- ground for BIGINT and carried the WIDTH across without the DOMAIN. A
    -- channel id is allocated by `DP-Ch11`'s `MAX() + 1`, which starts at 1.
    CONSTRAINT channels_id_positive CHECK (id > 0),
    CONSTRAINT channels_level_name_nonempty CHECK (length(btrim(level_name)) > 0),

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
--
-- `1b5-L3`, written down rather than discovered later: this index ignores
-- `lifecycle`, and `DP-Ch33` keeps a dissolved row indefinitely. So dissolving a
-- reality's root FORECLOSES that reality — no second root can ever be created in
-- it. That is the correct behaviour and not an oversight: `DP-Ch11` never
-- reissues an id, and a reality whose root is dissolved is a dissolved reality.
-- Making the predicate `lifecycle <> 'dissolved'` would say the opposite, and
-- would let a reality be re-rooted under a new tree while the old one's events
-- still reference the old root.
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

-- `1b5-L5` — `DP-Ch31` claims two things a `CHECK` cannot express, because both
-- are statements about a TRANSITION rather than about a row:
--
--   `17_channel_lifecycle.md:57` — "Dissolved | (any) | — | terminal, no
--     transitions", and :77 names the mechanism as a "row-level rule".
--   `17_channel_lifecycle.md:55` — dissolution requires "all descendants
--     Dissolved".
--
-- Before `1b.5` both fell to a plain `UPDATE`, and :77's "row-level rule" named
-- a mechanism that did not exist anywhere. This is that rule. It is deliberately
-- the DB's and not only the SDK's: `DP-Ch31` says "row-level rule + SDK
-- transition validator", and an SDK-only check is a check the next writer to
-- reach this table does not have.
--
-- Children, not descendants, and that is not a weakening: a child may only reach
-- Dissolved when ITS children are Dissolved, so by induction a Dissolved
-- channel's whole subtree is Dissolved.
CREATE OR REPLACE FUNCTION channels_lifecycle_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.lifecycle = 'dissolved' AND NEW.lifecycle <> 'dissolved' THEN
        RAISE EXCEPTION
            'channels_dissolved_is_terminal: channel % cannot leave lifecycle '
            '''dissolved'' (DP-Ch31: terminal, no transitions)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.lifecycle = 'dissolved' AND OLD.lifecycle <> 'dissolved'
       AND EXISTS (SELECT 1 FROM channels c
                    WHERE c.reality_id = NEW.reality_id
                      AND c.parent = NEW.id
                      AND c.lifecycle <> 'dissolved') THEN
        RAISE EXCEPTION
            'channels_dissolve_descendants_first: channel % still has a child '
            'that is not dissolved (DP-Ch33)', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER channels_lifecycle_guard_trg
    BEFORE UPDATE OF lifecycle ON channels
    FOR EACH ROW EXECUTE FUNCTION channels_lifecycle_guard();

COMMENT ON TABLE channels IS
    'DP-Ch2 channel registry, per reality. id is BIGINT (REC-103): DP-Ch11 allocates it as a '
    'monotonic counter seeded from MAX(), which a UUID cannot do. Cycles are unrepresentable '
    'rather than rejected (REC-106): parent_depth is generated from depth, and the parent FK '
    'carries it, so depth decreases by exactly one along every parent edge.';
