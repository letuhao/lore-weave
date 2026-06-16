#!/usr/bin/env bash
# scripts/perf/w1-provision.sh
#
# W1.5 (production wiring) — provisioner + Rust→Go meta-write bridge, LIVE.
#
# Starts the Go bridge-server (pkg/bridge over the meta DB) and runs the Rust
# provision-drill, which executes the REAL 11-step provision_reality with
# LiveEffects: register_pending + transitions via the bridge (I8 audit through
# Go MetaWrite), CREATE DATABASE + REVOKE CONNECT (I4) on the shard, skeleton
# migration. Closes D-S4-I4-PROVISIONER (core).
#
#   provision  end-to-end: registry active + I8 audit + DB created + REVOKE-
#              isolated + bridge calls audited.
#   bite       (A) no-revoke DB → foreign role connects (REVOKE is the enforcer);
#              (B) raw registry INSERT bypassing the bridge → 0 meta_write_audit
#              (I8 audit is produced BY the bridge's MetaWrite).
#
# Verdict: NOTRUN(2) setup; FAIL(1) a guard not holding / vacuous bite; PASS(0).
# Reuses the S12 scale rig (meta-pg + pg-shard-0). Re-runnable.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
META_C="scale-meta-pg"; SHARD_C="scale-pg-shard-0"
META_DB="w1_provision"
META_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55510/${META_DB}?sslmode=disable"
SHARD_ADMIN_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/foundation?sslmode=disable"
BRIDGE_ADDR="127.0.0.1:8090"
BRIDGE_TOKEN="w1-bridge-dev-token"

log()    { printf '[w1-provision] %s\n' "$*"; }
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
           016_service_to_service_audit 027_meta_write_audit_scrub_version; do
    docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" \
      < "migrations/meta/${m}.up.sql" || notrun "meta migration ${m} failed"
  done
  log "w1_provision migrated (registry + lifecycle + meta_write_audit + s2s_audit)"
}

build_bins() {
  log "building bridge-server + provision-drill ..."
  go -C services/meta-worker build -o bridge-server.exe ./cmd/bridge-server || notrun "build bridge-server failed"
  cargo build -p world-service --bin provision-drill || notrun "build provision-drill failed"
  BRIDGE_BIN="services/meta-worker/bridge-server.exe"
  DRILL="target/debug/provision-drill.exe"; [ -x "$DRILL" ] || DRILL="target/debug/provision-drill"
}

BRIDGE_PID=""
stop_bridge() { [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null || true; }
trap stop_bridge EXIT

start_bridge() {
  META_DB_URL="$META_DSN" \
  METAWORKER_BRIDGE_TOKEN="$BRIDGE_TOKEN" \
  METAWORKER_BRIDGE_ADDR="$BRIDGE_ADDR" \
  META_ALLOWLIST_PATH="contracts/meta/events_allowlist.yaml" \
  META_TRANSITIONS_PATH="contracts/meta/transitions.yaml" \
    "$BRIDGE_BIN" &
  BRIDGE_PID=$!
  # Readiness: an unauth POST should get 401 once the listener is up.
  local i
  for i in $(seq 1 30); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://${BRIDGE_ADDR}/internal/provisioner/transition" 2>/dev/null || true)"
    [ "$code" = "401" ] && { log "bridge ready (pid $BRIDGE_PID)"; return 0; }
    sleep 0.3
  done
  notrun "bridge did not become ready on ${BRIDGE_ADDR}"
}

main() {
  local sub="${1:-smoke}"
  require
  setup
  build_bins
  start_bridge
  PROVISION_META_DSN="$META_DSN" \
  PROVISION_SHARD_ADMIN_DSN="$SHARD_ADMIN_DSN" \
  PROVISION_BRIDGE_URL="http://${BRIDGE_ADDR}" \
  PROVISION_BRIDGE_TOKEN="$BRIDGE_TOKEN" \
  PROVISION_SHARD_HOSTPORT="127.0.0.1:55511" \
    "$DRILL" "$sub"
}
main "$@"
