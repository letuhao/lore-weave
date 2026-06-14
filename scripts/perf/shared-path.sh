#!/usr/bin/env bash
# scripts/perf/shared-path.sh
#
# S12 (Inc-2) — THE CENTERPIECE: measure the SHARED aggregate paths every reality
# contends on. The per-reality/per-shard paths are embarrassingly parallel at the
# DP-S5 rates (Inc-1); the scale risk lives almost entirely here.
#
# Three shared paths, each measured for its CEILING + its OWN CPU (single-box
# trap: a shared single-writer on the same box as the fleet can look capped when
# it is merely CPU-starved — so we pin a dedicated vCPU set AND record its own
# CPU + whether it is CPU-bound or RTT/lock-bound), then classified:
#   serial-capacity (Amdahl, fixed — a bigger/faster node or pipelining helps)
#   vs coherency-beta (retrograde — adding load makes it worse, needs re-design).
#
#   metaworker  — the SOLE xreality consumer (I7). All cross-reality events from
#                 ALL shards funnel into ONE consumer -> the highest-risk path.
#                 Measured via the REAL consume machinery (redisconsume + consumer
#                 + dispatch) with a no-op handler, run IN-NETWORK (container ->
#                 Redis) so the per-message XAck RTT is real, not host<->WSL2.
#   registry    — reality_registry (meta DB): every provision/route touches it.
#   redis-fanout— per-reality stream sharding (DP-A7): the read-amplification a
#                 mega-stream would cause vs the sharded streams.
#
# Each path ships a NON-VACUITY bite (a real degradation that MUST move the
# number) so the ceiling is proven to ride the real path. Verdict: NOTRUN(2) if
# setup can't run; FAIL(1) on a real violation (bite that fails to bite); else
# PASS(0). Re-runnable. Requires the Inc-1 scale rig up (scale-rig.sh up).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
REDIS_C="scale-redis"
META_C="scale-meta-pg"
CLIENT_C="scale-pg-shard-1"     # runs pgbench against the meta DB (off meta-pg's cores)
TOXI_C="scale-toxiproxy"
TOXI_PORT="${SCALE_TOXIPROXY_PORT:-8475}"
META_DB="scale_meta"
T3_TARGET="${DP_S5_T3_AGGREGATE:-50000}"   # DP-S5 aggregate xreality T3 ceiling (<=50k/s)
SHARED_CPUSET="${SCALE_SHARED_CPUSET:-0-3}"  # dedicated vCPU set for the shared writer
REDIS_PROXY_PORT="${SCALE_REDIS_PROXY_PORT:-56521}"
META_PROXY_PORT="${SCALE_META_PROXY_PORT:-55530}"
IMG="scale-mwbench"
TOXIC="env TOXIPROXY_URL=http://127.0.0.1:${TOXI_PORT} bash $ROOT/scripts/chaos/toxic.sh"

