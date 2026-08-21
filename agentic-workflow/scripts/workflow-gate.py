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
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(".workflow-state.json")
# NOTE (2026-08-03): AMAW was retired here. Its L3 layer used to bridge events to a ContextHub MCP
# server via scripts/mcp-query.py. That integration was never actually exercised —
# the server was listed in config but no agent called it — so it has been removed
# along with mcp-query.py, amaw-guardrail-gate.py, amaw-context-inject.py and
# seed-amaw-guardrails.py. AUDIT_LOG.jsonl stays as committed history — the writer
# that was carrying its weight. Do not re-add an MCP bridge here without a
# consumer that demonstrably reads it.

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


def _check_live_smoke_evidence(evidence: str) -> None:
    """Emit a soft WARN (stderr only, never blocks) when VERIFY evidence on a
    cross-service change lacks a live-smoke acknowledgement token.

    Motivation — recurring pattern caught 4 times in sessions 58-59:
    a feature ships across two service boundaries, the unit suite is green
    against mocks, but the actual cross-service contract is broken (timeout
    drift, header omission, UUID-vs-name drift, env mismatch). The bug surfaces
    only when the full stack runs. Mock-only coverage hides it for months.

    Soft signal: this prompts the agent / human to either:
      - paste a one-liner of live-smoke evidence, or
      - acknowledge the deferral (D-<NAME>-LIVE-SMOKE), or
      - acknowledge live infra unavailable (legitimate at dev time).

    "Cross-service" = git diff (HEAD baseline = staged + unstaged + working tree)
    touches ≥ 2 distinct ``services/<name>/`` prefixes. frontend/, contracts/,
    infra/, docs/ are NOT counted (service boundary risk lives in BE-to-BE
    contracts). Git failure → silent skip (workflow-gate must never break on
    infra failure).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return

    services = set()
    for path in files:
        m = re.match(r"^services/([^/]+)/", path)
        if m:
            services.add(m.group(1))

    if len(services) < 2:
        return

    # Acknowledgement tokens — any one in evidence satisfies the gate.
    ev_lower = evidence.lower()
    tokens = ("live smoke", "live-smoke", "live infra unavailable")
    if any(t in ev_lower for t in tokens):
        return

    services_list = ", ".join(sorted(services))
    print(
        f"WARN: VERIFY evidence does not acknowledge live-smoke for a cross-service\n"
        f"      change ({len(services)} services touched: {services_list}).\n"
        f"      Memory pattern feedback_mock_only_coverage_hides_crossservice_bugs:\n"
        f"      a feature green-on-mocks across a service boundary has ~40% chance\n"
        f"      of broken-at-birth on the first live smoke (4 hits sessions 58-59).\n"
        f"      Acknowledge by including ONE of these tokens in your evidence:\n"
        f"        - 'live smoke: <one-liner>' — confirm a real cross-service call ran\n"
        f"        - 'LIVE-SMOKE deferred to D-<NAME>-LIVE-SMOKE' — track the deferral\n"
        f"        - 'live infra unavailable: <reason>' — legitimate dev-time skip\n"
        f"      This is a soft warning only; the verify phase IS marked complete.",
        file=sys.stderr,
    )


def load_state() -> dict:
    if not STATE_FILE.exists():
        save_state(dict(INITIAL_STATE))
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        # DEFERRED-008: a corrupt / empty .workflow-state.json (manual edit, disk
        # corruption, an interrupted non-atomic write before #003) must NOT make
        # every gate command — including the pre-commit hook — die with a traceback
        # that blocks the commit. Reset to a clean initial state and warn loudly so
        # the operator knows the prior phase progress was lost (re-classify if needed).
        print(
            f"WARN: {STATE_FILE} is unreadable/corrupt ({exc}); resetting to initial state.",
            file=sys.stderr,
        )
        fresh = dict(INITIAL_STATE)
        save_state(fresh)
        return fresh


def save_state(state: dict) -> None:
    # Atomic write (DEFERRED #003): serialize to a temp file, then
    # Path.replace() for an atomic rename. Protects against PROCESS-crash
    # (Ctrl+C, exception, kill): STATE_FILE always holds either the complete
    # old state or the complete new state — a half-written file can only ever
    # be the .tmp, never STATE_FILE itself.
    #
    # The tmp is derived from STATE_FILE via with_name(), so the two always
    # share a parent directory — hence the same filesystem, the precondition
    # os.replace needs (cross-device rename raises EXDEV).
    #
    # The .{pid}. infix makes the tmp unique per process: two concurrent
    # workflow-gate.py invocations get distinct tmp files and cannot interleave
    # each other's bytes (Adversary r1 finding 1).
    #
    # NOT covered: power-loss durability — write_text does not fsync, so an
    # OS-buffered tmp whose rename is durable but contents are not could
    # survive a power cut as a partial STATE_FILE. Out of scope for a local
    # dev-tool state file; process-crash safety is the design target.
    tmp = STATE_FILE.with_name(f"{STATE_FILE.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)
    finally:
        # Clean our own tmp if replace() never ran (e.g. write failed, or
        # replace raised PermissionError on a Windows-locked dest).
        if tmp.exists():
            tmp.unlink(missing_ok=True)


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


SIZES = ["XS", "S", "M", "L", "XL"]


def _expected_size(files: int, logic: int, side_effects: int) -> tuple[str, int]:
    """Return (expected_size, risk_floor_index).

    Sizing is by COMPLEXITY + RISK, not file count (2026-06-12 redesign — file count
    over-sized wide-but-shallow changes, e.g. one param added across N files, forcing
    needless ceremony). `logic` (distinct SEMANTIC changes) is the primary axis; `files`
    is only a BREADTH signal that can bump one tier — and ONLY when the change is genuinely
    deep across that breadth (logic ≳ files), so a mechanical sweep (low logic-per-file)
    never escalates. `side_effects` (API/DB/config/migration/auth — real risk) set a hard
    floor that undersizing cannot cross."""
    if logic <= 1:
        base = 0   # XS
    elif logic <= 3:
        base = 1   # S
    elif logic <= 6:
        base = 2   # M
    elif logic <= 12:
        base = 3   # L
    else:
        base = 4   # XL
    # Breadth bump: a deep change spread across many files (NOT a mechanical sweep —
    # logic-per-file is substantial) is genuinely larger → +1 tier.
    if files >= 6 and logic >= files:
        base = min(4, base + 1)
    # Risk floor (load-bearing — undersizing below this BLOCKS): real side effects can't be XS.
    floor = 0
    if side_effects >= 1:
        floor = max(floor, 1)   # ≥ S
    if side_effects >= 2:
        floor = max(floor, 2)   # ≥ M
    base = max(base, floor)
    return SIZES[base], floor


def cmd_size(args: list[str]) -> None:
    if len(args) < 4:
        fail("Usage: workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <side_effects> [context_pct]")

    size = args[0].upper()
    if size not in SIZES:
        fail(f"Invalid size '{size}'. Must be XS, S, M, L, or XL.")

    files, logic, side_effects = int(args[1]), int(args[2]), int(args[3])
    context_pct = int(args[4]) if len(args) > 4 else None

    expected, floor = _expected_size(files, logic, side_effects)
    chosen_idx = SIZES.index(size)

    # Undersizing is now ADVISORY (your complexity judgment on breadth wins) — EXCEPT the
    # risk floor: real side effects keep a hard minimum. So a 20-file/1-logic sweep can be S,
    # but a schema migration can never be XS.
    if chosen_idx < floor:
        fail(
            f"Cannot undersize below the RISK floor: {side_effects} side effect(s) require "
            f"at least {SIZES[floor]} — you said {size}. (Breadth can be discounted; risk cannot.)"
        )

    state = load_state()
    state["size"] = size
    state["size_counts"] = {"files": files, "logic": logic, "side_effects": side_effects}
    if context_pct is not None:
        state["context_pct"] = context_pct
    save_state(state)

    skips = SKIPPABLE.get(size, set())
    skip_msg = f"  Allowed skips: {', '.join(sorted(skips))}" if skips else "  No phases may be skipped"
    print(f"OK: Task classified as {size} (files={files}, logic={logic}, side_effects={side_effects})")
    if chosen_idx < SIZES.index(expected):
        print(f"  NOTE: complexity suggests ~{expected}; you sized down to {size} (breadth-discounted — OK).")
    print(skip_msg)
    # Context-budget guidance (2026-06-12) — let budget, not file count, drive checkpoint cadence.
    if context_pct is not None:
        if context_pct < 60:
            print(f"  BUDGET: context at {context_pct}% — ample. Prefer ONE continuous run over "
                  f"many small tasks; checkpoint/commit at RISK boundaries (contract, migration, "
                  f"cross-service seam), not at file-count thresholds.")
        elif context_pct >= 80:
            print(f"  BUDGET: context at {context_pct}% — filling. Checkpoint/commit + /compact at "
                  f"the next risk boundary.")


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
    completed_at = datetime.now().isoformat()
    completed.append({
        "phase": phase,
        "completed_at": completed_at,
        "evidence": evidence,
    })
    state["phases_completed"] = completed
    if phase == "verify":
        state["verify_evidence"] = evidence
    save_state(state)

    print(f"OK: Phase '{phase}' marked complete")

    # Soft cross-service live-smoke check (debt-prevention; never blocks).
    if phase == "verify":
        _check_live_smoke_evidence(evidence)


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
    # Sweep stale save_state tmp files (e.g. `.workflow-state.json.1234.tmp`)
    # left by a process killed between write and replace (Adversary r1 finding 3).
    swept = 0
    parent = STATE_FILE.parent if str(STATE_FILE.parent) else Path(".")
    for stale in parent.glob(f"{STATE_FILE.name}.*.tmp"):
        stale.unlink(missing_ok=True)
        swept += 1
    msg = "OK: Workflow state reset. Ready for new task."
    if swept:
        msg += f" (swept {swept} stale tmp file{'s' if swept != 1 else ''})"
    print(msg)


def cmd_check_stack(args: list[str]) -> None:
    """ADVISORY stale-image guard (F-LIVE-1). Runs scripts/check_stack_freshness.py
    and surfaces drift / missing H0 routes — but NEVER blocks (always exits 0),
    mirroring the cross-service live-smoke soft-warning. Pass-through args (e.g.
    --probe-only, --drift-only, --services) are forwarded."""
    script = Path(__file__).resolve().parent / "check_stack_freshness.py"
    if not script.exists():
        print("WARN: check_stack_freshness.py not found — skipping stack-freshness check")
        return
    result = subprocess.run([sys.executable, str(script), *args])
    if result.returncode == 1:
        print("⚠️  WARN (advisory): a running image is STALE or an H0 route is "
              "missing — rebuild with scripts/build-stack.sh before a live run. "
              "(not blocking)")
    elif result.returncode == 3:
        print("note: docker/git unavailable — stack-freshness check skipped")
    # Advisory: never propagate a non-zero exit.


def cmd_slices(args: list[str]) -> None:
    """Validate a /warp slice manifest's independence invariants before fan-out.

    Thin wrapper over scripts/warp/slice-manifest-validate.py — the pairwise
    disjoint-write-set guarantee that makes parallel slice execution safe (see
    docs/specs/2026-06-12-warp-parallel-mode.md §6). Unlike check-stack this is a
    HARD gate: it propagates the validator's exit code (0 = clean / WARN-only,
    1 = BLOCK) so /warp can gate the DESIGN→REVIEW (PT-verdict) boundary — a
    BLOCK means the slicing is unsafe to fan out, fall back to serial /loom."""
    if not args:
        fail("Usage: workflow-gate.py slices <manifest.yaml|.json>")
    script = Path(__file__).resolve().parent / "warp" / "slice-manifest-validate.py"
    if not script.exists():
        fail(f"slice-manifest validator not found: {script}")
    result = subprocess.run([sys.executable, str(script), *args])
    sys.exit(result.returncode)


# ── Main ─────────────────────────────────────────────────────────────


COMMANDS = {
    "size": cmd_size,
    "phase": cmd_phase,
    "complete": cmd_complete,
    "check": cmd_check,
    "check-stack": cmd_check_stack,
    "slices": cmd_slices,
    "skip": cmd_skip,
    "pre-commit": cmd_pre_commit,
    "status": cmd_status,
    "reset": cmd_reset,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: workflow-gate.py {size|phase|complete|check|slices|skip|pre-commit|status|reset} [args]")
        print()
        print("Commands:")
        print("  size <XS|S|M|L|XL> <files> <logic> <effects>  Classify task size")
        print("  phase <name>                                   Enter a phase")
        print("  complete <name> <evidence>                     Mark phase done")
        print("  check <name>                                   Check if phase done")
        print("  skip <name> <reason>                           Skip with reason")
        print("  pre-commit                                     Gate check for commits")
        print("  check-stack [--probe-only|--drift-only]        ADVISORY: warn if a running image is stale (F-LIVE-1)")
        print("  slices <manifest.yaml|.json>                   /warp: assert slice write-sets are disjoint (gate before fan-out)")
        print("  status                                         Show current state")
        print("  reset                                          Reset for new task")
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
