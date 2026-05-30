#!/usr/bin/env bash
# files-from-cycle — P7 cross-cycle file lookup helper
# Per RAID_WORKFLOW.md §12.7: Raid Leader reads the ONE CYCLE_LOG.md row
# (~200 tokens) and uses this helper to list files touched by that cycle.
#
# Usage:
#   files-from-cycle.sh <cycle_number>
#
# Strategy:
#   1. Find the commit(s) whose message contains `Cycle: <N>` (per
#      CYCLE_DECOMPOSITION §6 commit format).
#   2. Print the diff --stat names from those commits.
set -euo pipefail
CYCLE="${1:-}"
if [ -z "$CYCLE" ]; then
  echo "usage: files-from-cycle.sh <cycle_number>" >&2
  exit 1
fi
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# Pattern matches commit subjects with raid-cycle-<N> OR body line "Cycle: <N>"
# Cycle 0 is special — handle the bootstrap commits.
# Use fixed-string matching (`-F`) for the parenthesized prefix to avoid regex pitfalls.
if [ "$CYCLE" = "0" ]; then
  PATTERNS_FIXED=("raid-c0" "Cycle 0 pre-stage" "raid-cycle-0")
  PATTERNS_REGEX=("raid-c0")
else
  PATTERNS_FIXED=("raid-cycle-${CYCLE}" "Cycle: ${CYCLE}")
  PATTERNS_REGEX=("raid-cycle-${CYCLE}")
fi

SHA_LIST=""
# Try fixed-string patterns first (most reliable)
for pat in "${PATTERNS_FIXED[@]}"; do
  SHAS="$(git log --all --format="%H" -F --grep="$pat" 2>/dev/null || true)"
  if [ -n "$SHAS" ]; then
    SHA_LIST="$SHAS"
    break
  fi
done
# Fall back to regex patterns
if [ -z "$SHA_LIST" ]; then
  for pat in "${PATTERNS_REGEX[@]}"; do
    SHAS="$(git log --all --format="%H" -E --grep="$pat" 2>/dev/null || true)"
    if [ -n "$SHAS" ]; then
      SHA_LIST="$SHAS"
      break
    fi
  done
fi

if [ -z "$SHA_LIST" ]; then
  echo "[files-from-cycle] no commit matched cycle $CYCLE patterns" >&2
  exit 2
fi

echo "[files-from-cycle] cycle $CYCLE → commits:"
for sha in $SHA_LIST; do
  echo "  $sha $(git log -1 --format=%s "$sha")"
done

echo ""
echo "[files-from-cycle] files touched:"
for sha in $SHA_LIST; do
  git show --stat --format="" "$sha" 2>/dev/null | awk '/\|/ {print "  " $1}'
done | sort -u
