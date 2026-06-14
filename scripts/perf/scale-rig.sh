#!/usr/bin/env bash
# scripts/perf/scale-rig.sh
#
# S12 (Inc-1) — the multi-shard SCALE rig: real separate-Postgres shards +
# per-node packing sweep + raw-PG cross-check + real cross-shard seed.
#
# WHY a NEW rig (vs S5/S6/S8/S11 which run many DBs on ONE postgres): the scale
# question "how many realities can one shard hold" only has a meaning if a shard
# is a REAL isolated Postgres process — one not sharing its buffer cache / WAL /
# fsync queue with the other shards. So this brings up N independent postgres:16
# instances (infra/scale/docker-compose.scale.yml) and measures ONE of them in
# isolation. Driving wg across all N also gives the FIRST real cross-shard run,
# closing D-WORKLOAD-GEN-REAL-SHARD.
#
# Subcommands:
#   up [N]                 boot meta + redis + toxiproxy + first N shards (N=SCALE_SHARDS)
#   down                   tear the rig down (-v, drops all shard volumes)
#   migrate [N]            create the meta + per-shard event/outbox schema
#   crossshard [N] [seed]  seed realities spread across N real shards; PROVE events
#                          land on >=2 distinct PG instances (closes D-WORKLOAD-GEN-REAL-SHARD)
#   pack [rungs] [secs]    per-node PACKING sweep on the ISOLATED shard (pgbench
#                          concurrency curve = raw-PG write ceiling) -> USL-ready JSON
#   spine-overhead [N] [s] wg sustained spine emit/s vs pgbench at same N -> overhead ratio
#   pgbench [secs] [c]     one raw-PG ceiling point on the isolated shard
#   bite [N]               NON-VACUITY: pgbench at N through the shard proxy, clean vs
#                          +latency -> throughput MUST drop (proves the sweep rides the real path)
#   smoke                  up + migrate + crossshard + pack + spine-overhead + pgbench + bite (small N)
#
# Verdict convention (S6/S8/S11): infra/setup couldn't run -> NOTRUN (2, never a
# flaky nightly fail). A real violation (e.g. cross-shard didn't spread; bite did
# NOT drop throughput) -> FAIL (1). Clean -> PASS (0). Re-runnable.
#
# Honesty rails wired in (spec §2/§3):
#  - PG durability is PRODUCTION-shaped (fsync/synchronous_commit ON — set in the
#    compose, asserted by `pg_settings` here). An off run is a fiction; we refuse it.
#  - The isolated shard is cpuset-pinnable (SCALE_SHARD0_CPUSET) and its OWN CPU is
#    recorded per rung (single-box trap). The pgbench CLIENT runs from a DIFFERENT
#    container so client CPU never steals from the measured shard's pinned cores.
#  - pgbench TPS = the RAW-PG write ceiling (no Go/validation) = an UPPER bound;
#    the wg spine-overhead ratio derates it to the realistic spine ceiling.
set -euo pipefail

# Git-Bash/MSYS rewrites any argument that looks like a Unix path (e.g. an
# in-container `/tmp/...` passed to `docker exec`) into a Windows path before the
# native docker.exe sees it — which made pgbench look for the script at
# C:/Users/.../Temp/... INSIDE the container. Disable that rewrite globally; every
# host path this script passes to a native exe is relative (no leading slash) so
# nothing else depends on the conversion.
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE="infra/scale/docker-compose.scale.yml"
PROJECT="scale"
PG_USER="foundation"; PG_PASS="foundation"
SHARDS="${SCALE_SHARDS:-4}"          # how many shard PGs to bring up / spread across
SHARD_DB="scale_shard"               # the per-shard event DB (one per PG instance)
META_DB="scale_meta"
ISO_C="scale-pg-shard-0"             # the ISOLATED shard we measure
CLIENT_C="scale-meta-pg"            # runs pgbench (NOT on the isolated cpuset)
TOXI_C="scale-toxiproxy"
TOXI_PORT="${SCALE_TOXIPROXY_PORT:-8475}"
SHARD0_PROXY_PORT="${SCALE_SHARD0_PROXY_PORT:-55520}"
SHARD0_CPUSET="${SCALE_SHARD0_CPUSET:-}"   # e.g. "0-3"; empty = unpinned (with a loud warning)
PACK_RUNGS="${PACK_RUNGS:-1 2 4 8}"
PACK_SECS="${PACK_SECS:-8}"
PGBENCH_SQL="/tmp/scale-pgbench-event-insert.sql"
DP_S5_PER_REALITY="${DP_S5_PER_REALITY:-550}"   # ~500 T2/s + 50 T3/s per reality (DP-S5)
TOXIC="env TOXIPROXY_URL=http://127.0.0.1:${TOXI_PORT} bash $ROOT/scripts/chaos/toxic.sh"

