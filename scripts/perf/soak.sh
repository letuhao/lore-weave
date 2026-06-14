#!/usr/bin/env bash
# scripts/perf/soak.sh
#
# S12 (Inc-4) — soak + the projection/delivery LAG metric (closes
# D-S7-SOAK-LAG-METRIC).
#
# The spine has NO live projection consumer (projections are rebuild-only — S11),
# so the lag that actually matters is DELIVERY lag: how far behind the publisher
# is at draining outbox -> Redis. We emit it as `lw_projection_lag_seconds`
# (= age of the oldest un-published outbox row) plus outbox depth + stream length,
# written as a Prometheus textfile (/tmp/scale-lag.prom) AND logged over time.
#
#   leak-smoke [secs] [rate]  steady emit at <rate>/s while the publisher drains;
#                             assert depth + lag stay BOUNDED (publisher keeps up,
#                             no unbounded backlog / no monotonic growth). CI-able.
#   bite [secs] [rate]        run steady, then throttle the publisher to ~0 (the
#                             extreme of "below emit rate") while emit continues →
#                             lag MUST trend UP (proves the lag detector bites).
#   manual [secs] [rate]      a long real-wall-clock soak (dispatch only — soak
#                             cannot be time-compressed); same sampler, longer T.
#
# Steady emit uses pgbench -R (rate-limited) into a FIXED set of 50 pre-registered
# realities so the publisher (which loads its reality set once at startup) actually
# drains them — wg can't sustain to a fixed reality (seed-derived ids). Verdict:
# NOTRUN(2) setup; FAIL(1) backlog grows under keep-up OR the bite fails to raise
# lag; PASS(0) clean. Requires scale-rig.sh up + migrate.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
ISO_C="scale-pg-shard-0"; META_C="scale-meta-pg"; REDIS_C="scale-redis"; CLIENT_C="scale-pg-shard-1"
SHARD_DB="scale_shard"; META_DB="scale_meta"
SHARD_HOSTPORT="127.0.0.1:55511"; META_HOSTPORT="127.0.0.1:55510"; REDIS_HOSTPORT="127.0.0.1:56510"
SHARD0_PROXY_PORT="${SCALE_SHARD0_PROXY_PORT:-55520}"
# 20 realities: the publisher opens ONE pool per active reality (≤10 conns each),
# so 20 keeps us well under shard-0's max_connections=300 (50 would exhaust it).
NREAL=20
PROM="/tmp/scale-lag.prom"
PGBENCH_SQL="/tmp/scale-emit.sql"

log()    { printf '[soak] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; pub_stop; exit 2; }
fail()   { log "FAIL: $*"; pub_stop; exit 1; }
psqlA()  { docker exec -i "$1" psql -tA -U "$PG_USER" -d "$2" -c "$3"; }

PUB_PID=""
pub_stop() { [ -n "$PUB_PID" ] && kill -9 "$PUB_PID" >/dev/null 2>&1 || true; PUB_PID=""; }
trap pub_stop EXIT

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
PUB="${PUB_BIN:-$(bin services/publisher/pub.exe services/publisher/pub)}" || true

require() {
  docker inspect -f '{{.State.Running}}' "$ISO_C" 2>/dev/null | grep -q true || notrun "$ISO_C not running (scale-rig.sh up)"
  [ -n "$PUB" ] || notrun "publisher not built (go -C services/publisher build -o pub.exe ./cmd/publisher)"
  psqlA "$ISO_C" "$SHARD_DB" "SELECT to_regclass('public.events_outbox')" 2>/dev/null | grep -q events_outbox || notrun "${SHARD_DB} not migrated (scale-rig.sh migrate)"
}

# Register exactly NREAL fixed realities on shard-0 + clear state for a fresh soak.
# TRUNCATE first: the publisher drains EVERY active reality, and prior increments
# (Inc-2 registry seed) left thousands of rows that would each open a pool to
# shard-0 and exhaust its connections.
setup_realities() {
  psqlA "$META_C" "$META_DB" "TRUNCATE reality_registry" >/dev/null || notrun "truncate registry failed"
  psqlA "$META_C" "$META_DB" "INSERT INTO reality_registry
      (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort)
    SELECT ('00000000-0000-0000-0000-'||lpad(g::text,12,'0'))::uuid,'pg-shard-0.internal','${SHARD_DB}','active','en',10,10,20,(g%100)
    FROM generate_series(1,${NREAL}) g ON CONFLICT DO NOTHING" >/dev/null || notrun "register realities failed"
  psqlA "$ISO_C" "$SHARD_DB" "TRUNCATE events_outbox" >/dev/null
  # purge prior soak streams
  for g in $(seq 1 "$NREAL"); do
    redis_rid="$(printf '00000000-0000-0000-0000-%012d' "$g")"
    docker exec "$REDIS_C" redis-cli DEL "lw.events.${redis_rid}" >/dev/null
  done
}

start_publisher() {
  : >/tmp/scale_soak_pub.log
  PUBLISHER_ID=scale-soak-pub SHARD_HOST=pg-shard-0.internal \
    META_DB_URL="postgres://${PG_USER}:${PG_PASS}@${META_HOSTPORT}/${META_DB}?sslmode=disable" \
    REDIS_URL="redis://${REDIS_HOSTPORT}/0" \
    SHARD_DB_USER="$PG_USER" SHARD_DB_PASSWORD="$PG_PASS" SHARD_DB_PORT="$SHARD0_PROXY_PORT" SHARD_DB_SSLMODE=disable \
    PUBLISHER_SHARD_HOST_OVERRIDE="*=127.0.0.1:${SHARD0_PROXY_PORT}" \
    POLL_INTERVAL=300ms BATCH_SIZE=1000 HEARTBEAT_INTERVAL=5s PUBLISHER_HTTP_ADDR=":18099" \
    "$PUB" >>/tmp/scale_soak_pub.log 2>&1 &
  PUB_PID=$!
  sleep 1
  kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/scale_soak_pub.log; notrun "publisher exited at startup"; }
}

