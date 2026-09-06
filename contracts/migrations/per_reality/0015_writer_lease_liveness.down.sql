BEGIN;

DROP INDEX IF EXISTS channel_writer_state_expiry_idx;
ALTER TABLE channel_writer_state
    DROP COLUMN IF EXISTS lease_expires_at,
    DROP COLUMN IF EXISTS holder_id;

COMMIT;
