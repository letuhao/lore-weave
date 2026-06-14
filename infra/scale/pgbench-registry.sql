-- infra/scale/pgbench-registry.sql
--
-- S12 (Inc-2) — load on the SHARED reality_registry (meta DB). Every provision
-- and every publisher/meta-worker startup routes through this one table, so it is
-- a shared read/write path the whole platform contends on.
--
-- Each iteration mixes the two hot shapes:
--   1. ROUTE read  — an indexed lookup of the shards a cohort of realities live on
--      (db_host is indexed); this is the shape route/resolve does.
--   2. PROVISION write — bump updated_at for a random deploy cohort (the shape a
--      status transition / re-provision writes).
-- Drive with: pgbench -n -f pgbench-registry.sql -c <N> -T <secs> ... scale_meta

\set shard random(0, 7)
\set cohort random(0, 99)

SELECT count(*) FROM reality_registry
 WHERE db_host = ('pg-shard-' || :shard || '.internal') AND status = 'active';

UPDATE reality_registry SET updated_at = now()
 WHERE deploy_cohort = :cohort;
