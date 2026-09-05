-- 0025_entity_binding.up.sql
--
-- WHERE THINGS ARE. `0024_map_layout` gave a node a KIND; nothing in this
-- database said where anything IS. `actors` (0022) is a pure identity bijection
-- -- (reality_id, actor_id UUID) <-> entity_id BIGINT -- with no location
-- column, and that was checked before this file was written rather than assumed.
--
-- THIS IMPLEMENTS `EF_001` SECTION 3.1. IT DOES NOT INVENT A TABLE. The space
-- tier's own `T7 node_occupancy (entity, node, local_pos)` was STRUCK by
-- `SDF-A34`: `entity_binding` already existed in design, is richer, and had
-- already settled the question `T7` silently re-opened.
--
-- NO FINE POSITION COLUMN, and this is the whole reason `T7` was struck.
--
--   `EF_001`s 2026-06-20 medium-reconciliation states it: `InCell(cell_id)` is
--   the COARSE cell membership -- authoritative, durable, evented on the cell
--   transition -- and is layer 1 of `ILR-A2`s three-layer position stack. The
--   fine continuous within-cell position is REALTIME-LAYER-OWNED ephemeral
--   state (`RTM-A1`), periodically checkpointed, NEVER PER-TICK IN THE EVENT
--   LOG. "entity_binding thus stays cell-granular BY DESIGN, NOT BY OMISSION."
--
--   Note that `EntityLocation`s own shape agrees: its `InCell` variant carries
--   a `cell_id` and nothing else. The enum had already refused what `T7`
--   proposed.
--
-- THE SUM TYPE. `EntityLocation` is a CLOSED four-variant enum, and `ITD-1`
-- confirms it stays closed -- "its four variants stay closed and correct" --
-- even as it proposes a SIBLING field. It is stored here as a discriminator
-- plus per-variant columns, with a CHECK asserting that EXACTLY one variant's
-- columns are present and every other variant's are NULL. A discriminator
-- without that CHECK is a sum type that can hold two variants at once, which is
-- not a sum type.
--
-- WHAT IS DEFERRED, each because it is undecided or another feature's:
--   owner: OwnerRef       -- PROPOSED (`ITD-1` / `IR-22`), not decided. Adding a
--                            column for a proposed field would decide it.
--   owner_node            -- the epoch-fenced writer binding (PL_001 3.6);
--                            nothing writes concurrently until a bootstrap does
--   affordance_overrides  -- None means "use the type default", and the
--                            type-level default set is not built
--   cell_owner            -- RES_001s, and `ITD-1` is generalising it away
--   inventory_cap         -- V1 is ALWAYS None per RES_001 Q6
--   the two *_fiction_time columns -- `FictionTime` has no column type here yet
--
-- Every one of those is an ALTER later. `local_pos` would not have been.

BEGIN;

