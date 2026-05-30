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

# Namespace selection (cycle-4 fix — base-branch collision):
#   git refuses to create `foo/bar/baz` when `foo/bar` already exists as a branch
#   (refs are filesystem-backed; a leaf ref can't also be a directory).
#   The original pattern `${BASE_BRANCH}/cycle-N-dps-I` collides whenever
#   BASE_BRANCH is an existing branch (the typical case — every active
#   foundation cycle runs off `mmo-rpg/foundation-mega-task`).
#
# Detection: if BASE_BRANCH resolves to a real ref, we use the flat
# `raid/cN/dps-I` namespace (matches the workaround cycles 1-3 used
# in-line). Otherwise (BASE_BRANCH is a tag, SHA, or non-existent placeholder)
# we keep the original nested form for backward-compat with any caller that
# relied on it.
USE_FLAT_NAMESPACE=0
if git show-ref --verify --quiet "refs/heads/${BASE_BRANCH}"; then
  USE_FLAT_NAMESPACE=1
fi

echo "[worktrees-create] cycle=$CYCLE dps_count=$DPS_COUNT base=$BASE_BRANCH flat=$USE_FLAT_NAMESPACE"
for i in $(seq 1 "$DPS_COUNT"); do
  WT_PATH="$WORKTREE_ROOT/cycle-${CYCLE}-dps-${i}"
  if [ "$USE_FLAT_NAMESPACE" = "1" ]; then
    BRANCH_NAME="raid/c${CYCLE}/dps-${i}"
  else
    BRANCH_NAME="${BASE_BRANCH}/cycle-${CYCLE}-dps-${i}"
  fi
  if [ -d "$WT_PATH" ]; then
    echo "  cycle=$CYCLE dps=$i — exists (skip)"
    continue
  fi
  git worktree add -b "$BRANCH_NAME" "$WT_PATH" "$BASE_BRANCH" 2>&1 | sed 's/^/  /'
done
echo "[worktrees-create] done"
