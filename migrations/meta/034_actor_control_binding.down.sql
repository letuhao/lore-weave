-- 034_actor_control_binding.down.sql
-- WARNING: drops the user->actor control binding. Only legitimate in dev
-- teardown: without it, no authenticated session can be resolved to a subject,
-- and the GDPR erasure cascade loses its list of realities to visit.
DROP TABLE IF EXISTS actor_control_binding CASCADE;