CREATE TABLE IF NOT EXISTS entity_binding (
    reality_id       UUID     NOT NULL,

    -- `EntityId(u64)` as the island holds it -- the same BIGINT that
    -- `actors.entity_id` carries, so an actor sited here is the actor that
    -- table names. `0023` already established that a negative is permanently
    -- unresolvable, because -1 as u64 is u64::MAX; the CHECK is repeated here
    -- rather than assumed, since an enumerated set of call sites is
    -- default-uncovered (NV-3).
    entity_id        BIGINT   NOT NULL,

    -- Denormalised discriminator. `EF_001` 3.1 states why it is stored: a
    -- sum-type variant tag is not directly indexable, and a validator enforces
    -- equality with the `entity_id` variant on every write.
    entity_type      TEXT     NOT NULL,

    -- `EntityLocation`s discriminator, then one column group per variant.
    location_kind    TEXT     NOT NULL,
    cell_id          BIGINT,            -- InCell
    holder_entity    BIGINT,            -- HeldBy
    container_entity BIGINT,            -- InContainer
    parent_entity    BIGINT,            -- Embedded
    slot             TEXT,              -- Embedded

    -- `D-12`, 2026-08-02: a DECLARED state ordinal, not a closed engine enum.
    -- "Existing / Suspended / Destroyed / Removed is ONE REALITYS VOCABULARY,
    -- not the engines type." The engine holds the ordinal and validates
    -- transitions against the declared set; it does not know what a state
    -- means. A bare ordinal is safe HERE and only here: `QTY-A14` / `S-11`
    -- require an ordinal that LEAVES the island to carry the digest that gives
    -- it meaning, and this table is per-reality, so nothing crosses.
    lifecycle_state  SMALLINT NOT NULL,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (reality_id, entity_id),

    CONSTRAINT entity_binding_entity_id_nonneg CHECK (entity_id >= 0),

    CONSTRAINT entity_binding_type_closed
        CHECK (entity_type IN ('pc', 'npc', 'item', 'env_object')),

    CONSTRAINT entity_binding_location_kind_closed
        CHECK (location_kind IN ('in_cell', 'held_by', 'in_container', 'embedded')),

    CONSTRAINT entity_binding_lifecycle_ordinal_nonneg
        CHECK (lifecycle_state >= 0),

    -- THE SUM TYPE, ENFORCED. Exactly one variant is populated. Without this a
    -- row could be `in_cell` AND carry a holder, and two readers would disagree
    -- about where the thing is.
    CONSTRAINT entity_binding_location_is_a_sum CHECK (
        CASE location_kind
            WHEN 'in_cell'      THEN cell_id IS NOT NULL
                                 AND holder_entity IS NULL
                                 AND container_entity IS NULL
                                 AND parent_entity IS NULL
                                 AND slot IS NULL
            WHEN 'held_by'      THEN holder_entity IS NOT NULL
                                 AND cell_id IS NULL
                                 AND container_entity IS NULL
                                 AND parent_entity IS NULL
                                 AND slot IS NULL
            WHEN 'in_container' THEN container_entity IS NOT NULL
                                 AND cell_id IS NULL
                                 AND holder_entity IS NULL
                                 AND parent_entity IS NULL
                                 AND slot IS NULL
            WHEN 'embedded'     THEN parent_entity IS NOT NULL
                                 AND slot IS NOT NULL
                                 AND cell_id IS NULL
                                 AND holder_entity IS NULL
                                 AND container_entity IS NULL
            ELSE FALSE
        END
    ),

    -- `slot` is "a freeform ID (e.g. lock_keyhole)", and freeform is not empty.
    CONSTRAINT entity_binding_slot_nonempty
        CHECK (slot IS NULL OR length(btrim(slot)) > 0),

    -- An entity cannot be inside itself, in any variant. Cheap to check here
    -- and impossible to debug at runtime -- the same argument `R-52` makes for
    -- holder NOT IN descendants(node) one tier up.
    CONSTRAINT entity_binding_not_self_referential CHECK (
        entity_id <> coalesce(holder_entity, -1)
        AND entity_id <> coalesce(container_entity, -1)
        AND entity_id <> coalesce(parent_entity, -1)
    ),

    -- `SDF-A34` + `SPG-R14`: an entity is sited AT A NODE, and the node must
    -- exist. `reality_id` in the key keeps the reference inside its own reality
    -- structurally rather than by a check.
    --
    -- NOT `ON DELETE CASCADE`, and the difference from `0024` is deliberate:
    -- deleting a node there removed a DESCRIPTION of it, while deleting one
    -- here would silently delete THE THINGS STANDING IN IT. `R-52` is the rule
    -- -- when a Domain dies, EVACUATE, never delete -- so a node with occupants
    -- must be REFUSED until they are moved. RESTRICT makes that refusal the
    -- databases, not a callers good intentions.
    CONSTRAINT entity_binding_cell_fk FOREIGN KEY (reality_id, cell_id)
        REFERENCES channels (reality_id, id) ON DELETE RESTRICT
);

-- "Who is in this node" -- the occupancy query itself, and the one `R-53` says
-- must be maintained incrementally on crossing rather than recomputed by search.
CREATE INDEX IF NOT EXISTS entity_binding_by_cell
    ON entity_binding (reality_id, cell_id) WHERE cell_id IS NOT NULL;

COMMIT;