# pgbench rate-limited steady emit into the 50 realities (background).
EMIT_PID=""
start_emit() { # rate secs
  # Emit ONLY into the NREAL registered realities (rid 1..NREAL) so every event
  # the publisher can drain — events for an unregistered reality would never be
  # drained and would look like a false backlog leak.
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
    pgbench -n -f "$PGBENCH_SQL" -c 8 -j 4 -R "$1" -T "$2" -h "$ISO_C" -p 5432 -U "$PG_USER" "$SHARD_DB" >/tmp/scale_soak_emit.log 2>&1 &
  EMIT_PID=$!
}

depth() { psqlA "$ISO_C" "$SHARD_DB" "SELECT count(*) FROM events_outbox WHERE published=FALSE" | tr -d '[:space:]'; }
lag()   { psqlA "$ISO_C" "$SHARD_DB" "SELECT COALESCE(EXTRACT(EPOCH FROM now()-min(enqueued_at)),0)::numeric(10,2) FROM events_outbox WHERE published=FALSE" | tr -d '[:space:]'; }

emit_prom() { # depth lag
  cat > "$PROM" <<EOF
# HELP lw_projection_lag_seconds Age of the oldest un-published outbox row (delivery lag).
# TYPE lw_projection_lag_seconds gauge
lw_projection_lag_seconds{shard="pg-shard-0"} ${2}
# HELP lw_outbox_depth Un-published outbox rows.
# TYPE lw_outbox_depth gauge
lw_outbox_depth{shard="pg-shard-0"} ${1}
EOF
}

# sample loop for `secs`, every 2s; echoes "max_depth final_depth final_lag max_lag" via files.
sample_loop() { # secs outfile
  local secs="$1" out="$2" t0 maxd=0 maxl=0 d l
  t0="$(date +%s)"
  while [ $(( $(date +%s) - t0 )) -lt "$secs" ]; do
    d="$(depth)"; l="$(lag)"; emit_prom "$d" "$l"
    [ "${d:-0}" -gt "$maxd" ] 2>/dev/null && maxd="$d"
    awk -v a="$l" -v b="$maxl" 'BEGIN{exit !(a>b)}' && maxl="$l"
    log "  t+$(( $(date +%s) - t0 ))s: depth=${d} lag=${l}s (-> ${PROM})"
    sleep 2
  done
  echo "${maxd} ${d} ${l} ${maxl}" > "$out"
}

cmd_leak_smoke() {
  local secs="${1:-40}" rate="${2:-200}"
  require; setup_realities; start_publisher; start_emit "$rate" "$((secs + 5))"
  log "leak-smoke: emit ${rate}/s for ${secs}s while publisher drains; lag must stay bounded ..."
  local outf; outf="$(mktemp)"; sample_loop "$secs" "$outf"
  read -r maxd fd fl maxl < "$outf"; rm -f "$outf"
  wait "$EMIT_PID" 2>/dev/null || true; pub_stop
  log "leak-smoke: max_depth=${maxd} max_lag=${maxl}s final_depth=${fd} final_lag=${fl}s (emit=${rate}/s)"
  # Publisher keeping up ⇒ backlog bounded. Bound = ~5s of emit; lag never large.
  local bound=$(( rate * 5 ))
  awk -v m="$maxd" -v b="$bound" 'BEGIN{exit !(m < b)}' \
    || fail "max outbox depth ${maxd} >= ${bound} (~5s of emit) — publisher NOT keeping up / backlog growing"
  awk -v m="$maxl" 'BEGIN{exit !(m < 5)}' \
    || fail "max lag ${maxl}s >= 5s under keep-up — delivery falling behind"
  log "PASS(leak-smoke): depth + lag bounded under steady ${rate}/s emit — no backlog growth, publisher keeps up"
}

cmd_bite() {
  local secs="${1:-30}" rate="${2:-200}"
  require; setup_realities; start_publisher; start_emit "$rate" "$((secs + 10))"
  log "bite: steady ${rate}/s with publisher draining; baseline lag ..."
  sleep 6; local l0; l0="$(lag)"; local d0; d0="$(depth)"
  log "  baseline: depth=${d0} lag=${l0}s"
  log "bite: THROTTLE publisher to ~0 (kill the drain) while emit continues — lag MUST climb ..."
  pub_stop
  local outf; outf="$(mktemp)"; sample_loop "$secs" "$outf"
  read -r maxd fd fl maxl < "$outf"; rm -f "$outf"
  wait "$EMIT_PID" 2>/dev/null || true
  log "bite: baseline lag=${l0}s → final lag=${fl}s (depth ${d0}→${fd})"
  awk -v a="$fl" -v b="$l0" 'BEGIN{exit !(a > b + 2)}' \
    && log "PASS(bite): throttling the publisher made lag trend UP (${l0}s→${fl}s) — the lag metric bites" \
    || fail "lag did NOT climb after throttling the publisher (${l0}s→${fl}s) — the lag metric is vacuous"
}

cmd_manual() { cmd_leak_smoke "${1:-3600}" "${2:-200}"; }

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    leak-smoke) cmd_leak_smoke "$@" ;;
    bite)       cmd_bite "$@" ;;
    manual)     cmd_manual "$@" ;;
    *) echo "usage: $0 {leak-smoke|bite|manual} [secs] [rate]" >&2; exit 2 ;;
  esac
}
main "$@"
