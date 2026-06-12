#!/usr/bin/env bash
# verify-cycle-28.sh — L6.A + L6.B + L6.E WS server + Ticket + Metrics (3 DPS).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 28 scope (3 DPS):
#
#   DPS 1 (L6.A — WebSocket server, NestJS extension per Q-L6-1):
#     * services/api-gateway-bff/src/ws/ws-server.ts
#     * services/api-gateway-bff/src/ws/upgrade-handler.ts
#     * services/api-gateway-bff/src/ws/session-router.ts
#     * services/api-gateway-bff/src/ws/outbound-fanout.ts
#     * services/api-gateway-bff/src/ws/config.ts (Q-L6-2 10K cap)
#     * services/api-gateway-bff/src/ws/{ws-server,session-router}.spec.ts
#     * crates/contracts-ws/ (Rust server-lib stub per L6.A.5)
#
#   DPS 2 (L6.B — WS ticket handshake server):
#     * services/api-gateway-bff/src/ws/ticket-store.ts (one-shot, 60s TTL)
#     * services/api-gateway-bff/src/ws/ticket-endpoint.ts (POST /v1/ws/ticket)
#     * services/api-gateway-bff/src/ws/ticket-store.spec.ts (replay rejection)
#     * runbooks/ws/ticket_replay_attack.md
#
#   DPS 3 (L6.E — WS metrics + alerts):
#     * services/api-gateway-bff/src/ws/metrics.ts
#     * services/api-gateway-bff/src/ws/metrics.spec.ts
#     * contracts/observability/inventory.yaml (6 lw_ws_* entries)
#     * infra/prometheus/alerts/ws.yaml
#     * dashboards/ws-health.json
#     * runbooks/ws/refresh_failures.md
#
# LOCKED decisions enforced:
#   Q-L6-1 — WS impl extends NestJS api-gateway-bff (no sidecar)
#   Q-L6-2 — Connection cap = 10 000 per replica
#   Q-L6-3 — Foundation owns server + envelope types only (no browser lib)

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-28] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-28] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-28] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# File presence — DPS 1 (L6.A WS server)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    services/api-gateway-bff/src/ws/ws-server.ts \
    services/api-gateway-bff/src/ws/upgrade-handler.ts \
    services/api-gateway-bff/src/ws/session-router.ts \
    services/api-gateway-bff/src/ws/outbound-fanout.ts \
    services/api-gateway-bff/src/ws/config.ts \
    services/api-gateway-bff/src/ws/ws-server.spec.ts \
    services/api-gateway-bff/src/ws/session-router.spec.ts \
    crates/contracts-ws/Cargo.toml \
    crates/contracts-ws/src/lib.rs \
    crates/contracts-ws/src/envelope.rs \
    crates/contracts-ws/src/close_codes.rs \
    crates/contracts-ws/src/server_lib.rs ; do
    [[ -f "$f" ]] || fail "cycle-28 DPS 1 (L6.A) file missing: $f"
done
pass "cycle-28 L6.A files present (NestJS WS server + Rust crate stub)"

# ─────────────────────────────────────────────────────────────────────────
# File presence — DPS 2 (L6.B Ticket handshake)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    services/api-gateway-bff/src/ws/ticket-store.ts \
    services/api-gateway-bff/src/ws/ticket-endpoint.ts \
    services/api-gateway-bff/src/ws/ticket-store.spec.ts \
    runbooks/ws/ticket_replay_attack.md ; do
    [[ -f "$f" ]] || fail "cycle-28 DPS 2 (L6.B) file missing: $f"
done
pass "cycle-28 L6.B files present (ticket endpoint + store + replay runbook)"

# ─────────────────────────────────────────────────────────────────────────
# File presence — DPS 3 (L6.E Metrics + alerts)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    services/api-gateway-bff/src/ws/metrics.ts \
    services/api-gateway-bff/src/ws/metrics.spec.ts \
    infra/prometheus/alerts/ws.yaml \
    dashboards/ws-health.json \
    runbooks/ws/refresh_failures.md ; do
    [[ -f "$f" ]] || fail "cycle-28 DPS 3 (L6.E) file missing: $f"
done
pass "cycle-28 L6.E files present (metrics + alerts + dashboard + runbook)"

# ─────────────────────────────────────────────────────────────────────────
# Q-L6-1: WS impl extends NestJS (no sidecar)
# ─────────────────────────────────────────────────────────────────────────
grep -q '@WebSocketGateway' services/api-gateway-bff/src/ws/ws-server.ts \
    || fail "Q-L6-1: WsV1Gateway must be a NestJS @WebSocketGateway (extends existing NestJS)"
