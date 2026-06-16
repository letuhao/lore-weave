-- 019_user_daily_cost.down.sql
DROP INDEX IF EXISTS idx_user_daily_cost_pseudonymization_due;
DROP INDEX IF EXISTS idx_user_daily_cost_date_capped;
DROP TABLE IF EXISTS user_daily_cost;
