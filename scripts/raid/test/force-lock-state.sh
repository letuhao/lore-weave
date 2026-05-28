#!/usr/bin/env bash
# force-lock-state — TEST-ONLY helper per R3-WARN-1 D-CYCLE-0-LOCK-PROBE-SETUP
# Pre-positions .session-cycle-lock + READY_FOR_CYCLE_<N>.signal to test
# orchestrator refusal logic at boundary states.
#
# THIS SCRIPT MUST NEVER BE INVOKED OUTSIDE A SMOKE/TEST HARNESS.
# It deliberately bypasses the atomic transition contract for testing the
# refusal rule. Production code (orchestrator.py, auto-dispatcher.py) must
# NOT call this script.
#
# Usage:
#   force-lock-state.sh <state> [signal-yaml-path]
#
# States:
#   UNLOCKED                                  — clean state
#   00X                                       — smoke active state
#   READY_FOR_<N>                             — auto-dispatcher emitted state (signal required)
#   <N>                                       — cycle in progress
#
# Example (probe 2: lock=READY_FOR_2 + signal exists):
#   force-lock-state.sh READY_FOR_2 /tmp/test-signal.yaml
set -euo pipefail
STATE="${1:-}"
SIG_YAML="${2:-}"
if [ -z "$STATE" ]; then
  echo "usage: force-lock-state.sh <state> [signal-yaml-path]" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
RAID_DIR="$REPO_ROOT/docs/raid"
LOCK_PATH="$RAID_DIR/.session-cycle-lock"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "[force-lock-state] WARNING: TEST-ONLY helper — bypassing atomic transition contract"
echo "[force-lock-state] forcing lock=$STATE"

cat > "$LOCK_PATH.tmp" <<EOF
$STATE
# Last updated: $NOW by force-lock-state.sh (TEST ONLY)
EOF
mv -f "$LOCK_PATH.tmp" "$LOCK_PATH"

# Maybe write/copy a signal file
if [[ "$STATE" =~ ^READY_FOR_([0-9]+|0)$ ]]; then
  N="${BASH_REMATCH[1]}"
  SIG="$RAID_DIR/READY_FOR_CYCLE_${N}.signal"
  if [ -n "$SIG_YAML" ] && [ -f "$SIG_YAML" ]; then
    cp "$SIG_YAML" "$SIG"
    echo "[force-lock-state] copied signal from $SIG_YAML → $SIG"
  fi
fi

mkdir -p "$(dirname "$AUDIT_LOG")"
echo "{\"ts\":\"$NOW\",\"event\":\"test_lock_forced\",\"state\":\"$STATE\",\"signal_source\":\"${SIG_YAML:-none}\"}" >> "$AUDIT_LOG"

echo "[force-lock-state] done"
