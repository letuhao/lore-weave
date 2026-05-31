-- 029 (cycle-4 / 076 Slice C): add pii_user_get + pii_user_erase to the
-- meta_read_audit query_type CHECK.
--
-- PII/retention classification (S08 §12X.3/§12X.4; pii-classify-lint). ALTER on
-- the existing meta_read_audit table — per the §12X.4 matrix row.
-- @pii_sensitivity: low (query metadata; parameters carry only opaque user_ref_id, never PII values)
-- @retention_class: meta_read_audit
-- @retention_hot: 2y
-- @erasure_method: crypto_shred_actor
-- @legal_basis: legitimate_interest
--
-- WHY: the canonical SSOT contracts/meta/meta-sensitive-read-paths.yml already
-- lists `pii_user_get` and `pii_user_erase` as valid query_type ids, but
-- migration 014 shipped an older enum that omitted them. The cycle-4 PII SDK
-- (contracts/pii.SDK.GetPII / ErasePII) mandatorily writes a meta_read_audit
-- row with these ids — so a real INSERT currently violates the CHECK and
-- ErasePII fails AFTER the KEK is already crypto-shredded ("erase succeeded but
-- audit failed"). This migration aligns the enum TOWARD the contract (union of
-- the existing 6 ids + the 2 PII ids; non-breaking — no row uses the new ids).
--
-- The other contract<->migration drift (contract `bulk_meta_query` vs migration
-- `bulk_pii_read`/`unbounded_select`/`consent_audit_export`) is pre-existing and
-- NOT touched here. Tracked: D-READAUDIT-ENUM-DRIFT (full reconciliation + a CI
-- validator that asserts the CHECK == the contract id set).

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
