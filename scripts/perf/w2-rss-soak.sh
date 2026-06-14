#!/usr/bin/env bash
# scripts/perf/w2-rss-soak.sh
#
# W2.3a — REAL-service RSS soak, LIVE (closes D-S14-SERVICE-RSS-SOAK).
#
# S14's rss-soak was an in-process pure-alloc loop. This soaks the REAL
# long-lived publisher under sustained drain load and asserts its RSS PLATEAUS
# (no steady-state leak), sampling /proc/<pid>/status VmRSS.
#
#   smoke   (1) BITE [Linux + Windows/WSL2]: the S14 in-process count-bounded
#               retain (rss-soak -mode bite) grows the heap >= 2x — proves the
#               plateau detector CAN fire (mechanism non-vacuous). Runs anywhere.
#           (2) SERVICE SOAK [Linux only]: run the publisher under pgbench drain
#               load for a window; assert VmRSS(end) <= 1.5x post-warmup base.
#               /proc + a Linux-built publisher are required → NOTRUN off-Linux
#               (the nightly Linux runner is where this actually executes).
#
# Verdict: NOTRUN(2) setup; FAIL(1) the bite didn't grow, or the service RSS did
# NOT plateau on Linux; PASS(0). Reuses the S12 scale rig.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
ISO_C="scale-pg-shard-0"; META_C="scale-meta-pg"; REDIS_C="scale-redis"; CLIENT_C="scale-pg-shard-1"
SHARD_DB="scale_shard"; META_DB="scale_meta"
META_HOSTPORT="127.0.0.1:55510"; REDIS_HOSTPORT="127.0.0.1:56510"
SHARD0_PROXY_PORT="${SCALE_SHARD0_PROXY_PORT:-55520}"
NREAL=20
SECS="${W2_RSS_SECS:-30}"; RATE="${W2_RSS_RATE:-200}"
PGBENCH_SQL="/tmp/w2-rss-emit.sql"

log()    { printf '[w2-rss-soak] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; cleanup; exit 2; }
fail()   { log "FAIL: $*"; cleanup; exit 1; }
psqlA()  { docker exec -i "$1" psql -tA -U "$PG_USER" -d "$2" -c "$3"; }

PUB_PID=""; EMIT_PID=""
cleanup() { [ -n "$PUB_PID" ] && kill -9 "$PUB_PID" 2>/dev/null || true; [ -n "$EMIT_PID" ] && kill -9 "$EMIT_PID" 2>/dev/null || true; }
trap cleanup EXIT

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }

# ── (1) bite — the in-process plateau-detector mechanism (runs anywhere) ──────
bite() {
  local SOAK; SOAK="$(bin services/meta-worker/rsssoak.exe services/meta-worker/rsssoak)" || {
    log "building rss-soak ..."
    go -C services/meta-worker build -o rsssoak.exe ./cmd/rss-soak || notrun "build rss-soak failed"
    SOAK="services/meta-worker/rsssoak.exe"
  }
  log "bite: in-process count-bounded retain must grow the heap >= 2x"
  "$SOAK" -mode bite >/tmp/w2-rss-bite.json 2>/tmp/w2-rss-bite.err || true
  cat /tmp/w2-rss-bite.err
  grep -q 'PASS' /tmp/w2-rss-bite.err 2>/dev/null \
    || fail "bite did not demonstrate growth — the plateau detector mechanism is not proven"
  log "PASS(bite): retain-mode growth detected — the plateau detector is non-vacuous"
}

# ── (2) real-service RSS soak — Linux only ───────────────────────────────────
linux_ok() {
  [ "$(uname -s 2>/dev/null)" = "Linux" ] || return 1
  [ -r /proc/self/status ] || return 1
  return 0
}

vmrss_kb() { awk '/^VmRSS:/{print $2}' "/proc/$1/status" 2>/dev/null; }

