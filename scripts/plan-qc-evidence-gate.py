#!/usr/bin/env python3
"""A ticked QC row must carry PASTED EVIDENCE, not a claim (plan T48).

WHY THIS EXISTS
---------------
T48's row states its own point: *"Every task fully implemented, nothing silently dropped, tests
green, **and every QC task's evidence actually pasted** — the evidence gate is the point, not
the checkbox."* There was no such gate; T48 was the promise to look.

A QC row is where the plan certifies something about the SYSTEM rather than about a file — a
live smoke, a recall measurement, a contract review. Those are exactly the claims that are
cheapest to assert and most expensive to be wrong about, and a checkbox costs one character.

⚠️ **THE FIRST VERSION OF THIS CHECK PRODUCED THREE FALSE POSITIVES**, and that shaped the rule.
It looked for fenced code blocks only, and reported `QC-0`, `QC-1` and `QC-2` as evidence-free.
Reading `QC-1` showed the opposite — `passed=9 failed=0` in its own title and a `| leg | result |`
results table underneath. **This plan pastes evidence in three forms and a detector fitted to
one of them is green by construction against the other two**, which is the failure mode the
plan itself catalogues. So all three count:

    fenced block   ```…```            command output
    results table  | leg | result |   a smoke's legs, a comparison's arms
    measured figure `4239 passed`, `passed=9`, `p50`, `exit 0`, `3/3`, `1826 rows`

    python scripts/plan-qc-evidence-gate.py
    python scripts/plan-qc-evidence-gate.py --selftest
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "plan_location", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "plan_location.py"))
_pl = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_pl)
PLAN = _pl.plan_path()

ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*")

#: A number that could only come from a run. Not "any digit": a date or a section number is not
#: evidence, and counting them would make this gate pass on prose.
FIGURE_RE = re.compile(
    r"\b\d+\s+passed\b|passed=\d+|failed=\d+|\bp50\b|\bp95\b|\bexit \d\b"
    r"|\b\d+\s*/\s*\d+\b|\b\d+\s+(?:rows?|files?|tests?|nodes?|entities|buffers?|modules?)\b",
    re.IGNORECASE,
)


def rows(lines: list[str]) -> list[tuple[int, str, str]]:
    return [(n, m.group(2), m.group(1))
            for n, l in enumerate(lines) for m in [ROW_RE.match(l)] if m]


def evidence_in(block: list[str]) -> dict[str, int]:
    """The three forms this plan actually pastes. See the module docstring."""
    fenced = sum(1 for x in block if x.strip().startswith("```")) // 2
    table = sum(1 for x in block if x.strip().startswith("|") and "---" in x)
    figures = sum(1 for x in block if FIGURE_RE.search(x))
    return {"fenced": fenced, "table": table, "figures": figures}


def offenders(text: str) -> list[tuple[str, dict[str, int]]]:
    lines = text.split("\n")
    rs = rows(lines)
    out = []
    for i, (n, name, state) in enumerate(rs):
        if state != "x" or not name.upper().startswith("QC"):
            continue
        end = rs[i + 1][0] if i + 1 < len(rs) else len(lines)
        ev = evidence_in(lines[n:end])
        if not any(ev.values()):
            out.append((name, ev))
    return out


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    with open(PLAN, encoding="utf-8") as fh:
        text = fh.read()
    bad = offenders(text)
    if bad:
        print("[plan-qc-evidence-gate] FAIL — QC row(s) ticked with NO pasted evidence:")
        for name, _ev in bad:
            print(f"    {name}")
        print("  A QC row certifies something about the SYSTEM — a live smoke, a recall")
        print("  measurement, a contract review. Those are the cheapest claims to assert and")
        print("  the most expensive to be wrong about. Paste the output, the results table, or")
        print("  the measured figure; a checkbox costs one character.")
        return 1
    lines = text.split("\n")
    rs = rows(lines)
    closed = [n for n, name, st in rs if st == "x" and name.upper().startswith("QC")]
    print(f"[plan-qc-evidence-gate] OK — {len(closed)} closed QC row(s), every one carrying "
          "pasted evidence (fenced output, a results table, or a measured figure).")
    return 0


def selftest() -> int:
    fails = []

    def c(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("plan-qc-evidence-gate · selftest")
    nl = chr(10)
    bare = nl.join([
        "- [x] **QC-9** — certified, allegedly",
        "  It all worked and the smoke was green.",
        "- [x] **T1** — a normal row",
    ])
    c("a QC row with only prose is caught", [n for n, _ in offenders(bare)] == ["QC-9"],
      str(offenders(bare)))

    # 🔴 THE THREE FALSE POSITIVES THAT SHAPED THIS GATE. A fenced-only detector reported
    # QC-0/1/2 as evidence-free; QC-1 carries `passed=9 failed=0` and a results table. Each
    # form is asserted separately, because a rule validated on the form it was written for is
    # green by construction against the others.
    tabled = nl.join([
        "- [x] **QC-9** — smoke",
        "  | leg | result |",
        "  |---|---|",
        "  | write | ok |",
        "- [x] **T1** — next",
    ])
    c("a RESULTS TABLE counts as evidence", offenders(tabled) == [], str(offenders(tabled)))

    figured = nl.join([
        "- [x] **QC-9** — smoke — **`passed=9 failed=0`**",
        "  Drove it through the gateway.",
        "- [x] **T1** — next",
    ])
    c("a MEASURED FIGURE counts as evidence", offenders(figured) == [], str(offenders(figured)))

    fenced = nl.join([
        "- [x] **QC-9** — smoke",
        "  ```",
        "  4239 passed",
        "  ```",
        "- [x] **T1** — next",
    ])
    c("FENCED output counts as evidence", offenders(fenced) == [], str(offenders(fenced)))

    # A date or a section number must NOT read as a measurement, or the gate passes on prose.
    prosey = nl.join([
        "- [x] **QC-9** — reviewed on 2026-08-14 per §6.4, decision 3 of 4.",
        "  Everything was verified thoroughly.",
        "- [x] **T1** — next",
    ])
    c("a date / section number is NOT evidence", [n for n, _ in offenders(prosey)] == ["QC-9"],
      str(offenders(prosey)))

    # Scope: only QC rows, and only CLOSED ones.
    openqc = nl.join(["- [~] **QC-9** — open, no evidence yet", "- [x] **T1** — next"])
    c("an OPEN QC row is not required to have evidence yet", offenders(openqc) == [])
    normal = nl.join(["- [x] **T9** — a normal row with prose only", "- [x] **T1** — next"])
    c("a non-QC row is out of scope", offenders(normal) == [])

    with open(PLAN, encoding="utf-8") as fh:
        real = fh.read()
    c("the REAL plan passes today", offenders(real) == [], str(offenders(real)))

    print("\n  all checks passed" if not fails else f"\n  {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