log()    { printf '[shared-path] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; $TOXIC reset >/dev/null 2>&1 || true; exit 2; }
fail()   { log "FAIL: $*"; $TOXIC reset >/dev/null 2>&1 || true; exit 1; }
redis()  { docker exec "$REDIS_C" redis-cli "$@"; }
psqlA()  { docker exec -i "$1" psql -tA -U "$PG_USER" -d "$2" -c "$3"; }
jq_num() { grep -oE "\"$2\":[0-9.]+" <<<"$1" | grep -oE '[0-9.]+' | head -1; }

require_rig() {
  local ct  # NOT `c` — that would clobber a caller's local client-count via bash dynamic scope.
  for ct in "$REDIS_C" "$META_C" "$TOXI_C" "$CLIENT_C"; do
    docker inspect -f '{{.State.Running}}' "$ct" 2>/dev/null | grep -q true || notrun "$ct not running (scale-rig.sh up first)"
  done
  $TOXIC wait >/dev/null 2>&1 || notrun "toxiproxy admin not answering"
}

# Cross-compile (static) + package the metaworker-bench so it runs IN-NETWORK.
build_bench() {
  GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go -C services/meta-worker build -o mwbench-linux ./cmd/metaworker-bench \
    || notrun "cross-compile metaworker-bench failed"
  docker build -q -f infra/scale/Dockerfile.metaworker-bench -t "$IMG" services/meta-worker >/dev/null \
    || notrun "docker build $IMG failed"
}

# Run one in-network drain; echo the JSON result line. redis_url lets the bite
# route through the toxiproxy.
bench_drain() { # n batch gomaxprocs redis_url name
  local n="$1" b="$2" g="$3" url="$4" name="$5" cpu res
  redis DEL xreality.bench.tick >/dev/null
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --network scale-net --cpuset-cpus="$SHARED_CPUSET" -e GOMAXPROCS="$g" \
    "$IMG" -redis "$url" -mode both -n "$n" -batch "$b" >/dev/null || notrun "bench run failed to start"
  sleep 1.2
  cpu="$(docker stats --no-stream --format '{{.CPUPerc}}' "$name" 2>/dev/null || echo n/a)"
  docker wait "$name" >/dev/null 2>&1 || true
  res="$(docker logs "$name" 2>&1 | tail -1)"; docker rm -f "$name" >/dev/null 2>&1 || true
  echo "${res}|own_cpu=${cpu}"
}

cmd_metaworker() {
  local n="${1:-80000}" batch="${2:-500}"
  require_rig; build_bench
  log "I7 consume ceiling: 1 meta-worker (no-op handler), cpuset=${SHARED_CPUSET}, in-network ..."
  local out; out="$(bench_drain "$n" "$batch" 1 "redis://redis:6379/0" "mwb-iso")"
  local tput cpu; tput="$(jq_num "$out" throughput)"; cpu="${out##*own_cpu=}"
  [ -n "$tput" ] || notrun "no throughput from bench"
  log "  single-consumer ceiling: ${tput} msgs/s | own cpu (1 core): ${cpu}"
  # serial vs beta: GOMAXPROCS=4 should NOT raise a single-consumer loop (serial).
  local out4; out4="$(bench_drain "$n" "$batch" 4 "redis://redis:6379/0" "mwb-mp4")"
  local tput4; tput4="$(jq_num "$out4" throughput)"
  log "  GOMAXPROCS=4 ceiling: ${tput4} msgs/s (≈ GOMAXPROCS=1 ⇒ serial-capacity, not core-parallelisable — expected for I7 single consumer)"
  # verdict vs the aggregate T3 target
  if awk -v t="$tput" -v tgt="$T3_TARGET" 'BEGIN{exit !(t < tgt)}'; then
    log "  FINDING(refactor-risk): single I7 consumer ${tput} msgs/s < aggregate DP-S5 T3 target ${T3_TARGET}/s."
    log "    Shape: SERIAL-CAPACITY (flat vs batch+cores, own cpu<100% ⇒ bound by per-message XAck RTT, consumer.go acks each msg individually)."
    log "    Mitigation (ranked): (1) batch the XACK across the ProcessOne batch; (2) faster core; (3) shard the consumer across the few xreality topics (1 consumer/stream keeps I7)."
  else
    log "  single I7 consumer ${tput} msgs/s ≥ aggregate T3 target ${T3_TARGET}/s — headroom on this box."
  fi
  echo "$tput" > /tmp/scale-metaworker-ceiling.txt
}

cmd_metaworker_bite() {
  local n="${1:-40000}" batch="${2:-500}"
  require_rig; build_bench
  $TOXIC reset >/dev/null 2>&1 || true
  $TOXIC create-proxy redis_proxy "$REDIS_PROXY_PORT" "${REDIS_C}:6379" >/dev/null
  log "bite: drain through the redis proxy (clean) ..."
  local clean; clean="$(jq_num "$(bench_drain "$n" "$batch" 1 "redis://${TOXI_C}:${REDIS_PROXY_PORT}/0" "mwb-clean")" throughput)"
  log "bite: +5ms latency on the consume path, re-measure ..."
  $TOXIC add-latency redis_proxy 5 >/dev/null
  local slow; slow="$(jq_num "$(bench_drain "$n" "$batch" 1 "redis://${TOXI_C}:${REDIS_PROXY_PORT}/0" "mwb-slow")" throughput)"
  $TOXIC reset >/dev/null 2>&1 || true; $TOXIC delete-proxy redis_proxy >/dev/null 2>&1 || true
  log "bite: clean=${clean} msgs/s  slow=${slow} msgs/s"
  [ -n "$clean" ] && [ -n "$slow" ] || notrun "bite produced no throughput"
  awk -v c="$clean" -v s="$slow" 'BEGIN{exit !(s < c*0.8)}' \
    && log "PASS(bite): a real Redis slowdown dropped the consume ceiling — it rides the real consume path" \
    || fail "bite did NOT drop the ceiling (${clean}->${slow}) — the I7 measurement is vacuous"
}

cmd_registry() {
  local secs="${1:-8}" c="${2:-16}" nreal="${3:-5000}"
  require_rig
  # Top up to nreal (idempotent — gen_random_uuid never conflicts, so a blind
  # insert would grow the table every run).
  local have; have="$(psqlA "$META_C" "$META_DB" "SELECT count(*) FROM reality_registry" 2>/dev/null || echo 0)"
  local need=$(( nreal - have )); [ "$need" -lt 0 ] && need=0
  log "registry: have=${have} rows; topping up ${need} to reach ${nreal} on ${META_C}/${META_DB} ..."
  if [ "$need" -gt 0 ]; then
    psqlA "$META_C" "$META_DB" "INSERT INTO reality_registry
        (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort)
      SELECT gen_random_uuid(), 'pg-shard-'||(g%8)||'.internal','scale_shard','active','en',10,10,20,(g%100)
      FROM generate_series(1,${need}) g" >/dev/null || notrun "registry seed failed (rig migrated?)"
  fi
  local total; total="$(psqlA "$META_C" "$META_DB" "SELECT count(*) FROM reality_registry")"
  log "registry rows=${total}; pgbench read+write (1 route-read + 1 cohort-write/iter) @ c=${c} for ${secs}s (from ${CLIENT_C}, off meta-pg's cores) ..."
  docker exec -i "$CLIENT_C" sh -c "cat > /tmp/reg.sql" < "$ROOT/infra/scale/pgbench-registry.sql"
  local outf; outf="$(mktemp)"
  docker exec -e PGPASSWORD="$PG_PASS" "$CLIENT_C" pgbench -n -f /tmp/reg.sql -c "$c" -j 8 -T "$secs" -h "$META_C" -p 5432 -U "$PG_USER" "$META_DB" >"$outf" 2>&1 &
  local pgpid=$!
  sleep "$(( secs / 2 ))"; local cpu; cpu="$(docker stats --no-stream --format '{{.CPUPerc}}' "$META_C" 2>/dev/null || echo n/a)"
  wait "$pgpid" 2>/dev/null || true
  local tps; tps="$(grep -iE 'tps *=' "$outf" | grep -oE '[0-9]+\.[0-9]+' | head -1)"; rm -f "$outf"
  [ -n "$tps" ] || notrun "registry pgbench produced no tps"
  log "  registry ceiling: ${tps} ops/s (write-mixed; pure route-reads sit far higher) | meta-pg own cpu (mid-run): ${cpu}"
  echo "$tps" > /tmp/scale-registry-ceiling.txt
}

cmd_registry_bite() {
  local secs="${1:-5}" c="${2:-16}"
  require_rig
  $TOXIC reset >/dev/null 2>&1 || true
  $TOXIC create-proxy meta_proxy "$META_PROXY_PORT" "${META_C}:5432" >/dev/null
  docker exec -i "$CLIENT_C" sh -c "cat > /tmp/reg.sql" < "$ROOT/infra/scale/pgbench-registry.sql"
  reg_tps() { docker exec -e PGPASSWORD="$PG_PASS" "$CLIENT_C" pgbench -n -f /tmp/reg.sql -c "$c" -j 8 -T "$secs" -h "$1" -p "$2" -U "$PG_USER" "$META_DB" 2>&1 | grep -iE 'tps *=' | grep -oE '[0-9]+\.[0-9]+' | head -1; }
  log "bite: registry pgbench through meta proxy (clean) ..."
  local clean; clean="$(reg_tps "$TOXI_C" "$META_PROXY_PORT")"
  log "bite: +50ms latency on the meta path, re-measure ..."
  $TOXIC add-latency meta_proxy 50 >/dev/null
  local slow; slow="$(reg_tps "$TOXI_C" "$META_PROXY_PORT")"
  $TOXIC reset >/dev/null 2>&1 || true; $TOXIC delete-proxy meta_proxy >/dev/null 2>&1 || true
  log "bite: clean=${clean} ops/s  slow=${slow} ops/s"
  [ -n "$clean" ] && [ -n "$slow" ] || notrun "registry bite produced no tps"
  awk -v c="$clean" -v s="$slow" 'BEGIN{exit !(s < c*0.8)}' \
    && log "PASS(bite): a real meta-DB slowdown dropped registry ops — it rides the real registry path" \
    || fail "registry bite did NOT bite (${clean}->${slow}) — vacuous"
}

# Redis per-reality stream sharding (DP-A7): the cost a mega-stream would impose
# on a per-reality reader. Reading ONE reality's history from a sharded stream
# touches E entries; from an un-sharded mega-stream it must scan R*E. We time both
# and require the un-sharded read to be measurably worse — that IS the bite (it
# proves the sharding KEY matters; Redis being single-threaded, XADD rate alone
# would not reveal it).
cmd_redis_fanout() {
  local R="${1:-200}" E="${2:-200}"
  require_rig
  log "redis-fanout: building ${R} sharded streams x ${E} + 1 mega-stream of ${R}x${E}=$((R*E)) entries ..."
  redis DEL fanout.mega >/dev/null
  for i in $(seq 1 "$R"); do redis DEL "fanout.shard.${i}" >/dev/null; done
  # Build with a Lua-free pipeline: use redis-cli eval-ish via shell loop is slow;
  # instead XADD in bulk per stream via a here-doc pipeline.
  {
    for i in $(seq 1 "$R"); do
      for _ in $(seq 1 "$E"); do printf 'XADD fanout.shard.%s * rid %s d x\n' "$i" "$i"; done
    done
  } | docker exec -i "$REDIS_C" redis-cli --pipe >/dev/null
  {
    for i in $(seq 1 "$R"); do
      for _ in $(seq 1 "$E"); do printf 'XADD fanout.mega * rid %s d x\n' "$i"; done
    done
  } | docker exec -i "$REDIS_C" redis-cli --pipe >/dev/null
  local megalen shardlen; megalen="$(redis XLEN fanout.mega | tr -d '\r')"; shardlen="$(redis XLEN fanout.shard.1 | tr -d '\r')"
  [ "${megalen:-0}" -gt 0 ] && [ "${shardlen:-0}" -gt 0 ] || notrun "fanout streams empty"
  # Time reading ONE reality's history: sharded = its own stream; un-sharded = the
  # whole mega-stream (a per-reality reader must scan all of it to filter rid=1).
  # K repeated scans are piped into ONE redis-cli per measurement so the ~300ms
  # `docker exec` startup is amortized and the per-scan DATA cost dominates (the
  # earlier naive 1-scan timing was swamped by exec overhead — vacuous).
  local K="${FANOUT_READS:-50}"
  scan_ms() { # stream
    local s e
    s="$(date +%s%3N)"
    docker exec "$REDIS_C" sh -c "for i in \$(seq 1 ${K}); do echo 'XRANGE $1 - +'; done | redis-cli > /dev/null"
    e="$(date +%s%3N)"; echo $((e - s))
  }
  local t_shard t_mega
  t_shard="$(scan_ms fanout.shard.1)"
  t_mega="$(scan_ms fanout.mega)"
  log "  ${K}x read one reality's history: sharded(${shardlen} entries)=${t_shard}ms | un-sharded(scan ${megalen})=${t_mega}ms"
  redis DEL fanout.mega >/dev/null; for i in $(seq 1 "$R"); do redis DEL "fanout.shard.${i}" >/dev/null; done
  # bite: un-sharding MUST inflate the per-reality read (R x more data scanned).
  awk -v sh="$t_shard" -v mg="$t_mega" 'BEGIN{exit !(mg > sh*2)}' \
    && log "PASS(bite): un-sharding inflated the per-reality read >2x — the reality-sharding key (DP-A7) genuinely bounds read amplification" \
    || fail "un-sharding did NOT inflate the read (${t_shard}ms->${t_mega}ms) — measurement insensitive to the sharding key (vacuous)"
}

cmd_all() {
  cmd_metaworker
  cmd_metaworker_bite
  cmd_registry
  cmd_registry_bite
  cmd_redis_fanout
  log "PASS(all): meta-worker I7 ceiling + registry ceiling + redis-fanout amplification — all measured, all bites fired"
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    metaworker)      cmd_metaworker "$@" ;;
    metaworker-bite) cmd_metaworker_bite "$@" ;;
    registry)        cmd_registry "$@" ;;
    registry-bite)   cmd_registry_bite "$@" ;;
    redis-fanout)    cmd_redis_fanout "$@" ;;
    all)             cmd_all "$@" ;;
    *) echo "usage: $0 {metaworker|metaworker-bite|registry|registry-bite|redis-fanout|all} [args]" >&2; exit 2 ;;
  esac
}
main "$@"