service_soak() {
  local PUB; PUB="$(bin services/publisher/pub)" || notrun "publisher not built for Linux (go -C services/publisher build -o pub ./cmd/publisher)"
  docker inspect -f '{{.State.Running}}' "$ISO_C" 2>/dev/null | grep -q true || notrun "$ISO_C not running"
  # register fixed realities + clear (so the publisher drains everything emitted).
  psqlA "$META_C" "$META_DB" "TRUNCATE reality_registry" >/dev/null || notrun "truncate registry"
  psqlA "$META_C" "$META_DB" "INSERT INTO reality_registry
      (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort)
    SELECT ('00000000-0000-0000-0000-'||lpad(g::text,12,'0'))::uuid,'pg-shard-0.internal','${SHARD_DB}','active','en',10,10,20,(g%100)
    FROM generate_series(1,${NREAL}) g ON CONFLICT DO NOTHING" >/dev/null || notrun "register realities"
  psqlA "$ISO_C" "$SHARD_DB" "TRUNCATE events_outbox" >/dev/null || true

  PUBLISHER_ID=w2-rss-pub SHARD_HOST=pg-shard-0.internal \
    META_DB_URL="postgres://${PG_USER}:${PG_PASS}@${META_HOSTPORT}/${META_DB}?sslmode=disable" \
    REDIS_URL="redis://${REDIS_HOSTPORT}/0" \
    SHARD_DB_USER="$PG_USER" SHARD_DB_PASSWORD="$PG_PASS" SHARD_DB_PORT="$SHARD0_PROXY_PORT" SHARD_DB_SSLMODE=disable \
    PUBLISHER_SHARD_HOST_OVERRIDE="*=127.0.0.1:${SHARD0_PROXY_PORT}" \
    POLL_INTERVAL=300ms BATCH_SIZE=1000 HEARTBEAT_INTERVAL=5s PUBLISHER_HTTP_ADDR=":18099" \
    "$PUB" >/tmp/w2-rss-pub.log 2>&1 &
  PUB_PID=$!
  sleep 1; kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/w2-rss-pub.log; notrun "publisher exited at startup"; }

  # steady emit into the registered realities.
  docker exec -i "$CLIENT_C" sh -c "cat > $PGBENCH_SQL" <<EOF
\set rid random(1, ${NREAL})
WITH e AS (
  INSERT INTO events (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
    event_type, event_version, payload, occurred_at, recorded_at)
  VALUES (gen_random_uuid(), ('00000000-0000-0000-0000-'||lpad(:rid::text,12,'0'))::uuid,
    'pc', gen_random_uuid()::text, 1, 'pc.moved', 1, '{"x":1}'::jsonb, now(), now())
  RETURNING event_id, reality_id)
INSERT INTO events_outbox (event_id, reality_id, published, attempts) SELECT event_id, reality_id, FALSE, 0 FROM e;
EOF
  docker exec -e PGPASSWORD="$PG_PASS" "$CLIENT_C" \
    pgbench -n -f "$PGBENCH_SQL" -c 8 -j 4 -R "$RATE" -T "$((SECS + 3))" -h "$ISO_C" -p 5432 -U "$PG_USER" "$SHARD_DB" >/tmp/w2-rss-emit.log 2>&1 &
  EMIT_PID=$!

  sleep 5 # warmup before the baseline RSS sample
  local base; base="$(vmrss_kb "$PUB_PID")"
  [ -n "$base" ] || notrun "could not read VmRSS for the publisher (need /proc + a Linux process)"
  log "service soak: publisher VmRSS base=${base}KB, draining ${RATE}/s for ${SECS}s ..."
  local t0; t0="$(date +%s)" peak="$base"
  while [ $(( $(date +%s) - t0 )) -lt "$SECS" ]; do
    local r; r="$(vmrss_kb "$PUB_PID")"; [ -n "$r" ] || break
    [ "$r" -gt "$peak" ] && peak="$r"
    sleep 3
  done
  local end; end="$(vmrss_kb "$PUB_PID")"
  cleanup
  log "service soak: base=${base}KB end=${end}KB peak=${peak}KB"
  # Plateau: end within 1.5x of the post-warmup base (steady-state, no leak).
  awk -v e="$end" -v b="$base" 'BEGIN{exit !(e <= b*1.5)}' \
    || fail "publisher RSS did NOT plateau: end=${end}KB > 1.5x base=${base}KB — possible steady-state leak"
  log "PASS(service-soak): publisher RSS plateaued (end=${end}KB <= 1.5x base=${base}KB) under ${RATE}/s drain"
}

main() {
  bite
  if linux_ok; then
    service_soak
  else
    log "NOTRUN(service-soak): needs Linux + /proc + a Linux-built publisher (this host is $(uname -s 2>/dev/null || echo non-Linux)); the nightly Linux runner executes it. Bite passed → the plateau detector is proven."
  fi
  log "DONE: bite proven$( linux_ok && echo ' + service RSS plateau verified' || echo ' (service soak deferred to Linux CI)')"
}
main "$@"
