-- 0014 down — remove channel ordering surfaces (S3a).
BEGIN;

DROP INDEX IF EXISTS events_channel_order_idx;
DROP TABLE IF EXISTS channel_event_index;
DROP TABLE IF EXISTS channel_writer_state;
ALTER TABLE events
    DROP COLUMN IF EXISTS causal_refs,
    DROP COLUMN IF EXISTS writer_epoch,
    DROP COLUMN IF EXISTS channel_event_id,
    DROP COLUMN IF EXISTS channel_id;

COMMIT;
