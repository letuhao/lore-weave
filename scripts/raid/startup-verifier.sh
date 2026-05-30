#!/usr/bin/env bash
# RAID startup-verifier — P2 5-step session startup routine + Step 6 drift check
# (R3-WARN-2 D-CYCLE-0-DRIFT-ENFORCER)
#
# Per RAID_WORKFLOW.md v1.4 §12.2:
#   Step 1: Read docs/raid/CYCLE_LOG.md tail (last 5 entries)
#   Step 2: Read cycle brief docs/raid/cycle_briefs/<NN>_*.md
#   Step 3: Read IN_PROGRESS state if exists (P3 resume)
#   Step 4: Verify git + deps + clean
#   Step 5: Read OPEN_QUESTIONS_LOCKED.md sections for current cycle layer
#   Step 6 (R3): Drift check — CYCLE_DECOMPOSITION header version vs
#                RAID_WORKFLOW.md frontmatter version; mismatch → ESCALATIONS
#
# Exit codes:
#   0 = all green
#   2 = brief missing
#   3 = git/deps inconsistent
#   4 = LOCKED file missing
#   5 = spec_drift detected (R3 D-CYCLE-0-DRIFT-ENFORCER)
#
# Usage:
#   startup-verifier.sh <cycle_number>
#   startup-verifier.sh <cycle_number> --resume-mode   # tolerate IN_PROGRESS presence
set -euo pipefail

CYCLE="${1:-}"
MODE="${2:-normal}"
if [ -z "$CYCLE" ]; then
  echo "usage: startup-verifier.sh <cycle_number> [--resume-mode]" >&2
  exit 1
fi

# PRR-11: JSON-encode the cycle value. Numeric cycles stay bare integers
# (matches the Python writers + int-based consumers in cost-tracker.py /
# health-dashboard.py); non-numeric bootstrap values like "00X" are quoted
# so the emitted line is always valid JSON. The C0 bootstrap previously wrote
# unquoted "cycle":00X, producing 17 malformed AUDIT_LOG rows.
if [[ "$CYCLE" =~ ^[0-9]+$ ]]; then CYCLE_JSON="$CYCLE"; else CYCLE_JSON="\"$CYCLE\""; fi

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_CONFIG="$REPO_ROOT/scripts/raid/task_config.py"
if [ ! -f "$TASK_CONFIG" ]; then
  echo "ERROR: scripts/raid/task_config.py missing — RAID v1.6 task-config required" >&2
  exit 3
fi
PLANS_DIR="$REPO_ROOT/$(python3 "$TASK_CONFIG" get plan_dir 2>/dev/null)"
RAID_DIR="$REPO_ROOT/$(python3 "$TASK_CONFIG" get brief_dir 2>/dev/null | xargs dirname)"
AUDIT_LOG="$REPO_ROOT/$(python3 "$TASK_CONFIG" get audit_log 2>/dev/null)"
DECOMP_DOC="$REPO_ROOT/$(python3 "$TASK_CONFIG" get decomposition_doc 2>/dev/null)"
WORKFLOW_DOC="$REPO_ROOT/$(python3 "$TASK_CONFIG" get workflow_doc 2>/dev/null)"
LOCKED_DOC="$REPO_ROOT/$(python3 "$TASK_CONFIG" get locked_qs_doc 2>/dev/null)"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() {
  local event="$1"; shift
  local fields="$*"
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$event\",\"cycle\":$CYCLE_JSON,$fields}" >> "$AUDIT_LOG"
}

step() { echo "[startup-verifier] step $1: $2"; }

# ───────── Step 1 ─────────
step 1 "Read CYCLE_LOG.md tail"
if [ ! -f "$RAID_DIR/CYCLE_LOG.md" ]; then
  echo "  ERROR: CYCLE_LOG.md missing" >&2
  exit 3
fi
echo "  ok ($(wc -l < "$RAID_DIR/CYCLE_LOG.md") lines)"

# ───────── Step 2 ─────────
step 2 "Read cycle brief for cycle $CYCLE"
CYCLE_PADDED="$(printf '%03d' "$CYCLE" 2>/dev/null || echo "$CYCLE")"
# allow 00X for smoke
if [ "$CYCLE" = "00X" ] || [ "$CYCLE" = "0" ]; then
  BRIEF_PAT="00X_*.md"
elif [ "$CYCLE" -lt 10 ]; then
  BRIEF_PAT="0${CYCLE}_*.md"
else
  BRIEF_PAT="${CYCLE}_*.md"
