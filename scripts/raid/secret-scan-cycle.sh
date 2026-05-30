#!/usr/bin/env bash
# secret-scan-cycle — B6 cycle-wide scan (Phase 6 VERIFY, before Tank rebase)
# Per RAID_WORKFLOW.md §13.6
#
# Usage: secret-scan-cycle.sh <cycle>
set -euo pipefail
CYCLE="${1:-}"
if [ -z "$CYCLE" ]; then
  echo "usage: secret-scan-cycle.sh <cycle>" >&2
  exit 1
fi
# PRR-11: JSON-encode cycle — bare int if numeric, quoted otherwise (e.g. "00X").
if [[ "$CYCLE" =~ ^[0-9]+$ ]]; then CYCLE_JSON="$CYCLE"; else CYCLE_JSON="\"$CYCLE\""; fi
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKTREE_ROOT="$REPO_ROOT/../foundation-worktrees"
CONFIG="$REPO_ROOT/.gitleaks.toml"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "[secret-scan-cycle] WARN: gitleaks not installed — skipping" >&2
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"secret_scan_skipped\",\"cycle\":$CYCLE_JSON,\"scope\":\"cycle\",\"reason\":\"gitleaks_not_installed\"}" >> "$AUDIT_LOG"
  exit 0
fi

LEAKS=0
for wt in "$WORKTREE_ROOT"/cycle-"$CYCLE"-dps-*; do
  [ -d "$wt" ] || continue
  if ! gitleaks detect --source "$wt" --config "$CONFIG" --no-banner --no-git --redact 2>&1; then
    LEAKS=$((LEAKS + 1))
  fi
done

# Also scan main worktree (foundation branch)
if ! gitleaks detect --source "$REPO_ROOT" --config "$CONFIG" --no-banner --no-git --redact 2>&1; then
  LEAKS=$((LEAKS + 1))
fi

if [ "$LEAKS" -eq 0 ]; then
  echo "[secret-scan-cycle] ok: cycle $CYCLE clean"
  echo "{\"ts\":\"$NOW\",\"event\":\"secret_scan_clean\",\"cycle\":$CYCLE_JSON,\"scope\":\"cycle\"}" >> "$AUDIT_LOG"
  exit 0
fi
echo "[secret-scan-cycle] $LEAKS leak(s) detected — halt rebase" >&2
echo "{\"ts\":\"$NOW\",\"event\":\"secret_leak\",\"cycle\":$CYCLE_JSON,\"scope\":\"cycle\",\"leak_count\":$LEAKS}" >> "$AUDIT_LOG"
exit 1
