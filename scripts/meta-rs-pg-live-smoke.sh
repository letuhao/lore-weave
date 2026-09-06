#!/usr/bin/env bash
# meta-rs-pg-live-smoke.sh — Q1 B2b
#
# Runs `crates/meta-rs/tests/pg_live.rs` against a real Postgres.
#
# WHY IT IS NOT ENOUGH TO UNIT-TEST THE ADAPTER. `sqlx_pg`'s in-module tests are
# string assertions over generated SQL. They prove the builder emits what was
# intended; they cannot prove Postgres accepts it. The adapter's whole design —
# `jsonb_populate_record(NULL::<table>, $1::jsonb)` so the SERVER types every
# parameter from the table's own row type — is a claim about server behaviour,
# and only a server can settle it. The same goes for the properties MetaWrite
# exists for: data row + audit row + outbox event in ONE transaction, and all
# three gone when the data write is refused. A fake TX records three calls
# either way.
#
#   bash scripts/meta-rs-pg-live-smoke.sh
#   PG_CONTAINER=infra-postgres-1 PG_USER=loreweave bash scripts/…
#
# Exit 0 = green; 1 = a test failed; 2 = setup could not run.
#
# db-safety-gate: file-ok — the DB name is overridable (META_RS_SMOKE_DB), which is
# exactly the shape that needs a guard rather than a promise, so there is one: the
# marker check below runs BEFORE the first destructive statement and exits 2 on a
# name that does not announce itself as disposable. The Rust tests themselves run
# no DELETE/TRUNCATE/DROP at all — they isolate with a fresh UUID per test, which
# is what an append-only table forces and is the better answer anyway.

set -uo pipefail

PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PG_USER="${PG_USER:-loreweave}"
PG_HOST_PORT="${PG_HOST_PORT:-5555}"
DB="${META_RS_SMOKE_DB:-loreweave_test_meta_rs_smoke}"

log() { printf '[meta-rs-live] %s\n' "$*"; }

case "$DB" in
  *test*|*smoke*) ;;
  *)
    log "FAIL(setup): refusing to DROP/CREATE '$DB' — a destructive fixture may only"
    log "             target a database whose name carries a throwaway marker."
    exit 2 ;;
esac

docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || {
  log "FAIL(setup): postgres container '$PG_CONTAINER' is not accepting connections."
  exit 2
}

psql_q() { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" -c "$2"; }

log "(re)creating throwaway DB $DB ..."
psql_q postgres "DROP DATABASE IF EXISTS ${DB}" >/dev/null 2>&1
psql_q postgres "CREATE DATABASE ${DB}" >/dev/null 2>&1 || { log "FAIL(setup): CREATE DATABASE"; exit 2; }

# The four migrations these tests touch. Listed rather than globbed on purpose:
# the meta directory has 33 migrations with inter-dependencies, and applying all
# of them would make a failure in an unrelated table look like an adapter bug.
# The cost of the list is that a NEW dependency has to be added here — so the
# apply loop stops on the first error and names the file, rather than continuing
# and failing later somewhere confusing.
MIGRATIONS=(
  # reality_registry is here for the ADAPTER, not for the binding: it is the
  # only allowlisted, WRITABLE meta table in this set, so it is the only place
  # build_update / build_delete / the CAS guard can be exercised against a real
  # server. reality_ruleset_binding is append-only by design and can only ever
  # prove that an UPDATE is refused.
  001_reality_registry
  013_meta_write_audit
  027_meta_write_audit_scrub_version
  030_meta_outbox
  033_reality_ruleset_binding
  # 5B — session_registry, the capability store. It is the only table in
  # this set whose write path exercises BYTEA-through-jsonb and a CAS on a
  # NULL column, both of which a unit test cannot reach.
  039_session_registry
)
for m in "${MIGRATIONS[@]}"; do
  f="migrations/meta/${m}.up.sql"
  [ -f "$f" ] || { log "FAIL(setup): $f not found (run from the repo root)"; exit 2; }
  if ! docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "$f" >/dev/null 2>&1; then
    log "FAIL(setup): $f did not apply:"
    docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$DB" < "$f" 2>&1 | sed 's/^/  /'
    exit 2
  fi
  log "  applied $m"
done

# The DSN needs a password and this file must not contain one. Take it from the
# environment if the caller supplied it, otherwise ask the RUNNING CONTAINER what
# it was started with — a dev-stack fact discovered at runtime rather than a
# credential committed to the repo. No fallback default: a wrong guess produces
# `password authentication failed` six times over, which reads like an adapter
# bug and is not one.
PG_PASSWORD="${PG_PASSWORD:-$(docker inspect "$PG_CONTAINER" \
  --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
  | sed -n 's/^POSTGRES_PASSWORD=//p' | head -1)}"
if [ -z "$PG_PASSWORD" ]; then
  log "FAIL(setup): no password. Container '$PG_CONTAINER' does not expose"
  log "             POSTGRES_PASSWORD; pass PG_PASSWORD=… explicitly."
  exit 2
fi

export META_RS_TEST_DATABASE_URL="postgres://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_HOST_PORT}/${DB}"
log "running the live tests ..."
# --nocapture so the SKIP lines are visible: a live suite that skips silently and
# reports "ok" is the failure mode this whole file exists to avoid.
cargo test -p meta-rs --features sqlx-pg --test pg_live -- --nocapture --test-threads=1
rc=$?

# …and the CONSUMER, against the same database. The adapter working in isolation
# is not the claim that matters: the claim is that `create_reality` /
# `load_reality` work with the binding in Postgres, which is where Q1's own exit
# criterion ("survives create -> store -> load -> digest with ordinals
# unchanged") is finally settled.
if [ "$rc" -eq 0 ]; then
  log "running the commit-service binding tests ..."
  cargo test -p commit-service --test pg_binding_live -- --nocapture --test-threads=1
  rc=$?
fi

if grep -q . <<<"$(printf '%s' "$rc")" && [ "$rc" -ne 0 ]; then
  log "FAIL — live tests did not pass (DB $DB left in place for inspection)"
  exit 1
fi

log "cleaning up $DB ..."
psql_q postgres "DROP DATABASE IF EXISTS ${DB}" >/dev/null 2>&1
log "PASS — the sqlx adapter works against a real Postgres"
exit 0
