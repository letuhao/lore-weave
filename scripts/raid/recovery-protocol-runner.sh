#!/usr/bin/env bash
# recovery-protocol-runner — P5 8-step recovery PROTOCOL executor
# Per RAID_WORKFLOW.md §12.5 (R3-Adversary-R2-BLOCK-1 fix)
#
# Steps (per §12.5):
#   1. Detect compaction (caller responsibility — usually compaction-detector.py)
#   2. Pause new tool calls (caller responsibility)
#   3. Re-read IN_PROGRESS state file (P3)
#   4. Re-read cycle brief (full)
#   5. Re-read OPEN_QUESTIONS_LOCKED.md sections for cycle's layer
#   6. Cross-reference against git log + AUDIT_LOG.jsonl tail + DPS worktrees
#   7. If CONSISTENT: emit "recovery_consistent" audit + continue from documented phase
#   8. If INCONSISTENT: HALT + ESCALATIONS row (type=p5_recovery_inconsistent)
#
# Exit codes:
#   0  = CONSISTENT (caller continues)
#   10 = INCONSISTENT (HALT — ESCALATIONS written)
#   2  = invalid input / missing state file
#
# Usage:
#   recovery-protocol-runner.sh <cycle_number>
set -euo pipefail
CYCLE="${1:-}"
if [ -z "$CYCLE" ]; then
  echo "usage: recovery-protocol-runner.sh <cycle_number>" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_CONFIG="$REPO_ROOT/scripts/raid/task_config.py"
if [ ! -f "$TASK_CONFIG" ]; then
  echo "ERROR: scripts/raid/task_config.py missing — RAID v1.6 task-config required" >&2
  exit 3
fi
RAID_DIR="$REPO_ROOT/$(python3 "$TASK_CONFIG" get brief_dir 2>/dev/null | xargs dirname)"
PLANS_DIR="$REPO_ROOT/$(python3 "$TASK_CONFIG" get plan_dir 2>/dev/null)"
LOCKED_DOC="$REPO_ROOT/$(python3 "$TASK_CONFIG" get locked_qs_doc 2>/dev/null)"
AUDIT_LOG="$REPO_ROOT/$(python3 "$TASK_CONFIG" get audit_log 2>/dev/null)"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CYCLE_PADDED="$(printf '%03d' "$CYCLE" 2>/dev/null || echo "$CYCLE")"

audit() {
  local event="$1"; local extra="${2:-}"
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$event\",\"cycle\":$CYCLE${extra:+,$extra}}" >> "$AUDIT_LOG"
}

echo "[recovery] cycle $CYCLE — executing P5 8-step protocol"

# Step 3 — Re-read IN_PROGRESS state
IP_STATE="$RAID_DIR/IN_PROGRESS/cycle-${CYCLE_PADDED}-state.md"
if [ ! -f "$IP_STATE" ]; then
  # PRR-10: a MISSING live state file is NOT automatically a crash. On normal
  # COMMIT the live state is MOVED to IN_PROGRESS/_archive/cycle-NNN-state.md
  # and the cycle is marked DONE in CYCLE_LOG.md. Treating "missing" as
  # INCONSISTENT produced 23 false-positive p5_recovery_inconsistent
  # escalations for completed cycles. Only a missing-AND-not-completed state
  # is a genuine crash.
  ARCHIVED_STATE="$RAID_DIR/IN_PROGRESS/_archive/cycle-${CYCLE_PADDED}-state.md"
  CYCLE_LOG="$RAID_DIR/CYCLE_LOG.md"
  CYCLE_DONE=0
  if [ -f "$CYCLE_LOG" ] && \
     grep -Eq "^\|[[:space:]]*${CYCLE}[[:space:]]*\|.*\|[[:space:]]*DONE[[:space:]]*\|" "$CYCLE_LOG"; then
    CYCLE_DONE=1
  fi
  if [ -f "$ARCHIVED_STATE" ] || [ "$CYCLE_DONE" = "1" ]; then
    echo "[recovery] step 3: live state missing but cycle $CYCLE already completed" \
         "(archived=$([ -f "$ARCHIVED_STATE" ] && echo yes || echo no), done=$CYCLE_DONE) — CONSISTENT, no recovery needed"
    audit "recovery_consistent" "\"reason\":\"cycle_completed_state_archived\",\"archived\":$([ -f "$ARCHIVED_STATE" ] && echo true || echo false),\"cycle_log_done\":$([ "$CYCLE_DONE" = "1" ] && echo true || echo false)"
    exit 0
  fi
  echo "[recovery] step 3 FAIL: no IN_PROGRESS state for cycle $CYCLE (and not completed/archived) — genuine crash" >&2
  audit "recovery_halted" "\"reason\":\"in_progress_missing\""
  python3 "$REPO_ROOT/scripts/raid/escalation-writer.py" \
    --type p5_recovery_inconsistent --cycle "$CYCLE" --phase recovery \
    --mismatch "IN_PROGRESS state file missing for cycle $CYCLE and cycle not completed/archived; cannot reconstruct phase" || true
  exit 10
fi
echo "[recovery] step 3 ok: read $IP_STATE"

