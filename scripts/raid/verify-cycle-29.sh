#!/usr/bin/env bash
# verify-cycle-29.sh — L6.C + L6.D WS per-message authz + forced disconnect (2 DPS).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 29 scope (2 DPS):
#
#   DPS 1 (L6.C — per-message re-auth):
#     * services/api-gateway-bff/src/ws/per-message-authz.ts
#     * services/api-gateway-bff/src/ws/per-message-authz.spec.ts
#     * crates/contracts-ws/src/authz.rs (Rust mirror)
#     * session-router.ts envelope passthrough extension
#     * inventory.yaml lw_ws_authz_rejections_total already declared (cycle 28)
#
#   DPS 2 (L6.D — forced disconnect via shared Redis):
#     * services/api-gateway-bff/src/ws/control-channel-consumer.ts
#     * services/api-gateway-bff/src/ws/disconnector.ts
#     * services/api-gateway-bff/src/ws/forced-disconnect.spec.ts
#     * crates/contracts-ws/src/control_channel.rs
#     * contracts/lifecycle/mode_propagation.go (KindWsDisconnectUser extension)
#     * runbooks/ws/forced_disconnect.md
#
# LOCKED decisions enforced:
#   Q-L6-1 — WS impl extends NestJS api-gateway-bff (no sidecar)
#   Cycle 7 L1.J — REUSE shared `lw:dependency:control` (no new channel)
#   Cycle 28 close_codes taxonomy — 11 codes (1000, 4001..4010)

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-29] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-29] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-29] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# File presence — DPS 1 (L6.C per-message authz)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    services/api-gateway-bff/src/ws/per-message-authz.ts \
    services/api-gateway-bff/src/ws/per-message-authz.spec.ts \
    crates/contracts-ws/src/authz.rs ; do
    [[ -f "$f" ]] || fail "cycle-29 DPS 1 (L6.C) file missing: $f"
done
pass "cycle-29 L6.C files present (per-message authz + Rust mirror)"

# ─────────────────────────────────────────────────────────────────────────
# File presence — DPS 2 (L6.D forced disconnect)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    services/api-gateway-bff/src/ws/control-channel-consumer.ts \
    services/api-gateway-bff/src/ws/disconnector.ts \
    services/api-gateway-bff/src/ws/forced-disconnect.spec.ts \
    crates/contracts-ws/src/control_channel.rs \
    runbooks/ws/forced_disconnect.md ; do
    [[ -f "$f" ]] || fail "cycle-29 DPS 2 (L6.D) file missing: $f"
done
pass "cycle-29 L6.D files present (consumer + disconnector + Rust mirror + runbook)"

# ─────────────────────────────────────────────────────────────────────────
# Q-L6-1: WS authz wired into NestJS gateway (no sidecar)
# ─────────────────────────────────────────────────────────────────────────
grep -q 'PerMessageAuthz' services/api-gateway-bff/src/ws/ws-server.ts \
    || fail "Q-L6-1: ws-server.ts must wire PerMessageAuthz (no separate sidecar)"
grep -q 'AUTHZ_PROVIDER' services/api-gateway-bff/src/ws/ws.module.ts \
    || fail "Q-L6-1: WsModule must bind AUTHZ_PROVIDER"
pass "Q-L6-1: per-message authz wired into existing NestJS gateway"

# ─────────────────────────────────────────────────────────────────────────
# Cycle 7 REUSE: shared `lw:dependency:control` channel name pinned
# ─────────────────────────────────────────────────────────────────────────
grep -q "'lw:dependency:control'" services/api-gateway-bff/src/ws/control-channel-consumer.ts \
    || fail "cycle-7 reuse: WS_CONTROL_REDIS_CHANNEL must equal 'lw:dependency:control'"
grep -q 'KindWsDisconnectUser MessageKind = "ws_disconnect_user"' contracts/lifecycle/mode_propagation.go \
    || fail "cycle-7 reuse: KindWsDisconnectUser extension missing from mode_propagation.go"
pass "cycle-7 channel reuse: lw:dependency:control extended with ws_disconnect_user kind"

# ─────────────────────────────────────────────────────────────────────────
# Cycle 28 close-code taxonomy honored (4007/4008/4009 documented)
# ─────────────────────────────────────────────────────────────────────────
grep -q '4007' runbooks/ws/forced_disconnect.md \
    || fail "runbook: close code 4007 (origin_mismatch) not documented"
grep -q '4008' runbooks/ws/forced_disconnect.md \
    || fail "runbook: close code 4008 (connection_limit) not documented"
grep -q '4009' runbooks/ws/forced_disconnect.md \
    || fail "runbook: close code 4009 (fingerprint_mismatch) not documented"
grep -q 'FORCE_DISCONNECT_CODES' services/api-gateway-bff/src/ws/disconnector.ts \
    || fail "disconnector: FORCE_DISCONNECT_CODES table missing"
pass "close-code taxonomy: 4007/4008/4009 documented in runbook + disconnector exports table"

