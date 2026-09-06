-- 0026_place.up.sql
--
-- SEMANTIC IDENTITY. `0024_map_layout` gave a node a KIND and `0025_entity_binding`
-- said where things ARE. Neither says what a node MEANS, and meaning is what an
-- LLM needs in order to narrate a scene an actor just walked into.
--
-- THIS IMPLEMENTS `PF_001` SECTION 3.1, CANDIDATE-LOCK 2026-04-26. That document
-- states in its own header that it resolves the "spawn-empty-place gap" and
-- defers spawn itself as "consumer responsibility" -- so this file builds the
-- place, and something else does the spawning.
--
-- `place_id` IS THE CHANNEL ID. `PF_001` declared `PlaceId(pub ChannelId)` in
-- April; `SDF-A31` reached the same rule from the id side in August -- an
-- AUTHORED node is a `channels` row and a GENERATED cell is an index, never a
-- row. Two tiers, one answer, four months apart, neither aware of the other. So
-- there is no new id space here and no allocator.
--
-- ONE PLACE PER `Domain`, AND IT IS STRUCTURAL RATHER THAN VALIDATED.
--
--   `PF_001` section 5's V1 invariant is 1:1 with a leaf node, and `SPG-R14`
--   re-states which leaf: the retired `ChannelTier` ladder's five rungs become
--   three kinds plus recursion, and `Cell` becomes `Domain`. A CHECK cannot
--   express "the row this points at has kind = domain" because a CHECK cannot
--   see another table.
--
--   The device is the one `0019_channels` already uses for its anti-cycle rule:
--   a GENERATED column pinned to a constant, carried into a composite foreign
--   key whose target is a UNIQUE index that includes the kind. A place row can
--   therefore only reference a `map_layout` row whose kind is literally
--   'domain'.
--
--   ⚠ AND THE SAME HONESTY `0019` HAD TO ADD LATER: this is stronger than a
--   check and it is NOT "unrepresentable". `ALTER TABLE ... ALTER COLUMN
--   kind_pin DROP EXPRESSION` needs only table ownership, after which a caller
--   supplies the value by hand. `0019`'s amendment records that exact route
--   after its own description outran its mechanism, so the claim is written at
--   its true strength here rather than discovered later.
--
-- WHAT IS DEFERRED, and the first one for the same reason `0024` deferred its
-- connections column:
--   `connections: Vec<ConnectionDecl>` -- a child table, and `SDF-R3` (PortalSet)
--       is still PROPOSED against doc 36 section 3. Shipping edges now would
--       decide the connective-adjacency relation BY ACCIDENT, twice.
--   `fixture_seed: Vec<EnvObjectSeed>` -- a child table whose rows describe
--       EnvObjects, and `PF_001` itself defers the EnvObject body to a "future
--       EnvObject feature". The seed_uid is UUID v5 over
--       (reality_id, place_id, slot_id) and stays derivable whenever it lands.
--   the two *_fiction_time columns -- `FictionTime` has no column type here yet,
--       the same gap `0025` recorded.

BEGIN;

-- The FK target. `(reality_id, channel_id)` is already unique as the primary
-- key; Postgres still requires a declared unique constraint on the exact
-- referenced column list, which is why the kind is repeated here.
ALTER TABLE map_layout
    DROP CONSTRAINT IF EXISTS map_layout_kind_uq;
ALTER TABLE map_layout
    ADD CONSTRAINT map_layout_kind_uq UNIQUE (reality_id, channel_id, kind);

CREATE TABLE IF NOT EXISTS place (
    reality_id       UUID    NOT NULL,

    -- `PlaceId(pub ChannelId)`. Not a new id.
    place_id         BIGINT  NOT NULL,

    -- Not a fact about this place -- a fact about the node it claims, written
    -- from this row so it cannot disagree with the foreign key below.
    kind_pin         TEXT    GENERATED ALWAYS AS ('domain') STORED,

    -- `PF_001` section 4, closed at ten. Closed "for compile-time
    -- exhaustiveness -- every consumer MUST handle each PlaceType or explicitly
    -- mark the wildcard", so a database that accepted an eleventh would be
    -- storing rows no consumer can narrate.
    place_type       TEXT    NOT NULL,

    -- `PF_001` section 7, four states. The TRANSITIONS are a state machine the
    -- database deliberately does not enforce: `Destroyed -> Pristine` is
    -- forbidden only via `Restored`, and expressing that needs the previous
    -- value, which a CHECK does not have. It is `place.invalid_structural_
    -- transition` at the write path, and putting half of it here would be worse
    -- than putting none.
    structural_state TEXT    NOT NULL DEFAULT 'pristine',

    -- REQUIRED by `PF_001`: every place is book-grounded, and a runtime-created
    -- one carries `AuthorCreated { reality_id, fiction_time, reason }` rather
    -- than nothing. JSONB because `BookCanonRef` is a SHARED schema whose
    -- ownership is explicitly deferred (`PF-D12`) -- giving it columns here
    -- would be this migration deciding another feature's contract.
    canon_ref        JSONB   NOT NULL,

    -- `LocalizedName { vi: String, en: Option<String> }`. The primary locale is
    -- required at V1 and the second is optional; that asymmetry is the feature's
    -- decision, recorded here as NOT NULL versus NULL rather than re-argued.
    name_vi          TEXT    NOT NULL,
    name_en          TEXT,

    -- Freeform per-reality drift. A bag the engine does not interpret, which is
    -- the same discipline `DP-A13` applies to channel metadata one tier down.
    narrative_drift  JSONB   NOT NULL DEFAULT '{}'::jsonb,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- "One row per place_id. Primary key conflict = place.duplicate_place."
    PRIMARY KEY (reality_id, place_id),

    CONSTRAINT place_type_closed CHECK (place_type IN (
        'residence', 'tavern', 'marketplace', 'temple', 'workshop',
        'official_hall', 'road', 'crossroads', 'wilderness', 'cave'
    )),

    CONSTRAINT place_structural_state_closed
        CHECK (structural_state IN ('pristine', 'damaged', 'destroyed', 'restored')),

    -- A name is required; a name of spaces is not a name.
    CONSTRAINT place_name_vi_nonempty CHECK (length(btrim(name_vi)) > 0),
    CONSTRAINT place_name_en_nonempty CHECK (name_en IS NULL OR length(btrim(name_en)) > 0),

    -- A canon reference that is `null` or a bare scalar is not a reference.
    CONSTRAINT place_canon_ref_is_object CHECK (jsonb_typeof(canon_ref) = 'object'),

    -- THE 1:1 RULE, STRUCTURALLY. `reality_id` in the key keeps the reference
    -- inside its own reality; `kind_pin` is what forbids a place on a `Region`,
    -- a `Locale`, a `World` or a `Universe`.
    --
    -- CASCADE is right here and RESTRICT was right in `0025`, and the asymmetry
    -- is the point: a place is a DESCRIPTION of a node, so it should die with
    -- it, while an occupant is a THING STANDING IN IT and must be evacuated
    -- first (`R-52`). Deleting a node therefore removes its description and is
    -- still refused while anyone is inside.
    CONSTRAINT place_domain_fk FOREIGN KEY (reality_id, place_id, kind_pin)
        REFERENCES map_layout (reality_id, channel_id, kind) ON DELETE CASCADE
);

-- "Every tavern in this reality" -- the query the NPC routine scheduler and the
-- LLM scene assembler both make, and the one a closed enum exists to serve.
CREATE INDEX IF NOT EXISTS place_by_type
    ON place (reality_id, place_type);

COMMIT;
