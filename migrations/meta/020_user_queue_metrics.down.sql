-- 020_user_queue_metrics.down.sql
DROP INDEX IF EXISTS idx_user_queue_metrics_abandoned_at;
DROP TABLE IF EXISTS user_queue_metrics;