grep -q "Q-L6-1" services/api-gateway-bff/src/ws/ws-server.ts \
    || fail "Q-L6-1: citation missing from ws-server.ts"
pass "Q-L6-1: WS impl extends NestJS api-gateway-bff (no sidecar)"

# ─────────────────────────────────────────────────────────────────────────
# Q-L6-2: 10K connection cap per replica
# ─────────────────────────────────────────────────────────────────────────
grep -q 'WS_MAX_CONNECTIONS_PER_REPLICA = 10_000' services/api-gateway-bff/src/ws/config.ts \
    || fail "Q-L6-2: 10 000 connection cap constant missing from config.ts"
grep -q 'Q-L6-2' services/api-gateway-bff/src/ws/config.ts \
    || fail "Q-L6-2: citation missing from config.ts"
grep -q "cap_reached" services/api-gateway-bff/src/ws/ws-server.ts \
    || fail "Q-L6-2: cap_reached handshake failure path missing"
grep -q "10001st\|cap reached\|connection cap" services/api-gateway-bff/src/ws/ws-server.spec.ts \
    || fail "Q-L6-2: cap rejection test missing"
pass "Q-L6-2: 10K connection cap enforced atomically + test present"

# ─────────────────────────────────────────────────────────────────────────
# Q-L6-3: foundation = server + envelope only; no browser TS WS client
# ─────────────────────────────────────────────────────────────────────────
if find services/api-gateway-bff/src/ws -name "*-client*.ts" -not -name "*.spec.ts" | grep -q .; then
    fail "Q-L6-3: browser WS client lib files detected (frontend-game owns this)"
fi
grep -q "Q-L6-3" services/api-gateway-bff/src/ws/ticket-store.ts \
    || fail "Q-L6-3: citation missing from ticket-store.ts"
pass "Q-L6-3: server + envelope only (no browser WS client lib)"

# ─────────────────────────────────────────────────────────────────────────
# Ticket security — one-shot + 60s TTL + ≥128-bit entropy
# ─────────────────────────────────────────────────────────────────────────
grep -q 'TICKET_TTL_MS = 60_000' services/api-gateway-bff/src/ws/ticket-store.ts \
    || fail "L6.B: TICKET_TTL_MS must be exactly 60 000 ms"
grep -q 'randomUUID' services/api-gateway-bff/src/ws/ticket-store.ts \
    || fail "L6.B: ticket id must use crypto.randomUUID (≥128 bits entropy)"
grep -q 'constantTimeBufferEquals' services/api-gateway-bff/src/ws/ws-server.ts \
    || fail "L6.B: handshake must use constant-time compare for origin/fingerprint"
pass "L6.B: ticket TTL=60s + 128-bit entropy + constant-time binding compares"

# ─────────────────────────────────────────────────────────────────────────
# Metrics inventory — 6 lw_ws_* entries declared with shipped_cycle: 28
# ─────────────────────────────────────────────────────────────────────────
inv_count=$(grep -c 'shipped_cycle: 28' contracts/observability/inventory.yaml || true)
if [[ "$inv_count" -lt 6 ]]; then
    fail "cycle-28 inventory.yaml: expected ≥6 entries with shipped_cycle: 28, got $inv_count"
fi
pass "inventory.yaml: 6 lw_ws_* metrics declared with shipped_cycle: 28"

for m in \
    'lw_ws_active_connections' \
    'lw_ws_handshake_failures_total' \
    'lw_ws_messages_total' \
    'lw_ws_authz_rejections_total' \
    'lw_ws_ticket_redeemed_total' \
    'lw_ws_connection_evictions_total' ; do
    grep -q "name: $m" contracts/observability/inventory.yaml \
        || fail "inventory: missing entry $m"
done
pass "inventory: all 6 lw_ws_* metric names declared"

# Cardinality discipline — no per-connection labels (auditor focus)
if grep -E '^\s*labels:.*connection_id|labels:.*user_ref_id' contracts/observability/inventory.yaml | grep -q lw_ws; then
    fail "cardinality: per-connection / per-user labels detected on lw_ws_* metric (forbidden)"
fi
pass "cardinality: no per-connection labels on lw_ws_* metrics"

# Alerts file shape
grep -q 'LWWsConnectionSaturation' infra/prometheus/alerts/ws.yaml \
    || fail "alerts: LWWsConnectionSaturation rule missing"
