#!/usr/bin/env bash
# verify-cycle-template — TEMPLATE for per-cycle verify-cycle-<N>.sh scripts
# Per RAID_WORKFLOW.md §13 (CI gate exit 0 = pass).
#
# Each cycle's brief generator produces a `verify-cycle-<N>.sh` from this
# template, filling in cycle-specific test commands.
#
# Skeleton phases:
#   1. Stack-up the per-DPS test infra (already done by DPS sub-agents; this
#      script assumes it's running)
#   2. Run unit + integration tests per cycle scope
#   3. Run cross-service smoke test if cycle touched ≥2 services
#   4. Report exit code (0 = pass, non-zero = fail → retry budget)
set -euo pipefail
CYCLE="${1:-CYCLE_NUM_PLACEHOLDER}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() {
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE${2:+,$2}}" >> "$AUDIT_LOG"
}

echo "[verify-cycle-$CYCLE] running CI gate"

# ─── Test commands (cycle-specific; populated by brief-generator) ───
# Examples (replace with actual cycle commands):
#   go test ./...
#   cargo test --release -p tilemap-service
#   pnpm --filter frontend-game test
#   pytest tests/integration/
#
# Placeholder for template — actual verify-cycle-<N>.sh appends specific commands

audit "verify_cycle_template_invoked"
echo "[verify-cycle-$CYCLE] TEMPLATE — no cycle-specific tests defined"
echo "[verify-cycle-$CYCLE] (this is the template; brief-generator emits per-cycle scripts)"
exit 0
