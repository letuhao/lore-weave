#!/bin/bash
# ─────────────────────────────────────────────────────────
# LoreWeave — Ensure all databases exist
# Runs inside the postgres container.
# Called by docker-compose healthcheck or manually.
#
# This is idempotent — safe to run every time postgres starts.
# ─────────────────────────────────────────────────────────

set -e

DATABASES="
loreweave_auth
loreweave_book
loreweave_sharing
loreweave_scheduler
loreweave_catalog
loreweave_provider_registry
loreweave_usage_billing
loreweave_translation
loreweave_glossary
loreweave_chat
loreweave_events
loreweave_statistics
loreweave_notification
loreweave_knowledge
loreweave_lore_enrichment
loreweave_learning
loreweave_composition
loreweave_campaign
loreweave_video_gen
loreweave_jobs
loreweave_roleplay
loreweave_agent_registry
loreweave_meta
"

for db in $DATABASES; do
  exists=$(psql -U loreweave -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" 2>/dev/null)
  if [ "$exists" != "1" ]; then
    echo "Creating database: $db"
    psql -U loreweave -d postgres -c "CREATE DATABASE $db;" 2>/dev/null || true
  fi
done

# ── SHARD REGISTRATION ────────────────────────────────────────────────────
# `shard_utilization` is not a metrics table -- it is where a shard DECLARES that
# it exists and what its capacity is. `capacity_glue` says so explicitly: the
# shard list and `capacity_max_dbs` come from here (cold config), while live
# occupancy comes from a fresh COUNT(*) over `reality_registry`, deliberately NOT
# from `current_db_count` (the metrics job that would refresh it is unbuilt, and
# trusting a stale zero would over-subscribe).
#
# So registering the dev cluster as a shard is CONFIGURATION, and it is
# per-environment: this box is `pg-shard-0.internal` (a compose network alias, so
# the name genuinely resolves and `reality_registry.db_host` stays a real host).
#
# Without this row `capacity_planner::pick_shard` has nothing to pick and every
# provisioning attempt is refused -- which is why zero realities have ever
# existed here.
SHARD_HOST="pg-shard-0.internal"
SHARD_MAX_DBS=50          # realities this dev box will host; raise deliberately
SHARD_MAX_BYTES=53687091200   # 50 GiB

meta_exists=$(psql -U loreweave -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='loreweave_meta'" 2>/dev/null)
if [ "$meta_exists" = "1" ]; then
  has_table=$(psql -U loreweave -d loreweave_meta -tAc "SELECT to_regclass('public.shard_utilization') IS NOT NULL" 2>/dev/null)
  if [ "$has_table" = "t" ]; then
    registered=$(psql -U loreweave -d loreweave_meta -tAc "SELECT 1 FROM shard_utilization WHERE shard_host='$SHARD_HOST' LIMIT 1" 2>/dev/null)
    if [ "$registered" != "1" ]; then
      echo "Registering shard: $SHARD_HOST (max_dbs=$SHARD_MAX_DBS)"
      psql -U loreweave -d loreweave_meta -c         "INSERT INTO shard_utilization
           (snapshot_id, shard_host, current_db_count, total_storage_bytes,
            cpu_load_pct, connection_count, capacity_max_dbs, capacity_max_bytes)
         VALUES (gen_random_uuid(), '$SHARD_HOST', 0, 0, 0, 0, $SHARD_MAX_DBS, $SHARD_MAX_BYTES);"         2>/dev/null || true
    fi
  fi
fi

# ── PROVISIONING ROLE (W7) ────────────────────────────────────────────────
# Reality creation ran as `loreweave`, which is `rolsuper` + `rolbypassrls`.
# That is the most privileged credential in the platform being used for its
# most routine automated write, and superuser is exactly the thing RLS, table
# ownership and per-database GRANTs cannot restrain: a bug in the provisioner
# had the whole cluster in reach, including every other tenant's database.
#
# What provisioning ACTUALLY needs is one attribute: CREATEDB. The role that
# creates a database owns it, so it can REVOKE CONNECT on it (I4 isolation) and
# create tables in it (the migrations) without any further grant.
#
# NOT a per-user role. Postgres roles are SYSTEM roles -- users never hold one
# (RUN-STATE `1b7db-03`). This is one service credential for the provisioner,
# the same for every tenant; user-level tenancy is `reality_registry.owner_*`
# (W6) and is enforced in the application, not by the database's login.
PROVISIONER_ROLE="loreweave_provisioner"
PROVISIONER_PASSWORD="${LOREWEAVE_PROVISIONER_PASSWORD:-loreweave_dev}"

role_exists=$(psql -U loreweave -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$PROVISIONER_ROLE'" 2>/dev/null)
if [ "$role_exists" != "1" ]; then
  echo "Creating provisioning role: $PROVISIONER_ROLE (CREATEDB, NOSUPERUSER)"
  psql -U loreweave -d postgres -c \
    "CREATE ROLE $PROVISIONER_ROLE LOGIN PASSWORD '$PROVISIONER_PASSWORD' \
     CREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;" 2>/dev/null || true
fi
# Re-assert the attributes every start: a role that drifted to SUPERUSER by hand
# would otherwise keep the name and lose the point.
psql -U loreweave -d postgres -c \
  "ALTER ROLE $PROVISIONER_ROLE CREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;" \
  2>/dev/null || true

# `vector` into template1 (W7). Migration 0008 runs `CREATE EXTENSION IF NOT
# EXISTS vector`, and pgvector's control file does NOT declare `trusted`, so
# installing it requires SUPERUSER -- which would force provisioning to stay
# superuser for one line of one migration. Every CREATE DATABASE copies
# template1, so installing it there once makes 0008 a no-op that any role can
# run. Preferred over marking the extension trusted: this changes only THIS
# cluster's template, not the privilege rules of an extension.
psql -U loreweave -d template1 -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || true

# The provisioner also READS meta -- live capacity (`shard_utilization` +
# `reality_registry`) and, since the retry fix, the existing registration for
# the reality it is about to place. Grant exactly those two tables, SELECT only.
# It must never WRITE reality_registry: that is invariant I8 (every write goes
# through Go MetaWrite so the meta_write_audit row lands in the same TX), and
# the absence of INSERT/UPDATE here is what makes the bridge the only door.
if [ "$meta_exists" = "1" ]; then
  psql -U loreweave -d postgres -c \
    "GRANT CONNECT ON DATABASE loreweave_meta TO $PROVISIONER_ROLE;" 2>/dev/null || true
  psql -U loreweave -d loreweave_meta -c \
    "GRANT USAGE ON SCHEMA public TO $PROVISIONER_ROLE;" 2>/dev/null || true
  psql -U loreweave -d loreweave_meta -c \
    "GRANT SELECT ON shard_utilization, reality_registry TO $PROVISIONER_ROLE;" 2>/dev/null || true
fi

# Return healthy
echo "All databases verified."