# Parse IN_PROGRESS frontmatter for current_phase + dps_status via Python
IP_DATA="$(python3 "$REPO_ROOT/scripts/raid/in-progress-state-writer.py" read --cycle "$CYCLE" 2>/dev/null || echo "{}")"
CURRENT_PHASE="$(echo "$IP_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('current_phase',''))" 2>/dev/null || true)"
DPS_STATUS_RAW="$(echo "$IP_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('dps_status', [])))" 2>/dev/null || echo "[]")"
echo "[recovery]   parsed current_phase=$CURRENT_PHASE"

# Step 4 — Re-read cycle brief
if [ "$CYCLE" = "0" ] || [ "$CYCLE" = "00X" ]; then
  BRIEF_PAT="00X_*.md"
elif [ "$CYCLE" -lt 10 ]; then
  BRIEF_PAT="0${CYCLE}_*.md"
else
  BRIEF_PAT="${CYCLE}_*.md"
fi
BRIEF="$(ls "$RAID_DIR/cycle_briefs/"$BRIEF_PAT 2>/dev/null | head -1 || true)"
if [ -z "$BRIEF" ]; then
  echo "[recovery] step 4 FAIL: no brief matching $BRIEF_PAT" >&2
  audit "recovery_halted" "\"reason\":\"brief_missing\""
  python3 "$REPO_ROOT/scripts/raid/escalation-writer.py" \
    --type p5_recovery_inconsistent --cycle "$CYCLE" --phase recovery \
    --mismatch "Cycle brief missing during P5 recovery — cycle scope unrecoverable" || true
  exit 10
fi
echo "[recovery] step 4 ok: brief=$BRIEF"

# Step 5 — Re-read OPEN_QUESTIONS_LOCKED.md (existence check is enough; layer-specific load is caller's job)
LOCKED="$LOCKED_DOC"
if [ ! -f "$LOCKED" ]; then
  echo "[recovery] step 5 FAIL: LOCKED file missing" >&2
  audit "recovery_halted" "\"reason\":\"locked_missing\""
  exit 10
fi
echo "[recovery] step 5 ok: LOCKED present"

# Step 6 — Cross-reference git log + AUDIT_LOG + DPS worktree states
cd "$REPO_ROOT"
INCONSISTENCIES=""

# (a) phase=COMMIT requires HEAD commit message to reference THIS cycle
# Pattern matches only the cycle being tested (raid-c0 only matches cycle 0)
if [ "$CURRENT_PHASE" = "COMMIT" ] || [ "$CURRENT_PHASE" = "RETRO" ]; then
  HEAD_MSG="$(git log -1 --format=%s 2>/dev/null || echo "")"
  if [ "$CYCLE" = "0" ] || [ "$CYCLE" = "00X" ]; then
    CYCLE_PAT="(raid-cycle-0|raid-c0|Cycle:[[:space:]]+0\$)"
  else
    CYCLE_PAT="(raid-cycle-${CYCLE}|Cycle:[[:space:]]+${CYCLE}\$)"
  fi
  if ! echo "$HEAD_MSG" | grep -qE "$CYCLE_PAT"; then
    INCONSISTENCIES="${INCONSISTENCIES}phase=$CURRENT_PHASE but HEAD subject does not reference cycle ${CYCLE}; "
  fi
fi

# (b) DPS commit_sha must exist if status=complete (delegate to Python helper)
DPS_ERR="$(python3 "$REPO_ROOT/scripts/raid/_recovery_dps_check.py" "$CYCLE_PADDED" 2>/dev/null || true)"
if [ -n "$DPS_ERR" ]; then
  INCONSISTENCIES="${INCONSISTENCIES}${DPS_ERR}; "
fi

# (c) AUDIT_LOG tail should mention this cycle if phase progressed past CLARIFY
if [ -f "$AUDIT_LOG" ] && [ "$CURRENT_PHASE" != "CLARIFY" ]; then
  CYCLE_EVENTS="$(tail -50 "$AUDIT_LOG" | grep -c "\"cycle\":$CYCLE" 2>/dev/null || echo 0)"
  if [ "$CYCLE_EVENTS" = "0" ]; then
    INCONSISTENCIES="${INCONSISTENCIES}IN_PROGRESS phase=$CURRENT_PHASE but no audit events for cycle $CYCLE in tail; "
  fi
fi

echo "[recovery] step 6 ok: cross-references checked"

# Step 7 / 8 — decide
if [ -z "$INCONSISTENCIES" ]; then
  echo "[recovery] step 7: CONSISTENT — continue from phase=$CURRENT_PHASE"
  audit "recovery_consistent" "\"phase\":\"$CURRENT_PHASE\",\"dps_resumed_from\":\"see in_progress dps_status\""
  exit 0
else
  echo "[recovery] step 8: INCONSISTENT — HALT + ESCALATIONS"
  echo "[recovery]   mismatches: $INCONSISTENCIES" >&2
  audit "recovery_halted" "\"reason\":\"inconsistent\",\"mismatch\":\"${INCONSISTENCIES//\"/\\\"}\""
  python3 "$REPO_ROOT/scripts/raid/escalation-writer.py" \
    --type p5_recovery_inconsistent --cycle "$CYCLE" --phase recovery \
    --mismatch "$INCONSISTENCIES" || true
  exit 10
fi
