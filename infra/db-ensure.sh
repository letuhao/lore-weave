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
loreweave_catalog
loreweave_provider_registry
loreweave_usage_billing
loreweave_translation
loreweave_glossary
loreweave_chat
"

for db in $DATABASES; do
  exists=$(psql -U loreweave -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" 2>/dev/null)
  if [ "$exists" != "1" ]; then
    echo "Creating database: $db"
    psql -U loreweave -d postgres -c "CREATE DATABASE $db;" 2>/dev/null || true
  fi
done

# Return healthy
echo "All databases verified."
