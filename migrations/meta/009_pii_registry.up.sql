-- 009_pii_registry.up.sql
-- L1.A-2 (cycle 3) — canonical store for every user's PII (email, display_name,
-- legal_name, timezone, verified_phone); referenced by opaque `user_ref_id` everywhere else.
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §2.1
-- Owning kernel chunk: S08 §12X.2
-- Retention: forever (erasure via crypto-shred — KEK destroyed, blob remains unreadable)
-- Written by: auth-service via MetaWrite()
-- Read by: services with PII access need (rare — most code uses user_ref_id opaque)
--
-- Crypto-shred semantics: encrypted_blob is AES-256-GCM ciphertext keyed by the
-- KEK referenced by kek_id. When the corresponding pii_kek row is destroyed
-- (destroyed_at IS NOT NULL), the blob becomes permanently unreadable —
-- that's how GDPR Art. 17 erasure is satisfied without losing the row
-- (which is required for audit trail integrity).
--
-- NOTE: kek_id is NOT a FK to pii_kek. Rationale:
--   1. KEK rotation creates a NEW pii_kek row then UPDATEs pii_registry.kek_id
--      to point to it. The old kek row remains for audit (destroyed_at on
--      rotated-out keks stays NULL).
--   2. On user erasure, the CURRENT kek's destroyed_at is set. The pii_registry
--      row stays intact; the blob is just unreadable.
--   3. FK would force CASCADE or restrict semantics that don't match this
--      lifecycle. Application-level invariant (asserted by tests + library).

CREATE TABLE IF NOT EXISTS pii_registry (
    user_ref_id        UUID            PRIMARY KEY,

    -- KEK pointer (logical reference, not FK — see header note)
    kek_id             UUID            NOT NULL,

    -- AES-256-GCM ciphertext envelope: header (version+nonce+aad) + payload + auth tag
    encrypted_blob     BYTEA           NOT NULL,
    blob_schema_ver    INT             NOT NULL,

    -- Bookkeeping
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    last_rotated_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- Erasure tombstone (GDPR Art. 17 audit trail — does NOT erase the blob;
    -- the actual unreadability comes from destroying the KEK in pii_kek)
    erased_at          TIMESTAMPTZ     NULL,
    erased_by_ticket   TEXT            NULL,

    CONSTRAINT pii_registry_blob_schema_ver_positive CHECK (blob_schema_ver >= 1),
    CONSTRAINT pii_registry_encrypted_blob_nonempty CHECK (length(encrypted_blob) >= 28),
    -- 28 = minimum AES-256-GCM envelope overhead (12 nonce + 16 tag). Real
    -- payload obviously larger; check defends against accidental empty insert.

    CONSTRAINT pii_registry_erasure_ticket_when_erased CHECK (
        (erased_at IS NULL AND erased_by_ticket IS NULL) OR
        (erased_at IS NOT NULL AND erased_by_ticket IS NOT NULL AND length(erased_by_ticket) > 0)
    )
);

-- Lookup index for "find the kek row for this user"
CREATE INDEX IF NOT EXISTS idx_pii_registry_kek_id
    ON pii_registry (kek_id);

-- Partial index for "all non-erased users" (admin export, billing, etc.)
CREATE INDEX IF NOT EXISTS idx_pii_registry_not_erased
    ON pii_registry (user_ref_id)
    WHERE erased_at IS NULL;

-- updated-at not needed; pii_registry tracks last_rotated_at explicitly
-- and erased_at as one-shot transition. KEK rotation = UPDATE kek_id +
-- last_rotated_at via MetaWrite().

COMMENT ON TABLE pii_registry IS
    'L1.A-2 — canonical user PII envelope. AES-256-GCM blob keyed by pii_kek.kek_id. Erasure via crypto-shred (destroy KEK).';
COMMENT ON COLUMN pii_registry.encrypted_blob IS
    'AES-256-GCM ciphertext. Format: header(version+nonce+aad) | payload | auth_tag. Decrypt path is in contracts/meta (OpenPII helper).';
COMMENT ON COLUMN pii_registry.kek_id IS
    'Pointer to current pii_kek row. Not FK — KEK rotation invariant maintained at application layer.';
COMMENT ON COLUMN pii_registry.erased_at IS
    'GDPR Art. 17 erasure audit tombstone. The actual unreadability is from destroying the linked pii_kek row.';
