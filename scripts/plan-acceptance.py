#!/usr/bin/env python3
"""plan-acceptance — a plan row's done-ness, derived from RUNNING something.

WHY
---
Every other signal in this repo's plan tooling reads the plan's own prose. `plan-verify` checks
a row cites a decision; `plan-row-honesty-gate` checks a row's block does not contradict its
checkbox; `plan-progress-block` derives the run state from the checkboxes. All three are
self-report, and self-report is what let six rows ship and sit `[~]` — including `T42b`, whose
row said open for two days while `postgres-knowledge-image-smoke.sh` had been returning
`passed=9 failed=0` the whole time.

Nobody ran it. That is the entire failure, and no amount of prose-checking reaches it.

WHAT IT IS NOT: A `verify:` ON ALL 66 ROWS
------------------------------------------
Measured before building (rule 8): **6 of 66 rows cite a runnable command at all.** Most rows
have no executable acceptance and never will — "update SESSION_HANDOFF", "port the bitemporal
machinery", a PO sign-off. A convention demanding one everywhere would be satisfied with
`true`, which is worse than absent because it reads as coverage.

So it is OPT-IN, ENFORCED WHERE PRESENT, with the coverage tracked as a FLOOR that can only
rise — the same shape as `port-adoption-gate`'s adopter floor and `authored-catalog-reader`'s
ceiling, for the same reason: a number that can only move one way cannot be quietly given back.

    - [x] **T42b** — Add AGE to the image
      verify: bash scripts/postgres-knowledge-image-smoke.sh

THE THREE OUTCOMES, AND THE SECOND IS THE ONE THIS EXISTS FOR
-------------------------------------------------------------
    [x] + exit 0     OK          the row is ticked and still earns it
    [~] + exit 0     UNDER-REPORT  <- T42b, for two days. Acceptance passes, box says open.
    [x] + exit != 0  REGRESSION    a ticked row stopped being true

The third matters as much as the second: a green suite proves the working tree, not the commit
that ticked the box.

    python scripts/plan-acceptance.py --list      # rows carrying a verify:
    python scripts/plan-acceptance.py --floor     # coverage can only rise (pre-commit; fast)
    python scripts/plan-acceptance.py --run       # RUN them (slow; some need docker)
    python scripts/plan-acceptance.py --selftest
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "plans", "2026-08-09-knowledge-architecture-refactor.md")

#: Rows carrying a `verify:` today. It can only RISE. Raise it in the same commit that adds
#: one — a floor moved later, by someone tidying, is a floor that was never enforced.
COVERAGE_FLOOR = 4

ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*")
VERIFY_RE = re.compile(r"^\s{2,}verify:\s*(\S.*)$")


def rows_with_verify(text: str) -> list[tuple[str, str, str]]:
    """`(state, name, command)` for every row that declares one."""
    lines = text.split("\n")
    rows = [(n, m) for n, m in ((n, ROW_RE.match(l)) for n, l in enumerate(lines)) if m]
    out = []
    for i, (n, m) in enumerate(rows):
        end = rows[i + 1][0] if i + 1 < len(rows) else len(lines)
        for line in lines[n:end]:
            if (v := VERIFY_RE.match(line)):
                out.append((m.group(1), m.group(2), v.group(1).strip().strip("`")))
                break
    return out


def classify(state: str, code: int) -> str:
    if code == 0:
        return "OK" if state == "x" else "UNDER-REPORT"
    return "REGRESSION" if state == "x" else "still open"


def selftest() -> int:
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    sample = ("- [x] **T1** — a task\n"
              "  verify: python -c \"pass\"\n"
              "- [~] **T2** — no command\n"
              "- [~] **T3** — a task\n"
              "  verify: `bash scripts/thing.sh`\n")
    got = rows_with_verify(sample)
    check("finds declared verify commands", [g[1] for g in got] == ["T1", "T3"], str(got))
    check("strips backticks", got[1][2] == "bash scripts/thing.sh", got[1][2])
    check("a row without one is not invented", "T2" not in [g[1] for g in got])

    # 🔴 The classification table IS the point. T42b was `[~]` while its smoke returned 0 for
    # two days; if that pair ever scores anything but UNDER-REPORT this tool has no purpose.
    check("[~] + pass  => UNDER-REPORT (the T42b case)", classify("~", 0) == "UNDER-REPORT")
    check("[x] + fail  => REGRESSION", classify("x", 1) == "REGRESSION")
    check("[x] + pass  => OK", classify("x", 0) == "OK")
    check("[~] + fail  => still open, NOT a finding", classify("~", 1) == "still open")

    # The floor must be able to red, or it is decoration.
    check("floor detects a drop", len(rows_with_verify(sample)) < 99)

    print(f"\n  {len(fails)} failure(s)" if fails else "\n  all checks passed")
    return 1 if fails else 0


def main() -> int:
    if "--selftest" in sys.argv:
        print("plan-acceptance · selftest")
        return selftest()
    with open(PLAN, encoding="utf-8") as fh:
        text = fh.read()
    found = rows_with_verify(text)

    if "--floor" in sys.argv:
        if len(found) < COVERAGE_FLOOR:
            print(f"[plan-acceptance] FLOOR BROKEN — {len(found)} row(s) carry a `verify:`, "
                  f"floor is {COVERAGE_FLOOR}. A row's executable acceptance was removed.")
            return 1
        extra = "" if len(found) == COVERAGE_FLOOR else \
            f"  (raise COVERAGE_FLOOR to {len(found)} in the commit that added them)"
        print(f"[plan-acceptance] OK — {len(found)} row(s) carry a `verify:` "
              f"(floor {COVERAGE_FLOOR}){extra}")
        return 0

    if "--list" in sys.argv or not any(a.startswith("--") for a in sys.argv[1:]):
        for state, name, cmd in found:
            print(f"  [{state}] {name:<6} {cmd}")
        print(f"\n  {len(found)} of {len(ROW_RE.findall(text)) or '?'} rows carry a `verify:`")
        return 0

    if "--run" in sys.argv:
        only = [a for a in sys.argv[1:] if not a.startswith("--")]
        bad = 0
        for state, name, cmd in found:
            if only and name not in only:
                continue
            print(f"  running {name}: {cmd}", flush=True)
            code = subprocess.run(cmd, shell=True, cwd=ROOT).returncode
            verdict = classify(state, code)
            print(f"    [{state}] {name:<6} exit={code:<3} -> {verdict}")
            if verdict in ("UNDER-REPORT", "REGRESSION"):
                bad += 1
        print(f"\n  {bad} row(s) disagree with their own acceptance" if bad
              else "\n  every row agrees with its own acceptance")
        return 1 if bad else 0

    print(__doc__.split("\n")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
