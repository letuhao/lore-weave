-- 028_pii_kek_single_active.up.sql
--
-- PII/retention classification (S08 §12X.3/§12X.4; pii-classify-lint). ALTER
-- (UNIQUE partial index) on the existing pii_kek table — the per-user KEK
-- envelope whose destruction IS the GDPR Art.17 crypto-shred (Slice B).
-- @pii_sensitivity: sensitive (the KEK is the key material gating the user's PII)
-- @retention_class: pii_envelope  -- NOTE: §12X.4 matrix has no PII-envelope row yet (pii_registry/pii_kek); flag → DEFERRED-111 to add it
-- @retention_hot: until_erasure (KEK retained while the user's PII exists; destroyed on Art.17 erasure)
-- @erasure_method: crypto_shred
-- @legal_basis: contract
--
-- 076 Slice B (code-review BLOCK) — enforce AT MOST ONE active (non-destroyed)
-- KEK per user, structurally.
--
-- DestroyKEK's erasure guarantee ("set destroyed_at ⇒ OpenPII refuses to
-- decrypt") is only TOTAL if each user has a single active KEK. Migration 010's
-- idx_pii_kek_user_active_partial was a PLAIN index (writer-side comments asked
-- for the invariant but nothing enforced it), so a double-provision or a
-- rotation that inserted the new KEK before destroying the old could leave two
-- active rows — and erasing one would leave PII readable via the other.
--
-- This UNIQUE partial index makes ≥2-active impossible. (DestroyKEK is ALSO
-- now set-based as defense-in-depth.) Greenfield: no existing data to violate
-- it. Rotation (Slice C) must mark the old KEK destroyed in the SAME tx that
-- inserts the new one to respect this.

CREATE UNIQUE INDEX IF NOT EXISTS uq_pii_kek_user_active
    ON pii_kek (user_ref_id)
    WHERE destroyed_at IS NULL;

-- 010's plain idx_pii_kek_user_active_partial covered the identical predicate;
-- the UNIQUE index subsumes it for both uniqueness AND the "current KEK" lookup.
-- Drop the redundant plain index (avoids double write-amplification + the trap
-- where rolling back 028 silently removes the uniqueness guard while a lookalike
-- plain index lingers). The 028 down migration recreates the plain index.
DROP INDEX IF EXISTS idx_pii_kek_user_active_partial;

COMMENT ON INDEX uq_pii_kek_user_active IS
    '076 Slice B — at most one active KEK per user; makes crypto-shred erasure provably total.';
