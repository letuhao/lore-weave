#!/usr/bin/env bash
# infra/foundation-dev/pgvector-init.sh
#
# Cycle 16 (L3.I) — pgvector extension bootstrap for the foundation-dev
# Postgres container. Runs ONCE during first container boot (when
# /var/lib/postgresql/data is empty), via the `/docker-entrypoint-initdb.d/`
# hook provided by the official Postgres + pgvector images.
#
# What this does:
#   1. CREATE EXTENSION IF NOT EXISTS vector  — in the `foundation`
#      bootstrap database, so any per-reality DB cloned from `template1`
#      inherits it.
#   2. CREATE EXTENSION ... in `template1`  — every new database created
#      via `CREATE DATABASE` after this point will have the extension
#      preinstalled. Per-reality migrations (0008_pgvector_setup.up.sql)
#      still run `CREATE EXTENSION IF NOT EXISTS` defensively so the
#      schema is self-describing.
#
# Locked decisions consumed:
#   - Q-L3-1 (OPEN_QUESTIONS_LOCKED §5 line 73): embedding worker in
#     world-service async queue V1. THIS script provisions the database
#     side; the queue lives in services/world-service/src/embedding_queue/.
#   - Q-L3I-1 (line 77): dim=1536 hard-coded V1. The extension supports
#     arbitrary dimensions; the dim cap is enforced at the column level
#     in cycle-13 0006_projections.up.sql + cycle-16 0008_pgvector_setup.
#
# This script is idempotent — IF NOT EXISTS makes re-runs safe — but
# `/docker-entrypoint-initdb.d/` only fires once per data-volume lifetime,
# so we don't actually depend on idempotency at container level.

set -euo pipefail

echo "[pgvector-init] cycle 16 L3.I — installing pgvector in foundation + template1"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "foundation" <<-'EOSQL'
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "template1" <<-'EOSQL'
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

echo "[pgvector-init] done — vector extension present in foundation + template1"
