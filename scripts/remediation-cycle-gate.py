#!/usr/bin/env python3
"""Gate: an acceptance criterion reaches `met` only through a recorded five-stage cycle.

THE RULE lives in `docs/standards/remediation-cycle.md` (RC-1..6).

WHY. `plan-acceptance-criteria-gate.py` made plans state what DONE means. This makes the MOVEMENT
auditable: a criterion that flips to `✅ met` must be traceable to a cycle that investigated, posted
issues, fixed, PROVED the fix, and named the criterion it moved.

Each stage is here because skipping it has failed in this repo already. Seven premises in the
2026-09-12 plan were wrong and were corrected by looking rather than recalling — that is INVESTIGATE.
A fix nobody can find is a fix nobody reviews — ISSUES. "I fixed it" is a claim and a check watched
going red is evidence — PROOF, which is Non-Vacuity's whole subject. And a fix that moves no
criterion did not move the bar — AC IMPACT, which is the failure that created the acceptance-criteria
standard: a board filling with finished work while the ship question stayed exactly where it was.

The loop is EXPECTED to run many times. `🚧 partial` is why a cycle can record real movement without
overclaiming.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLANS = REPO / "docs" / "plans"

CYCLE_HEAD = re.compile(r"^###\s+Cycle\s+(\d+)\b(.*)$")
AC_ROW = re.compile(r"^\|\s*\*{0,2}(AC-\d+)\*{0,2}\s*\|(.*)$")
FIELD = re.compile(r"^\*\*(Investigated|Issues|Fix|Proof|AC impact):\*\*\s*(.*)$", re.IGNORECASE)

REQUIRED = ("investigated", "issues", "fix", "proof", "ac impact")
MET = "✅ met"


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def check(text: str, name: str = "<plan>") -> list[str]:
    """Problems in one plan. Pure, so `--self-test` drives fixtures instead of the real corpus."""
    problems: list[str] = []
    lines = text.splitlines()

    if not any(ln.strip() == "## Cycles" for ln in lines):
        return []  # a plan with no cycle log is out of this gate's scope.

    # ── carve the cycle blocks ────────────────────────────────────────────────
    blocks: list[tuple[int, str, list[str]]] = []
    cur: list[str] | None = None
    cur_n = cur_title = None
    for ln in lines:
        m = CYCLE_HEAD.match(ln)
        if m:
            if cur is not None:
                blocks.append((cur_n, cur_title, cur))
            cur_n, cur_title, cur = int(m.group(1)), m.group(2).strip(" —-"), []
            continue
        if cur is not None:
            if ln.startswith("## "):  # a new top-level section ends the log
                blocks.append((cur_n, cur_title, cur))
                cur = None
                continue
            cur.append(ln)
    if cur is not None:
        blocks.append((cur_n, cur_title, cur))

    seen_numbers: list[int] = []
    moved_acs: set[str] = set()

    for num, title, body in blocks:
        label = f"Cycle {num}"
        seen_numbers.append(num)
        joined = "\n".join(body)

        fields: dict[str, str] = {}
        for ln in body:
            fm = FIELD.match(ln.strip())
            if fm:
                fields[fm.group(1).lower()] = fm.group(2).strip()

        for req in REQUIRED:
            if req not in fields:
                problems.append(
                    f"{name}: {label} has no **{req.title()}:** field (RC-1). A missing stage is a "
                    f"stage that did not happen — say so explicitly rather than omitting it."
                )
            elif not fields[req] and req != "proof":
                # `proof` is exempt from the inline-value check ON PURPOSE: its content is the
                # fenced block BELOW the label, which is the whole point of RC-3. The first version
                # required an inline value here and rejected every correctly-formed cycle — caught
                # by this file's own self-test on its first run, which is what the fixtures are for.
                problems.append(f"{name}: {label}'s **{req.title()}:** is empty (RC-1).")

        # RC-2 — issues, or a stated reason there are none.
        issues = fields.get("issues", "")
        if issues and not re.search(r"#\d+", issues):
            if not issues.lower().lstrip().startswith("none"):
                problems.append(
                    f"{name}: {label} **Issues:** names no #<number> and does not begin with "
                    f"'none — <reason>' (RC-2). A defect with no public record is one that gets "
                    f"rediscovered."
                )

        # RC-3 — proof is a pasted block, not a description of one.
        if "proof" in fields and "```" not in joined:
            problems.append(
                f"{name}: {label} **Proof:** has no fenced block (RC-3). Prose describing a result "
                f"is not the result — paste what the check printed."
            )

        # RC-4 — the cycle must name what it moved.
        impact = fields.get("ac impact", "")
        found = re.findall(r"AC-\d+", impact)
        if impact and not found:
            problems.append(
                f"{name}: {label} **AC impact:** names no AC-<n> (RC-4). A cycle that moved no "
                f"criterion should say which one it was aiming at and why it did not move."
            )
        moved_acs.update(found)

    # RC-6 — unique, ascending.
    if len(set(seen_numbers)) != len(seen_numbers):
        problems.append(f"{name}: duplicate cycle number(s) (RC-6); a re-used number overwrites history.")
    elif seen_numbers != sorted(seen_numbers):
        problems.append(f"{name}: cycle numbers are not ascending: {seen_numbers} (RC-6).")

    # RC-5 — every met criterion is traceable to a cycle, unless it is grandfathered.
    for ln in lines:
        m = AC_ROW.match(ln)
        if not m:
            continue
        cells = _cells(ln)
        if len(cells) < 5:
            continue
        ac_id, status = m.group(1), cells[4]
        if MET.split()[0] in status and ac_id not in moved_acs:
            if "pre-cycle" in status.lower():
                continue
            problems.append(
                f"{name}: {ac_id} is marked met but no cycle's **AC impact** names it (RC-5). "
                f"Either record the cycle that moved it, or mark the evidence 'pre-cycle' if it "
                f"predates this log."
            )

    return problems


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--self-test" in args:
        return self_test()

    if not PLANS.is_dir():
        print("remediation-cycle-gate: no docs/plans directory; nothing to check")
        return 0

    plans = sorted(p for p in PLANS.glob("*.md") if p.is_file())
    with_log = 0
    problems: list[str] = []
    for p in plans:
        text = p.read_text(encoding="utf-8")
        if any(ln.strip() == "## Cycles" for ln in text.splitlines()):
            with_log += 1
        problems.extend(check(text, p.name))

    if problems:
        print("remediation-cycle-gate: FAIL")
        for pr in problems:
            print(f"  - {pr}")
        return 1

    print(
        f"remediation-cycle-gate: OK -- {with_log} plan(s) keep a cycle log; "
        f"{len(plans) - with_log} plan(s) have none and are out of scope"
    )
    return 0


_AC = ("## Acceptance criteria\n\n| AC | Must be true | Verified by | Rows | Status |\n"
       "|---|---|---|---|---|\n")
_FULL = (
    "**Investigated:** read every audit\n"
    "**Issues:** #251\n"
    "**Fix:** `abc1234` bumps it\n"
    "**Proof:**\n\n```\nEXIT=0\n```\n\n"
    "**AC impact:** AC-1 ❌ → ✅ met\n"
)


def self_test() -> int:
    """Each case is a way a bar moves without anyone being able to check that it should have."""
    def plan(status: str, cycles: str) -> str:
        return (_AC + f"| **AC-1** | a | `s.py` | — | {status} |\n\n## Cycles\n\n" + cycles)

    cases = [
        ("a complete cycle passes", plan("✅ met — gate OK", "### Cycle 1 — x\n\n" + _FULL), False),
        ("a plan with NO cycle log is out of scope", _AC + "| **AC-1** | a | `s.py` | — | ✅ met — x |\n", False),
        ("a missing stage FAILS",
         plan("❌ not met", "### Cycle 1 — x\n\n**Investigated:** y\n**Issues:** #1\n**Fix:** z\n**AC impact:** AC-1\n"), True),
        ("an empty stage FAILS",
         plan("❌ not met", "### Cycle 1 — x\n\n**Investigated:**\n**Issues:** #1\n**Fix:** z\n**Proof:**\n\n```\nok\n```\n\n**AC impact:** AC-1\n"), True),
        ("Issues with no number and no 'none' reason FAILS",
         plan("❌ not met", "### Cycle 1 — x\n\n**Investigated:** y\n**Issues:** filed some\n**Fix:** z\n**Proof:**\n\n```\nok\n```\n\n**AC impact:** AC-1\n"), True),
        ("Issues saying 'none — reason' passes",
         plan("❌ not met", "### Cycle 1 — x\n\n**Investigated:** y\n**Issues:** none — internal CI config, no user impact\n**Fix:** z\n**Proof:**\n\n```\nok\n```\n\n**AC impact:** AC-1\n"), False),
        ("Proof without a fenced block FAILS",
         plan("❌ not met", "### Cycle 1 — x\n\n**Investigated:** y\n**Issues:** #1\n**Fix:** z\n**Proof:** it passed now\n\n**AC impact:** AC-1\n"), True),
        ("AC impact naming no AC FAILS",
         plan("❌ not met", "### Cycle 1 — x\n\n**Investigated:** y\n**Issues:** #1\n**Fix:** z\n**Proof:**\n\n```\nok\n```\n\n**AC impact:** things improved\n"), True),
        ("a met criterion no cycle names FAILS (RC-5)",
         plan("✅ met — gate OK", "### Cycle 1 — x\n\n**Investigated:** y\n**Issues:** #1\n**Fix:** z\n**Proof:**\n\n```\nok\n```\n\n**AC impact:** AC-9 moved\n"), True),
        ("a met criterion marked pre-cycle passes",
         plan("✅ met — pre-cycle, bitten 2026-09-13", "### Cycle 1 — x\n\n**Investigated:** y\n**Issues:** #1\n**Fix:** z\n**Proof:**\n\n```\nok\n```\n\n**AC impact:** AC-9\n"), False),
        ("duplicate cycle numbers FAIL",
         plan("❌ not met", "### Cycle 1 — a\n\n" + _FULL + "\n### Cycle 1 — b\n\n" + _FULL), True),
        ("descending cycle numbers FAIL",
         plan("❌ not met", "### Cycle 2 — a\n\n" + _FULL + "\n### Cycle 1 — b\n\n" + _FULL), True),
        ("a cycle that moved nothing is still a valid cycle",
         plan("❌ not met", "### Cycle 1 — x\n\n**Investigated:** y\n**Issues:** #1\n**Fix:** none yet\n**Proof:**\n\n```\nstill red\n```\n\n**AC impact:** AC-1 ❌ → ❌, the journey still fails\n"), False),
    ]

    failures = 0
    for desc, text, expect in cases:
        got = bool(check(text))
        good = got == expect
        failures += not good
        print(f"  {'ok  ' if good else 'FAIL'} {desc}")

    print(f"remediation-cycle-gate --self-test: {'FAIL' if failures else 'OK'} "
          f"({len(cases) - failures}/{len(cases)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
