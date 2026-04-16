#!/usr/bin/env bash
# workflow-gate.sh — Enforce workflow state transitions for AI coding agents
# Part of the Agentic Workflow v2 bundle.
#
# Usage:
#   ./scripts/workflow-gate.sh phase <phase_name>    # Transition to phase
#   ./scripts/workflow-gate.sh complete <name> <evidence> # Mark phase done
#   ./scripts/workflow-gate.sh check <phase_name>    # Check if phase was completed
#   ./scripts/workflow-gate.sh status                # Show current state
#   ./scripts/workflow-gate.sh pre-commit            # Pre-commit gate check
#   ./scripts/workflow-gate.sh reset                 # Reset state (new task)
#   ./scripts/workflow-gate.sh skip <phase> <reason> # Record authorized skip
#   ./scripts/workflow-gate.sh size <XS|S|M|L|XL> <files> <logic> <side_effects>
#
# Requirements: bash, python 3.x
# State file: .workflow-state.json (add to .gitignore)

STATE_FILE=".workflow-state.json"

# Phase order (index = sequence number)
# [CUSTOMIZE] Add/remove phases to match your workflow
PHASES=("clarify" "design" "review-design" "plan" "build" "verify" "review-code" "qc" "session" "commit" "retro")

# Phases skippable per size classification:
# XS: clarify + plan   S: plan only   M/L/XL: nothing
SKIPPABLE_XS=("clarify" "plan")
SKIPPABLE_S=("plan")
SKIPPABLE=()  # default: nothing skippable until size is set

# --- Detect python command ---
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
  PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
  PYTHON_CMD="python"
else
  echo "ERROR: python3 or python not found. Install Python 3.x."
  exit 1
fi

get_phase_index() {
  local phase="$1"
  for i in "${!PHASES[@]}"; do
    if [[ "${PHASES[$i]}" == "$phase" ]]; then
      echo "$i"
      return 0
    fi
  done
  echo "-1"
  return 1
}

init_state() {
  if [[ ! -f "$STATE_FILE" ]]; then
    cat > "$STATE_FILE" << 'INIT'
{
  "task": "",
  "size": null,
  "size_counts": {"files": 0, "logic": 0, "side_effects": 0},
  "current_phase": null,
  "current_phase_index": -1,
  "phases_completed": [],
  "phases_skipped": [],
  "verify_evidence": null,
  "started_at": null,
  "last_transition": null
}
INIT
  fi
}

cmd_phase() {
  local phase="$1"
  local idx
  idx=$(get_phase_index "$phase")

  if [[ "$idx" == "-1" ]]; then
    echo "ERROR: Unknown phase '$phase'. Valid phases: ${PHASES[*]}"
    exit 1
  fi

  init_state

  local current_idx
  current_idx=$($PYTHON_CMD -c "import json; print(json.load(open('$STATE_FILE'))['current_phase_index'])" 2>/dev/null || echo "-1")

  # Load size-based skippable list
  local task_size
  task_size=$($PYTHON_CMD -c "import json; print(json.load(open('$STATE_FILE')).get('size') or 'none')" 2>/dev/null || echo "none")

  local skippable_for_size=()
  case "$task_size" in
    XS) skippable_for_size=("${SKIPPABLE_XS[@]}") ;;
    S)  skippable_for_size=("${SKIPPABLE_S[@]}") ;;
    *)  skippable_for_size=() ;;  # M/L/XL/unset: nothing auto-skippable
  esac

  # Check for phase skipping — all intermediate phases must be completed or skipped
  if [[ "$current_idx" == "null" ]]; then current_idx=-1; fi
  {
    local expected_next=$((current_idx + 1))
    if [[ "$idx" -gt "$expected_next" ]]; then
      # Get list of already completed/skipped phases
      local completed_phases
      completed_phases=$($PYTHON_CMD -c "
import json
state = json.load(open('$STATE_FILE'))
print(' '.join([p['phase'] for p in state.get('phases_completed', [])]))
" 2>/dev/null || echo "")

      local has_unskippable=false
      for ((i=expected_next; i<idx; i++)); do
        local skipped_phase="${PHASES[$i]}"
        # Check if already completed/skipped
        if echo "$completed_phases" | grep -qw "$skipped_phase"; then
          continue
        fi
        # Not completed — check if it's in the size-based skippable list
        local is_skippable=false
        for s in "${skippable_for_size[@]}"; do
          if [[ "$s" == "$skipped_phase" ]]; then
            is_skippable=true
            break
          fi
        done
        if [[ "$is_skippable" == false ]]; then
          has_unskippable=true
          echo "WARNING: Phase '${PHASES[$i]}' not completed and not auto-skippable for size '$task_size'"
        fi
      done

      if [[ "$has_unskippable" == true ]]; then
        local from_label="(start)"
        if [[ "$current_idx" -ge 0 ]]; then from_label="'${PHASES[$current_idx]}'"; fi
        echo "BLOCKED: Cannot skip from $from_label to '$phase'."
        if [[ "$task_size" == "none" ]]; then
          echo "Task size not classified yet! Run: workflow-gate.sh size <XS|S|M|L|XL> <files> <logic> <side_effects>"
        else
          echo "Task size is '$task_size'. Missing phases must be completed or explicitly skipped."
        fi
        exit 1
      fi
    fi
  }

  # Update state
  $PYTHON_CMD -c "
import json, datetime
state = json.load(open('$STATE_FILE'))
state['current_phase'] = '$phase'
state['current_phase_index'] = $idx
state['last_transition'] = datetime.datetime.now().isoformat()
if not state.get('started_at'):
    state['started_at'] = datetime.datetime.now().isoformat()
json.dump(state, open('$STATE_FILE', 'w'), indent=2)
"
  echo "OK: Entered phase '$phase' (${idx}/${#PHASES[@]})"
}

