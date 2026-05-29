#!/usr/bin/env bash
# worktrees-cleanup — B1 worktree lifecycle (Phase 11 COMMIT)
# Per RAID_WORKFLOW.md §13.1
#
# For each cycle-N-dps-I worktree:
#   - If branch merged + tree clean: git worktree remove + delete branch
#   - If tree dirty: ARCHIVE to _archive/ with timestamp + AUDIT warning
#
# Usage: worktrees-cleanup.sh <cycle_number>
set -euo pipefail
CYCLE="${1:-}"
if [ -z "$CYCLE" ]; then
  echo "usage: worktrees-cleanup.sh <cycle>" >&2
  exit 1
fi
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKTREE_ROOT="$REPO_ROOT/../foundation-worktrees"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TS="$(date -u +%Y%m%dT%H%M%S)"

audit() {
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE${2:+,$2}}" >> "$AUDIT_LOG"
}

cd "$REPO_ROOT"
echo "[worktrees-cleanup] cycle=$CYCLE"

for wt in "$WORKTREE_ROOT"/cycle-"$CYCLE"-dps-*; do
  [ -d "$wt" ] || continue
  name="$(basename "$wt")"
  # check tree clean
  if [ -n "$(cd "$wt" && git status --porcelain 2>/dev/null)" ]; then
    archive="$WORKTREE_ROOT/_archive/${name}-DIRTY-${TS}"
    echo "  $name — DIRTY → archive to $archive (preserve forensic)"
    mv "$wt" "$archive"
    audit "worktree_archived_dirty" "\"name\":\"$name\",\"archive\":\"$archive\""
    continue
  fi
  echo "  $name — clean → removing"
  git worktree remove --force "$wt" 2>&1 | sed 's/^/    /' || true
  # delete branch if exists
  branch="mmo-rpg/foundation-mega-task/${name}"
  git branch -D "$branch" 2>/dev/null || true
  audit "worktree_removed" "\"name\":\"$name\""
done
echo "[worktrees-cleanup] done"
