#!/usr/bin/env bash
# `DFO-7` — stack up two throwaway databases and drive the `spine` BINARY.
#
# The one path a real deployment runs was the one nothing exercised, which is
# how `spine --drain-once` came to block forever without a single red test.
# This script provisions what that binary needs and hands the DSNs to
# `services/commit-service/tests/spine_drain_once_live.rs`, which spawns it and
# requires it to TERMINATE.
#
#   bash scripts/smoke/spine-drain-once.sh
#
# Override the endpoints with PGHOSTPORT / REDIS_URL / PGUSER / PGPASSWORD.
set -euo pipefail
cd "$(dirname "$0")/../.."

PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PGHOSTPORT="${PGHOSTPORT:-localhost:5555}"
PGUSER="${PGUSER:-loreweave}"
PGPASSWORD="${PGPASSWORD:-loreweave_dev}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6399/0}"

META_DB=loreweave_spine_smoke_meta
CHAN_DB=loreweave_spine_smoke_channel

psql_db() { docker exec -i "$PG_CONTAINER" psql -U "$PGUSER" -d "$1" -v ON_ERROR_STOP=1 -q; }

# ── Provision. Both names carry the `smoke` marker the fixture's `guarded()`
# demands before it will touch a server; a rename that drops it FAILS the test
# rather than quietly pointing a seeding fixture at something real.
echo "== provisioning $META_DB + $CHAN_DB on $PG_CONTAINER =="
docker exec "$PG_CONTAINER" psql -U "$PGUSER" -d postgres -q \
  -c "DROP DATABASE IF EXISTS $META_DB" -c "CREATE DATABASE $META_DB" \
  -c "DROP DATABASE IF EXISTS $CHAN_DB" -c "CREATE DATABASE $CHAN_DB" >/dev/null

# ── Migrate. A failing migration is REPORTED, never swallowed: the two that
# need pgvector are expected to fail on a stock postgres image and the spine
# path does not touch what they create, but a NEW failure here would otherwise
# look exactly like a passing setup with a missing table underneath it.
skipped=()
apply() { # apply <db> <glob-dir>
  for f in "$2"/*.up.sql; do
    if ! psql_db "$1" < "$f" >/tmp/spine-smoke-migrate.log 2>&1; then
      skipped+=("$(basename "$f"): $(head -1 /tmp/spine-smoke-migrate.log)")
    fi
  done
}
echo "== applying migrations/meta =="
apply "$META_DB" migrations/meta
echo "== applying contracts/migrations/per_reality =="
apply "$CHAN_DB" contracts/migrations/per_reality

if [ ${#skipped[@]} -gt 0 ]; then
  echo "!! ${#skipped[@]} migration(s) did not apply:"
  printf '   %s\n' "${skipped[@]}"
fi

# ── The four tables the binary actually needs. Checked rather than assumed:
# a migration set that half-applied would otherwise surface as a confusing
# failure inside the smoke instead of here, where the cause is visible.
need_meta="session_registry reality_registry reality_ruleset_binding"
need_chan="events channels channel_writer_state channel_event_index"
missing=0
for t in $need_meta; do
  docker exec "$PG_CONTAINER" psql -U "$PGUSER" -d "$META_DB" -tAc \
    "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='$t'" | grep -q 1 \
    || { echo "MISSING $META_DB.$t"; missing=1; }
done
for t in $need_chan; do
  docker exec "$PG_CONTAINER" psql -U "$PGUSER" -d "$CHAN_DB" -tAc \
    "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='$t'" | grep -q 1 \
    || { echo "MISSING $CHAN_DB.$t"; missing=1; }
done
[ "$missing" -eq 0 ] || { echo "setup incomplete — refusing to report a smoke result"; exit 2; }

BASE="postgres://$PGUSER:$PGPASSWORD@$PGHOSTPORT"
export SPINE_SMOKE_META_TEST_DATABASE_URL="$BASE/$META_DB"
export SPINE_SMOKE_CHANNEL_TEST_DATABASE_URL="$BASE/$CHAN_DB"
export SPINE_SMOKE_REDIS_URL="$REDIS_URL"

echo "== driving the binary =="
cargo test -p commit-service --test spine_drain_once_live -- --nocapture
