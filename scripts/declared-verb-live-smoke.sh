#!/usr/bin/env bash
# declared-verb-live-smoke.sh — `M2` Axis 2
#
# The DECLARED VERB path end to end against a real Postgres:
#
#   a submitted command -> admission (real vocabulary + real verb table)
#                       -> the island (real domain, real ruleset)
#                       -> ChannelWriter::append          (real channel log)
#                       -> read the row BACK out of Postgres
#                       -> TurnOutcome::from_resolution   (the client wire)
#
# WHY THIS EXISTS, when the unit suite is already green
# -----------------------------------------------------
# A unit suite proves the substrate RESOLVES. It cannot prove the fact reaches
# the log, survives a round trip through Postgres, and projects to the shape a
# browser reads. Four cross-service contract bugs in this repository were hidden
# by mock-only coverage, which is why VERIFY asks for a live smoke whenever a
# cycle touches more than one service.
#
# It also drives the REFUSAL path, which is the half of `CMD-5` a happy-path
# smoke never reaches: the verb is submitted once more than its declared `focus`
# allows, and the last submission must commit a `refused` fact carrying its
# reason ordinal.
#
#   bash scripts/declared-verb-live-smoke.sh
#   PG_CONTAINER=infra-postgres-1 PG_USER=loreweave bash scripts/…
#
# Exit 0 = green; 1 = a test failed; 2 = setup could not run.
#
# db-safety-gate: file-ok — the DB name is overridable, which is exactly the
# shape that needs a guard rather than a promise, so there are two: the marker
# check below runs BEFORE the first destructive statement, and the Rust test
# re-checks its own DSN (`guarded()`) so running it by hand cannot skip the
# check. The test itself contains no DELETE/TRUNCATE/DROP — isolation is a fresh
# reality UUID per run, which an append-only channel log forces anyway.

set -uo pipefail

PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PG_USER="${PG_USER:-loreweave}"
PG_HOST_PORT="${PG_HOST_PORT:-5555}"
DB="${DECLARED_VERB_SMOKE_DB:-loreweave_test_declared_verb_smoke}"

log() { printf '[verb-live] %s\n' "$*"; }

case "$DB" in
  *test*|*smoke*) ;;
  *)
    log "FAIL(setup): refusing to DROP/CREATE '$DB' — a destructive fixture may"
    log "             only target a database whose name carries a throwaway marker."
    exit 2 ;;
esac

docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || {
  log "live infra unavailable: postgres container '$PG_CONTAINER' is not accepting connections."
  exit 2
}

psql_q() { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" -c "$2"; }

log "(re)creating throwaway DB $DB ..."
psql_q postgres "DROP DATABASE IF EXISTS $DB" >/dev/null 2>&1
psql_q postgres "CREATE DATABASE $DB" >/dev/null 2>&1 \
  || { log "FAIL(setup): CREATE DATABASE $DB"; exit 2; }

# GLOBBED, not listed. The per-reality set is a migration SEQUENCE applied in
# full to every reality DB, so a hand-picked subset here would test a schema no
# reality ever runs — the defect that left the publisher smoke two migrations
# behind production and red for two days without anyone noticing.
mapfile -t PER_REALITY < <(ls contracts/migrations/per_reality/*.up.sql | sort)
[ "${#PER_REALITY[@]}" -gt 0 ] || { log "FAIL(setup): no per_reality migrations found"; exit 2; }

SKIPPED=()
for f in "${PER_REALITY[@]}"; do
  out="$(docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "$f" 2>&1)"
  if [ $? -eq 0 ]; then continue; fi
  # One reason a migration may be skipped, matched on the SERVER'S OWN ERROR
  # TEXT rather than on a filename — so a new migration is applied by default
  # and a list cannot silently go stale.
  if grep -q 'extension .* is not available' <<<"$out"; then
    SKIPPED+=("$(basename "$f")")
    continue
  fi
  log "FAIL(setup): $f did not apply:"
  sed 's/^/  /' <<<"$out"
  exit 2
done
log "applied ${#PER_REALITY[@]} per-reality migration(s), ${#SKIPPED[@]} skipped for a missing extension"

# The DSN needs a password and this file must not contain one. Ask the RUNNING
# container what it was started with — a dev-stack fact discovered at runtime
# rather than a credential committed to the repo.
PG_PASSWORD="${PG_PASSWORD:-$(docker inspect "$PG_CONTAINER" \
  --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
  | sed -n 's/^POSTGRES_PASSWORD=//p' | head -1)}"
if [ -z "$PG_PASSWORD" ]; then
  log "FAIL(setup): no password. Container '$PG_CONTAINER' does not expose"
  log "             POSTGRES_PASSWORD; pass PG_PASSWORD=… explicitly."
  exit 2
fi

export DECLARED_VERB_TEST_DATABASE_URL="postgres://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_HOST_PORT}/${DB}"

# REQUIRE_LIVE=1 turns a missing DSN into a FAILURE rather than a green skip.
# Without it this script could report success having touched no database.
export REQUIRE_LIVE=1

log "running the live declared-verb test ..."
cargo test -p commit-service --test declared_verb_live -- --nocapture
rc=$?
[ $rc -eq 0 ] && log "GREEN" || log "RED (exit $rc)"
exit $rc
