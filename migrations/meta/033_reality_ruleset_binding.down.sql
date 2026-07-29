-- 033_reality_ruleset_binding.down.sql
DROP TRIGGER IF EXISTS reality_ruleset_binding_epoch_is_next_trg ON reality_ruleset_binding;
DROP TRIGGER IF EXISTS reality_ruleset_binding_append_only_trg ON reality_ruleset_binding;
DROP FUNCTION IF EXISTS reality_ruleset_binding_epoch_is_next();
DROP FUNCTION IF EXISTS reality_ruleset_binding_append_only();
DROP INDEX IF EXISTS idx_reality_ruleset_binding_digest;
DROP INDEX IF EXISTS idx_reality_ruleset_binding_current;
DROP TABLE IF EXISTS reality_ruleset_binding;
