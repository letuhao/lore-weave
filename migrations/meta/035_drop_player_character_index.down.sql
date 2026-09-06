-- 035_drop_player_character_index.down.sql
-- Re-creates nothing. `012_player_character_index.up.sql` is the definition; a
-- copy here would be a second SSOT for a schema, and the down-path for "the old
-- table is gone" is to re-run 012 rather than to maintain a duplicate of it.
--
-- What this DOES restore is the read-audit CHECK enum, because 035's up-leg
-- redefined it and the drift lint reads the LATEST migration that does so. Left
-- alone, a down-migration would leave the CHECK naming an audit path the
-- contract no longer lists.

ALTER TABLE meta_read_audit DROP CONSTRAINT IF EXISTS meta_read_audit_query_type_enum;

ALTER TABLE meta_read_audit ADD CONSTRAINT meta_read_audit_query_type_enum CHECK (
    query_type IN (
        'player_index_cross_user',
        'audit_query',
        'admin_bulk_export',
        'bulk_meta_query',
        'bulk_pii_read',
        'pii_user_get',
        'pii_user_erase'
    )
);
