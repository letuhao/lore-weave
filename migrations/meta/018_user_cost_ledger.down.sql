-- 018_user_cost_ledger.down.sql
DROP INDEX IF EXISTS idx_user_cost_ledger_corrections;
DROP INDEX IF EXISTS idx_user_cost_ledger_pseudonymization_due;
DROP INDEX IF EXISTS idx_user_cost_ledger_session_created;
DROP INDEX IF EXISTS idx_user_cost_ledger_reality_created;
DROP INDEX IF EXISTS idx_user_cost_ledger_user_created;
DROP TABLE IF EXISTS user_cost_ledger;