log()    { printf '[scale-rig] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
dc()     { docker compose -p "$PROJECT" -f "$COMPOSE" "$@"; }
# psql against (container, db) — tab-separated, ON_ERROR_STOP.
psql_c() { docker exec -i "$1" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$2" "${@:3}"; }
psqlA()  { docker exec -i "$1" psql -tA -U "$PG_USER" -d "$2" -c "$3"; }

shard_container() { echo "scale-pg-shard-$1"; }
shard_host_port() { echo "127.0.0.1:$((55511 + $1))"; }   # matches compose port map
# logical db_host for the registry — MUST match reality_registry's CHECK
# (^pg-shard-[0-9]+\.(internal|prod|staging)$).
shard_logical()   { echo "pg-shard-$1.internal"; }

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
WG="${WG_BIN:-$(bin tests/workload-gen/wg.exe tests/workload-gen/wg)}" || notrun "workload-gen not built (go build -C tests/workload-gen -o wg ./cmd/workload-gen)"

# ── shard / meta schema ──────────────────────────────────────────────────────
migrate_one_shard() { # container
  local c="$1"
  psql_c "$c" foundation -c "DROP DATABASE IF EXISTS ${SHARD_DB}" >/dev/null
  psql_c "$c" foundation -c "CREATE DATABASE ${SHARD_DB}" >/dev/null
  for m in 0001_initial 0002_events_table 0005_events_outbox_table; do
    docker exec -i "$c" psql -q -U "$PG_USER" -d "$SHARD_DB" < "contracts/migrations/per_reality/${m}.up.sql"
  done
  # A DEFAULT partition catches every recorded_at month (the rig isn't running the
  # 7-day-ahead partition manager) so all inserts land.
  psql_c "$c" "$SHARD_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
}

migrate_meta() {
  psql_c "$CLIENT_C" foundation -c "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null
  psql_c "$CLIENT_C" foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
  for m in 001_reality_registry 003_publisher_heartbeats; do
    docker exec -i "$CLIENT_C" psql -q -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql"
  done
}

# Refuse a durability-faked run (honesty rail): the isolated shard MUST have
# fsync=on AND synchronous_commit=on, else the ceiling is a fiction.
assert_production_durability() {
  local fsync sc
  fsync="$(psqlA "$ISO_C" foundation "SHOW fsync" | tr -d '[:space:]')"
  sc="$(psqlA "$ISO_C" foundation "SHOW synchronous_commit" | tr -d '[:space:]')"
  log "durability on ${ISO_C}: fsync=${fsync} synchronous_commit=${sc}"
  [ "$fsync" = "on" ] || notrun "fsync is '${fsync}', not on — packing ceiling would be inflated fiction"
  case "$sc" in on|local|remote_apply|remote_write) ;; *) notrun "synchronous_commit='${sc}' is async — refusing" ;; esac
}

pin_isolated_shard() {
  if [ -n "$SHARD0_CPUSET" ]; then
    docker update --cpuset-cpus="$SHARD0_CPUSET" "$ISO_C" >/dev/null
    log "pinned ${ISO_C} to cpuset ${SHARD0_CPUSET} (dedicated vCPU set — single-box trap guard)"
  else
    log "WARN: SCALE_SHARD0_CPUSET unset — isolated shard NOT pinned; its ceiling may be a CPU-starvation artifact (set e.g. SCALE_SHARD0_CPUSET=0-3 for an honest number)"
  fi
}

# Sample the isolated shard's OWN CPU% + block IO (single-box trap evidence).
shard_own_cpu() { docker stats --no-stream --format '{{.CPUPerc}}|{{.BlockIO}}|{{.MemUsage}}' "$ISO_C" 2>/dev/null || echo "n/a|n/a|n/a"; }

wait_healthy() { # container...
  local c  # local — bash dynamic scope would otherwise leak this into a caller's `c`
  for c in "$@"; do
    for _ in $(seq 1 60); do
      docker exec "$c" pg_isready -U "$PG_USER" >/dev/null 2>&1 && break
      sleep 1
    done
    docker exec "$c" pg_isready -U "$PG_USER" >/dev/null 2>&1 || notrun "shard ${c} never became ready"
  done
}

