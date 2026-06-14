#!/usr/bin/env bash
# scripts/perf/w3-schema-derived.sh
#
# W3.2 — schema-derived projection-table sweep, LIVE (closes D-PROJCHECK-TABLE-DRIFT).
#
# The no-orphan sweep used to read a HARDCODED list of projection tables; a new
# projection table added by a migration was silently unchecked. projcheck now
# DERIVES the table set from the live schema (every projection table carries the
# VerificationMeta `last_verified_event_version` column). This drill proves a NEW
# projection table is automatically swept:
#
#   smoke   clean DB → -check-projections PASS. Then create a NEW projection table
#           `zzz_projection` (with the verif-meta marker) carrying an ORPHAN row
#           (event_id not in events) → -check-projections now CATCHES it, naming
#           zzz_projection. A hardcoded list (the canonical 11) would have MISSED
#           it → the schema-derivation closed the drift (non-vacuous).
#
# Verdict: NOTRUN(2) setup; FAIL(1) the new table's orphan not caught / clean DB
# flagged; PASS(0). Reuses the S12 scale rig shard-0 (no pgvector needed).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
SHARD_C="scale-pg-shard-0"
DB="w3_schema"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/${DB}?sslmode=disable"

log()    { printf '[w3-schema] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
require() { docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true || notrun "$SHARD_C not running"; }
psql_adm() { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }
psql_db()  { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" "$@"; }

setup() {
  psql_adm -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${DB}" >/dev/null
  local m
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0006_projections 0009_canon_projection; do
    docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" \
      < "contracts/migrations/per_reality/${m}.up.sql" || notrun "migration ${m} failed"
  done
  psql_db -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null || notrun "default partition"
  # One real event so there's a non-empty reference set for the no-orphan check.
  psql_db -c "INSERT INTO events
      (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version, event_type, event_version, payload, occurred_at, recorded_at)
      VALUES (gen_random_uuid(), gen_random_uuid(), 'region', 'r1', 1, 'region.created', 1, '{}'::jsonb, now(), now())" >/dev/null \
    || notrun "seed event failed"
  log "w3_schema ready (projection tables, no zzz yet)"
}

build_bin() {
  go -C tests/workload-gen build -o wg.exe ./cmd/workload-gen || notrun "build wg failed"
  WG="tests/workload-gen/wg.exe"
}

main() {
  require; setup; build_bin

  # Clean: no orphan rows anywhere → sweep passes.
  "$WG" -check-projections -dsn "$DSN" >/dev/null 2>&1 || fail "clean projection DB flagged as having orphans"
  log "PASS(clean): no-orphan sweep clean on the migrated DB"

  # Add a NEW projection table the hardcoded list never knew about, with the
  # VerificationMeta marker + an ORPHAN row (event_id not in events).
  psql_db -c "CREATE TABLE zzz_projection (
      id text PRIMARY KEY, event_id uuid NOT NULL, aggregate_version bigint,
      applied_at timestamptz, last_verified_event_version bigint, last_verified_at timestamptz)" >/dev/null \
    || notrun "create zzz_projection failed"
  psql_db -c "INSERT INTO zzz_projection (id, event_id) VALUES ('x', gen_random_uuid())" >/dev/null \
    || notrun "insert zzz orphan failed"
  log "added zzz_projection (NOT in the old hardcoded 11) with an orphan row"

  # The schema-derived sweep MUST now discover zzz_projection and flag its orphan.
  out="$("$WG" -check-projections -dsn "$DSN" 2>&1)" && {
    fail "bite VACUOUS: -check-projections PASSED with an orphan in zzz_projection — the new table was NOT discovered (a hardcoded list would miss it)"
  }
  case "$out" in
    *zzz_projection*) log "PASS(bite): the schema-derived sweep DISCOVERED zzz_projection and caught its orphan — a hardcoded list would have missed it (drift closed)" ;;
    *) fail "the sweep failed but did NOT name zzz_projection — got: ${out}" ;;
  esac
}
main "$@"
