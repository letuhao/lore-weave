#!/usr/bin/env bash
# secret-scan-dps — B6 secret scan on DPS branch (Phase 5 BUILD end)
# Per RAID_WORKFLOW.md §13.6
#
# Usage: secret-scan-dps.sh <cycle> <dps_id>
set -euo pipefail
CYCLE="${1:-}"
DPS="${2:-}"
if [ -z "$CYCLE" ] || [ -z "$DPS" ]; then
  echo "usage: secret-scan-dps.sh <cycle> <dps_id>" >&2
  exit 1
fi
# PRR-11: JSON-encode cycle — bare int if numeric, quoted otherwise (e.g. "00X").
if [[ "$CYCLE" =~ ^[0-9]+$ ]]; then CYCLE_JSON="$CYCLE"; else CYCLE_JSON="\"$CYCLE\""; fi
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WT="$REPO_ROOT/../foundation-worktrees/cycle-${CYCLE}-dps-${DPS}"
CONFIG="$REPO_ROOT/.gitleaks.toml"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "[secret-scan-dps] WARN: gitleaks binary not installed — skipping (non-blocking; install in CI)" >&2
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"secret_scan_skipped\",\"cycle\":$CYCLE_JSON,\"dps\":$DPS,\"reason\":\"gitleaks_not_installed\"}" >> "$AUDIT_LOG"
  exit 0
fi

if [ ! -d "$WT" ]; then
  # smoke fallback: scan repo root
  SCAN_PATH="$REPO_ROOT"
else
  SCAN_PATH="$WT"
fi

if gitleaks detect --source "$SCAN_PATH" --config "$CONFIG" --no-banner --no-git --redact --report-format json --report-path "/tmp/raid-c${CYCLE}-dps${DPS}-leaks.json" 2>&1; then
  echo "[secret-scan-dps] ok: no leaks (cycle=$CYCLE dps=$DPS)"
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"secret_scan_clean\",\"cycle\":$CYCLE_JSON,\"dps\":$DPS}" >> "$AUDIT_LOG"
  exit 0
else
  echo "[secret-scan-dps] LEAK detected cycle=$CYCLE dps=$DPS — quarantine" >&2
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"secret_leak\",\"cycle\":$CYCLE_JSON,\"dps\":$DPS,\"report\":\"/tmp/raid-c${CYCLE}-dps${DPS}-leaks.json\"}" >> "$AUDIT_LOG"
  python3 "$REPO_ROOT/scripts/raid/escalation-writer.py" \
    --type secret_leak --cycle "$CYCLE" --phase build \
    --reason "gitleaks fired on cycle $CYCLE DPS $DPS — see /tmp/raid-c${CYCLE}-dps${DPS}-leaks.json" || true
  exit 1
fi