# ── subcommands ──────────────────────────────────────────────────────────────
cmd_up() {
  local n="${1:-$SHARDS}" k
  local svcs=(meta-pg redis toxiproxy)
  for k in $(seq 0 $((n - 1))); do svcs+=("pg-shard-$k"); done
  log "bringing up meta + redis + toxiproxy + ${n} shard(s): ${svcs[*]}"
  dc up -d "${svcs[@]}" >/dev/null
  local conts=("$CLIENT_C")
  for k in $(seq 0 $((n - 1))); do conts+=("$(shard_container "$k")"); done
  wait_healthy "${conts[@]}"
  $TOXIC wait >/dev/null 2>&1 || notrun "toxiproxy admin API never answered"
  $TOXIC create-proxy shard0 "$SHARD0_PROXY_PORT" "${ISO_C}:5432" >/dev/null
  log "rig up: ${n} shards healthy, shard0 proxy on :${SHARD0_PROXY_PORT}"
}

cmd_down() { log "tearing down rig (-v)"; dc down -v >/dev/null 2>&1 || true; }

cmd_migrate() {
  local n="${1:-$SHARDS}" k
  log "migrating meta + ${n} shard schemas ..."
  migrate_meta
  for k in $(seq 0 $((n - 1))); do migrate_one_shard "$(shard_container "$k")"; done
  log "schema applied (meta + ${n} shards)"
}

# Real cross-shard: emit one reality's stream to EACH of N shards, register each
# in the meta reality_registry with its real db_host, and PROVE events exist on
# >=2 distinct PG INSTANCES (not >=2 DBs on one instance). This is the artifact
# that closes D-WORKLOAD-GEN-REAL-SHARD.
cmd_crossshard() {
  local n="${1:-$SHARDS}" seed="${2:-100}" k
  [ "$n" -ge 2 ] || notrun "cross-shard needs N>=2 (got ${n})"
  log "seeding ${n} shards (one reality each) via the real spine emit path ..."
  local instances_with_events=0
  for k in $(seq 0 $((n - 1))); do
    local c dsn rid nev host
    c="$(shard_container "$k")"
    dsn="postgres://${PG_USER}:${PG_PASS}@$(shard_host_port "$k")/${SHARD_DB}?sslmode=disable"
    "$WG" -seed "$((seed + k))" -profile single-reality -emit -dsn "$dsn" 2>/dev/null \
      || notrun "wg emit to shard ${k} failed (rig not migrated?)"
    nev="$(psqlA "$c" "$SHARD_DB" "SELECT count(*) FROM events")"
    [ "${nev:-0}" -gt 0 ] || fail "shard ${k} has 0 events after emit — cross-shard spread broken"
    instances_with_events=$((instances_with_events + 1))
    # register every reality on this shard in the meta registry, pointing at the
    # shard's REAL logical host (so the publisher fleet / Inc-2 can route to it).
    host="$(shard_logical "$k")"
    for rid in $(psqlA "$c" "$SHARD_DB" "SELECT DISTINCT reality_id FROM events"); do
      psql_c "$CLIENT_C" "$META_DB" -c "INSERT INTO reality_registry
          (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort)
        VALUES ('${rid}','${host}','${SHARD_DB}','active','en',10,10,20,5)
        ON CONFLICT (reality_id) DO NOTHING" >/dev/null
    done
    log "  shard ${k} (${host}): events=${nev}"
  done
  # The closing assertion: distinct PG instances each holding events.
  [ "$instances_with_events" -ge 2 ] \
    || fail "only ${instances_with_events} instance(s) hold events — not real cross-shard"
  local reg
  reg="$(psqlA "$CLIENT_C" "$META_DB" "SELECT count(DISTINCT db_host) FROM reality_registry WHERE status='active'")"
  [ "${reg:-0}" -ge 2 ] || fail "registry spans only ${reg} db_host(s) — cross-shard routing not recorded"
  log "PASS(cross-shard): ${instances_with_events} distinct PG instances hold events; registry spans ${reg} db_hosts (D-WORKLOAD-GEN-REAL-SHARD closed)"
}

# pgbench against the isolated shard FROM the client container (so the load
# generator's CPU is off the measured shard's pinned cores). host/port let the
# bite redirect through the toxiproxy. Echoes the TPS (float).
# Write the pgbench workload into the client container via stdin (NOT `docker cp`,
# whose host-side source path is an MSYS path docker.exe can't always resolve).
ensure_pgbench_sql() {
  docker exec -i "$CLIENT_C" sh -c "cat > $PGBENCH_SQL" < "$ROOT/infra/scale/pgbench-event-insert.sql"
}

