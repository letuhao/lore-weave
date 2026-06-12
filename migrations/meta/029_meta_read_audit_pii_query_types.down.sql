-- 029 DOWN: restore the original migration-014 6-id meta_read_audit query_type
-- CHECK (drops pii_user_get + pii_user_erase). Safe at the point this migration
-- is rolled back IFF no meta_read_audit row uses the two PII ids; if any do, the
-- re-added CHECK will reject them (expected — roll back before such rows exist).
ALTER TABLE meta_read_audit DROP CONSTRAINT IF EXISTS meta_read_audit_query_type_enum;

ALTER TABLE meta_read_audit ADD CONSTRAINT meta_read_audit_query_type_enum CHECK (
    query_type IN (
        'player_index_cross_user',
        'audit_query',
        'admin_bulk_export',
        'unbounded_select',
        'bulk_pii_read',
        'consent_audit_export'
    )
);
