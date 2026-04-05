#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Infrastructure Health Check Test (INF-04)
#
# Tests /health (basic) and /health/ready (deep) endpoints on all services.
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-infra-health.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PASS=0
FAIL=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

assert_status() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label (HTTP $actual)"; PASS=$((PASS+1))
  else
    red "$label (expected HTTP $expected, got $actual)"; FAIL=$((FAIL+1))
  fi
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -q "$needle"; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected to contain: $needle, got: $haystack)"; FAIL=$((FAIL+1))
  fi
}

# Service ports (host-mapped)
declare -A SERVICES=(
  [auth-service]=8204
  [book-service]=8205
  [sharing-service]=8206
  [catalog-service]=8207
  [provider-registry-service]=8208
  [usage-billing-service]=8209
  [glossary-service]=8211
)

# ── T1: /health basic (DB ping) ─────────────────────────────────────────────
header "INF-04a: /health basic (DB ping)"

for svc in "${!SERVICES[@]}"; do
  port=${SERVICES[$svc]}
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/health")
  assert_status "$svc /health" "200" "$STATUS"
done

# ── T2: /health/ready deep (SELECT 1) ───────────────────────────────────────
header "INF-04b: /health/ready deep (SELECT 1)"

for svc in "${!SERVICES[@]}"; do
  port=${SERVICES[$svc]}
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/health/ready")
  assert_status "$svc /health/ready" "200" "$STATUS"
done

# ── T3: /health/ready returns JSON with status=ready ─────────────────────────
header "INF-04c: /health/ready response body"

for svc in "${!SERVICES[@]}"; do
  port=${SERVICES[$svc]}
  BODY=$(curl -s "http://localhost:$port/health/ready")
  assert_contains "$svc body contains ready" '"status":"ready"' "$BODY"
done

# ── T4: Gateway /health ──────────────────────────────────────────────────────
header "INF-04d: Gateway health"

GW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:3123/health")
assert_status "gateway /health" "200" "$GW_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
printf "\n\033[1m═══ Results ═══\033[0m\n"
printf "\033[32m  PASS: %d\033[0m\n" "$PASS"
if [ "$FAIL" -gt 0 ]; then
  printf "\033[31m  FAIL: %d\033[0m\n" "$FAIL"
  exit 1
else
  printf "\033[32m  FAIL: 0\033[0m\n"
  printf "\033[1;32m  All tests passed!\033[0m\n"
fi
