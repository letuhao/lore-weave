#!/usr/bin/env python3
# DEPRECATED (v1.5+): superseded by the Agent-tool Coordinator (.claude/commands/raid.md).
# Kept for v1.4 backwards-compat only; do NOT use for new runs.
"""
auto-dispatcher — Semi-AUTO ready-signal emitter (R3 redesign per Adversary R2 BLOCK 2)
Per RAID_WORKFLOW.md v1.4 §13.7 + CYCLE_0_PLAN.md §3 B6.

NOT a session spawner — Claude tool harness cannot fork a fresh Claude
session. This script emits a ready signal + acquires lock transition,
then prints user instruction block. User opens fresh Claude Code session
and runs /raid <N> manually.

Atomic transition: lock=00X (or UNLOCKED if --from-clean) → READY_FOR_<N>
AND signal file written in single fs ordering (no UNLOCKED window).

Usage:
  auto-dispatcher.py --next-cycle 1                # normal post-smoke
  auto-dispatcher.py --next-cycle 1 --skip-countdown  # smoke harness (no 60s wait)
  auto-dispatcher.py --next-cycle 1 --from-clean      # rare: allow UNLOCKED→READY_FOR_<N>
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAID_DIR = REPO_ROOT / "docs" / "raid"
LOCK_PATH = RAID_DIR / ".session-cycle-lock"
CYCLE_LOG = RAID_DIR / "CYCLE_LOG.md"
AUDIT_LOG = REPO_ROOT / "docs" / "audit" / "AUDIT_LOG.jsonl"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def audit(event: str, **fields) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": now_iso(), "event": event, **fields}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def read_lock() -> str:
    if not LOCK_PATH.exists():
        return "UNLOCKED"
    for line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return "UNLOCKED"


def signal_path(cycle: int) -> Path:
    return RAID_DIR / f"READY_FOR_CYCLE_{cycle}.signal"


def get_head_sha() -> str:
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def find_deps_satisfied(target: int) -> list[int]:
    """Read CYCLE_LOG.md; return list of cycle numbers marked DONE."""
    if not CYCLE_LOG.exists():
        return []
    done = []
    for line in CYCLE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("|") and " DONE " in line.upper():
            parts = [p.strip() for p in line.split("|")]
            for p in parts:
                if p.isdigit():
                    done.append(int(p))
                    break
    return done


def emit_signal(cycle: int) -> Path:
    sig = signal_path(cycle)
    yaml_text = f"""# Emitted by auto-dispatcher.py at {now_iso()}
schema_version: 1
next_cycle: {cycle}
ready_at: {now_iso()}
deps_satisfied: {find_deps_satisfied(cycle)}
smoke_evidence_sha: {get_head_sha()}
dispatcher_pid: {os.getpid()}
"""
    tmp = sig.with_suffix(".signal.tmp")
    tmp.write_text(yaml_text, encoding="utf-8")
    os.replace(tmp, sig)
    return sig


def write_lock_atomic(value: str) -> None:
    tmp = LOCK_PATH.with_suffix(".tmp")
    tmp.write_text(
        f"{value}\n# Last updated: {now_iso()} by auto-dispatcher.py\n",
        encoding="utf-8",
    )
    os.replace(tmp, LOCK_PATH)


def atomic_transition_to_ready(cycle: int, from_clean: bool) -> int:
    """Validate current lock + perform atomic transition to READY_FOR_<N>."""
    current = read_lock()
    target = f"READY_FOR_{cycle}"

    if current == "00X":
        pass  # normal post-smoke
    elif current == "UNLOCKED" and from_clean:
        pass  # explicit operator override
    elif current == "UNLOCKED" and not from_clean:
        print(
            f"[auto-dispatcher] error: lock=UNLOCKED expected 00X; "
            f"smoke incomplete? Use --from-clean to override (operator only).",
            file=sys.stderr,
        )
        audit("auto_dispatcher_refused", reason="lock_unlocked_no_smoke")
        return 2
    elif current.startswith("READY_FOR_"):
        existing_n = current.replace("READY_FOR_", "")
        if existing_n == str(cycle):
            print(f"[auto-dispatcher] idempotent: signal for cycle {cycle} already emitted")
            audit("auto_dispatcher_idempotent", cycle=cycle)
            # Refresh signal file just in case
            emit_signal(cycle)
            return 0
        print(
            f"[auto-dispatcher] error: stale READY_FOR_{existing_n} signal; "
            f"refusing to overwrite. Run scripts/raid/recover-from-crash.sh --inspect.",
            file=sys.stderr,
        )
        audit("auto_dispatcher_refused", reason="stale_signal", existing=existing_n)
        return 2
    else:
        # Cycle in progress (numeric lock)
        print(
            f"[auto-dispatcher] error: cycle {current} in progress; refusing",
            file=sys.stderr,
        )
        audit("auto_dispatcher_refused", reason="cycle_in_progress", current=current)
        return 2

    # Atomic transition order chosen per Adversary code-review R1 WARN 1:
    # Write LOCK FIRST, then signal. Crash window leaves:
    #   lock=READY_FOR_<N> + signal missing
    # which IS in the recovery table (row 4 → `recover-from-crash.sh --rewrite-signal <N>`).
    # The reverse order would leave `lock=00X + signal exists` which the recovery
    # table marks "impossible" (row 3) — implementer-introduced out-of-table state.
    write_lock_atomic(target)
    sig = emit_signal(cycle)
    audit(
        "auto_dispatcher_transition",
        cycle=cycle,
        from_state=current,
        to_state=target,
        signal=str(sig.name),
    )
    return 0


def countdown(seconds: int) -> None:
    """Print countdown; allow ctrl-C with short sleep increments."""
    print(f"[auto-dispatcher] {seconds}-second pause — Ctrl-C to halt")
    for s in range(seconds, 0, -10):
        remaining = min(10, s)
        print(f"  [{s}s remaining]")
        time.sleep(remaining)


def print_user_instructions(cycle: int) -> None:
    border = "═" * 59
    print()
    print(border)
    print(f"C0 SMOKE GREEN — READY FOR CYCLE {cycle}")
    print(border)
    print(f"  1. Close this Claude Code session (P1 fresh-session invariant)")
    print(f"  2. Open a NEW Claude Code session in the same repo")
    print(f"  3. Run:  /raid {cycle}")
    print(f"  4. Orchestrator detects READY_FOR_CYCLE_{cycle}.signal +")
    print(f"     acquires lock transition READY_FOR_{cycle} → {cycle:03d}")
    print(border)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--next-cycle", type=int, required=True)
    p.add_argument("--skip-countdown", action="store_true",
                   help="smoke harness mode — no 60s wait")
    p.add_argument("--from-clean", action="store_true",
                   help="allow UNLOCKED→READY_FOR_<N> (operator override)")
    args = p.parse_args(argv)

    if not args.skip_countdown:
        countdown(60)

    rc = atomic_transition_to_ready(args.next_cycle, args.from_clean)
    if rc != 0:
        return rc
    print_user_instructions(args.next_cycle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
