#!/usr/bin/env bash
# scripts/perf/s14-memory.sh
#
# S14 (D2) — Memory exhaustion: Redis eviction safety + RSS-leak soak. LIVE.
#
# Absorbs D-S12-RSS-MEMORY-SOAK.
#
# === evict ===  Redis under memory pressure must NOT silently drop undelivered
# xreality events. With maxmemory + `noeviction` (the safe config for an event
# stream) a full Redis REJECTS new XADD (caller sees the OOM error → can retry → no
# loss) and never evicts what is already there. The BITE flips the policy to
# `allkeys-lru` → entries are silently evicted → undelivered events vanish → the
# no-loss check catches it. Run against a DEDICATED throwaway redis (never the shared
# rig redis — a low maxmemory there would reject/evict real data; this also supersedes
# the snapshot/restore rail since the instance is disposable).
#
# === rss ===   An in-process RSS-leak soak (R5: the WSL2-reliable fallback — docker
# --memory OOM-kill is not observable under WSL2). The rss-soak Go harness runs the
# REAL meta write-path allocation loop (build intent → QueryBuilder → discard) for a
# window and asserts the live heap PLATEAUS; the BITE retains every built object →
# the heap grows monotonically → the leak detector fires.
#
# Verdict: NOTRUN(2) setup / didn't saturate; FAIL(1) silent loss / vacuous bite /
# leak-detector blind; PASS(0). Self-contained; cleans up on exit.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
RIMG="${S14_REDIS_IMAGE:-redis:7-alpine}"
RC="s14m-redis"
KEY="s14:evict"
MAXMEM="${MAXMEM:-4mb}"
MAXITER="${MAXITER:-50000}"
RSS_SECS="${RSS_SECS:-6}"

