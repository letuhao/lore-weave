#!/usr/bin/env bash
# S11 — Antithesis init: create the meta + shard DBs, run migrations, emit the
# initial workload, and register each reality so the publisher service drains it.
# Runs once at composer startup, then exits 0. (TEMPLATE — wire to the real
# Antithesis composer host/creds as part of D-S11-ANTITHESIS-RUN.)
set -euo pipefail

PGHOST="${PGHOST:-postgres}"
PGUSER="${PGUSER:-foundation}"
export PGPASSWORD="${PGPASSWORD:-foundation}"
META_DB="wholestack_antithesis_meta"
SHARD_DB="wholestack_antithesis"
SEED="${WG_SEED:-7}"
PROFILE="${WG_PROFILE:-multi-reality}"
SHARD_DSN="postgres://${PGUSER}:${PGPASSWORD}@${PGHOST}:5432/${SHARD_DB}?sslmode=disable"

psql_db() { psql -v ON_ERROR_STOP=1 -h "$PGHOST" -U "$PGUSER" -d "$1" "${@:2}"; }

until pg_isready -h "$PGHOST" -U "$PGUSER" >/dev/null 2>&1; do sleep 1; done

psql_db foundation -c "DROP DATABASE IF EXISTS ${META_DB}"; psql_db foundation -c "CREATE DATABASE ${META_DB}"
for m in 001_reality_registry 003_publisher_heartbeats; do psql_db "$META_DB" -f "/migrations/meta/${m}.up.sql"; done
psql_db foundation -c "DROP DATABASE IF EXISTS ${SHARD_DB}"; psql_db foundation -c "CREATE DATABASE ${SHARD_DB}"
for m in 0001_initial 0002_events_table 0005_events_outbox_table; do psql_db "$SHARD_DB" -f "/migrations/per_reality/${m}.up.sql"; done
psql_db "$SHARD_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT"

/usr/local/bin/wg -seed "$SEED" -profile "$PROFILE" -emit -dsn "$SHARD_DSN"

for rid in $(psql_db "$SHARD_DB" -tAc "SELECT DISTINCT reality_id FROM events"); do
  psql_db "$META_DB" -c "INSERT INTO reality_registry
      (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort)
    VALUES ('${rid}','${PGHOST}','${SHARD_DB}','active','en',10,10,20,5)
    ON CONFLICT (reality_id) DO NOTHING"
done
echo "[init] migrated + seeded ${SHARD_DB} (seed=${SEED} profile=${PROFILE}); realities registered"
