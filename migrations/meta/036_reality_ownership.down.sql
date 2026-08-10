-- Down for 036 — reality ownership (W6).
--
-- ⚠ THIS DESTROYS TENANCY DATA. Dropping the columns discards which user owns
-- which reality, and unlike most rollbacks there is no way to recover it from
-- elsewhere: nothing else in the platform records reality ownership.
--
-- The first version of this file argued rollback was safe "because every row
-- today is owner_kind='system' with a NULL owner, so there is nothing to lose."
-- That was true when it was written and **false within the hour** — the same
-- session provisioned user-owned realities. A safety argument that depends on
-- the current contents of a table is not a safety argument; it is a race with
-- the feature it ships beside. So the file now CHECKS instead of asserting, and
-- the check runs before anything is dropped.
--
-- It also used to DROP a constraint named `reality_registry_owner_consistent`,
-- which never existed in any applied schema — it was the name from the
-- single-disjunction draft the up.sql abandoned (see its NV-1 note). The DROPs
-- happened to work anyway because DROP COLUMN cascades CHECKs and indexes,
-- which meant every explicit DROP here was decorative and a wrong name could
-- never be noticed. They are now correct AND ordered before the column drop, so
-- a rename in the up.sql will actually surface here.

-- ⚠ AMENDED 2026-08-10 (`META-DOWN-UNCOVERED`). The early return below is not
-- defensive padding — without it this file could not be run twice.
--
-- Measured, on a throwaway meta database with all 39 up-migrations applied: the
-- first run succeeded, and the second died with
-- `ERROR: column "owner_kind" does not exist` from the guard's own SELECT,
-- because by then the column it protects has been dropped. Every DDL statement
-- below was already made `IF EXISTS` in the same pass, and it made no
-- difference: **the file still failed before reaching any of them.**
--
-- That is worth stating plainly, because the text linter went GREEN on this
-- file. `migration-idempotency-validator` blanks dollar-quoted bodies on
-- purpose — a PL/pgSQL body is not DDL, and reading it would be guessing — so
-- the one statement that broke the retry is in the one region the lint cannot
-- see. The lint is a proxy for retry-safety; running it twice is the property.
DO $guard$
DECLARE
    owned_count BIGINT;
BEGIN
    -- Already rolled back: the column this guard protects is gone, so there is
    -- no ownership left to erase and nothing to refuse. Returning early rather
    -- than erroring is what makes a re-run a no-op instead of a failure.
    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name   = 'reality_registry'
           AND column_name  = 'owner_kind'
    ) THEN
        RETURN;
    END IF;

    SELECT count(*) INTO owned_count
      FROM reality_registry
     WHERE owner_kind = 'user';

    IF owned_count > 0 AND
       coalesce(current_setting('loreweave.allow_ownership_rollback', true), '') <> 'yes'
    THEN
        RAISE EXCEPTION
            'refusing to roll back 036: % realit(y|ies) are user-owned and this migration '
            'would erase the only record of who owns them. Reassign them to the platform '
            '(owner_kind=''system'', owner_user_id=NULL) first, or set '
            'loreweave.allow_ownership_rollback=''yes'' to accept the loss.',
            owned_count;
    END IF;
END
$guard$;

-- Constraints first, so a name that no longer matches the up.sql fails loudly
-- here rather than being silently swept away by the column drop's cascade.
ALTER TABLE reality_registry
    DROP CONSTRAINT IF EXISTS reality_registry_owner_user_set;

ALTER TABLE reality_registry
    DROP CONSTRAINT IF EXISTS reality_registry_owner_system_null;

ALTER TABLE reality_registry
    DROP CONSTRAINT IF EXISTS reality_registry_owner_kind_enum;

DROP INDEX IF EXISTS idx_reality_registry_owner;

ALTER TABLE reality_registry
    DROP COLUMN IF EXISTS owner_user_id,
    DROP COLUMN IF EXISTS owner_kind;
