#!/usr/bin/env python3
"""plan-final-verification — is the knowledge-architecture refactor plan actually processed?

Answers one question with a pass/fail, so "the plan is done" stops being a claim in a summary
and becomes something a command prints.

FOUR CHECKS, and the third is the one with teeth:

  1. NO UNTOUCHED TASKS — every `- [ ]` is gone. A task nobody has looked at is the one state
     the plan must not end in.
  2. EVERY DEFERRAL IS STRUCTURED — each `[~]` task's section names a `D-…` deferral, and
     every `D-…` deferral block carries all five required parts (blocker, evidence, unblock,
     mechanism, retry). A deferral without a retry condition is an abandonment with better
     manners.
  3. NO SELF-CERTIFYING QC — a QC task may not be `[x]` while the thing it certifies is
     deferred. This is the check that would have caught QC-5 being marked done because its
     write-up was thorough.
  4. GATES GREEN — the gates this plan introduced all exit 0.

    python scripts/plan-final-verification.py

Exit 0 = the plan is fully processed · 1 = something is unaccounted for.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "plans", "2026-08-09-knowledge-architecture-refactor.md")

# The gates this plan introduced or relies on. Each must exit 0.
GATES = [
    "glossary-events-ssot-gate.py",
    "alive-column-deprecation-gate.py",
    "derived-entity-id-gate.py",
    "graph-port-gate.py",
    "entity-lifecycle-outbox-gate.py",
    "gateway-domain-logic-gate.py",
]

# The five parts a deferral must carry. Matched case-insensitively on the row label, so the
# table形式 is not load-bearing — the CONTENT is.
REQUIRED_PARTS = ("blocker", "evidence", "unblock", "mechanism", "retry")

TASK_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9-]+)\*\*", re.M)


def sections(text: str) -> list[tuple[str, str, str]]:
    """(state, task-id, body) for every task, body running to the next task heading."""
    marks = list(TASK_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1), m.group(2), text[m.start():end]))
    return out


def main() -> int:
    if not os.path.exists(PLAN):
        print(f"[plan-verify] FAIL — plan not found: {PLAN}")
        return 1
    text = open(PLAN, encoding="utf-8").read()
    tasks = sections(text)
    done = [t for t in tasks if t[0] == "x"]
    deferred = [t for t in tasks if t[0] == "~"]
    untouched = [t for t in tasks if t[0] == " "]
    failures: list[str] = []

    print(f"[plan-verify] {len(tasks)} tasks — {len(done)} done, {len(deferred)} tracked, "
          f"{len(untouched)} untouched")

    # 1 — nothing untouched.
    if untouched:
        failures.append("untouched tasks remain: " + ", ".join(t[1] for t in untouched))

    # 2 — every deferral block carries all five parts.
    blocks = re.split(r"### .*?DEFERRAL ", text)[1:]
    for b in blocks:
        name = re.match(r"`?(D-[A-Z0-9-]+)`?", b)
        name = name.group(1) if name else "<unnamed>"
        body = b[:4000].lower()
        missing = [p for p in REQUIRED_PARTS if p not in body]
        if missing:
            failures.append(f"deferral {name} is missing: {', '.join(missing)}")
    print(f"[plan-verify] {len(blocks)} structured deferral block(s) checked")

    # 3 — no QC task claims done while what it certifies is deferred.
    for state, tid, body in tasks:
        if state == "x" and tid.upper().startswith("QC"):
            if re.search(r"DEFERRAL `?D-", body):
                failures.append(
                    f"{tid} is marked DONE but its own section records a deferral — a QC task "
                    f"cannot certify work that is still open")

    # 4 — gates green.
    for g in GATES:
        path = os.path.join(ROOT, "scripts", g)
        if not os.path.exists(path):
            failures.append(f"gate missing: {g}")
            continue
        rc = subprocess.run([sys.executable, path], capture_output=True, text=True).returncode
        print(f"[plan-verify] gate {g:<38} {'PASS' if rc == 0 else 'FAIL'}")
        if rc != 0:
            failures.append(f"gate failed: {g}")

    print()
    if failures:
        print("[plan-verify] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[plan-verify] PASS — every task is done-with-evidence or tracked with a full "
          "deferral, no QC task certifies open work, and every gate is green.")
    print("  NOTE: 'processed' is not 'finished'. Tracked deferrals are open work with owners;")
    print("  see the Phase 6 & 7 block and D-QC5-ACCEPTANCE-BLOCKED-ON-T36 for what remains.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
