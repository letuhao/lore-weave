#!/usr/bin/env bash
# scripts/chaos/recover-replay-determinism.sh
#
# S8 (Technique G) — drill G4: replay determinism across two rebuilds.
#
# Rebuild a projection from the SAME events twice and assert the two results are
# byte-identical. This is the deterministic-replay facet of C (run-to-run, same
# engine) — NOT H0 (the cross-language Go-write/Rust-replay differential); do not
# double-count.
#
# DETERMINISTIC COLUMNS ONLY (S8 review MED-3): pc_projection carries `applied_at`
# and `last_verified_at` (VerificationMeta timestamps) that are set at rebuild/
# verify wall-clock time and therefore DIFFER run-to-run even when the projected
# state is identical. The snapshot strips them (`to_jsonb(t) - 'applied_at' -
# 'last_verified_at'`); otherwise G4 would falsely fail on a timestamp.
#
# Bite: rebuild a DIFFERENT seed's events → the snapshot DIFFERS from run A →
# proves the byte-compare distinguishes (a vacuous always-equal compare fails it).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"; PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
SHARD_DB="recover_determinism_shard"; BITE_DB="recover_determinism_bite"
PROFILE="${PROFILE:-single-reality}"
SEED="${SEED:-3}"; BITE_SEED="${BITE_SEED:-99}"
PROJECTION="${PROJECTION:-pc_projection}"
PK="${PK:-pc_id}"
DET_SNAPSHOT="to_jsonb(t) - 'applied_at' - 'last_verified_at'"   # strip non-deterministic cols (MED-3)
BITE="${BITE:-0}"
for a in "$@"; do case "$a" in --bite) BITE=1 ;; esac; done

log() { printf '[determinism] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
WG="${WG_BIN:-$(bin tests/workload-gen/wg.exe tests/workload-gen/wg)}" || notrun "workload-gen not built"
REBUILDER="${REBUILDER_BIN:-$(bin target/debug/rebuilder.exe target/debug/rebuilder)}" || notrun "rebuilder not built"

docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || notrun "foundation Postgres not reachable"

build_shard() { # $1=db $2=seed  -> emits + returns reality id on stdout
  local db="$1" seed="$2" dsn="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/$1?sslmode=disable"
  psql_db foundation -c "DROP DATABASE IF EXISTS ${db}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${db}" >/dev/null
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256 0006_projections 0007_drift_metadata 0008_pgvector_setup 0009_canon_projection; do
    docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$db" < "contracts/migrations/per_reality/${m}.up.sql"
  done
  psql_db "$db" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
  "$WG" -seed "$seed" -profile "$PROFILE" -emit -dsn "$dsn" >/dev/null
  psql_db "$db" -tA -c "SELECT DISTINCT reality_id FROM events LIMIT 1"
}
rebuild_snapshot() { # $1=db $2=rid  -> deterministic snapshot on stdout
  local db="$1" rid="$2" dsn="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/$1?sslmode=disable"
  psql_db "$db" -c "TRUNCATE ${PROJECTION}" >/dev/null
  REALITY_DB_URL="$dsn" "$REBUILDER" --reality-id "$rid" --projection "$PROJECTION" >/dev/null 2>&1 || return 1
  psql_db "$db" -tA -c "SELECT ${DET_SNAPSHOT} FROM ${PROJECTION} t ORDER BY ${PK}"
}

log "building shard (seed=$SEED) ..."
RID="$(build_shard "$SHARD_DB" "$SEED")"
[ -n "$RID" ] || notrun "no reality after emit"
NROWS_PRE="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events")"

log "rebuild #1 → snapshot A ..."
A="$(rebuild_snapshot "$SHARD_DB" "$RID")" || notrun "rebuild #1 errored"
log "rebuild #2 → snapshot B ..."
B="$(rebuild_snapshot "$SHARD_DB" "$RID")" || notrun "rebuild #2 errored"

nA="$(printf '%s\n' "$A" | grep -c . )"
[ "${nA:-0}" -gt 0 ] || notrun "snapshot A empty — ${PROJECTION} rebuilt 0 rows (determinism check would be vacuous)"

if [ "$A" = "$B" ]; then
  log "DETERMINISTIC: two rebuilds of ${PROJECTION} (${nA} rows) are byte-identical (deterministic cols)"
else
  log "first differing rows:"; diff <(printf '%s\n' "$A") <(printf '%s\n' "$B") | head -6
  fail "two rebuilds of ${PROJECTION} DIFFER — replay is non-deterministic"
fi

# ── BITE: a DIFFERENT seed's rebuild must DIFFER from A ───────────────────────
if [ "$BITE" = "1" ]; then
  log "BITE: rebuild a DIFFERENT seed (seed=$BITE_SEED) → snapshot must DIFFER from A ..."
  BRID="$(build_shard "$BITE_DB" "$BITE_SEED")"
  C="$(rebuild_snapshot "$BITE_DB" "$BRID")" || notrun "bite rebuild errored"
  if [ "$A" = "$C" ]; then
    log "FAIL(harness): a different seed produced an IDENTICAL snapshot — the byte-compare is vacuous"; exit 2
  fi
  log "PASS(bite): a different seed's rebuild differs from A — the determinism compare distinguishes (has teeth)"
fi

log "PASS: replay determinism — two same-events rebuilds byte-identical (C deterministic-replay facet, not H0)"