pgbench_tps() { # secs clients host port db
  local secs="$1" c="$2" host="$3" port="$4" db="$5" out
  ensure_pgbench_sql
  out="$(docker exec -e PGPASSWORD="$PG_PASS" "$CLIENT_C" \
      pgbench -n -f "$PGBENCH_SQL" -c "$c" -j "$(( c < 8 ? c : 8 ))" -T "$secs" \
      -h "$host" -p "$port" -U "$PG_USER" "$db" 2>&1)" || { echo "$out" >&2; echo "0"; return; }
  # pgbench prints "tps = NNN.NN (without initial connection time)" on recent versions.
  printf '%s\n' "$out" | grep -iE 'tps *=' | grep -oE '[0-9]+\.[0-9]+' | head -1
}

cmd_pgbench() {
  local secs="${1:-$PACK_SECS}" c="${2:-8}"
  assert_production_durability
  local tps; tps="$(pgbench_tps "$secs" "$c" "$ISO_C" 5432 "$SHARD_DB")"
  [ -n "$tps" ] || fail "pgbench produced no TPS (is the shard migrated?)"
  log "pgbench raw-PG: ${tps} tps (events/s) @ c=${c} on ${ISO_C}"
  echo "$tps"
}

# Per-node packing sweep: pgbench concurrency curve on the isolated shard. Each
# txn = 1 event + 1 outbox row (the spine T2 write shape), so tps ~= events/s.
# Emits a USL-ready JSON series {n,throughput} + the OWN-CPU per rung.
cmd_pack() {
  local rungs="${1:-$PACK_RUNGS}" secs="${2:-$PACK_SECS}" n
  assert_production_durability
  pin_isolated_shard
  log "packing sweep on ${ISO_C}: rungs=[${rungs}] secs=${secs} (raw-PG write ceiling)"
  local json="["; local first=1
  for n in $rungs; do
    # sample OWN CPU mid-run: launch a background sampler, run pgbench, collect.
    local cpufile; cpufile="$(mktemp)"
    ( sleep "$(( secs / 2 ))"; shard_own_cpu > "$cpufile" ) &
    local sampler=$!
    local tps; tps="$(pgbench_tps "$secs" "$n" "$ISO_C" 5432 "$SHARD_DB")"
    wait "$sampler" 2>/dev/null || true
    local cpu; cpu="$(cat "$cpufile" 2>/dev/null || echo 'n/a|n/a|n/a')"; rm -f "$cpufile"
    [ -n "$tps" ] || { tps="0"; }
    log "  N=${n}: throughput=${tps} ev/s | shard own cpu|io|mem=${cpu}"
    [ "$first" = 1 ] && first=0 || json+=","
    json+="{\"n\":${n},\"throughput\":${tps:-0},\"own_cpu\":\"${cpu%%|*}\"}"
  done
  json+="]"
  printf '%s\n' "$json" > /tmp/scale-pack-series.json
  log "USL-ready series -> /tmp/scale-pack-series.json"
  printf '%s\n' "$json"
  # Translate the top rung to a packing estimate vs the DP-S5 per-reality rate.
  local top; top="$(printf '%s' "$json" | grep -oE '"throughput":[0-9.]+' | grep -oE '[0-9.]+' | sort -g | tail -1)"
  if [ -n "$top" ]; then
    local pack; pack="$(awk -v t="$top" -v r="$DP_S5_PER_REALITY" 'BEGIN{ if(r>0) printf "%.0f", t/r; else print "n/a" }')"
    log "raw-PG packing UPPER BOUND: ~${pack} realities/shard at ${DP_S5_PER_REALITY} ev/s each at this rung set (the realistic spine figure comes from the Inc-3 long-lived emitter, not from this raw ceiling)"
  fi
}

