#!/usr/bin/env bash
# epoch-activation-live-smoke.sh — Q0b B3b + B3c
#
# The epoch path end to end against a real Postgres:
#
#   activate_reality_epoch -> reality_ruleset_binding (meta DB)
#   reconcile_and_commit   -> re-reads the binding -> island switches
#                          -> ChannelWriter::append -> events (channel DB)
#
# TWO databases, because production has two. The meta DB holds the binding; the
# per-reality DB holds the channel log and the writer lease. Collapsing them
# into one would exercise a topology nothing runs, and would hide the thing this
# smoke exists to show: the decision crosses a database boundary.
#
#   bash scripts/epoch-activation-live-smoke.sh
#   PG_CONTAINER=infra-postgres-1 PG_USER=loreweave bash scripts/…
#
# Exit 0 = green; 1 = a test failed; 2 = setup could not run.
#
# db-safety-gate: file-ok — both DB names are overridable, which is exactly the
# shape that needs a guard rather than a promise, so there is one: the marker
# check below runs BEFORE the first destructive statement, and the Rust tests
# re-check their own DSNs (`guarded()`) so running them by hand cannot skip it.
# The tests themselves contain no DELETE/TRUNCATE/DROP — isolation is a fresh
# reality UUID per test, which an append-only binding table forces anyway.

set -uo pipefail

PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PG_USER="${PG_USER:-loreweave}"
PG_HOST_PORT="${PG_HOST_PORT:-5555}"
META_DB="${EPOCH_META_SMOKE_DB:-loreweave_test_epoch_meta_smoke}"
CHAN_DB="${EPOCH_CHANNEL_SMOKE_DB:-loreweave_test_epoch_channel_smoke}"

log() { printf '[epoch-live] %s\n' "$*"; }

for db in "$META_DB" "$CHAN_DB"; do
  case "$db" in
    *test*|*smoke*) ;;
    *)
      log "FAIL(setup): refusing to DROP/CREATE '$db' — a destructive fixture may"
      log "             only target a database whose name carries a throwaway marker."
      exit 2 ;;
  esac
done

docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || {
  log "FAIL(setup): postgres container '$PG_CONTAINER' is not accepting connections."
  exit 2
}

psql_q() { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" -c "$2"; }

recreate() {
  log "(re)creating throwaway DB $1 ..."
  psql_q postgres "DROP DATABASE IF EXISTS $1" >/dev/null 2>&1
  psql_q postgres "CREATE DATABASE $1" >/dev/null 2>&1 \
    || { log "FAIL(setup): CREATE DATABASE $1"; exit 2; }
}

SKIPPED=()

# apply <db> <file...>
#
# One migration is allowed to be skipped, and only for one reason: the server
# does not have an EXTENSION it needs (the dev container ships without
# pgvector). That is a property of the machine, not of the migration, and it is
# matched on the SERVER'S OWN ERROR TEXT rather than on a filename — so a new
# migration is applied by default and a list cannot silently go stale. Any other
# failure aborts. If a later migration then fails because of the skip, it aborts
# too and says which, which is the honest outcome: this smoke needs a schema the
# machine cannot build.
apply() {
  local db="$1"; shift
  for f in "$@"; do
    [ -f "$f" ] || { log "FAIL(setup): $f not found (run from the repo root)"; exit 2; }
    local out
    out="$(docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$db" < "$f" 2>&1)"
    if [ $? -eq 0 ]; then
      log "  applied $(basename "$f") -> $db"
      continue
    fi
    if grep -q 'extension .* is not available' <<<"$out"; then
      SKIPPED+=("$(basename "$f")")
      log "  SKIPPED $(basename "$f") — this server has no such extension:"
      grep -o 'extension "[^"]*" is not available' <<<"$out" | sort -u | sed 's/^/      /'
      continue
    fi
    log "FAIL(setup): $f did not apply to $db:"
    sed 's/^/  /' <<<"$out"
    exit 2
  done
}

recreate "$META_DB"
# Listed rather than globbed: the meta directory has 33 migrations with
# inter-dependencies, and applying all of them would make an unrelated failure
# look like a defect in this path. The apply loop stops on the first error and
# names the file, so a NEW dependency surfaces as a clear setup failure.
apply "$META_DB" \
  migrations/meta/013_meta_write_audit.up.sql \
  migrations/meta/027_meta_write_audit_scrub_version.up.sql \
  migrations/meta/030_meta_outbox.up.sql \
  migrations/meta/033_reality_ruleset_binding.up.sql

recreate "$CHAN_DB"
# The channel side is GLOBBED, and the difference from the list above is
# deliberate. The per-reality set is a migration SEQUENCE applied in full to
# every reality DB, so a hand-picked subset here would test a schema no reality
# ever runs — the exact defect that left the publisher smoke two migrations
# behind production and red for two days without anyone noticing. A migration
# added tomorrow is applied by this smoke tomorrow, without anyone editing it.
mapfile -t PER_REALITY < <(ls contracts/migrations/per_reality/*.up.sql | sort)
[ "${#PER_REALITY[@]}" -gt 0 ] || { log "FAIL(setup): no per_reality migrations found"; exit 2; }
apply "$CHAN_DB" "${PER_REALITY[@]}"

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

export EPOCH_META_TEST_DATABASE_URL="postgres://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_HOST_PORT}/${META_DB}"
export EPOCH_CHANNEL_TEST_DATABASE_URL="postgres://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_HOST_PORT}/${CHAN_DB}"

if [ "${#SKIPPED[@]}" -gt 0 ]; then
  log "NOTE: ${#SKIPPED[@]} migration(s) skipped for a missing server extension:"
  printf '[epoch-live]       %s\n' "${SKIPPED[@]}"
  log "      The channel tables this smoke uses (events, channel_writer_state,"
  log "      channel_event_index) do not depend on them — and if that ever stops"
  log "      being true, the tests below fail rather than this line growing."
fi

log "running the live epoch-activation tests ..."
# --nocapture so a SKIP is visible: a live suite that skips silently and reports
# "ok" is the failure mode this whole file exists to avoid.
cargo test -p commit-service --test epoch_activation_live -- --nocapture --test-threads=1
rc=$?

if [ "$rc" -ne 0 ]; then
  log "FAIL — live tests did not pass ($META_DB / $CHAN_DB left in place for inspection)"
  exit 1
fi

log "cleaning up ..."
psql_q postgres "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null 2>&1
psql_q postgres "DROP DATABASE IF EXISTS ${CHAN_DB}" >/dev/null 2>&1
log "PASS — an authorised epoch switch reaches the channel log, joinable to its binding row"
exit 0
