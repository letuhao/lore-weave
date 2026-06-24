-- 011_user_consent_ledger.down.sql
-- WARNING: drops consent ledger. Only legitimate in dev teardown.
-- Production has 2y+account-lifetime retention; rows are NEVER deleted in prod.
DROP TABLE IF EXISTS user_consent_ledger CASCADE;
