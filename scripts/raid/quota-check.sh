#!/usr/bin/env bash
# quota-check — Q4 pre-cycle quota check
# Per RAID_WORKFLOW.md §14.4
#
# Reads QUOTA_LOG.jsonl + quota-profile.yaml; computes estimated remaining
# 5h window; outputs decision PROCEED|RISKY|WAIT.
#
# Exit codes (consumed by orchestrator.py):
#   0 = PROCEED
#   1 = RISKY (warn; orchestrator continues)
#   2 = WAIT-FOR-RESET (orchestrator halts)
#
# Sub-commands:
#   quota-check.sh <cycle>                       # main pre-cycle check
#   quota-check.sh --classify <complexity>       # dump dps_cap from profile
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROFILE="$REPO_ROOT/contracts/raid/quota-profile.yaml"
QUOTA_LOG="$REPO_ROOT/docs/raid/QUOTA_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ ! -f "$PROFILE" ]; then
  echo "[quota-check] ERROR: profile missing: $PROFILE" >&2
  exit 3
fi

# --classify mode: print dps_cap for given complexity
if [ "${1:-}" = "--classify" ]; then
  COMPLEXITY="${2:-medium}"
  CAP="$(python3 "$REPO_ROOT/scripts/raid/_quota_helper.py" --classify "$COMPLEXITY")"
  echo "dps_cap: $CAP"
  exit 0
fi

CYCLE="${1:-}"
if [ -z "$CYCLE" ]; then
  echo "usage: quota-check.sh <cycle> | --classify <complexity>" >&2
  exit 3
fi

# Delegate computation to a Python helper to avoid shell-quoting hell
DECISION_LINE="$(python3 "$REPO_ROOT/scripts/raid/_quota_helper.py" --decide --cycle "$CYCLE" --quota-log "$QUOTA_LOG" --profile "$PROFILE")"
# Output format: DECISION:remaining:typical:burn
DECISION="${DECISION_LINE%%:*}"
REST="${DECISION_LINE#*:}"
REMAINING="${REST%%:*}"
REST="${REST#*:}"
TYPICAL="${REST%%:*}"
RECENT_BURN="${REST#*:}"

# Map decision → exit code
case "$DECISION" in
  PROCEED) EXIT=0 ;;
  RISKY)   EXIT=1 ;;
  WAIT)    EXIT=2 ;;
  *)       echo "[quota-check] unknown decision: $DECISION" >&2; exit 3 ;;
esac

mkdir -p "$(dirname "$QUOTA_LOG")"
printf '{"ts":"%s","cycle":"%s","phase":"pre_cycle","event":"quota_check","recommendation":"%s","estimated_remaining":%s,"typical_cycle":%s,"recent_burn":%s}\n' \
  "$NOW" "$CYCLE" "$DECISION" "$REMAINING" "$TYPICAL" "$RECENT_BURN" >> "$QUOTA_LOG"

echo "[quota-check] cycle=$CYCLE recent_burn=${RECENT_BURN} remaining=${REMAINING} typical=${TYPICAL} → ${DECISION}"
exit "$EXIT"
