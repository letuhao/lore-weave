-- Down for 037 — re-permits the nil UUID as an owner.
--
-- Safe to roll back: it removes a restriction rather than data. Nothing is lost,
-- though ('user', 00000000-…) becomes representable again and the application
-- layers become the only thing refusing it.

ALTER TABLE reality_registry
    DROP CONSTRAINT reality_registry_owner_not_nil_uuid;
