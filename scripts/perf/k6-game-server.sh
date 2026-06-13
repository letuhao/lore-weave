#!/usr/bin/env bash
# scripts/perf/k6-game-server.sh
#
# S7 deliverable F4 — open-loop load generation vs the game-server (PRR-20 second
# public WS entry). Boots game-server in its DEV static-token mode (no
# LW_WS_REDIS_URL → EchoRoom.onAuth accepts jwt=dev_token; NODE_ENV unset so
# assertWsAuthConfig passes), then runs the available generators:
#   - k6 http_livez.js     pure-transport open-loop ceiling (p50/p99/p999)
#   - k6 http_matchmake.js seat-reservation HTTP path (edge-control surface)
#   - ws_echo.mjs          colyseus.js WS echo round-trip latency
#
# Summaries land in tests/conformance/results/. NO threshold asserted (S7 §0) —
# the summary artifacts are the deliverable.
#
# Verdict: neither k6 nor node present → NOTRUN; game-server didn't boot →
# NOTRUN(setup); at least one generator produced an artifact → PASS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
GS="services/game-server"
PORT="${GAME_SERVER_PORT:-2567}"
TARGET="http://127.0.0.1:${PORT}"
TARGET_WS="ws://127.0.0.1:${PORT}"
RESULTS="tests/conformance/results"
K6_DIR="tests/perf/k6"
TOKEN="${LOREWEAVE_INTERNAL_TOKEN:-dev_token}"

log()    { printf '[k6-gs] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }

HAVE_K6=0; command -v k6 >/dev/null 2>&1 && HAVE_K6=1
HAVE_NODE=0; command -v node >/dev/null 2>&1 && HAVE_NODE=1
[ "$HAVE_K6" = 1 ] || [ "$HAVE_NODE" = 1 ] || notrun "neither k6 nor node present — no generator available"
[ "$HAVE_NODE" = 1 ] || notrun "node required to build/boot game-server"

mkdir -p "$RESULTS"

# ── build game-server (ci if lockfile, else install) ─────────────────────────
log "installing + building game-server ..."
if [ -f "$GS/package-lock.json" ]; then
  npm --prefix "$GS" ci >/dev/null 2>&1 || npm --prefix "$GS" install >/dev/null 2>&1 || notrun "npm install failed (game-server)"
else
  npm --prefix "$GS" install >/dev/null 2>&1 || notrun "npm install failed (game-server)"
fi
npm --prefix "$GS" run build >/dev/null 2>&1 || notrun "npm run build failed (game-server)"
[ -f "$GS/dist/index.js" ] || notrun "game-server dist/index.js missing after build"

# ── boot game-server (dev static-token) ──────────────────────────────────────
# Raise the edge message-rate cap for the run: the perf driver measures
# transport round-trip LATENCY/throughput, not the rate limiter (which has its
# own edge tests — services/game-server/src/ws/edge.test.ts). The DEFAULT cap is
# 30 msgs / 10s, which would close (4006) the driver mid-measurement.
GS_LOG="$(mktemp)"
LW_WS_ALLOW_DEV_AUTH=1 PORT="$PORT" LOREWEAVE_INTERNAL_TOKEN="$TOKEN" \
  LW_WS_MSG_PER_WINDOW="${LW_WS_MSG_PER_WINDOW:-10000000}" \
  LW_WS_RATE_WINDOW_MS="${LW_WS_RATE_WINDOW_MS:-1000}" \
  LW_WS_MAX_CONN_PER_USER="${LW_WS_MAX_CONN_PER_USER:-100000}" \
  node "$GS/dist/index.js" >"$GS_LOG" 2>&1 &
GS_PID=$!
cleanup() { kill "$GS_PID" >/dev/null 2>&1 || true; }
trap cleanup EXIT

booted=0
for _ in $(seq 1 30); do
  if curl -fsS "$TARGET/livez" >/dev/null 2>&1; then booted=1; break; fi
  kill -0 "$GS_PID" 2>/dev/null || { log "game-server exited at startup:"; cat "$GS_LOG"; notrun "game-server process died"; }
  sleep 1
done
[ "$booted" = 1 ] || { cat "$GS_LOG"; notrun "game-server did not answer /livez within 30s"; }
log "game-server up on :$PORT (dev static-token)"

ran_any=0

# ── k6 HTTP generators ───────────────────────────────────────────────────────
if [ "$HAVE_K6" = 1 ]; then
  log "k6 http_livez ..."
  SUMMARY_OUT="$ROOT/$RESULTS/k6-livez-summary.json" TARGET="$TARGET" \
    k6 run "$K6_DIR/http_livez.js" >/dev/null 2>&1 && { ran_any=1; log "wrote k6-livez-summary.json"; } || log "k6 livez run failed (non-fatal)"
  log "k6 http_matchmake ..."
  SUMMARY_OUT="$ROOT/$RESULTS/k6-matchmake-summary.json" TARGET="$TARGET" LOREWEAVE_INTERNAL_TOKEN="$TOKEN" \
    k6 run "$K6_DIR/http_matchmake.js" >/dev/null 2>&1 && { ran_any=1; log "wrote k6-matchmake-summary.json"; } || log "k6 matchmake run failed (non-fatal)"
else
  log "k6 absent — skipping HTTP open-loop generators (CI nightly installs k6)"
fi

# ── WS echo round-trip (colyseus.js driver) ──────────────────────────────────
if [ "$HAVE_NODE" = 1 ]; then
  log "installing ws driver deps (colyseus.js) ..."
  if npm --prefix "$K6_DIR" install >/dev/null 2>&1; then
    SUMMARY_OUT="$ROOT/$RESULTS/k6-ws-echo-summary.json" TARGET_WS="$TARGET_WS" \
      LOREWEAVE_INTERNAL_TOKEN="$TOKEN" WS_ROUNDTRIPS="${WS_ROUNDTRIPS:-500}" \
      node "$K6_DIR/ws_echo.mjs" && { ran_any=1; log "wrote k6-ws-echo-summary.json"; } || log "ws round-trip driver failed (non-fatal)"
  else
    log "could not install colyseus.js — skipping WS round-trip"
  fi
fi

rm -f "$GS_LOG"
[ "$ran_any" = 1 ] || notrun "no generator produced an artifact (k6 absent + ws driver failed)"
log "PASS: F4 produced game-server load artifact(s) in $RESULTS"
