-- 022_feature_flags.down.sql
DROP INDEX IF EXISTS idx_feature_flags_default_enabled;
DROP INDEX IF EXISTS idx_feature_flags_expiring;
DROP INDEX IF EXISTS idx_feature_flags_owner;
DROP TABLE IF EXISTS feature_flags;
