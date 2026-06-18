-- 028_pii_kek_single_active.down.sql
-- Rollback: drop the UNIQUE single-active-KEK index AND recreate migration 010's
-- plain partial index that 028 up dropped.
DROP INDEX IF EXISTS uq_pii_kek_user_active;
CREATE INDEX IF NOT EXISTS idx_pii_kek_user_active_partial
    ON pii_kek (user_ref_id)
    WHERE destroyed_at IS NULL;
