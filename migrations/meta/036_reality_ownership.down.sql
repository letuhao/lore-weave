-- Down for 036 — reality ownership (W6).
--
-- Dropping the columns discards which user owned which reality. That is
-- acceptable ONLY because this migration is being applied before users can
-- request realities: every row today is owner_kind='system' with a NULL owner,
-- so there is nothing to lose. Once a user-owned row exists, rolling this back
-- destroys tenancy data and the correct move is a forward fix instead.

DROP INDEX IF EXISTS idx_reality_registry_owner;

ALTER TABLE reality_registry
    DROP CONSTRAINT IF EXISTS reality_registry_owner_consistent;

ALTER TABLE reality_registry
    DROP CONSTRAINT IF EXISTS reality_registry_owner_kind_enum;

ALTER TABLE reality_registry
    DROP COLUMN IF EXISTS owner_user_id,
    DROP COLUMN IF EXISTS owner_kind;
