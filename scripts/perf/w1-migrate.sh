#!/usr/bin/env bash
# scripts/perf/w1-migrate.sh
#
# W1.2 (production wiring) — migrate CLI live-wiring, LIVE against real Postgres.
#
# Binds the `migrate` CLI's dispatch to real collaborators (pkg/live):
#   - pgx SQLApplier      — runs the migration UP SQL on each per-reality DB,
#                           resolving the DSN from reality_registry.
#   - MetaCollaborator    — runner Auditor + StateWriter + canary AbortAuditor,
#                           writing reality_migration_audit + instance_schema_
#                           migrations through contracts/meta MetaWrite (I8).
#   - canary / runner     — breaking → canary gate; non-breaking → runner.
# Closes D-MIGRATE-CLI-LIVE-WIRING.
#
# The migrate-drill exercises the SAME live.RunMigration the CLI calls and
# asserts on the real meta tables:
#   apply  good non-breaking migration → fleet applied + I8 audit present
#   abort  broken breaking migration → canary fails → fan-out NEVER attempted
#   bite   buggy ignore-canary flow fans out anyway → abort guard non-vacuous
# Then a REAL-CLI smoke runs `migrate 0001_initial` (the skeleton) end-to-end.
#
# Verdict: NOTRUN(2) setup; FAIL(1) a guard not holding / vacuous bite; PASS(0).
# Reuses the S12 scale rig (meta-pg + pg-shard-0). Re-runnable (fresh each run).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
META_C="scale-meta-pg"
META_DB="w1_migrate"
META_HOSTPORT="127.0.0.1:55510"
SHARD_HOSTPORT="127.0.0.1:55511"
META_DSN="postgres://${PG_USER}:${PG_PASS}@${META_HOSTPORT}/${META_DB}?sslmode=disable"
SHARD_ADMIN_DSN="postgres://${PG_USER}:${PG_PASS}@${SHARD_HOSTPORT}/foundation?sslmode=disable"

log()    { printf '[w1-migrate] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

require() {
  docker inspect -f '{{.State.Running}}' "$META_C" 2>/dev/null | grep -q true \
    || notrun "$META_C not running (infra/scale/scale-rig.sh up)"
}

psql_adm() { docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }

# Fresh w1_migrate with the tables the live wiring touches:
# reality_registry (001), instance_schema_migrations (002), reality_migration_audit
# (007), meta_write_audit (013) + scrub_version (027).
migrate_meta() {
  psql_adm -c "DROP DATABASE IF EXISTS ${META_DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${META_DB}" >/dev/null
  local m
  for m in 001_reality_registry 002_instance_schema_migrations 007_reality_migration_audit \
           013_meta_write_audit 027_meta_write_audit_scrub_version; do
    docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" \
      < "migrations/meta/${m}.up.sql" || notrun "meta migration ${m} failed"
  done
  log "w1_migrate migrated (registry + instance_schema_migrations + audit tables)"
}

build_bin() {
  log "building migrate + migrate-drill ..."
  go -C services/migration-orchestrator build -o migrate.exe ./cmd/migrate || notrun "build migrate failed"
  go -C services/migration-orchestrator build -o migrate-drill.exe ./cmd/migrate-drill || notrun "build migrate-drill failed"
  DRILL="services/migration-orchestrator/migrate-drill.exe"
  MIGRATE="services/migration-orchestrator/migrate.exe"
}

# Real-CLI smoke: apply the per-reality skeleton (0001_initial, non-breaking)
# through the actual `migrate` binary against the fleet the drill left seeded.
cli_smoke() {
  log "real-CLI smoke: migrate 0001_initial through the binary"
  "$MIGRATE" 0001_initial \
    --meta-dsn "$META_DSN" \
    --sql-dir contracts/migrations/per_reality \
    --host-override "*=${SHARD_HOSTPORT}" \
    --ssl disable \
    || fail "real-CLI migrate 0001_initial failed"
  log "PASS(cli-smoke): migrate 0001_initial applied through the real CLI"
}

main() {
  local sub="${1:-smoke}"
  require
  migrate_meta
  build_bin
  case "$sub" in
    apply|abort|bite)
      "$DRILL" -mode "$sub" -meta-dsn "$META_DSN" -shard-admin-dsn "$SHARD_ADMIN_DSN" -shard-hostport "$SHARD_HOSTPORT"
      ;;
    smoke)
      "$DRILL" -mode smoke -meta-dsn "$META_DSN" -shard-admin-dsn "$SHARD_ADMIN_DSN" -shard-hostport "$SHARD_HOSTPORT"
      cli_smoke
      ;;
    *) echo "usage: $0 {apply|abort|bite|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
