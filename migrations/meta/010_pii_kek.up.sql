-- 010_pii_kek.up.sql
-- L1.A-2 (cycle 3) — per-user Key Encryption Key envelope; destroyed (crypto-shred) on user erasure.
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §2.2
-- Owning kernel chunk: S08 §12X.2
-- Retention: forever (destroyed_at marker = erasure satisfied; row stays for audit)
-- Written by: auth-service (creation), admin-cli (admin/user-erasure Tier 1 destructive)
-- Read by: KMS adapter (decrypt path)
--
-- Crypto-shred mechanism:
--   - key_material is KMS CIPHERTEXT (envelope-encrypted by a KMS master key).
--     The KEK PLAINTEXT bytes never live outside the KMS/HSM boundary.
--   - On user erasure, the destroyed_at column is set AND a KMS
--     ScheduleKeyDeletion(30d) call is fired by the admin-cli erasure
--     command (out of scope for this cycle — admin-cli ships in L7).
--   - After destroyed_at is set, contracts/meta refuses to decrypt
--     (OpenPII returns ErrPIIErased), so the linked pii_registry.encrypted_blob
--     is functionally unreadable.

CREATE TABLE IF NOT EXISTS pii_kek (
    kek_id             UUID            PRIMARY KEY,

    -- Owner — every KEK is bound to exactly one user. FK enforces referential
    -- integrity. ON DELETE NO ACTION because erasure = mark destroyed_at, not
    -- DROP the row.
    user_ref_id        UUID            NOT NULL
        REFERENCES pii_registry(user_ref_id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY DEFERRED,
    -- DEFERRABLE INITIALLY DEFERRED lets us create the pair (registry + kek)
    -- in a single TX with the FK satisfied at commit time. Order of insert
    -- still has to be:  INSERT pii_registry → INSERT pii_kek → UPDATE
    -- pii_registry.kek_id  — all in one batch via MetaWriteBatch.

    -- KMS ciphertext envelope. NEVER plaintext key bytes. Tests use a
    -- deterministic placeholder envelope (see kms_test.go); production uses
    -- the configured KMS adapter (AWS KMS / HashiCorp Vault — out of scope).
    key_material       BYTEA           NOT NULL,

    -- KMS provenance — which KMS provider/key produced this envelope.
    -- Format: "<provider>:<key_arn_or_alias>" (e.g., "aws-kms:arn:aws:kms:...").
    -- Used by the KMS adapter to route decrypt calls.
    kms_key_ref        TEXT            NOT NULL,

    -- Bookkeeping
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    rotated_from       UUID            NULL,  -- prior kek_id when this row replaces it

    -- Crypto-shred marker. When set:
    --   1. contracts/meta OpenPII refuses to decrypt (ErrPIIErased)
    --   2. KMS ScheduleKeyDeletion has been (or will be) fired
    --   3. row STAYS for audit — never DELETEd
    destroyed_at       TIMESTAMPTZ     NULL,
    destroyed_by_ticket TEXT           NULL,
    destroyed_reason    TEXT           NULL,

    CONSTRAINT pii_kek_key_material_nonempty CHECK (length(key_material) >= 16),
    CONSTRAINT pii_kek_kms_key_ref_format CHECK (
        kms_key_ref ~ '^[a-z][a-z0-9-]*:[A-Za-z0-9:_/.@%-]+$'
    ),
    -- Either fully destroyed (all three columns set) or fully active (all NULL)
    CONSTRAINT pii_kek_destroyed_columns_consistent CHECK (
        (destroyed_at IS NULL AND destroyed_by_ticket IS NULL AND destroyed_reason IS NULL) OR
        (destroyed_at IS NOT NULL AND destroyed_by_ticket IS NOT NULL AND length(destroyed_by_ticket) > 0
            AND destroyed_reason IS NOT NULL AND length(destroyed_reason) > 0)
    )
);

-- Lookup: "what's the current (non-destroyed) KEK for this user?"
CREATE INDEX IF NOT EXISTS idx_pii_kek_user_active_partial
    ON pii_kek (user_ref_id)
    WHERE destroyed_at IS NULL;

-- Audit lookup: "who erased this user and when?"
CREATE INDEX IF NOT EXISTS idx_pii_kek_destroyed_at
    ON pii_kek (destroyed_at)
    WHERE destroyed_at IS NOT NULL;

-- Rotation chain lookup (for crypto-rotation audit)
CREATE INDEX IF NOT EXISTS idx_pii_kek_rotated_from
    ON pii_kek (rotated_from)
    WHERE rotated_from IS NOT NULL;

-- Append-only on the key_material itself — REVOKE UPDATE on key_material
-- column would be ideal but Postgres column-level REVOKE doesn't cover
-- application roles cleanly. Enforced by contracts/meta library: only INSERT
-- of new pii_kek rows allowed; UPDATEs limited to destroyed_* columns via
-- MetaWrite ExpectedBefore guard.
DO $$
BEGIN
    -- App roles can INSERT (rotate) and UPDATE (mark destroyed) but never DELETE
    EXECUTE 'REVOKE DELETE ON TABLE pii_kek FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE DELETE ON TABLE pii_kek FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE pii_kek IS
    'L1.A-2 — per-user Key Encryption Key envelope. PLAINTEXT key bytes never leave KMS. Crypto-shred = set destroyed_at + KMS ScheduleKeyDeletion(30d).';
COMMENT ON COLUMN pii_kek.key_material IS
    'KMS CIPHERTEXT envelope. Never plaintext. Decrypted only inside KMS/HSM boundary by the KMS adapter.';
COMMENT ON COLUMN pii_kek.destroyed_at IS
    'Crypto-shred marker. When set, contracts/meta OpenPII returns ErrPIIErased. Row stays for audit; never DELETEd.';
