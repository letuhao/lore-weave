#!/usr/bin/env bash
# scripts/perf/roleplay-load.sh
#
# S12 (Inc-3) — drives the I6 LOAD-SKELETON (tests/perf/roleplay-load) against the
# scale rig's isolated shard. This validates the I6 *concurrency assumption* (one
# command processor per session ⇒ serial FIFO), NOT a scaling ceiling: a session
# is ~10 participants @ ~10 T2/T3 writes/s, so per-session is bounded SMALL — the
# question is correctness + data-plane ack latency, not throughput.
#
#   run [sessions] [events]  many small sessions + a hot reality (≈50 on one shard)
#                            → assert every session is serial-FIFO + p99 ack vs DP-T3
#   bite [sessions] [events] give ONE session two processors → the sequence MUST fork
#   smoke                    run + bite
#
# Verdict: NOTRUN(2) setup; FAIL(1) a real serial-FIFO break under single routing,
# or a bite that fails to fork; PASS(0) clean. Requires scale-rig.sh up + migrate.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
SHARD_HOSTPORT="127.0.0.1:$((55511 + 0))"   # scale rig isolated shard-0
SHARD_DB="scale_shard"
DSN="postgres://${PG_USER}:${PG_PASS}@${SHARD_HOSTPORT}/${SHARD_DB}?sslmode=disable"
TARGET_MS="${DP_T3_TARGET_MS:-50}"

log()    { printf '[roleplay-load] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
ensure_bin() {
  RP="$(bin tests/perf/roleplay-load/rpload.exe tests/perf/roleplay-load/rpload)" && return 0
  log "building roleplay-load ..."
  go -C tests/perf/roleplay-load build -o rpload.exe . || notrun "build failed"
  RP="tests/perf/roleplay-load/rpload.exe"
}

require_shard() {
  docker inspect -f '{{.State.Running}}' scale-pg-shard-0 2>/dev/null | grep -q true || notrun "scale-pg-shard-0 not running (scale-rig.sh up)"
  docker exec -i scale-pg-shard-0 psql -tA -U "$PG_USER" -d "$SHARD_DB" -c "SELECT 1 FROM events LIMIT 1" >/dev/null 2>&1 \
    || docker exec -i scale-pg-shard-0 psql -tA -U "$PG_USER" -d "$SHARD_DB" -c "SELECT to_regclass('public.events')" 2>/dev/null | grep -q events \
    || notrun "${SHARD_DB}.events not present (scale-rig.sh migrate)"
}

cmd_run() {
  local s="${1:-50}" e="${2:-20}"
  ensure_bin; require_shard
  log "I6: ${s} sessions x ${e} events @ ~10/s on one shard (hot reality) → serial-FIFO + p99 ack vs ${TARGET_MS}ms ..."
  "$RP" -dsn "$DSN" -sessions "$s" -events "$e" -rate 10 -target-ms "$TARGET_MS"
}

cmd_bite() {
  local s="${1:-20}" e="${2:-20}"
  ensure_bin; require_shard
  log "bite: one session gets TWO processors → its version sequence MUST fork ..."
  "$RP" -dsn "$DSN" -sessions "$s" -events "$e" -rate 10 -target-ms "$TARGET_MS" -bite
}

cmd_smoke() {
  cmd_run 50 20
  cmd_bite 20 20
  log "PASS(smoke): I6 serial-FIFO holds under single-processor routing; the dual-processor bite forks the sequence"
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    run)   cmd_run "$@" ;;
    bite)  cmd_bite "$@" ;;
    smoke) cmd_smoke "$@" ;;
    *) echo "usage: $0 {run|bite|smoke} [sessions] [events]" >&2; exit 2 ;;
  esac
}
main "$@"