# Spine-path liveness + a CONSERVATIVE emit floor — NOT a clean per-event overhead
# number. wg is one-shot per process, so this loops wg with rotating seeds; each
# invocation pays Go process startup + a fresh connection, which DOMINATES the
# measured rate. So treat the wg ev/s as a "the real spine emit path commits events
# under concurrency" sanity + a hard floor, NOT as the spine's per-event cost. The
# CLEAN spine throughput (a long-lived command-processor, no per-event spawn) is
# measured by the Inc-3 roleplay load-skeleton; the honest spine-vs-raw ratio lives
# there. We deliberately do NOT derive a packing derate from this spawn-bound ratio.
cmd_spine_overhead() {
  local n="${1:-4}" secs="${2:-$PACK_SECS}"
  assert_production_durability
  local dsn deadline; dsn="postgres://${PG_USER}:${PG_PASS}@$(shard_host_port 0)/${SHARD_DB}?sslmode=disable"
  log "spine-overhead: ${n} concurrent wg emitters for ${secs}s vs pgbench raw @ c=${n}"
  deadline=$(( $(date +%s) + secs ))
  local pids=() outs=()
  for w in $(seq 0 $((n - 1))); do
    local of; of="$(mktemp)"; outs+=("$of")
    (
      tot=0 i=0
      while [ "$(date +%s)" -lt "$deadline" ]; do
        seed=$(( 1000000 * (w + 1) + i ))
        m="$("$WG" -seed "$seed" -profile single-reality -emit -dsn "$dsn" 2>&1 | grep -oiE 'emitted [0-9]+' | grep -oE '[0-9]+' || true)"
        tot=$(( tot + ${m:-0} )); i=$((i + 1))
      done
      echo "$tot" > "$of"
    ) &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p" 2>/dev/null || true; done
  local total=0; for of in "${outs[@]}"; do total=$(( total + $(cat "$of" 2>/dev/null || echo 0) )); rm -f "$of"; done
  local spine; spine="$(awk -v t="$total" -v s="$secs" 'BEGIN{ printf "%.1f", t/s }')"
  local raw; raw="$(pgbench_tps "$secs" "$n" "$ISO_C" 5432 "$SHARD_DB")"
  [ "${total:-0}" -gt 0 ] || fail "wg emitted 0 events under concurrency — the spine emit path is broken"
  log "spine emit FLOOR (wg CLI, spawn-bound): ${spine} ev/s | raw pgbench: ${raw} ev/s @ c=${n}"
  log "NOTE: the wg/raw gap here is per-invocation CLI startup, NOT per-event spine cost; the clean spine ceiling is the Inc-3 long-lived load-skeleton (no derate computed from this floor)"
}

# NON-VACUITY BITE: run pgbench at one N through the shard proxy CLEAN, then with
# a latency toxic on the shard's read/commit path. Throughput MUST drop, proving
# the packing sweep measures the REAL shard path (not an unrelated bottleneck).
cmd_bite() {
  local n="${1:-4}"
  assert_production_durability
  $TOXIC reset >/dev/null 2>&1 || true
  $TOXIC create-proxy shard0 "$SHARD0_PROXY_PORT" "${ISO_C}:5432" >/dev/null
  log "bite: pgbench @ c=${n} through the shard proxy (clean) ..."
  local clean; clean="$(pgbench_tps 6 "$n" "$TOXI_C" "$SHARD0_PROXY_PORT" "$SHARD_DB")"
  log "bite: inject +150ms latency on the shard proxy, re-measure ..."
  $TOXIC add-latency shard0 150 >/dev/null
  local slow; slow="$(pgbench_tps 6 "$n" "$TOXI_C" "$SHARD0_PROXY_PORT" "$SHARD_DB")"
  $TOXIC reset >/dev/null 2>&1 || true
  log "bite: clean=${clean} ev/s  slow=${slow} ev/s"
  [ -n "$clean" ] && [ -n "$slow" ] || notrun "bite produced no TPS (proxy path mis-wired)"
  if awk -v c="$clean" -v s="$slow" 'BEGIN{exit !(s < c * 0.8)}'; then
    log "PASS(bite): a real shard slowdown dropped measured throughput (${clean} -> ${slow}) — the sweep rides the real path"
  else
    fail "bite did NOT drop throughput (${clean} -> ${slow}) — the packing sweep is NOT measuring the shard's real path (vacuous)"
  fi
}

cmd_smoke() {
  local n="${1:-3}"
  cmd_up "$n"
  cmd_migrate "$n"
  cmd_crossshard "$n"
  cmd_pack "1 2 4" 6
  cmd_spine_overhead 4 6
  cmd_pgbench 6 8
  cmd_bite 4
  log "PASS(smoke): rig + real cross-shard + packing curve + spine-overhead + pgbench + bite all fired"
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    up)             cmd_up "$@" ;;
    down)           cmd_down "$@" ;;
    migrate)        cmd_migrate "$@" ;;
    crossshard)     cmd_crossshard "$@" ;;
    pack)           cmd_pack "$@" ;;
    spine-overhead) cmd_spine_overhead "$@" ;;
    pgbench)        cmd_pgbench "$@" ;;
    bite)           cmd_bite "$@" ;;
    smoke)          cmd_smoke "$@" ;;
    *) echo "usage: $0 {up|down|migrate|crossshard|pack|spine-overhead|pgbench|bite|smoke} [args]" >&2; exit 2 ;;
  esac
}
main "$@"
