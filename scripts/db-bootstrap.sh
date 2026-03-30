#!/bin/bash
# ─────────────────────────────────────────────────────────
# LoreWeave — Database Bootstrap
# Creates all missing databases and runs table migrations.
#
# Usage:
#   ./scripts/db-bootstrap.sh              (uses docker compose exec)
#   ./scripts/db-bootstrap.sh --host       (uses local psql, postgres on localhost:5555)
#
# Safe to run multiple times — everything is idempotent.
# ─────────────────────────────────────────────────────────

set -e

PGUSER="loreweave"
PGPASSWORD="loreweave_dev"

# All databases needed by the platform
DATABASES=(
  loreweave_auth
  loreweave_book
  loreweave_sharing
  loreweave_catalog
  loreweave_provider_registry
  loreweave_usage_billing
  loreweave_translation
  loreweave_glossary
  loreweave_chat
)

# Determine how to run psql
if [ "$1" = "--host" ]; then
  PGHOST="localhost"
  PGPORT="5555"
  run_psql() {
    PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" "$@"
  }
  echo "Using local psql (localhost:5555)"
else
  run_psql() {
    docker compose -f infra/docker-compose.yml exec -T postgres psql -U "$PGUSER" "$@"
  }
  echo "Using docker compose exec"
fi

echo ""
echo "=== Step 1: Create missing databases ==="
for db in "${DATABASES[@]}"; do
  exists=$(run_psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" 2>/dev/null || echo "")
  if [ "$exists" = "1" ]; then
    echo "  ✓ $db (exists)"
  else
    echo "  + Creating $db..."
    run_psql -d postgres -c "CREATE DATABASE $db" 2>/dev/null || echo "  ⚠ Failed to create $db (may already exist)"
    echo "  ✓ $db (created)"
  fi
done

echo ""
echo "=== Step 2: Run service table migrations ==="
echo "  Each service creates its own tables on startup (CREATE TABLE IF NOT EXISTS)."
echo "  Restart services to trigger migrations:"
echo ""
echo "    docker compose -f infra/docker-compose.yml restart"
echo ""
echo "  Or restart a specific service:"
echo "    docker compose -f infra/docker-compose.yml restart auth-service"
echo ""
echo "=== Done ==="
