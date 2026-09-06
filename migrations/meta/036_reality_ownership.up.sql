-- 036 — reality ownership (W6).
--
-- WHY
-- ---
-- `reality_registry` had no owner. It carries `close_initiated_by` and
-- `drop_approved_by` — the ADMINS who acted on a reality — and nothing at all
-- saying whose reality it is. `owner_user_id` appears in zero meta migrations
-- and no design document specifies reality ownership, so this is a genuine gap
-- rather than a rename.
--
-- It has to close before users can request realities, not after. CLAUDE.md
-- (User Boundaries, LOCKED) is explicit: every table holding user-customizable
-- data carries a scope key, and every query filters by it. A reality created
-- today belongs to nobody, so there is no query that could filter by owner and
-- no way to tell one user's reality from another's. Backfilling ownership onto
-- rows that were created without it is exactly the migration this ordering
-- avoids.
--
-- WHY TWO COLUMNS AND NOT A NULLABLE UUID
-- ---------------------------------------
-- A bare nullable `owner_user_id` makes NULL mean two different things — "the
-- platform owns this" and "nobody recorded an owner" — and those need opposite
-- responses. So the TIER is declared explicitly, matching the System / Per-user
-- table in CLAUDE.md:
--
--   owner_kind='system'  → the platform owns it; owner_user_id MUST be NULL
--   owner_kind='user'    → a user owns it;      owner_user_id MUST be set
--
-- The CHECK makes the inconsistent states unrepresentable rather than merely
-- discouraged (the same discipline as REC-106 on `channels`): a 'user' row with
-- no owner, and a 'system' row with one, are both refused by the database.
--
-- DEFAULT 'system' is safe for the three existing rows precisely BECAUSE it
-- forces owner_user_id to stay NULL — it cannot silently attribute an existing
-- reality to a user. Admin-provisioned realities are genuinely platform-owned,
-- so this is the true value for them, not a placeholder.
--
-- @pii_sensitivity: low (owner_user_id is an opaque loreweave_auth user id; it
--   identifies a user by reference but carries no attribute about them, and
--   owner_kind is a two-value tier)
-- @retention_class: tenancy_binding
-- @retention_hot: lifetime_of_reality (the row IS the reality's registration;
--   the binding cannot outlive it or precede it)
-- @erasure_method: reassign_to_system_on_user_erasure — an erasure request must
--   NOT delete the reality, which may hold other users' play. Setting
--   (owner_kind='system', owner_user_id=NULL) severs the link to the person
--   while leaving the world intact, and the CHECK constraints below make that
--   the only well-formed way to do it. NOT nullify-in-place: clearing
--   owner_user_id alone leaves owner_kind='user' and is REFUSED by
--   reality_registry_owner_user_set, so a partial erasure cannot be written.
-- @legal_basis: contract (a user's realities are part of the service they are
--   provided; ownership must be recorded to serve and to bill it)
--
-- NO FOREIGN KEY, AND THAT IS NOT AN OVERSIGHT
-- --------------------------------------------
-- `reality_registry` lives in `loreweave_meta`; users live in `loreweave_auth`.
-- Postgres cannot declare a foreign key across databases, which is why the
-- existing actor columns (`close_initiated_by`, `drop_approved_by`) carry none
-- either. Referential integrity for this column is the writer's obligation.

ALTER TABLE reality_registry
    ADD COLUMN IF NOT EXISTS owner_kind    TEXT NOT NULL DEFAULT 'system',
    ADD COLUMN IF NOT EXISTS owner_user_id UUID;

-- `DROP … IF EXISTS` first, because Postgres has no `ADD CONSTRAINT IF NOT
-- EXISTS` and a retried migration must not fail on the second attempt. This is
-- the idiom seven sibling meta migrations already use (029, 031, 032, 035, …);
-- 036 and 037 were the only two that did not, measured 2026-08-10 by re-running
-- them against a throwaway meta database.
--
-- ONE STATEMENT, not two. This file has no `BEGIN;`, so psql runs each statement
-- in its own transaction — and a separate `DROP …;` followed by a separate
-- `ADD …;` leaves a window in which the constraint DOES NOT EXIST. These three
-- are the tenancy rules (`owner_kind`/`owner_user_id`), so that window is one in
-- which a `user`-kind row with a NULL owner would be accepted. `ALTER TABLE`
-- takes a comma-separated action list and applies it atomically, which costs
-- nothing and closes the window. Caught by `/review-impl`, which noticed that
-- 037 — the same change, the same session — had already been written this way.
ALTER TABLE reality_registry
    DROP CONSTRAINT IF EXISTS reality_registry_owner_kind_enum,
    ADD CONSTRAINT reality_registry_owner_kind_enum
        CHECK (owner_kind IN ('system', 'user'));

-- The consistency rule, as two IMPLICATIONS rather than one disjunction.
--
-- This shape is deliberate and was chosen after biting the first draft. That
-- draft wrote the rule as a single disjunction:
--
--     CHECK ((owner_kind='system' AND owner_user_id IS NULL)
--         OR (owner_kind='user'   AND owner_user_id IS NOT NULL))
--
-- which is correct, and which made the enum CHECK above **unreachable**:
-- `owner_kind='wizard'` fails both branches of the disjunction, so the
-- consistency constraint always fired first and the enum could never be the
-- binding one. A constraint that cannot fail is not a constraint
-- (`docs/standards/non-vacuity.md`, NV-1) — and this is its hardest shape, an
-- adjacent decision defeating a check while both look individually right.
--
-- As implications, an unknown kind satisfies BOTH (their antecedents are
-- false), so it reaches the enum. Each of the three constraints now has a
-- distinct, reachable job:
--
--   enum              → rejects a kind outside the closed set
--   owner_system_null → rejects a system row that names an owner
--   owner_user_set    → rejects a user row with no owner
ALTER TABLE reality_registry
    DROP CONSTRAINT IF EXISTS reality_registry_owner_system_null,
    ADD CONSTRAINT reality_registry_owner_system_null
        CHECK (owner_kind <> 'system' OR owner_user_id IS NULL);

ALTER TABLE reality_registry
    DROP CONSTRAINT IF EXISTS reality_registry_owner_user_set,
    ADD CONSTRAINT reality_registry_owner_user_set
        CHECK (owner_kind <> 'user' OR owner_user_id IS NOT NULL);

-- The access pattern this column exists for: "list the realities user X owns".
-- Partial, because system-owned rows are never fetched by owner.
CREATE INDEX IF NOT EXISTS idx_reality_registry_owner
    ON reality_registry (owner_user_id)
    WHERE owner_user_id IS NOT NULL;

COMMENT ON COLUMN reality_registry.owner_kind IS
    'Tenancy tier: system (platform-owned, owner_user_id NULL) or user (owner_user_id set). See CLAUDE.md User Boundaries.';
COMMENT ON COLUMN reality_registry.owner_user_id IS
    'Owning user (loreweave_auth.users.id). No FK: cross-database. NULL iff owner_kind=system.';
