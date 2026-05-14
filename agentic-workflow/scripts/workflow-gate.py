#!/usr/bin/env python3
"""workflow-gate.py — Enforce workflow state transitions for AI coding agents.

Python rewrite of workflow-gate.sh. Cross-platform (no bash escaping issues
on Windows). State persisted in .workflow-state.json.

Usage:
  python scripts/workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <side_effects>
  python scripts/workflow-gate.py phase <phase_name>
  python scripts/workflow-gate.py complete <name> <evidence>
  python scripts/workflow-gate.py check <phase_name>
  python scripts/workflow-gate.py status
  python scripts/workflow-gate.py pre-commit
  python scripts/workflow-gate.py reset
  python scripts/workflow-gate.py skip <phase> <reason>
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(".workflow-state.json")

PHASES = [
    "clarify", "design", "review-design", "plan", "build",
    "verify", "review-code", "qc", "post-review", "session",
    "commit", "retro",
]

SKIPPABLE = {
    "XS": {"clarify", "plan"},
    "S": {"plan"},
}

INITIAL_STATE = {
    "task": "",
    "size": None,
    "size_counts": {"files": 0, "logic": 0, "side_effects": 0},
    "current_phase": None,
    "current_phase_index": -1,
    "phases_completed": [],
    "phases_skipped": [],
    "verify_evidence": None,
    "started_at": None,
    "last_transition": None,
}


def load_state() -> dict:
    if not STATE_FILE.exists():
        save_state(dict(INITIAL_STATE))
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def phase_index(name: str) -> int:
    try:
        return PHASES.index(name)
    except ValueError:
        return -1


def completed_phases(state: dict) -> set[str]:
    return {p["phase"] for p in state.get("phases_completed", [])}


def fail(msg: str) -> None:
    print(f"BLOCKED: {msg}", file=sys.stderr)
    sys.exit(1)


# ── Commands ─────────────────────────────────────────────────────────


def cmd_size(args: list[str]) -> None:
    if len(args) < 4:
        fail("Usage: workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <side_effects>")

    size = args[0].upper()
    if size not in ("XS", "S", "M", "L", "XL"):
        fail(f"Invalid size '{size}'. Must be XS, S, M, L, or XL.")

    files, logic, side_effects = int(args[1]), int(args[2]), int(args[3])

    # Determine expected size from counts
    if files <= 1 and logic <= 1 and side_effects == 0:
        expected = "XS"
    elif files <= 2 and logic <= 3 and side_effects == 0:
        expected = "S"
    elif files <= 5:
        expected = "M"
    elif files <= 9:
        expected = "L"
    else:
        expected = "XL"

    sizes = ["XS", "S", "M", "L", "XL"]
    if sizes.index(size) < sizes.index(expected):
        fail(
            f"Cannot undersize: you said {size} but counts suggest {expected} "
            f"({files} files, {logic} logic, {side_effects} side effects). "
            f"Use '{expected}' or larger."
        )

    state = load_state()
    state["size"] = size
    state["size_counts"] = {"files": files, "logic": logic, "side_effects": side_effects}
    save_state(state)

    skips = SKIPPABLE.get(size, set())
    skip_msg = f"  Allowed skips: {', '.join(sorted(skips))}" if skips else "  No phases may be skipped"
    print(f"OK: Task classified as {size} (files={files}, logic={logic}, side_effects={side_effects})")
    print(skip_msg)


def cmd_phase(args: list[str]) -> None:
    if not args:
        fail("Usage: workflow-gate.py phase <phase_name>")

    phase = args[0].lower()
    idx = phase_index(phase)
    if idx < 0:
        fail(f"Unknown phase '{phase}'. Valid: {', '.join(PHASES)}")

    state = load_state()
    task_size = state.get("size")
    if task_size is None:
        fail("Task size not classified yet! Run: workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <side_effects>")

    current_idx = state.get("current_phase_index", -1)
    if current_idx is None:
        current_idx = -1

    skippable = SKIPPABLE.get(task_size, set())
    done = completed_phases(state)

    # Check all intermediate phases are completed or skippable
    for i in range(current_idx + 1, idx):
        p = PHASES[i]
        if p in done:
            continue
        if p in skippable:
            continue
        from_label = f"'{PHASES[current_idx]}'" if current_idx >= 0 else "(start)"
        fail(
            f"Phase '{p}' not completed and not auto-skippable for size '{task_size}'. "
            f"Cannot jump from {from_label} to '{phase}'."
        )

    state["current_phase"] = phase
    state["current_phase_index"] = idx
    state["last_transition"] = datetime.now().isoformat()
    if not state.get("started_at"):
        state["started_at"] = datetime.now().isoformat()
    save_state(state)

    print(f"OK: Entered phase '{phase}' ({idx}/{len(PHASES)})")


def cmd_complete(args: list[str]) -> None:
    if len(args) < 2:
        fail("Usage: workflow-gate.py complete <phase> <evidence>")

    phase = args[0].lower()
    evidence = args[1]

    state = load_state()
    completed = [p for p in state.get("phases_completed", []) if p["phase"] != phase]
    completed.append({
        "phase": phase,
        "completed_at": datetime.now().isoformat(),
        "evidence": evidence,
    })
    state["phases_completed"] = completed
    if phase == "verify":
        state["verify_evidence"] = evidence
    save_state(state)

    print(f"OK: Phase '{phase}' marked complete")


def cmd_check(args: list[str]) -> None:
    if not args:
        fail("Usage: workflow-gate.py check <phase>")

    phase = args[0].lower()
    state = load_state()
    if phase in completed_phases(state):
        print(f"OK: Phase '{phase}' is completed")
    else:
        print(f"NOT COMPLETED: Phase '{phase}' has not been completed yet")
        sys.exit(1)


def cmd_skip(args: list[str]) -> None:
    if len(args) < 2:
        fail("Usage: workflow-gate.py skip <phase> <reason>")

    phase = args[0].lower()
    reason = args[1]

    state = load_state()
    skipped = state.get("phases_skipped", [])
    skipped.append({
        "phase": phase,
        "reason": reason,
        "skipped_at": datetime.now().isoformat(),
    })
    state["phases_skipped"] = skipped

    # Also count as completed so the gate doesn't block
    completed = [p for p in state.get("phases_completed", []) if p["phase"] != phase]
    completed.append({
        "phase": phase,
        "completed_at": datetime.now().isoformat(),
        "evidence": f"SKIPPED: {reason}",
    })
    state["phases_completed"] = completed
    save_state(state)

    print(f"OK: Phase '{phase}' skipped (reason: {reason})")


def cmd_pre_commit(_args: list[str]) -> None:
    if not STATE_FILE.exists():
        print("WARNING: No workflow state found. Proceeding without enforcement.")
        sys.exit(0)

    state = load_state()
    done = completed_phases(state)

    gates = [
        ("verify", "Phase 6 VERIFY not done — run tests and record evidence"),
        ("post-review", "Phase 9 POST-REVIEW not done — present changes to user"),
        ("session", "Phase 10 SESSION not done — update session notes"),
    ]

    for phase, msg in gates:
        if phase not in done:
            print(f"\n{'=' * 50}")
            print(f"  COMMIT BLOCKED: {msg}")
            print(f"{'=' * 50}")
            print(f"\n  Fix: python scripts/workflow-gate.py complete {phase} \"<evidence>\"")
            print(f"  Or:  python scripts/workflow-gate.py skip {phase} \"<reason>\"\n")
            sys.exit(1)

    print("OK: Pre-commit checks passed (verify + post-review + session completed)")
    sys.exit(0)


def cmd_status(_args: list[str]) -> None:
    state = load_state()
    done = completed_phases(state)
    skipped = {p["phase"] for p in state.get("phases_skipped", [])}
    current = state.get("current_phase")
    size = state.get("size", "NOT SET")
    counts = state.get("size_counts", {})

    print(f"Task: {state.get('task') or '(unnamed)'}")
    print(f"Size: {size} (files={counts.get('files', 0)}, logic={counts.get('logic', 0)}, side_effects={counts.get('side_effects', 0)})")
    print(f"Current phase: {current or 'none'}")
    print()

    for p in PHASES:
        if p in skipped:
            marker = "[S]"
        elif p in done:
            marker = "[x]"
        elif p == current:
            marker = "[>]"
        else:
            marker = "[ ]"
        print(f"  {marker} {p}")


def cmd_reset(_args: list[str]) -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print("OK: Workflow state reset. Ready for new task.")


# ── Main ─────────────────────────────────────────────────────────────


COMMANDS = {
    "size": cmd_size,
    "phase": cmd_phase,
    "complete": cmd_complete,
    "check": cmd_check,
    "skip": cmd_skip,
    "pre-commit": cmd_pre_commit,
    "status": cmd_status,
    "reset": cmd_reset,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: workflow-gate.py {size|phase|complete|check|skip|pre-commit|status|reset} [args]")
        print()
        print("Commands:")
        print("  size <XS|S|M|L|XL> <files> <logic> <effects>  Classify task size")
        print("  phase <name>                                   Enter a phase")
        print("  complete <name> <evidence>                     Mark phase done")
        print("  check <name>                                   Check if phase done")
        print("  skip <name> <reason>                           Skip with reason")
        print("  pre-commit                                     Gate check for commits")
        print("  status                                         Show current state")
        print("  reset                                          Reset for new task")
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