# ─────────────────────────────────────────────────────────────────────────
# Per-msg authz — cache discipline (5s TTL pinned)
# ─────────────────────────────────────────────────────────────────────────
grep -q 'AUTHZ_CACHE_TTL_MS = 5_000' services/api-gateway-bff/src/ws/per-message-authz.ts \
    || fail "L6.C: 5-second authz cache TTL constant missing"
grep -q 'invalidateUser' services/api-gateway-bff/src/ws/per-message-authz.ts \
    || fail "L6.C: invalidateUser cache-eviction hook missing"
pass "L6.C: 5s cache TTL + per-user invalidation hook present"

# ─────────────────────────────────────────────────────────────────────────
# Forced disconnect — idempotency via nonce LRU
# ─────────────────────────────────────────────────────────────────────────
grep -q 'seenNonces' services/api-gateway-bff/src/ws/control-channel-consumer.ts \
    || fail "L6.D: nonce dedup LRU missing"
grep -q "tag: 'duplicate'" services/api-gateway-bff/src/ws/control-channel-consumer.ts \
    || fail "L6.D: duplicate detection branch missing"
grep -q 'idempotent\|nonce_id' services/api-gateway-bff/src/ws/forced-disconnect.spec.ts \
    || fail "L6.D: idempotency test missing"
pass "L6.D: nonce-based idempotency + duplicate test present"

# ─────────────────────────────────────────────────────────────────────────
# Malformed payload safety
# ─────────────────────────────────────────────────────────────────────────
grep -q 'malformed_json\|invalid_payload' services/api-gateway-bff/src/ws/control-channel-consumer.ts \
    || fail "L6.D: consumer must drop malformed payloads (not crash)"
grep -q 'MALFORMED\|malformed' services/api-gateway-bff/src/ws/forced-disconnect.spec.ts \
    || fail "L6.D: malformed-payload test missing"
pass "L6.D: malformed payload safety + test present"

# ─────────────────────────────────────────────────────────────────────────
# Cycle 28 metric reused (no new lw_ws_* metric in cycle 29 inventory)
# ─────────────────────────────────────────────────────────────────────────
# Cycle 28 already declared lw_ws_authz_rejections_total with shipped_cycle:28.
# Cycle 29 just consumes it — no NEW inventory entry expected.
inv_29=$(grep -c 'shipped_cycle: 29' contracts/observability/inventory.yaml || true)
if [[ "$inv_29" -gt 0 ]]; then
    fail "cycle-29 should NOT add new inventory entries (consumes cycle-28's lw_ws_authz_rejections_total); found $inv_29"
fi
pass "inventory: cycle-29 consumes cycle-28 metric (no new entries — scope discipline)"

# ─────────────────────────────────────────────────────────────────────────
# Build + test gates.
# ─────────────────────────────────────────────────────────────────────────

# TypeScript: api-gateway-bff jest suite (WS additions + existing regression).
note "npx jest src/ws/ (api-gateway-bff)"
( cd services/api-gateway-bff && npx jest --testPathPattern='src/ws/' >/dev/null 2>&1 ) \
    || fail "api-gateway-bff WS jest suite FAILED"
pass "api-gateway-bff WS jest suite PASS (6 suites: ticket-store + ws-server + metrics + session-router + per-message-authz + forced-disconnect)"

# Rust: contracts-ws crate.
note "cargo test -p contracts-ws --lib"
cargo test -p contracts-ws --lib --quiet >/dev/null 2>&1 \
    || fail "contracts-ws cargo tests FAILED"
pass "contracts-ws cargo tests PASS (envelope + close-codes + authz + control_channel)"

# Go: contracts/lifecycle (control-channel extension). Module is its own
# go.mod — cd into it.
note "go test ./contracts/lifecycle/..."
( cd contracts/lifecycle && go test ./... >/dev/null 2>&1 ) \
    || fail "contracts/lifecycle go tests FAILED"
pass "contracts/lifecycle go tests PASS (KindWsDisconnectUser round-trip + bounds)"

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
    services/api-gateway-bff/src/ws/per-message-authz.ts
    services/api-gateway-bff/src/ws/per-message-authz.spec.ts
    services/api-gateway-bff/src/ws/control-channel-consumer.ts
    services/api-gateway-bff/src/ws/disconnector.ts
    services/api-gateway-bff/src/ws/forced-disconnect.spec.ts
    crates/contracts-ws/src/authz.rs
    crates/contracts-ws/src/control_channel.rs
    runbooks/ws/forced_disconnect.md
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -EHn "$SECRET_PATTERNS" "$f" 2>/dev/null; then
        fail "B6: secret-like content in $f"
    fi
done
pass "B6 secret-scan: cycle-29 new files clean"

if bash scripts/raid/secret-scan-cycle.sh 29 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle 29 clean"
else
    fail "B6 secret-scan-cycle 29 FAILED"
fi

echo
echo "[verify-cycle-29] ALL ${step} STEPS PASS"
echo "[verify-cycle-29] L6 WS security shipped — per-msg authz (S2+S3 regression guard) + forced disconnect via cycle-7 shared Redis channel."
echo "[verify-cycle-29] Next: cycle 30 (L6.F + L6.G — admission runtimes)."