log()    { printf '[s14-memory] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; cleanup; exit 2; }
fail()   { log "FAIL: $*"; cleanup; exit 1; }
cleanup(){ docker rm -f "$RC" >/dev/null 2>&1 || true; }
trap cleanup EXIT

rc() { docker exec "$RC" redis-cli "$@"; }

start_redis() { # policy
  docker rm -f "$RC" >/dev/null 2>&1 || true
  docker run -d --name "$RC" "$RIMG" redis-server \
    --maxmemory "$MAXMEM" --maxmemory-policy "$1" --save '' --appendonly no >/dev/null \
    || notrun "docker run redis failed"
  local i
  for i in $(seq 1 30); do rc PING >/dev/null 2>&1 && return 0; sleep 0.3; [ "$i" = 30 ] && notrun "redis not ready"; done
}

# fill → echoes "<rejected>" : DELs the stream, then sends MAXITER INDIVIDUAL XADDs
# via `redis-cli --pipe` (each command is independently OOM-checked — a single Lua
# script would be OOM-checked only at start, defeating the test). --pipe reports the
# count of error replies = the XADDs the server REFUSED.
fill() {
  local payload out; payload="$(printf 'x%.0s' $(seq 256))"
  rc DEL "$KEY" >/dev/null
  out="$(yes "XADD $KEY * p $payload" | head -n "$MAXITER" \
        | docker exec -i "$RC" redis-cli --pipe 2>&1 || true)"
  printf '%s\n' "$out" | sed -n 's/.*errors: \([0-9]*\),.*/\1/p' | head -1
}

cmd_evict() {
  docker info >/dev/null 2>&1 || notrun "docker not available"

  # SAFE config: noeviction → XADD rejected when full, nothing already-stored is lost.
  start_redis noeviction
  local rej_ne xlen_ne acc_ne
  rej_ne="$(fill)"; rej_ne="${rej_ne:-0}"
  xlen_ne="$(rc XLEN "$KEY" | tr -d '[:space:]')"
  acc_ne=$(( MAXITER - rej_ne ))
  log "noeviction: accepted=${acc_ne} rejected(OOM back-pressure)=${rej_ne} XLEN=${xlen_ne} (of ${MAXITER})"

  # BITE: allkeys-lru → XADD keeps 'succeeding' but silently evicts (here, the whole
  # stream key) → undelivered entries vanish with NO error to the caller.
  rc CONFIG SET maxmemory-policy allkeys-lru >/dev/null
  local rej_lru xlen_lru acc_lru
  rej_lru="$(fill)"; rej_lru="${rej_lru:-0}"
  xlen_lru="$(rc XLEN "$KEY" | tr -d '[:space:]')"
  acc_lru=$(( MAXITER - rej_lru ))
  log "allkeys-lru (BITE): accepted=${acc_lru} rejected=${rej_lru} XLEN=${xlen_lru}"

  local loss_ne loss_lru
  loss_ne=$(( acc_ne - xlen_ne ))      # accepted but missing under noeviction (must be 0)
  loss_lru=$(( acc_lru - xlen_lru ))   # silently dropped under lru (must be > 0)
  printf '{"phase":"evict","noeviction":{"accepted":%s,"rejected":%s,"xlen":%s,"silent_loss":%s},"lru_bite":{"accepted":%s,"rejected":%s,"xlen":%s,"silent_loss":%s}}\n' \
    "$acc_ne" "$rej_ne" "$xlen_ne" "$loss_ne" "$acc_lru" "$rej_lru" "$xlen_lru" "$loss_lru"

  # self-saturation: noeviction must have actually hit the wall (rejected some) — else
  # maxmemory wasn't low enough / MAXITER too small to fill → NOTRUN.
  if [ "${rej_ne:-0}" -le 0 ]; then
    notrun "noeviction never rejected an XADD — never filled maxmemory ${MAXMEM}; lower MAXMEM / raise MAXITER"
  fi
  # SAFE: under noeviction nothing already-accepted was lost.
  [ "${loss_ne:-1}" -le 0 ] || fail "noeviction LOST ${loss_ne} already-accepted entries — eviction safety broken"
  # BITE non-vacuity: lru must have silently dropped entries (loss > 0, no errors raised).
  [ "${loss_lru:-0}" -gt 0 ] || fail "allkeys-lru did NOT silently drop entries (loss=${loss_lru}) — bite vacuous (maxmemory not exceeded?)"
  [ "${rej_lru:-0}" -eq 0 ] || log "  note: lru also raised ${rej_lru} errors (still silently lost ${loss_lru})"
  log "PASS(evict): noeviction REJECTED ${rej_ne} XADDs (visible back-pressure, 0 silent loss); BITE allkeys-lru silently dropped ${loss_lru} undelivered events with no caller error — proving noeviction is the correct event-stream policy"
}

cmd_rss() {
  command -v go >/dev/null 2>&1 || notrun "go not on PATH"
  local bin; bin="$(ls services/meta-worker/rsssoak.exe services/meta-worker/rsssoak 2>/dev/null | head -1 || true)"
  if [ -z "$bin" ]; then
    log "building rss-soak ..."
    go -C services/meta-worker build -o rsssoak.exe ./cmd/rss-soak || notrun "build failed"
    bin="services/meta-worker/rsssoak.exe"
  fi
  log "RSS-leak soak: steady-state meta write-path allocation loop for ${RSS_SECS}s (heap must plateau) ..."
  "$bin" -secs "$RSS_SECS" -mode soak
  log "RSS-leak BITE: same loop but retaining every object (heap must grow) ..."
  "$bin" -secs "$RSS_SECS" -mode bite
}

cmd_smoke() { cmd_evict; cmd_rss; log "PASS(smoke): redis eviction safety (noeviction vs lru bite) + RSS-leak soak (plateau vs leaky bite)"; }

main() {
  case "${1:-smoke}" in
    evict) cmd_evict ;;
    rss)   cmd_rss ;;
    smoke) cmd_smoke ;;
    *) echo "usage: $0 {evict|rss|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
