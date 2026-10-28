#!/usr/bin/env bash
# W3.1 current generator/rebuild coverage: canon is the only production projection.
# Migrations 0017/0018 intentionally retired the pc/npc/region/session/world-kv
# projections. Their historical generator events are not live projection coverage.
# Exercise the surviving canon stream -> real rebuild -> populated rows -> orphan
# detector, with a real corruption bite. Do not restore retired vocabulary.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
COMPOSE="infra/foundation-dev/docker-compose.yml"
SHARD_C="foundation-dev-postgres"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
DB="w3_gen"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${DB}?sslmode=disable"
SEED="${W3_SEED:-3}"; PROFILE="${W3_PROFILE:-single-reality}"
log() { printf '[w3-generator] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail() { log "FAIL: $*"; exit 1; }
require() {
  # Reuse the running test rig; compose may recreate it while sibling drills run.
  if docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true; then
    docker exec "$SHARD_C" pg_isready -U "$PG_USER" >/dev/null 2>&1 && return 0
  else
    docker compose -f "$COMPOSE" up -d postgres-foundation >/dev/null 2>&1 || notrun "could not start foundation-dev postgres"
  fi
  local i
  for i in $(seq 1 30); do
    docker exec "$SHARD_C" pg_isready -U "$PG_USER" >/dev/null 2>&1 && return 0
    sleep 2
  done
  notrun "foundation-dev postgres not ready"
}
psql_adm() { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }
psql_db() { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" "$@"; }
scalar() { docker exec -i "$SHARD_C" psql -tA -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" -c "$1" | tr -d '[:space:]'; }
setup() {
  psql_adm -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${DB}" >/dev/null
  local m
  # Do not apply 0006 just to resurrect retired tables. Canon has independent DDL.
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0009_canon_projection 0013_events_content_sha256 0014_channel_ordering 0016_events_ruleset_digest; do
    docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "contracts/migrations/per_reality/${m}.up.sql" || notrun "migration ${m} failed"
  done
  psql_db -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null || notrun "default partition"
  log "w3_gen ready (events + canon_projection; coverage shrank with 0017/0018)"
}
build_bins() {
  go -C tests/workload-gen build -o wg.exe ./cmd/workload-gen || notrun "build wg failed"
  WG="tests/workload-gen/wg.exe"
  # Build the current allowlist instead of trusting a stale pre-retirement binary.
  cargo build -p world-service --bin rebuilder || notrun "build rebuilder failed"
  REB="target/debug/rebuilder.exe"; [ -x "$REB" ] || REB="target/debug/rebuilder"
}
main() {
  require; setup; build_bins
  log "emit seed=${SEED} profile=${PROFILE}"
  "$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$DSN" >/dev/null || fail "emit failed"
  local rid out failed n expected orphan
  rid="$(scalar "SELECT DISTINCT reality_id FROM events LIMIT 1")"
  [ -n "$rid" ] || fail "no events emitted"
  expected="$(scalar "SELECT count(*) FROM events WHERE reality_id='${rid}' AND event_type='canon.entry.created'")"
  [ "${expected:-0}" -ge 1 ] || fail "generator emitted no canon creations"
  out="$(REALITY_DB_URL="$DSN" "$REB" --reality-id "$rid" --projection canon_projection 2>&1)" || fail "canon rebuild failed: ${out}"
  failed="$(printf '%s' "$out" | grep -o '"aggregates_failed":[0-9]*' | grep -o '[0-9]*' || true)"
  [ "$failed" = 0 ] || fail "canon rebuild produced no clean stats: ${out}"
  n="$(scalar "SELECT count(*) FROM canon_projection")"
  [ "$n" = "$expected" ] || fail "canon rows=${n}, expected ${expected} emitted creations (non-vacuity)"
  "$WG" -check-projections -dsn "$DSN" || fail "no-orphan sweep failed on clean canon rebuild"
  log "PASS(clean): canon rebuild populated ${n} rows and no-orphan sweep is clean"
  psql_db -c "UPDATE canon_projection SET event_id=gen_random_uuid() WHERE canon_entry_id=(SELECT canon_entry_id FROM canon_projection LIMIT 1)" >/dev/null || fail "could not orphan canon row"
  orphan="$(scalar "SELECT count(*) FROM canon_projection p WHERE NOT EXISTS (SELECT 1 FROM events e WHERE e.event_id=p.event_id)")"
  [ "$orphan" = 1 ] || fail "bite must orphan exactly one canon row, got ${orphan}"
  out="$("$WG" -check-projections -dsn "$DSN" 2>&1)" && fail "bite VACUOUS: orphaned canon row passed"
  case "$out" in
    *canon_projection*) log "PASS(bite): no-orphan caught exactly one orphaned canon_projection row" ;;
    *) fail "sweep failed without naming canon_projection: ${out}" ;;
  esac
}
main "$@"