cmd_size() {
  local size="$1"
  local files="${2:-0}"
  local logic="${3:-0}"
  local side_effects="${4:-0}"

  # Validate size
  case "$size" in
    XS|S|M|L|XL) ;;
    *)
      echo "ERROR: Invalid size '$size'. Must be XS, S, M, L, or XL."
      exit 1
      ;;
  esac

  # Validate size matches counts
  local expected_size=""
  if [[ "$files" -le 1 && "$logic" -le 1 && "$side_effects" -eq 0 ]]; then
    expected_size="XS"
  elif [[ "$files" -le 2 && "$logic" -le 3 && "$side_effects" -eq 0 ]]; then
    expected_size="S"
  elif [[ "$files" -le 5 ]]; then
    expected_size="M"
  elif [[ "$files" -le 9 ]]; then
    expected_size="L"
  else
    expected_size="XL"
  fi

  # Warn if claimed size is smaller than what counts suggest
  local size_order="XS S M L XL"
  local claimed_pos=$(echo "$size_order" | tr ' ' '\n' | grep -n "^${size}$" | cut -d: -f1)
  local expected_pos=$(echo "$size_order" | tr ' ' '\n' | grep -n "^${expected_size}$" | cut -d: -f1)

  if [[ "$claimed_pos" -lt "$expected_pos" ]]; then
    echo "WARNING: You classified as $size but counts suggest $expected_size ($files files, $logic logic, $side_effects side effects)"
    echo "BLOCKED: Cannot undersize a task. Use '$expected_size' or larger."
    exit 1
  fi

  init_state

  $PYTHON_CMD -c "
import json, datetime
state = json.load(open('$STATE_FILE'))
state['size'] = '$size'
state['size_counts'] = {'files': $files, 'logic': $logic, 'side_effects': $side_effects}
json.dump(state, open('$STATE_FILE', 'w'), indent=2)
"
  echo "OK: Task classified as $size (files=$files, logic=$logic, side_effects=$side_effects)"

  case "$size" in
    XS) echo "  Allowed skips: CLARIFY, PLAN" ;;
    S)  echo "  Allowed skips: PLAN only" ;;
    *)  echo "  No phases may be skipped" ;;
  esac
}

