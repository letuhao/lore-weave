-- 0029_layer_registry.up.sql
--
-- `T4` -- THE LAYER REGISTRY, and with it `SDF-R5`.
--
-- `SDF-R5` says layers bind to a `MapKind` and `home_kinds` is REQUIRED,
-- validated on write. It has been PROPOSED since 2026-08-02 with one reason:
-- there was no registry to require anything of. This is that registry.
--
-- ## Why `home_kinds` is the highest-leverage column in this file
--
-- `R-29`, and the number is the whole argument:
--
--     Weather on a `Region` is 200 rows. Weather on every node is 300 000.
--
-- Almost nothing wants a value on EVERY node. Scale is axis 1; density is only
-- axis 2. A ~1000x reduction that costs nothing and requires no cleverness --
-- it falls straight out of the closed `MapKind` set `0024_map_layout` already
-- ships. Factorio reached the same shape from another direction: pollution,
-- enemy expansion and pathfinding all run per 32x32 CHUNK, never per tile.
--
-- A layer needing two scales registers TWO LAYERS plus an explicit aggregation
-- function, which forces the designer to STATE the aggregation instead of
-- discovering it later as a bug.
--
-- ## EVERY POLICY COLUMN IS `NOT NULL` WITH NO DEFAULT, AND THAT IS THE DESIGN
--
-- `SDF-A6`: *"No `Default` impl anywhere in it. Omitting a field is a compile
-- error."* The reason is `R-30`'s number -- ~150 Unreal components that do
-- LITERALLY NOTHING cost 1 ms on console, and 18 layers x 16 384 nodes is
-- 295 000 attachments, so a default of "tick" is ~2000x over a 100 ms budget
-- BEFORE any work. A column with a DEFAULT is that mistake with a database
-- behind it: *"the default is what you get when someone doesn't think about it,
-- and these are precisely the fields that must be thought about."*
--
-- So there is no `DEFAULT` on `update_policy`, `lifecycle_policy`, `edges` or
-- `projection`. An INSERT that omits one is refused by `NOT NULL`, which is the
-- schema's version of a compile error.
--
-- ## `id` is content-addressed and NEVER reused
--
-- `blake3-128` of the fully-qualified name, so the same name is the same id on
-- every machine and no allocator is involved -- the same reasoning `SDF-A31`
-- applies to generated cells. `R-19` is why reuse is fatal: `LayerId` must come
-- from an ordered append-only source, and *"removing a plugin must not renumber
-- the survivors, or every recorded event log misroutes."* `SDF-A12` therefore
-- retires a layer rather than deleting it, which is why `retired_at` exists and
-- `DELETE` is not the intended path.
--
-- ## Scope: PER-RULESET, not per-reality
--
-- `SDF-A30` / `WDS-A10`: anything derived from the RULESET is per-ruleset,
-- itself pinned per `(reality, epoch)`. The registry is ruleset data, so
-- `ruleset_digest` is in the primary key -- two epochs of one reality may
-- legitimately disagree about what layers exist, and a row is addressed by the
-- digest that gives it meaning. That is `QTY-A14`'s rule applied to a table:
-- an ordinal (here, a `LayerId`) means nothing without the digest it came from.

BEGIN;

