#!/usr/bin/env bash
# scripts/chaos/fault-pg-down.sh
#
# S6 (Battery D) — GRACEFUL-DEGRADATION drill: Postgres unreachable on the EMIT
# path. This is NOT a convergence drill (an interrupted, non-idempotent emit
# can't be completed and C3 against the full seed would flag it incomplete —
# see the S6 spec §3.2). It asserts the WRITER fails fast + cleanly under a PG
# outage, leaves NO partial corruption, and that a fresh emit converges on recovery.
#
# Deterministic bracket (no timing race against a sub-second batch):
#   down pg_proxy → emit through the proxy MUST fail fast (fault-real guard) →
#   assert 0 rows written (transactional: connection refused / tx rollback) →
#   up pg_proxy → a FRESH emit → workload-gen -verify (C3) clean.
#
# Setup (CREATE DATABASE + migrations) goes DIRECT to PG; only the workload DSN
# goes through the proxy. Re-runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"           # DIRECT (setup)
PG_PROXY_PORT="${FOUNDATION_PG_PROXY_PORT:-55433}" # via toxiproxy (workload)
DB="chaos_pgdown_shard"
PROFILE="${PROFILE:-single-reality}"
SEED="${SEED:-1}"
TOXIC="bash $ROOT/scripts/chaos/toxic.sh"
PROXY_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PROXY_PORT}/${DB}?sslmode=disable"

log() { printf '[pg-down] %s\n' "$*"; }
# Verdict convention (review-impl #1): fault couldn't be injected → NOTRUN
# (exit 2). System invariant violated under the fault (didn't fail fast, partial
# corruption, broken recovery) → FAIL (exit 1).
notrun() { log "NOTRUN(setup/timing): $*"; $TOXIC up pg_proxy >/dev/null 2>&1 || true; exit 2; }
fail()   { log "FAIL: $*"; $TOXIC up pg_proxy >/dev/null 2>&1 || true; exit 1; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }

WG="${WG_BIN:-}"
[ -n "$WG" ] || { [ -x tests/workload-gen/wg.exe ] && WG="tests/workload-gen/wg.exe"; }
[ -n "$WG" ] || { [ -x tests/workload-gen/wg ] && WG="tests/workload-gen/wg"; }
[ -n "$WG" ] || { log "FAIL(setup): workload-gen binary not found"; exit 2; }

log "bringing up postgres + toxiproxy ..."
docker compose -f "$COMPOSE" up -d postgres-foundation toxiproxy-foundation >/dev/null
for _ in $(seq 1 30); do docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 && break; sleep 1; done
$TOXIC wait
$TOXIC create-proxy pg_proxy "$PG_PROXY_PORT" "${PG_CONTAINER}:5432"

log "(re)creating shard DB $DB + migrations (DIRECT) ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${DB}" >/dev/null
psql_db foundation -c "CREATE DATABASE ${DB}" >/dev/null
for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256; do
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "contracts/migrations/per_reality/${m}.up.sql"
done
psql_db "$DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null

# ── bracket: down → emit MUST fail fast + clean ──────────────────────────────
log "DOWN pg_proxy; attempting emit through the (dead) proxy ..."
$TOXIC down pg_proxy
start="$(date +%s%3N)"
rc=0
out="$("$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$PROXY_DSN" 2>&1)" || rc=$?
elapsed=$(( $(date +%s%3N) - start ))

# fault-real: emit SUCCEEDING while down = the fault didn't inject (the down
# mis-fired / DSN bypassed the proxy) → NOTRUN, not a system fail.
[ "$rc" -ne 0 ] || notrun "emit succeeded while pg_proxy was down — the fault did not inject"
# fail FAST: a connection refused returns promptly; a multi-second hang = a REAL
# bad behavior (pool/timeout misconfig). 20s is a generous ceiling for "did not hang".
[ "$elapsed" -lt 20000 ] || fail "emit took ${elapsed}ms to fail — did not fail fast (hang/timeout misconfig)"
log "emit failed fast in ${elapsed}ms (rc=$rc) — graceful: ${out##*$'\n'}"

# no partial corruption: the failed emit (connection refused / tx rollback) must
# have written NOTHING. A non-zero count is a REAL atomicity violation → FAIL.
wrote="$(psql_db "$DB" -tA -c "SELECT count(*) FROM events")"
[ "$wrote" = "0" ] || fail "${wrote} event(s) written by a FAILED emit — partial corruption"
log "no partial state: 0 events written by the failed emit (transactional)"

# ── recovery: up → fresh emit → C3 verify clean ──────────────────────────────
log "UP pg_proxy; fresh emit + C3 verify on recovery ..."
$TOXIC up pg_proxy
"$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$PROXY_DSN"
ev="$(psql_db "$DB" -tA -c "SELECT count(*) FROM events")"
[ "$ev" -gt 0 ] || fail "fresh emit wrote 0 events after recovery — recovery broken"
"$WG" -seed "$SEED" -profile "$PROFILE" -verify -dsn "$PROXY_DSN"
$TOXIC reset
$TOXIC delete-proxy pg_proxy
log "PASS: PG-down → emit failed fast + clean (0 partial) → recovery emit ${ev} events, C3 verified"
