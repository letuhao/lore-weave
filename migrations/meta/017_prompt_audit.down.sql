-- 017_prompt_audit.down.sql — reverses 017_prompt_audit.up.sql

DROP INDEX IF EXISTS idx_prompt_audit_context_hash;
DROP INDEX IF EXISTS idx_prompt_audit_template_created;
DROP INDEX IF EXISTS idx_prompt_audit_reality_created;
DROP INDEX IF EXISTS idx_prompt_audit_user_created;

DROP TABLE IF EXISTS prompt_audit;
