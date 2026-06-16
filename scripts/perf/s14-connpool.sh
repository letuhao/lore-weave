#!/usr/bin/env bash
# scripts/perf/s14-connpool.sh
#
# S14 (D3) — Connection-pool exhaustion at large N, LIVE.
#
# S12 hit the max_connections wall. This drill proves a BOUNDED pgxpool keeps a large
# caller fan-out SAFE (callers queue on the pool, all complete, the server is never
# exhausted, the pool drains after = recovery), while the BITE — unbounded raw
# connections, no pool — blows past the server cap and is rejected with FATAL 53300.
#
# Dedicated throwaway PG with a LOW max_connections (the cap needs a restart — must not
# disturb the shared rig).
#
#   pooled  N workers >> cap through a MaxConns-bounded pool → all complete, recovers
#   bite    N raw connections held at once → server rejects the overflow (53300)
#   smoke   pooled + bite
#
# Verdict: NOTRUN(2) setup / never exhausted; FAIL(1) pool didn't absorb / no recovery;
# PASS(0). Self-contained; cleans up on exit.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
IMG="${S14_PG_IMAGE:-postgres:16}"
PGUSER="foundation"; PGPASS="foundation"; PGDB="foundation"
PG="s14c-pg"; PORT="55590"
MAXCONN_SERVER="${MAXCONN_SERVER:-20}"   # server cap (low → reachable)
WORKERS="${WORKERS:-50}"                 # >> server cap
POOL="${POOL:-10}"                       # bounded pool size (< usable server conns)
OPS="${OPS:-20}"
DSN="postgres://${PGUSER}:${PGPASS}@127.0.0.1:${PORT}/${PGDB}?sslmode=disable"

log()    { printf '[s14-connpool] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; cleanup; exit 2; }
cleanup(){ docker rm -f "$PG" >/dev/null 2>&1 || true; }
trap cleanup EXIT

bin() { local c; for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
ensure_bin() {
  CP="$(bin services/meta-worker/connpool.exe services/meta-worker/connpool)" && return 0
  log "building connpool-stress ..."
  go -C services/meta-worker build -o connpool.exe ./cmd/connpool-stress || notrun "build failed"
  CP="services/meta-worker/connpool.exe"
}

start_pg() {
  docker info >/dev/null 2>&1 || notrun "docker not available"
  docker rm -f "$PG" >/dev/null 2>&1 || true
  docker run -d --name "$PG" -p "${PORT}:5432" \
    -e POSTGRES_USER="$PGUSER" -e POSTGRES_PASSWORD="$PGPASS" -e POSTGRES_DB="$PGDB" \
    "$IMG" -c max_connections="$MAXCONN_SERVER" >/dev/null || notrun "docker run failed"
  local i
  for i in $(seq 1 40); do
    docker exec "$PG" pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  notrun "$PG not ready"
}

cmd_pooled() { ensure_bin; "$CP" -dsn "$DSN" -mode pooled -workers "$WORKERS" -maxconns "$POOL" -ops "$OPS"; }
cmd_bite()   { ensure_bin; "$CP" -dsn "$DSN" -mode unbounded -workers "$WORKERS"; }

cmd_smoke() {
  ensure_bin; start_pg
  log "server max_connections=${MAXCONN_SERVER}; ${WORKERS} workers"
  log "pooled: ${WORKERS} workers >> server cap, through a ${POOL}-conn bounded pool ..."
  cmd_pooled
  log "BITE: ${WORKERS} raw connections held at once (no pool) ..."
  cmd_bite
  log "PASS(smoke): bounded pool absorbed the fan-out + recovered; unbounded raw conns exhausted the server (53300) — the pool is what prevents exhaustion"
}

main() {
  case "${1:-smoke}" in
    pooled) start_pg; cmd_pooled ;;
    bite)   start_pg; cmd_bite ;;
    smoke)  cmd_smoke ;;
    *) echo "usage: $0 {pooled|bite|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
