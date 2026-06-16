-- contracts/migrations/per_reality/0013_events_content_sha256.down.sql
--
-- Reverses 0013: drops the stored content-checksum column. Metadata-only on the
-- partitioned table; IF EXISTS for idempotent re-apply.

BEGIN;

ALTER TABLE events DROP COLUMN IF EXISTS content_sha256;

COMMIT;