fi
BRIEF="$(ls "$RAID_DIR/cycle_briefs/"$BRIEF_PAT 2>/dev/null | head -1 || true)"
if [ -z "$BRIEF" ]; then
  echo "  ERROR: no brief matching $BRIEF_PAT" >&2
  audit "startup_brief_missing" "\"pattern\":\"$BRIEF_PAT\""
  exit 2
fi
echo "  ok: $BRIEF"

# ───────── Step 3 ─────────
step 3 "Read IN_PROGRESS state (P3 resume check)"
IP_STATE="$RAID_DIR/IN_PROGRESS/cycle-${CYCLE_PADDED}-state.md"
if [ -f "$IP_STATE" ]; then
  if [ "$MODE" = "--resume-mode" ]; then
    echo "  ok: IN_PROGRESS exists; resume mode"
    audit "startup_resume_mode" "\"state_file\":\"$IP_STATE\""
  else
    echo "  ok: IN_PROGRESS exists; will resume from documented phase"
    audit "startup_resume_detected" "\"state_file\":\"$IP_STATE\""
  fi
else
  echo "  ok: no IN_PROGRESS (fresh cycle)"
fi

# ───────── Step 4 ─────────
step 4 "Verify git + deps + clean"
cd "$REPO_ROOT"
GIT_STATUS="$(git status --porcelain 2>/dev/null || echo "UNAVAILABLE")"
if [ "$GIT_STATUS" = "UNAVAILABLE" ]; then
  echo "  ERROR: git not available" >&2
  exit 3
fi
BRANCH="$(git branch --show-current 2>/dev/null || echo "")"
if [ -z "$BRANCH" ]; then
  echo "  ERROR: not on a branch" >&2
  exit 3
fi
echo "  ok: branch=$BRANCH; git status lines=$(echo "$GIT_STATUS" | grep -c . || true)"

# ───────── Step 5 ─────────
step 5 "Read OPEN_QUESTIONS_LOCKED.md sections (deferred to caller for layer-specific load)"
LOCKED="$LOCKED_DOC"
if [ ! -f "$LOCKED" ]; then
  echo "  ERROR: OPEN_QUESTIONS_LOCKED.md missing" >&2
  exit 4
fi
echo "  ok ($(wc -l < "$LOCKED") lines)"

# ───────── Step 6 (R3 D-CYCLE-0-DRIFT-ENFORCER) ─────────
step 6 "Drift check — CYCLE_DECOMPOSITION header version vs RAID_WORKFLOW frontmatter"
CD_VERSION="$(grep -m1 'last_synced_with_RAID_WORKFLOW_version:' "$DECOMP_DOC" 2>/dev/null | sed -E 's/.*last_synced_with_RAID_WORKFLOW_version:\*{0,2}[[:space:]]*//' | awk '{print $1}' || true)"
RW_VERSION="$(grep -m1 -E 'Version[^A-Za-z]+RAID[[:space:]]+v[0-9]+\.[0-9]+' "$WORKFLOW_DOC" 2>/dev/null | sed -E 's/.*RAID[[:space:]]+(v[0-9]+\.[0-9]+).*/\1/' || true)"
if [ -z "$CD_VERSION" ] || [ -z "$RW_VERSION" ]; then
  echo "  WARN: could not extract version markers (CD=$CD_VERSION RW=$RW_VERSION) — drift check inconclusive"
  audit "startup_drift_check_inconclusive" "\"cd\":\"$CD_VERSION\",\"rw\":\"$RW_VERSION\""
elif [ "$CD_VERSION" = "$RW_VERSION" ]; then
  echo "  ok: CD=$CD_VERSION matches RW=$RW_VERSION"
  audit "startup_drift_check_passed" "\"version\":\"$CD_VERSION\""
else
  echo "  ERROR: spec drift detected — CYCLE_DECOMPOSITION=$CD_VERSION RAID_WORKFLOW=$RW_VERSION" >&2
  audit "startup_drift_detected" "\"cd\":\"$CD_VERSION\",\"rw\":\"$RW_VERSION\""
  python3 "$REPO_ROOT/scripts/raid/escalation-writer.py" \
    --type spec_drift \
    --cycle "$CYCLE" \
    --phase clarify \
    --reason "CYCLE_DECOMPOSITION header version $CD_VERSION != RAID_WORKFLOW $RW_VERSION" 2>/dev/null || true
  exit 5
fi

echo "[startup-verifier] all 6 steps complete"
audit "startup_verifier_complete" "\"steps\":6"
exit 0
