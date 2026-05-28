#!/usr/bin/env bash
# worktrees-create — B1 worktree lifecycle (Phase 4 PLAN)
# Per RAID_WORKFLOW.md §13.1
#
# Usage: worktrees-create.sh <cycle_number> <dps_count> [base_branch]
set -euo pipefail
CYCLE="${1:-}"
DPS_COUNT="${2:-}"
BASE_BRANCH="${3:-mmo-rpg/foundation-mega-task}"
if [ -z "$CYCLE" ] || [ -z "$DPS_COUNT" ]; then
  echo "usage: worktrees-create.sh <cycle> <dps_count> [base_branch]" >&2
  exit 1
fi
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKTREE_ROOT="$REPO_ROOT/../foundation-worktrees"
mkdir -p "$WORKTREE_ROOT/_archive" "$WORKTREE_ROOT/_quarantine"

cd "$REPO_ROOT"
echo "[worktrees-create] cycle=$CYCLE dps_count=$DPS_COUNT base=$BASE_BRANCH"
for i in $(seq 1 "$DPS_COUNT"); do
  WT_PATH="$WORKTREE_ROOT/cycle-${CYCLE}-dps-${i}"
  BRANCH_NAME="${BASE_BRANCH}/cycle-${CYCLE}-dps-${i}"
  if [ -d "$WT_PATH" ]; then
    echo "  cycle=$CYCLE dps=$i — exists (skip)"
    continue
  fi
  git worktree add -b "$BRANCH_NAME" "$WT_PATH" "$BASE_BRANCH" 2>&1 | sed 's/^/  /'
done
echo "[worktrees-create] done"
