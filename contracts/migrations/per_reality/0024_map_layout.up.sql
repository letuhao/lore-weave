-- 0024_map_layout.up.sql
--
-- THE FIRST ROW OF THE SPACE SPINE. `MapKind` was designed on 2026-07-29
-- (`36_map_architecture.md`, `SPG-A3`) and until this migration it did not
-- appear in a single `.rs` file or a single table: the closed kind set, the
-- containment matrix and fifteen amendment rows all described a structure the
-- database had never heard of. `channels` (0019) ships the TREE -- per-reality,
-- parent-linked, acyclic by construction. It does not ship what a node IS.
--
-- This table is that, and nothing else.
--
-- WHY IT IS A FEATURE TABLE AND NOT A DATA-PLANE COLUMN. `SPG-R2` proposed
-- narrowing `DP-Ch1`'s `channels.level_name` to the closed set and was RETIRED
-- the same day: `DP-A13` keeps the data plane deliberately agnostic to level
-- semantics so a reality can name its own levels (`phu`, `chau`). Two fields,
-- two jobs -- `channels.level_name` is the reality's own word, `map_layout.kind`
-- is the structural kind the engine understands. `SPG-Q1` settled that the row
-- is AUTHORITATIVE and never derived from the channel tree, because under
-- `MapKind` a derivation is unobtainable.
--
-- ⛔ WHAT THIS TABLE DELIBERATELY DOES NOT HAVE: a `materialization` column.
--
--   `SPG-A12` says an interior is a declaration until something enters it, and
--   `MAP_001` §3.1 carried that as a per-node enum. `SDF-R1` (applied 2026-08-22)
--   moves it: THE LIVE SET IS AN INDEX AND THE NODE CARRIES NOTHING. It is the
--   only row in that document backed by a measurement rather than an argument --
--   ladder-as-FIELD versus ladder-as-INDEX is 92.4x at 0.1% live (doc 41 §2:
--   rustc 1.89, release+LTO+cgu=1, best-of-7, single core, 65 536 residents).
--
--   The measurement's limits travel with it: the advantage COLLAPSES to 0.7x at
--   100% live and 1.3x under heavy per-node work. So this is a win for a world
--   where almost nothing is live, which is the world `SPG-A12` describes.
--
--   The point of applying `SDF-R1` before writing this file is that a column is
--   cheap to add and expensive to remove. Doc 36's own opening states the stake:
--   "the cost of being wrong rises to a migration the moment the first row is
--   written." `materialization` would have been the first column in the space
--   schema that this project had ALREADY MEASURED as wrong.
--
-- WHAT IS DEFERRED, AND WHY EACH IS SOMEONE ELSE'S DECISION. `MAP_001` §3.1
-- declares five more fields. None is needed for a node to have a kind and a
-- place in its parent, and each needs a decision this migration must not make:
--   `tier_metadata`      -- shape is per-kind and unsettled under `SPG-R13`
--   `icon/background/inline_artwork` -- V1 slot reservations, pipeline is V1+
--   `connections`        -- `MapConnectionDecl` is unshaped, and `SDF-R3`
--                           (PortalSet) is still PROPOSED against doc 36 §3.
--                           Shipping a connection column now would decide the
--                           connective-adjacency relation by accident.
-- Adding a column later is an ALTER. Adding the wrong one is a migration
-- through the spine.

BEGIN;

CREATE TABLE IF NOT EXISTS map_layout (
    -- Carried even though the database is per-reality, matching `channels`,
    -- `events` and `actors`. The rebuild path reads rows out of context.
    reality_id  UUID    NOT NULL,

    -- The node this layout describes. NOT a new id space: `SDF-A31` says an
    -- AUTHORED node IS a `channels` row, minted by the shipped `ChannelTree`,
    -- and a GENERATED cell is an index into its owner's baseline and never a
    -- row at all. So there is no third id here and no allocator -- which is
    -- also why `PF_001`'s `PlaceId(pub ChannelId)`, written in April, needed no
    -- change when `SDF-A31` was written in August. Two tiers, one answer.
    channel_id  BIGINT  NOT NULL,

    -- `SPG-A3`. A closed set validated on write, replacing `MAP_001`'s retired
    -- `ChannelTier` ordinal ladder (`SPG-R1`). The ladder's five rungs map onto
    -- three kinds plus recursion (`SPG-R14`): Continent/Country/District all
    -- become a NESTING `Region`, Town becomes `Locale`, Cell becomes `Domain`.
    --
    -- `Vessel` is RESERVED in doc 36 and is deliberately NOT accepted here. A
    -- database that accepts a kind the engine has no semantics for lets a row
    -- exist that nothing can interpret; widening a CHECK later is cheap and
    -- reversible, and a row written under a name with no meaning is neither.
    kind        TEXT    NOT NULL,

    -- `SPG-A5`/`SPG-A17`: parent-RELATIVE, never absolute, in `MAP_001`'s
    -- 0..1000 normalised frame. INTEGER is not an optimisation here -- `SDF-R2`
    -- (applied 2026-08-22) makes it a correctness requirement, because this
    -- simulation is event-sourced and replayed and float is not bit-reproducible
    -- across machines. `MAP_001` had already specified `u32`, so the amendment
    -- costs this table nothing; it is the deeper tiers that had to change.
    pos_x       INTEGER NOT NULL,
    pos_y       INTEGER NOT NULL,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (reality_id, channel_id),

    -- A layout cannot describe a node that does not exist, and `reality_id` in
    -- the key is what stops a layout in reality A naming a channel in reality B
    -- -- structurally, not by a check. This is the same shape `channels` uses
    -- for its own parent edge.
    CONSTRAINT map_layout_channel_fk FOREIGN KEY (reality_id, channel_id)
        REFERENCES channels (reality_id, id) ON DELETE CASCADE,

    CONSTRAINT map_layout_kind_closed
        CHECK (kind IN ('universe', 'world', 'region', 'locale', 'domain', 'passage', 'arena')),

    -- `MAP_001` §3.1: 0..1000 within the parent frame. Stated as a CHECK rather
    -- than a convention because the frame only composes if every level agrees
    -- on its extent -- `SPG-A5`'s accumulation walks these numbers.
    CONSTRAINT map_layout_pos_x_in_frame CHECK (pos_x >= 0 AND pos_x <= 1000),
    CONSTRAINT map_layout_pos_y_in_frame CHECK (pos_y >= 0 AND pos_y <= 1000)
);

-- "Every node of kind K" is the query `SDF-A5` makes constant: a layer binds to
-- a `MapKind`, so weather over a Region is 200 rows rather than 300 000, and
-- that reduction is only real if the kind is indexed.
CREATE INDEX IF NOT EXISTS map_layout_by_kind
    ON map_layout (reality_id, kind);

COMMIT;
