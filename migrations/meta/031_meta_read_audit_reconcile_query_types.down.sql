-- 031 DOWN — restore the pre-031 (migration 029) meta_read_audit query_type
-- CHECK enum: re-add the orphan ids (`unbounded_select`, `consent_audit_export`)
-- and drop `bulk_meta_query`, reverting to the 8-id set 029 left in place.

ALTER TABLE meta_read_audit DROP CONSTRAINT IF EXISTS meta_read_audit_query_type_enum;

ALTER TABLE meta_read_audit ADD CONSTRAINT meta_read_audit_query_type_enum CHECK (
    query_type IN (
        'player_index_cross_user',
        'audit_query',
        'admin_bulk_export',
        'unbounded_select',
        'bulk_pii_read',
        'consent_audit_export',
        'pii_user_get',
        'pii_user_erase'
    )
);
