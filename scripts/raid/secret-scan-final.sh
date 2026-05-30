#!/usr/bin/env bash
# secret-scan-final — B6 final scan before COMMIT (Phase 11)
# Per RAID_WORKFLOW.md §13.6
set -euo pipefail
CYCLE="${1:-}"
if [ -z "$CYCLE" ]; then
  echo "usage: secret-scan-final.sh <cycle>" >&2
  exit 1
fi
# PRR-11: JSON-encode cycle — bare int if numeric, quoted otherwise (e.g. "00X").
if [[ "$CYCLE" =~ ^[0-9]+$ ]]; then CYCLE_JSON="$CYCLE"; else CYCLE_JSON="\"$CYCLE\""; fi
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$REPO_ROOT/.gitleaks.toml"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "[secret-scan-final] WARN: gitleaks not installed — skipping" >&2
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"secret_scan_skipped\",\"cycle\":$CYCLE_JSON,\"scope\":\"final\",\"reason\":\"gitleaks_not_installed\"}" >> "$AUDIT_LOG"
  exit 0
fi
cd "$REPO_ROOT"
if gitleaks detect --source "$REPO_ROOT" --config "$CONFIG" --no-banner --no-git --redact 2>&1; then
  echo "[secret-scan-final] ok: cycle $CYCLE clean for commit"
  echo "{\"ts\":\"$NOW\",\"event\":\"secret_scan_clean\",\"cycle\":$CYCLE_JSON,\"scope\":\"final\"}" >> "$AUDIT_LOG"
  exit 0
fi
echo "[secret-scan-final] LEAK detected at commit boundary — aborting" >&2
echo "{\"ts\":\"$NOW\",\"event\":\"secret_leak\",\"cycle\":$CYCLE_JSON,\"scope\":\"final\"}" >> "$AUDIT_LOG"
exit 1
