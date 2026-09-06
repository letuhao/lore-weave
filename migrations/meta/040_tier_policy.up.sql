-- 040_tier_policy.up.sql
-- `DP-C4` — the TIER POLICY REGISTRY: "the authoritative record of every
-- aggregate type that exists in the system", and the capability grants over it.
-- Source: docs/03_planning/LLM_MMO_RPG/06_data_plane/05_control_plane_spec.md
--         DP-C4, whose DDL is transcribed here rather than invented.
-- Written by: a feature's deploy manifest, through CP's offline admin API
--   (DP-C10) -- never by a game-layer service at runtime.
-- Read by: `GetTierPolicy` + `StreamTierPolicyUpdates` (DP-C3), and
--   `GetSchemaVersion` / `AnnounceMigrationStart` / `AnnounceMigrationComplete`
--   (DP-C5), all five of which return UNIMPLEMENTED today for want of this.
--
-- @pii_sensitivity: none (aggregate type names, service names, tier letters)
-- @retention_class: operational
-- @retention_hot: indefinite
-- @erasure_method: hard_delete
-- @legal_basis: legitimate_interest
--
-- ── WHY TWO TABLES IN ONE MIGRATION ─────────────────────────────────────────
--
-- `tier_capability.aggregate_type` REFERENCES `tier_policy(aggregate_type)`.
-- Splitting them across two versions would leave a migration that cannot be
-- applied alone, which is what `migration-manifest-gate`'s forward-dependency
-- arm exists to refuse. They are one spec section and they are one unit.
--
-- ── WHAT THIS DOES *NOT* ADD, AND WHY THAT IS NOT AN OMISSION ───────────────
--
-- `npc_binding` (DP-A11) is the fourth table the control plane names as
-- missing, and it is NOT here. The spec references it twice -- "NPC-to-node
-- binding (DP-A11)" and a bullet in the deployment model -- and gives **no
-- DDL for it anywhere**, unlike DP-C4's two tables above. Writing a schema for
-- it would be inventing the contract rather than transcribing it, and a
-- fabricated shape in a LOCKED tier is worse than an absent one: the next
-- reader cannot tell which of the two it is.
--
-- So `GetNpcNode` and `ReportNodeHandoff` stay UNIMPLEMENTED, and their reason
-- is corrected from "has no migration in this repo" -- which implies the
-- migration is the only missing piece -- to naming the design gap. Recorded as
-- a run-state row rather than guessed at here.
--
-- `schema_version` is likewise not a table: DP-C4 makes it a COLUMN of
-- `tier_policy`, and the control plane's blocker string calling it a missing
-- table is the same imprecision. `GetSchemaVersion` reads the column below.

BEGIN;

CREATE TABLE IF NOT EXISTS tier_policy (
    aggregate_type    TEXT PRIMARY KEY,
    declared_tier     TEXT NOT NULL CHECK (declared_tier IN ('T0','T1','T2','T3')),
    schema_version    INT NOT NULL,
    feature_owner     TEXT NOT NULL,
    registered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_migration_at TIMESTAMPTZ,
    notes             TEXT,

    -- Not in DP-C4's DDL, and added because the column is meaningless without
    -- it: a schema version counts UP from 1, and `0` or a negative would make
    -- `DP-C5`'s expand/migrate/contract arithmetic (`k+1`) silently wrong.
    CONSTRAINT tier_policy_schema_version_pos CHECK (schema_version >= 1),
    -- Same reasoning as `channels.level_name`: an empty owner is not an owner,
    -- and "who owns this aggregate" is the question DP-C4 exists to answer.
    CONSTRAINT tier_policy_owner_nonempty CHECK (length(trim(feature_owner)) > 0)
);

COMMENT ON TABLE tier_policy IS
    'DP-C4 tier policy registry: every aggregate type, its design-time tier, its schema version and its owning feature. Written offline by deploy manifests (DP-C10), never by a game service at runtime.';
COMMENT ON COLUMN tier_policy.schema_version IS
    'DP-C5 expand/migrate/contract counter. A tier CHANGE is a migration producing a new aggregate type, NOT an UPDATE of declared_tier.';

CREATE TABLE IF NOT EXISTS tier_capability (
    service_id        TEXT NOT NULL,
    aggregate_type    TEXT NOT NULL REFERENCES tier_policy(aggregate_type),
    tiers_allowed     TEXT[] NOT NULL,
    can_read          BOOL NOT NULL,
    can_write         BOOL NOT NULL,
    granted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at        TIMESTAMPTZ,
    PRIMARY KEY (service_id, aggregate_type),

    -- `tiers_allowed` is "a subset of {T0,T1,T2,T3}" in DP-C4's own comment,
    -- and a TEXT[] enforces nothing by itself. Without this, a typo'd 'T4' or
    -- a lowercase 't2' grants a capability that matches no tier and fails
    -- later as "denied" rather than "misconfigured".
    CONSTRAINT tier_capability_tiers_known
        CHECK (tiers_allowed <@ ARRAY['T0','T1','T2','T3']::TEXT[]),
    -- An EMPTY array is a grant that grants nothing — representable, and never
    -- what anyone means. Revoking is `revoked_at`, which is a different fact.
    CONSTRAINT tier_capability_tiers_nonempty CHECK (cardinality(tiers_allowed) > 0),
    -- A row that permits neither read nor write is the same shape of nothing.
    CONSTRAINT tier_capability_grants_something CHECK (can_read OR can_write)
);

COMMENT ON TABLE tier_capability IS
    'DP-C4 per-service grants over an aggregate type. Revocation sets revoked_at; subsequent bind_session mints JWTs without the capability and the next refresh_capability drops it.';

-- The read `GetTierPolicy` makes is by aggregate_type (the PK). The index below
-- is for the OTHER read DP-C4 describes: a service asking what it may touch,
-- which is `tier_capability` by service_id — the PK's leading column, so it is
-- already served. The one shape neither covers is the live-grants scan, and
-- that is what this partial index is for.
CREATE INDEX IF NOT EXISTS tier_capability_live_idx
    ON tier_capability (aggregate_type)
    WHERE revoked_at IS NULL;

COMMIT;
