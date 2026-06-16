-- 025_scaling_events.down.sql
DROP INDEX IF EXISTS idx_scaling_events_active_overrides;
DROP INDEX IF EXISTS idx_scaling_events_shard_created;
DROP INDEX IF EXISTS idx_scaling_events_type_created;
DROP INDEX IF EXISTS idx_scaling_events_created;
DROP TABLE IF EXISTS scaling_events;
