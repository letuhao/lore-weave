#!/usr/bin/env bash
# scripts/chaos/toxic.sh
#
# S6 (Battery D) — thin driver over the toxiproxy admin API. Fault drills use it
# to inject network faults between consumers and postgres/redis WITHOUT touching
# production code (the drills point their DSN at the proxy listen port).
#
# Subcommands:
#   wait                                  — block until the admin API answers
#   create-proxy <name> <listen_port> <upstream_host:port>
#   add-latency <name> <ms> [jitter_ms]   — latency toxic (downstream)
#   add-timeout <name> <ms>               — timeout toxic (cuts the stream after ms)
#   down <name> | up <name>               — disable / enable the proxy (hard cut)
#   delete-proxy <name>                   — remove a proxy
#   reset                                 — remove ALL toxics, enable ALL proxies
#   selftest                              — Inc 2 verify: prove a toxic sits on the path
#
# Admin API at $TOXIPROXY_URL (default 127.0.0.1:$FOUNDATION_TOXIPROXY_PORT).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE="$ROOT/infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
TOXI_CONTAINER="foundation-dev-toxiproxy"
PG_USER="foundation"
TOXI_PORT="${FOUNDATION_TOXIPROXY_PORT:-8474}"
TOXIPROXY_URL="${TOXIPROXY_URL:-http://127.0.0.1:${TOXI_PORT}}"
PG_PROXY_PORT="${FOUNDATION_PG_PROXY_PORT:-55433}"

log() { printf '[toxic] %s\n' "$*"; }
api() { # method path [json-body]
  local method="$1" path="$2" body="${3:-}"
  if [ -n "$body" ]; then
    curl -fsS -X "$method" -H 'Content-Type: application/json' -d "$body" "${TOXIPROXY_URL}${path}"
  else
    curl -fsS -X "$method" "${TOXIPROXY_URL}${path}"
  fi
}

cmd_wait() {
  for _ in $(seq 1 30); do
    if curl -fsS "${TOXIPROXY_URL}/version" >/dev/null 2>&1; then
      log "toxiproxy up: $(curl -fsS "${TOXIPROXY_URL}/version")"
      return 0
    fi
    sleep 1
  done
  log "FAIL: toxiproxy admin API never answered at ${TOXIPROXY_URL}"
  return 1
}

cmd_create_proxy() { # name listen_port upstream
  local name="$1" port="$2" upstream="$3"
  # Idempotent: delete any prior proxy of this name first (ignore 404).
  curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/${name}" >/dev/null 2>&1 || true
  api POST /proxies \
    "{\"name\":\"${name}\",\"listen\":\"0.0.0.0:${port}\",\"upstream\":\"${upstream}\",\"enabled\":true}" >/dev/null
  log "proxy ${name}: 0.0.0.0:${port} -> ${upstream}"
}

cmd_add_latency() { # name ms [jitter]
  local name="$1" ms="$2" jitter="${3:-0}"
  api POST "/proxies/${name}/toxics" \
    "{\"type\":\"latency\",\"attributes\":{\"latency\":${ms},\"jitter\":${jitter}}}" >/dev/null
  log "proxy ${name}: +${ms}ms latency (jitter ${jitter})"
}

cmd_add_timeout() { # name ms
  local name="$1" ms="$2"
  api POST "/proxies/${name}/toxics" \
    "{\"type\":\"timeout\",\"attributes\":{\"timeout\":${ms}}}" >/dev/null
  log "proxy ${name}: timeout ${ms}ms"
}

cmd_set_enabled() { # name true|false
  api POST "/proxies/$1" "{\"enabled\":$2}" >/dev/null
  log "proxy $1: enabled=$2"
}

cmd_delete_proxy() { curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/$1" >/dev/null 2>&1 || true; log "proxy $1 deleted"; }
cmd_reset() { api POST /reset >/dev/null; log "reset: all toxics removed, all proxies enabled"; }

# Round-trip a `SELECT 1` through the pg proxy and print the wall time in ms.
# Runs psql FROM the postgres container, dialing the toxiproxy container by name
# (foundation-dev-toxiproxy:<listen>) → no host psql needed, container-to-container.
rtt_pg_ms() { # listen_port
  local port="$1" start end
  start="$(date +%s%3N)"
  docker exec -e PGPASSWORD=foundation "$PG_CONTAINER" \
    psql -h "$TOXI_CONTAINER" -p "$port" -U "$PG_USER" -d foundation -tAc "SELECT 1" >/dev/null
  end="$(date +%s%3N)"
  echo $((end - start))
}

cmd_selftest() {
  log "selftest: boot toxiproxy + prove a latency toxic sits on the pg path ..."
  docker compose -f "$COMPOSE" up -d toxiproxy-foundation postgres-foundation >/dev/null
  cmd_wait
  for _ in $(seq 1 30); do
    docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 && break; sleep 1
  done

  cmd_create_proxy pg_proxy "$PG_PROXY_PORT" "${PG_CONTAINER}:5432"

  # Baseline RTT (no toxic).
  local base latent delta
  base="$(rtt_pg_ms "$PG_PROXY_PORT")"
  log "baseline SELECT 1 RTT through proxy: ${base}ms"

  # Inject 500ms latency, re-measure.
  cmd_add_latency pg_proxy 500
  latent="$(rtt_pg_ms "$PG_PROXY_PORT")"
  log "with +500ms latency toxic:           ${latent}ms"

  cmd_reset
  cmd_delete_proxy pg_proxy

  delta=$((latent - base))
  # The latency toxic must add a CLEAR, observable RTT increase (≥300ms, well
  # under the injected 500 to allow timing noise but far above baseline jitter).
  # This is the non-vacuity proof: the toxic genuinely sits on the data path.
  if [ "$delta" -ge 300 ]; then
    log "PASS: latency toxic added ${delta}ms (base ${base} -> ${latent}) — toxic is on the real path"
    return 0
  fi
  log "FAIL: latency toxic added only ${delta}ms (base ${base} -> ${latent}); expected >= 300ms"
  return 1
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    wait)          cmd_wait ;;
    create-proxy)  cmd_create_proxy "$@" ;;
    add-latency)   cmd_add_latency "$@" ;;
    add-timeout)   cmd_add_timeout "$@" ;;
    down)          cmd_set_enabled "$1" false ;;
    up)            cmd_set_enabled "$1" true ;;
    delete-proxy)  cmd_delete_proxy "$@" ;;
    reset)         cmd_reset ;;
    selftest)      cmd_selftest ;;
    *) echo "usage: $0 {wait|create-proxy|add-latency|add-timeout|down|up|delete-proxy|reset|selftest}" >&2; exit 2 ;;
  esac
}
main "$@"
