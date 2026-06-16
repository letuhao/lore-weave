#!/usr/bin/env bash
# scripts/perf/w1-capacity.sh
#
# W1.1 (production wiring) — capacity routing glue, LIVE against real Postgres.
#
# Wires CapacityPlanner to a live snapshot (shard_utilization caps × a fresh
# reality_registry count) and serializes the count→register critical section
# with a per-shard advisory lock, closing the provision-time TOCTOU
# (D-S13-CAPACITY-ROUTING-GLUE). This drill proves the enforcement is
# non-vacuous via the lock-on / lock-off contrast:
#
#   concurrent  K parallel placements onto an M<K-slot shard, lock ON
#               → EXACTLY M succeed, final reality_registry count == M.
#   bite        the SAME race, lock OFF → over-subscription (final count > M).
#               Proves the lock+recount is the enforcer.
#
# Verdict: NOTRUN(2) setup/race-missed; FAIL(1) over-subscription leaked with the
# lock on, or a vacuous bite; PASS(0) clean. Reuses the S12 scale rig's meta-pg.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
META_C="scale-meta-pg"
META_DB="w1_capacity"
META_HOSTPORT="127.0.0.1:55510"
DSN="postgres://${PG_USER}:${PG_PASS}@${META_HOSTPORT}/${META_DB}?sslmode=disable"

log()    { printf '[w1-capacity] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

require() {
  docker inspect -f '{{.State.Running}}' "$META_C" 2>/dev/null | grep -q true \
    || notrun "$META_C not running (infra/scale/scale-rig.sh up)"
}

psql_adm() { docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }

# Fresh w1_capacity with exactly the two tables the glue reads:
# reality_registry (001) + shard_utilization (024).
migrate_meta() {
  psql_adm -c "DROP DATABASE IF EXISTS ${META_DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${META_DB}" >/dev/null
  local m
  for m in 001_reality_registry 024_shard_utilization; do
    docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" \
      < "migrations/meta/${m}.up.sql" || notrun "meta migration ${m} failed"
  done
  log "w1_capacity migrated (reality_registry + shard_utilization)"
}

ensure_bin() {
  BIN="services/world-service/../../target/debug/capacity-place.exe"
  [ -x "$BIN" ] || BIN="target/debug/capacity-place.exe"
  [ -x "$BIN" ] || BIN="target/debug/capacity-place"
  if [ ! -x "$BIN" ]; then
    log "building capacity-place ..."
    cargo build -p world-service --bin capacity-place || notrun "cargo build failed"
    BIN="target/debug/capacity-place.exe"
    [ -x "$BIN" ] || BIN="target/debug/capacity-place"
  fi
  [ -x "$BIN" ] || notrun "capacity-place binary not found after build"
}

main() {
  local sub="${1:-smoke}"
  require
  ensure_bin
  case "$sub" in
    snapshot|concurrent|bite|smoke)
      migrate_meta
      "$BIN" -dsn "$DSN" -mode "$sub"
      ;;
    *) echo "usage: $0 {snapshot|concurrent|bite|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
