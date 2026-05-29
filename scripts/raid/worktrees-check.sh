#!/usr/bin/env bash
# worktrees-check — Pre-cycle startup check (runs as part of P2 startup routine).
# Refuses to start a new cycle if stale worktrees from prior cycles exist.
# Per RAID_WORKFLOW.md §13.1
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKTREE_ROOT="$REPO_ROOT/../foundation-worktrees"

cd "$REPO_ROOT"
STALE="$(git worktree list --porcelain 2>/dev/null | grep "foundation-worktrees" | grep -v "_archive" | grep -v "_quarantine" || true)"
if [ -z "$STALE" ]; then
  echo "[worktrees-check] ok: no stale worktrees"
  exit 0
fi
echo "[worktrees-check] STALE WORKTREES from prior cycles:" >&2
echo "$STALE" >&2
echo "" >&2
echo "Refusing to start cycle. Run scripts/raid/worktrees-cleanup.sh <prior-cycle> or" >&2
echo "scripts/raid/recover-from-crash.sh --inspect to investigate." >&2
exit 1
