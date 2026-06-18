#!/usr/bin/env bash
# scripts/perf/w1-closure.sh
#
# W1.3 (production wiring) — closure-drain orchestrator, LIVE against real Postgres.
#
# On active→pending_close the reality is frozen for appends (W1.4); the
# orchestrator then drains the reality's events_outbox to the publisher
# high-water (unpublished=0) before allowing →frozen. A drain timeout aborts
# (pending_close→active) instead of forcing →frozen. Closes D-S13-CLOSURE-DRAIN.
#
#   drain    publisher catches up → →frozen only after backlog hits 0.
#   timeout  no publisher → abort to active, events preserved (not stranded).
#   bite     naive close (no drain gate) → frozen WITH undrained outbox =
#            stranded events → proves the gate is non-vacuous.
#
# Verdict: NOTRUN(2) setup; FAIL(1) freeze-with-undrained / vacuous bite; PASS(0).
# Reuses the S12 scale rig (meta-pg + pg-shard-0). Re-runnable.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
META_C="scale-meta-pg"
SHARD_C="scale-pg-shard-0"
META_DB="w1_closure"
REALITY_DB="w1c_reality"
META_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55510/${META_DB}?sslmode=disable"
REALITY_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/${REALITY_DB}?sslmode=disable"

log()    { printf '[w1-closure] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }

require() {
  docker inspect -f '{{.State.Running}}' "$META_C" 2>/dev/null | grep -q true || notrun "$META_C not running"
  docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true || notrun "$SHARD_C not running"
}

setup() {
  docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation \
    -c "DROP DATABASE IF EXISTS ${META_DB} WITH (FORCE)" >/dev/null
  docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation \
    -c "CREATE DATABASE ${META_DB}" >/dev/null
  local m
  for m in 001_reality_registry 004_lifecycle_transition_audit 013_meta_write_audit \
           027_meta_write_audit_scrub_version; do
    docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" \
      < "migrations/meta/${m}.up.sql" || notrun "meta migration ${m} failed"
  done
  # Per-reality DB with the production events_outbox table (0005).
  docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation \
    -c "DROP DATABASE IF EXISTS ${REALITY_DB} WITH (FORCE)" >/dev/null
  docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation \
    -c "CREATE DATABASE ${REALITY_DB}" >/dev/null
  docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$REALITY_DB" \
    < "contracts/migrations/per_reality/0005_events_outbox_table.up.sql" || notrun "outbox migration failed"
  log "w1_closure (meta) + w1c_reality (events_outbox) ready"
}

build_bin() {
  log "building closure-drill ..."
  go -C services/meta-worker build -o closure-drill.exe ./cmd/closure-drill || notrun "build failed"
  BIN="services/meta-worker/closure-drill.exe"
}

main() {
  local sub="${1:-smoke}"
  require
  setup
  build_bin
  "$BIN" -mode "$sub" -meta-dsn "$META_DSN" -reality-dsn "$REALITY_DSN"
}
main "$@"
