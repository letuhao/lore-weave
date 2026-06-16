-- 024_shard_utilization.down.sql
DROP INDEX IF EXISTS idx_shard_utilization_at;
DROP INDEX IF EXISTS idx_shard_utilization_host_at;
DROP TABLE IF EXISTS shard_utilization;