cmd_check() {
  local phase="$1"
  init_state

  local completed
  completed=$($PYTHON_CMD -c "
import json
state = json.load(open('$STATE_FILE'))
phases = [p['phase'] for p in state.get('phases_completed', [])]
print('yes' if '$phase' in phases else 'no')
" 2>/dev/null || echo "no")

  if [[ "$completed" == "yes" ]]; then
    echo "OK: Phase '$phase' is completed"
    return 0
  else
    echo "NOT COMPLETED: Phase '$phase' has not been completed yet"
    return 1
  fi
}

cmd_complete() {
  local phase="$1"
  local evidence="$2"
  init_state

  $PYTHON_CMD -c "
import json, datetime
state = json.load(open('$STATE_FILE'))
if 'phases_completed' not in state:
    state['phases_completed'] = []
entry = {
    'phase': '$phase',
    'completed_at': datetime.datetime.now().isoformat(),
    'evidence': '''$evidence'''
}
# Remove existing entry for this phase if re-completing
state['phases_completed'] = [p for p in state['phases_completed'] if p['phase'] != '$phase']
state['phases_completed'].append(entry)
if '$phase' == 'verify':
    state['verify_evidence'] = '''$evidence'''
json.dump(state, open('$STATE_FILE', 'w'), indent=2)
"
  echo "OK: Phase '$phase' marked complete"
}

cmd_skip() {
  local phase="$1"
  local reason="$2"

  if [[ -z "$reason" ]]; then
    echo "ERROR: Must provide a reason for skipping. Usage: workflow-gate.sh skip <phase> <reason>"
    exit 1
  fi

  init_state

  $PYTHON_CMD -c "
import json, datetime
state = json.load(open('$STATE_FILE'))
if 'phases_skipped' not in state:
    state['phases_skipped'] = []
entry = {
    'phase': '$phase',
    'reason': '''$reason''',
    'skipped_at': datetime.datetime.now().isoformat()
}
state['phases_skipped'].append(entry)
# Also count as completed (so gate doesn't block)
if 'phases_completed' not in state:
    state['phases_completed'] = []
state['phases_completed'] = [p for p in state['phases_completed'] if p['phase'] != '$phase']
state['phases_completed'].append({
    'phase': '$phase',
    'completed_at': datetime.datetime.now().isoformat(),
    'evidence': 'SKIPPED: ' + '''$reason'''
})
json.dump(state, open('$STATE_FILE', 'w'), indent=2)
"
  echo "OK: Phase '$phase' skipped (reason: $reason)"
}

cmd_pre_commit() {
  init_state

  if [[ ! -f "$STATE_FILE" ]]; then
    echo "WARNING: No workflow state found. Proceeding without enforcement."
    exit 0
  fi

  # Check that verify phase was completed
  local verify_done
  verify_done=$($PYTHON_CMD -c "
import json
state = json.load(open('$STATE_FILE'))
phases = [p['phase'] for p in state.get('phases_completed', [])]
print('yes' if 'verify' in phases else 'no')
" 2>/dev/null || echo "no")

  if [[ "$verify_done" == "no" ]]; then
    echo ""
    echo "============================================"
    echo "  COMMIT BLOCKED: Phase 6 VERIFY not done"
    echo "============================================"
    echo ""
    echo "You must complete the verification gate before committing."
    echo "Run your tests/build, read the output, then:"
    echo "  ./scripts/workflow-gate.sh complete verify \"<test output summary>\""
    echo ""
    echo "Or if this is a trivial change that doesn't need verification:"
    echo "  ./scripts/workflow-gate.sh skip verify \"trivial change: <reason>\""
    echo ""
    exit 1
  fi

  # [CUSTOMIZE] Remove this block if your project doesn't use session tracking
  # Check that session phase was completed
  local session_done
  session_done=$($PYTHON_CMD -c "
import json
state = json.load(open('$STATE_FILE'))
phases = [p['phase'] for p in state.get('phases_completed', [])]
print('yes' if 'session' in phases else 'no')
" 2>/dev/null || echo "no")

  if [[ "$session_done" == "no" ]]; then
    echo ""
    echo "============================================"
    echo "  COMMIT BLOCKED: Phase 9 SESSION not done"
    echo "============================================"
    echo ""
    echo "Update session notes before committing, then:"
    echo "  ./scripts/workflow-gate.sh complete session \"updated session notes\""
    echo ""
    exit 1
  fi

  echo "OK: Pre-commit checks passed (verify + session completed)"
  exit 0
}

cmd_status() {
  init_state

  if [[ ! -f "$STATE_FILE" ]]; then
    echo "No workflow state. Run: workflow-gate.sh phase clarify"
    exit 0
  fi

  $PYTHON_CMD -c "
import json
state = json.load(open('$STATE_FILE'))
completed = [p['phase'] for p in state.get('phases_completed', [])]
skipped = [p['phase'] for p in state.get('phases_skipped', [])]
current = state.get('current_phase', 'none')
phases = ['clarify','design','review-design','plan','build','verify','review-code','qc','session','commit','retro']

size = state.get('size', 'NOT SET')
counts = state.get('size_counts', {})
print(f'Task: {state.get(\"task\", \"(unnamed)\")}')
print(f'Size: {size} (files={counts.get(\"files\",0)}, logic={counts.get(\"logic\",0)}, side_effects={counts.get(\"side_effects\",0)})')
print(f'Current phase: {current}')
print()
for p in phases:
    if p in completed and p in skipped:
        status = 'SKIPPED'
    elif p in completed:
        status = 'DONE'
    elif p == current:
        status = 'IN PROGRESS'
    else:
        status = '  '
    marker = {'DONE': '[x]', 'SKIPPED': '[S]', 'IN PROGRESS': '[>]'}.get(status, '[ ]')
    print(f'  {marker} {p}')
"
}

cmd_reset() {
  rm -f "$STATE_FILE"
  echo "OK: Workflow state reset. Ready for new task."
}

# Main dispatcher
case "${1:-}" in
  phase)    cmd_phase "$2" ;;
  complete) cmd_complete "$2" "$3" ;;
  check)    cmd_check "$2" ;;
  skip)     cmd_skip "$2" "$3" ;;
  size)     cmd_size "$2" "${3:-0}" "${4:-0}" "${5:-0}" ;;
  pre-commit) cmd_pre_commit ;;
  status)   cmd_status ;;
  reset)    cmd_reset ;;
  *)
    echo "Usage: workflow-gate.sh {phase|complete|check|skip|size|pre-commit|status|reset} [args]"
    echo ""
    echo "Commands:"
    echo "  phase <name>                          Enter a phase"
    echo "  complete <name> <evidence>             Mark phase as done with evidence"
    echo "  check <name>                           Check if phase is completed"
    echo "  skip <name> <reason>                   Skip a phase (must give reason)"
    echo "  size <XS|S|M|L|XL> <files> <logic> <side_effects>  Classify task size"
    echo "  pre-commit                             Run pre-commit gate checks"
    echo "  status                                 Show current workflow state"
    echo "  reset                                  Reset for new task"
    exit 1
    ;;
esac
