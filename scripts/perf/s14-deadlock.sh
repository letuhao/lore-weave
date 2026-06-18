#!/usr/bin/env bash
# scripts/perf/s14-deadlock.sh
#
# S14 (D4) — Deadlock / lock-contention, LIVE. Validates the ORDERING PRINCIPLE I6
# relies on: consistent global lock order ⇒ no deadlock. (roleplay-service is
# `missing` — the shipped one-processor-per-session command processor does not exist
# yet — so this drives the principle directly against real Postgres, NOT the shipped
# processor.)
#
#   ordered  two txns lock A,B in the SAME order → 0 deadlocks, both commit
#   bite     OPPOSING order with a barrier (both hold their first lock, then grab the
#            second) → real PG deadlock (40P01) → proves ordering is what prevents it
#   smoke    ordered + bite
#
# Verdict: NOTRUN(2) setup / race missed; FAIL(1) ordered deadlocked; PASS(0).
# Dedicated throwaway PG; cleans up on exit.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
IMG="${S14_PG_IMAGE:-postgres:16}"
PGUSER="foundation"; PGPASS="foundation"; PGDB="foundation"
PG="s14dl-pg"; PORT="55591"
ROUNDS="${ROUNDS:-5}"
DSN="postgres://${PGUSER}:${PGPASS}@127.0.0.1:${PORT}/${PGDB}?sslmode=disable"

log()    { printf '[s14-deadlock] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; cleanup; exit 2; }
cleanup(){ docker rm -f "$PG" >/dev/null 2>&1 || true; }
trap cleanup EXIT

bin() { local c; for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
ensure_bin() {
  DP="$(bin services/meta-worker/dlprobe.exe services/meta-worker/dlprobe)" && return 0
  log "building deadlock-probe ..."
  go -C services/meta-worker build -o dlprobe.exe ./cmd/deadlock-probe || notrun "build failed"
  DP="services/meta-worker/dlprobe.exe"
}

start_pg() {
  docker info >/dev/null 2>&1 || notrun "docker not available"
  docker rm -f "$PG" >/dev/null 2>&1 || true
  docker run -d --name "$PG" -p "${PORT}:5432" \
    -e POSTGRES_USER="$PGUSER" -e POSTGRES_PASSWORD="$PGPASS" -e POSTGRES_DB="$PGDB" \
    "$IMG" >/dev/null || notrun "docker run failed"
  local i
  for i in $(seq 1 40); do
    docker exec "$PG" pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  notrun "$PG not ready"
}

cmd_ordered() { ensure_bin; "$DP" -dsn "$DSN" -mode ordered -rounds "$ROUNDS"; }
cmd_bite()    { ensure_bin; "$DP" -dsn "$DSN" -mode bite -rounds "$ROUNDS"; }

cmd_smoke() {
  ensure_bin; start_pg
  log "ordered: consistent lock order (the I6 principle) ..."
  cmd_ordered
  log "BITE: opposing lock order with hold-and-wait barrier ..."
  cmd_bite
  log "PASS(smoke): consistent order → 0 deadlocks; opposing order → real 40P01 — the I6 ordering principle prevents the deadlock"
}

main() {
  case "${1:-smoke}" in
    ordered) start_pg; cmd_ordered ;;
    bite)    start_pg; cmd_bite ;;
    smoke)   cmd_smoke ;;
    *) echo "usage: $0 {ordered|bite|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