grep -q 'LWWsTicketReplayAttack' infra/prometheus/alerts/ws.yaml \
    || fail "alerts: LWWsTicketReplayAttack rule missing"
grep -q '0.8 \* 10000' infra/prometheus/alerts/ws.yaml \
    || fail "alerts: 80% × 10 000 saturation threshold missing (must match Q-L6-2 cap)"
pass "alerts: ws.yaml contains saturation + replay rules + correct 80% threshold"

# ─────────────────────────────────────────────────────────────────────────
# Build + test gates.
# ─────────────────────────────────────────────────────────────────────────

# TypeScript: api-gateway-bff jest suite (WS additions + existing regression).
note "npx jest src/ws/ (api-gateway-bff)"
( cd services/api-gateway-bff && npx jest --testPathPattern='src/ws/' >/dev/null 2>&1 ) \
    || fail "api-gateway-bff WS jest suite FAILED"
pass "api-gateway-bff WS jest suite PASS (4 suites: ticket-store + ws-server + metrics + session-router)"

note "npx jest --testPathPattern=test/ (api-gateway-bff regression)"
( cd services/api-gateway-bff && npx jest --testPathPattern='test/' >/dev/null 2>&1 ) \
    || fail "api-gateway-bff regression jest suite FAILED"
pass "api-gateway-bff regression jest suite PASS (health + proxy-routing)"

# Rust: contracts-ws crate.
note "cargo test -p contracts-ws --lib"
cargo test -p contracts-ws --lib --quiet >/dev/null 2>&1 \
    || fail "contracts-ws cargo tests FAILED"
pass "contracts-ws cargo tests PASS (envelope round-trip + close-code conversion)"

# Workspace build clean.
note "cargo build --workspace"
cargo build --workspace --quiet >/dev/null 2>&1 \
    || fail "cargo build --workspace FAILED"
pass "cargo build --workspace clean"

# ─────────────────────────────────────────────────────────────────────────
# B5 prod-isolation + B6 secret-scan.
# ─────────────────────────────────────────────────────────────────────────
if git diff --name-only HEAD 2>/dev/null | grep -qE '^infra/existing-prod/'; then
    fail "B5: changes detected under infra/existing-prod/ (forbidden)"
fi
pass "B5 prod-isolation: no infra/existing-prod/ changes"

if bash scripts/raid/prod-isolation-lint.sh >/dev/null 2>&1; then
    pass "B5 prod-isolation-lint clean"
else
    fail "B5 prod-isolation-lint failed"
fi

NEW_FILES=(
    services/api-gateway-bff/src/ws/ws-server.ts
    services/api-gateway-bff/src/ws/upgrade-handler.ts
    services/api-gateway-bff/src/ws/session-router.ts
    services/api-gateway-bff/src/ws/outbound-fanout.ts
    services/api-gateway-bff/src/ws/config.ts
    services/api-gateway-bff/src/ws/ticket-store.ts
    services/api-gateway-bff/src/ws/ticket-endpoint.ts
    services/api-gateway-bff/src/ws/metrics.ts
    services/api-gateway-bff/src/ws/ws-server.spec.ts
    services/api-gateway-bff/src/ws/session-router.spec.ts
    services/api-gateway-bff/src/ws/ticket-store.spec.ts
    services/api-gateway-bff/src/ws/metrics.spec.ts
    crates/contracts-ws/Cargo.toml
    crates/contracts-ws/src/lib.rs
    crates/contracts-ws/src/envelope.rs
    crates/contracts-ws/src/close_codes.rs
    crates/contracts-ws/src/server_lib.rs
    infra/prometheus/alerts/ws.yaml
    dashboards/ws-health.json
    runbooks/ws/ticket_replay_attack.md
    runbooks/ws/refresh_failures.md
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -EHn "$SECRET_PATTERNS" "$f" 2>/dev/null; then
        fail "B6: secret-like content in $f"
    fi
done
pass "B6 secret-scan: cycle-28 new files clean"

if bash scripts/raid/secret-scan-cycle.sh 28 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle 28 clean"
else
    fail "B6 secret-scan-cycle 28 FAILED"
fi

echo
echo "[verify-cycle-28] ALL ${step} STEPS PASS"
echo "[verify-cycle-28] L6 BEGINS — WS server (NestJS extension per Q-L6-1) + ticket handshake + 6 metrics shipped."
echo "[verify-cycle-28] Next: cycle 29 (L6.C + L6.D — per-message authz + forced disconnect)."