CREATE TABLE IF NOT EXISTS layer_registry (
    reality_id       UUID    NOT NULL,

    -- `SDF-A30`: the registry is per-RULESET. Two epochs of one reality may
    -- declare different layer sets, and both are correct.
    ruleset_digest   TEXT    NOT NULL,

    -- blake3-128 of the fully-qualified name, hex. Content-addressed, so it is
    -- derived rather than allocated, and NEVER reused (`SDF-A12`).
    layer_id         TEXT    NOT NULL,

    -- "weather.state" -- namespaced. The id's preimage.
    name             TEXT    NOT NULL,

    -- The ONLY module that may write this layer (`SDF-A7`). The load-bearing
    -- check is `layer.foreign_write` at the event-log validator, "because it
    -- holds across process boundaries, across replay, and against a mod, which
    -- the type system does not" -- this column is what that check reads.
    owner_module     TEXT    NOT NULL,

    -- ⭐ `SDF-R5` / `SDF-A5`. NEVER EMPTY -- see the CHECK below.
    home_kinds       TEXT[]  NOT NULL,

    storage_class    TEXT    NOT NULL,
    update_policy    TEXT    NOT NULL,      -- NO DEFAULT, deliberately
    lifecycle_policy TEXT    NOT NULL,      -- NO DEFAULT, deliberately
    -- `SDF-A27`. Per edge kind: does this layer cross it? The simulation group
    -- is the connected components under the edges marked `propagates`, which is
    -- why air does not group like heat.
    edges            JSONB   NOT NULL,      -- NO DEFAULT, deliberately
    inheritance      TEXT    NOT NULL,
    -- `R-41`, from GeoPackage: it lets a consumer that has never heard of this
    -- layer decide BY POLICY, not by guessing, whether it may still safely read
    -- the node. Without it, "unknown layer" is undecidable.
    read_scope       TEXT    NOT NULL,
    projection       JSONB   NOT NULL,      -- NO DEFAULT, deliberately
    schema_version   INTEGER NOT NULL,
    visibility       TEXT    NOT NULL,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- `SDF-A12`: a layer is RETIRED, never deleted. A tombstone still decodes,
    -- because deleting the decoder makes the log un-replayable and "for an
    -- event-sourced world that means the world is gone."
    retired_at       TIMESTAMPTZ,

    PRIMARY KEY (reality_id, ruleset_digest, layer_id),

    -- A name resolves to one layer within a ruleset, or the id is not a
    -- function of the name and content-addressing is a fiction.
    CONSTRAINT layer_registry_name_uq UNIQUE (reality_id, ruleset_digest, name),

    CONSTRAINT layer_registry_name_nonempty  CHECK (length(btrim(name)) > 0),
    CONSTRAINT layer_registry_owner_nonempty CHECK (length(btrim(owner_module)) > 0),
    CONSTRAINT layer_registry_id_is_blake3_128
        CHECK (layer_id ~ '^[0-9a-f]{32}$'),

    -- ⭐ `SDF-R5`, THE POINT OF THIS FILE. `home_kinds` NEVER EMPTY -- an empty
    -- set is "every node", which is the 300 000-row outcome `R-29` exists to
    -- prevent, and it would arrive as an omission rather than a decision.
    CONSTRAINT layer_registry_home_kinds_nonempty
        CHECK (cardinality(home_kinds) > 0),

    -- ...and every member is a real `MapKind`. The set is the one
    -- `0024_map_layout`'s `map_layout_kind_closed` accepts, repeated because a
    -- CHECK cannot reach another table -- `Vessel` is excluded here for the same
    -- reason it is excluded there.
    CONSTRAINT layer_registry_home_kinds_closed CHECK (
        home_kinds <@ ARRAY['universe','world','region','locale','domain','passage','arena']::text[]
    ),

    CONSTRAINT layer_registry_storage_closed CHECK (storage_class IN (
        'uniform', 'dense', 'sparse', 'rare', 'interval',
        'derived', 'baseline_overlay', 'per_observer'
    )),
    CONSTRAINT layer_registry_update_closed CHECK (update_policy IN (
        'immutable', 'event_driven', 'lazy', 'scheduled', 'decay'
    )),
    CONSTRAINT layer_registry_lifecycle_closed CHECK (lifecycle_policy IN (
        'derived', 'authored', 'cache'
    )),
    CONSTRAINT layer_registry_inheritance_closed CHECK (inheritance IN (
        'none', 'resolved_cached'
    )),
    CONSTRAINT layer_registry_read_scope_closed CHECK (read_scope IN (
        'read_write', 'write_only'
    )),
    CONSTRAINT layer_registry_visibility_closed CHECK (visibility IN (
        'public', 'owner_only', 'per_observer'
    )),
    CONSTRAINT layer_registry_schema_version_positive CHECK (schema_version > 0),

    -- The two JSONB policies are objects, not scalars or nulls-as-json. A
    -- policy that decodes to `null` is an omitted policy wearing a value.
    CONSTRAINT layer_registry_edges_is_object      CHECK (jsonb_typeof(edges) = 'object'),
    CONSTRAINT layer_registry_projection_is_object CHECK (jsonb_typeof(projection) = 'object')
);

-- "Every layer whose home includes this kind" -- the query `SDF-A5` makes
-- constant, and the one that turns 300 000 rows into 200. GIN, because the
-- predicate is array containment.
CREATE INDEX IF NOT EXISTS layer_registry_by_home_kind
    ON layer_registry USING GIN (home_kinds);

-- The live set. `SDF-A12` keeps retired rows decodable, so every hot-path read
-- has to exclude them and a partial index is what makes that free.
CREATE INDEX IF NOT EXISTS layer_registry_live
    ON layer_registry (reality_id, ruleset_digest) WHERE retired_at IS NULL;

COMMIT;
