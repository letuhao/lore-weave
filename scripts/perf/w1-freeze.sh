#!/usr/bin/env bash
# scripts/perf/w1-freeze.sh
#
# W1.4 (production wiring) — kernel write-freeze guard, LIVE against real Postgres.
#
# dp_kernel::PgEventStore + MetaFreezeGuard reject event appends to a reality
# whose authoritative (uncached) reality_registry.status is frozen
# (migrating / pending_close / frozen / archived…). Closes D-S13-RELOCATE-FREEZE
# and hardens the Inc-4 relocation + W1.3 closure-drain quiescence assumption.
#
#   guarded  active append OK; migrating/pending_close/frozen → REJECTED; the
#            frozen appends never land (only the 2 active-state appends do).
#   bite     same flip with NO guard → the append LANDS (would be lost on flip)
#            → proves the guard is the enforcer.
#
# Verdict: NOTRUN(2) setup; FAIL(1) a frozen append leaking / vacuous bite;
# PASS(0). Reuses the S12 scale rig (meta-pg + pg-shard-0). Re-runnable.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
META_C="scale-meta-pg"
SHARD_C="scale-pg-shard-0"
META_DB="w1_freeze"
REALITY_DB="w1f_reality"
META_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55510/${META_DB}?sslmode=disable"
REALITY_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/${REALITY_DB}?sslmode=disable"

log()    { printf '[w1-freeze] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }

require() {
  docker inspect -f '{{.State.Running}}' "$META_C" 2>/dev/null | grep -q true || notrun "$META_C not running"
  docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true || notrun "$SHARD_C not running"
}

setup() {
  # Meta DB with reality_registry (001).
  docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation \
    -c "DROP DATABASE IF EXISTS ${META_DB} WITH (FORCE)" >/dev/null
  docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation \
    -c "CREATE DATABASE ${META_DB}" >/dev/null
  docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" \
    < "migrations/meta/001_reality_registry.up.sql" || notrun "meta migration failed"
  # Per-reality DB (the drill creates the minimal events table itself).
  docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation \
    -c "DROP DATABASE IF EXISTS ${REALITY_DB} WITH (FORCE)" >/dev/null
  docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation \
    -c "CREATE DATABASE ${REALITY_DB}" >/dev/null
  log "w1_freeze (meta + reality_registry) + w1f_reality (per-reality DB) ready"
}

build_bin() {
  log "building freeze-drill ..."
  cargo build -p world-service --bin freeze-drill || notrun "cargo build failed"
  BIN="target/debug/freeze-drill.exe"
  [ -x "$BIN" ] || BIN="target/debug/freeze-drill"
  [ -x "$BIN" ] || notrun "freeze-drill binary not found"
}

main() {
  local sub="${1:-smoke}"
  require
  setup
  build_bin
  FREEZE_META_DSN="$META_DSN" FREEZE_REALITY_DSN="$REALITY_DSN" "$BIN" "$sub"
}
main "$@"
