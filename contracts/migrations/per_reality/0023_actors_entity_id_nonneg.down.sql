-- Reverse of 0023. Dropping the CHECK returns `actors.entity_id` to accepting
-- any BIGINT, including the negatives that make an actor creatable, grantable
-- and permanently unable to act. The code guard in
-- `actor_registry::checked_island_id` still refuses them at both edges, so this
-- reopens the hole only for a writer that skips the helper — which is exactly
-- the case the constraint was added for.

ALTER TABLE actors
    DROP CONSTRAINT IF EXISTS actors_entity_id_nonneg;
