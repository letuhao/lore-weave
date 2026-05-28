#!/usr/bin/env bash
# brief-structure-validator — B4 schema lint per RAID_WORKFLOW.md §13.4.
#
# Checks every brief has all 10 required sections + REMINDERS has ≥3 🔴 lines
# + total ≤ 4000 tokens (≈ 16000 chars heuristic).
#
# Usage: brief-structure-validator.sh <brief_path>
#        brief-structure-validator.sh --all       # validate all in cycle_briefs/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BRIEFS_DIR="$REPO_ROOT/docs/raid/cycle_briefs"

REQUIRED_SECTIONS=(
  "## 🎯 TL;DR"
  "## Dependencies"
  "## Scope (IN)"
  "## Scope (OUT"
  "## Acceptance criteria"
  "## DPS parallelism plan"
  "## Adversary review focus"
  "## Scope Guard CLEAR criteria"
  "## Cross-references"
  "## ⚠️ REMINDERS"
)

MAX_CHARS=16000  # ≈ 4000 token soft cap

validate_one() {
  local f="$1"
  local errs=()
  for sec in "${REQUIRED_SECTIONS[@]}"; do
    if ! grep -Fq "$sec" "$f"; then
      errs+=("missing section: $sec")
    fi
  done
  local red_count
  red_count="$(grep -c '🔴' "$f" || true)"
  if [ "$red_count" -lt 3 ]; then
    errs+=("REMINDERS must have ≥3 🔴 lines; found $red_count")
  fi
  local chars
  chars="$(wc -c < "$f" | tr -d ' ')"
  if [ "$chars" -gt "$MAX_CHARS" ]; then
    errs+=("brief size $chars chars > $MAX_CHARS (≈ 4000 tokens cap)")
  fi
  if [ "${#errs[@]}" -gt 0 ]; then
    echo "[validator] FAIL: $f" >&2
    for e in "${errs[@]}"; do echo "  $e" >&2; done
    return 1
  fi
  echo "[validator] ok: $(basename "$f")"
  return 0
}

if [ "${1:-}" = "--all" ]; then
  RC=0
  for f in "$BRIEFS_DIR"/*.md; do
    [ -f "$f" ] || continue
    if ! validate_one "$f"; then
      RC=1
    fi
  done
  exit "$RC"
fi

if [ -z "${1:-}" ]; then
  echo "usage: brief-structure-validator.sh <brief_path> | --all" >&2
  exit 2
fi
validate_one "$1"
