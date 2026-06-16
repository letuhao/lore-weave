-- 031 (cycle-4 / D-READAUDIT-ENUM-DRIFT): reconcile the meta_read_audit
-- query_type CHECK enum with the SSOT contracts/meta/meta-sensitive-read-paths.yml.
--
-- PII/retention classification (S08 §12X.3/§12X.4; pii-classify-lint). ALTER on
-- the existing meta_read_audit table — per the §12X.4 matrix row (unchanged from
-- migration 029; query metadata only, opaque user_ref_id, never PII values).
-- @pii_sensitivity: low (query metadata; parameters carry only opaque user_ref_id, never PII values)
-- @retention_class: meta_read_audit
-- @retention_hot: 2y
-- @erasure_method: crypto_shred_actor
-- @legal_basis: legitimate_interest
--
-- WHY: migration 014 shipped a CHECK enum that drifted from the YAML SSOT, and
-- 029 (PII ids) deferred the full reconciliation to D-READAUDIT-ENUM-DRIFT. The
-- drift after 029:
--   * CHECK had `unbounded_select` + `consent_audit_export` — ORPHANS: never
--     written by any code path and never listed in the contract YAML (they were
--     speculative entries in migration 014). REMOVED here.
--   * CHECK lacked `bulk_meta_query` — present in the YAML SSOT (catch-all bulk
--     scan path) + the Go/Rust loaders' tests. ADDED here (forward-compatible:
--     a future bulk-query auditor writes it; no existing row uses it).
--   * `bulk_pii_read` is ACTIVELY written by the contracts/pii SDK (Go
--     TagBulkPIIRead + Rust SensitiveReadTag::BulkPiiRead) but was MISSING from
--     the YAML — the YAML was the incomplete side; it is added in the same
--     change as this migration so CHECK == YAML.
--
-- Result: the CHECK enum now equals the 7-id YAML SSOT set exactly. A new CI
-- gate (scripts/read-audit-query-type-drift-lint.sh) asserts CHECK == YAML so
-- they cannot silently drift again.
--
-- Safety: removing `unbounded_select`/`consent_audit_export` is non-breaking —
-- no writer emits them, so no existing row can violate the tighter CHECK (this
-- migration applies to the test/meta DB only).

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
