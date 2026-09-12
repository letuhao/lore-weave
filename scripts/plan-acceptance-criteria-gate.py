#!/usr/bin/env python3
"""Gate: a plan declares what DONE means, and cannot claim a criterion without evidence.

THE RULE lives in `docs/standards/plan-acceptance-criteria.md`. This enforces its seven clauses.

WHY. On 2026-09-13 a release candidate reached `main` with a 23-row board fully ticked, every row
carrying pasted bite evidence, every gate green — and the question *"can this ship?"* had no answer.
The PO: *"this work is ad-hoc … what have we done and not, without ACs we cannot decide this repo
can ship v0.1.0 or not"*.

Nothing had failed. A board records intentions carried out; it does not record whether the result is
acceptable, because acceptable was never written down. A finished task list is not a definition of
done, and this gate exists so a plan cannot pretend otherwise.

SCOPE, and it is deliberately partial. Only plans dated 2026-09-13 or later, read from the filename.
The repo's existing corpus predates the rule. Retrofitting it would paint dozens of closed plans red
and teach everyone to scroll past this gate — a gate people ignore enforces nothing. The skip count
is PRINTED on every run: a check that quietly examines a fraction of its subject is a failure mode
this repo has already paid for.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLANS = REPO / "docs" / "plans"

#: The rule's start date. A plan older than this is out of scope, loudly.
IN_SCOPE_FROM = "2026-09-13"

#: Status tokens a criterion may carry (AC-4).
MET, NOT_MET, PARTIAL, WAIVED = "✅ met", "❌ not met", "🚧 partial", "🅿 waived"
STATUSES = (MET, NOT_MET, PARTIAL, WAIVED)

#: Words that look like a verification method and are not one (AC-3). Each names no artifact a
#: third party could re-run or read, which is the whole point of the column.
NON_METHODS = {
    "reviewed", "review", "tested", "test", "checked", "check", "verified", "verify",
    "done", "n/a", "na", "none", "-", "tbd", "manual", "manually", "inspection",
}

AC_ROW = re.compile(r"^\|\s*\*{0,2}(AC-\d+)\*{0,2}\s*\|(.*)$")
TASK_ROW = re.compile(r"^-\s*\[[ x~]\]\s*\*\*(T\d+)\*\*")
HEADING = re.compile(r"^##\s+Acceptance criteria\s*$", re.IGNORECASE)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def check(text: str, name: str = "<plan>") -> list[str]:
    """Problems in one plan's text. Pure, so `--self-test` drives it on fixtures."""
    problems: list[str] = []
    lines = text.splitlines()

    if not any(HEADING.match(ln) for ln in lines):
        return [
            f"{name}: no '## Acceptance criteria' section. A board of tasks says what someone "
            f"intends to DO; it does not say what must be TRUE afterwards, and only the second "
            f"can settle whether this is done. See docs/standards/plan-acceptance-criteria.md."
        ]

    rows: list[tuple[str, list[str]]] = []
    for ln in lines:
        m = AC_ROW.match(ln)
        if m:
            rows.append((m.group(1), _cells(ln)))

    if not rows:
        problems.append(f"{name}: the Acceptance criteria section has no AC-<n> rows (AC-1).")
        return problems

    seen: set[str] = set()
    covered_rows: set[str] = set()

    for ac_id, cells in rows:
        if ac_id in seen:
            problems.append(f"{name}: duplicate criterion id {ac_id} (AC-2).")
        seen.add(ac_id)

        # | AC | Must be true | Verified by | Rows | Status |
        if len(cells) < 5:
            problems.append(
                f"{name}: {ac_id} has {len(cells)} column(s), expected 5 "
                f"(AC | Must be true | Verified by | Rows | Status)."
            )
            continue

        criterion, method, row_refs, status = cells[1], cells[2], cells[3], cells[4]

        if not criterion:
            problems.append(f"{name}: {ac_id} states no criterion.")

        bare = method.strip().strip("*`_").lower().rstrip(".")
        if not method or bare in NON_METHODS:
            problems.append(
                f"{name}: {ac_id} names no verification method ({method!r}) (AC-3). "
                f"'reviewed' and 'tested' name no artifact anyone can re-run or read — name the "
                f"script, the suite, the live run, or the document."
            )

        matched = [s for s in STATUSES if s.split()[0] in status]
        if not matched:
            problems.append(
                f"{name}: {ac_id} status {status!r} is not one of {', '.join(STATUSES)} (AC-4)."
            )
            continue
        token = matched[0]

        if token == MET:
            # Evidence is whatever follows the tick. A tick alone is the claim this repo
            # refuses everywhere else.
            tail = status.split("met", 1)[-1].strip(" —-–:")
            if len(tail) < 3:
                problems.append(
                    f"{name}: {ac_id} is marked met with no evidence (AC-5). Say what was run "
                    f"and what it printed."
                )
        if token == WAIVED:
            tail = status.split("waived", 1)[-1].strip(" —-–:")
            if len(tail) < 3:
                problems.append(
                    f"{name}: {ac_id} is waived without naming who waived it and why (AC-6). "
                    f"An unattributed waiver is a decision with no owner."
                )

        covered_rows.update(re.findall(r"T\d+", row_refs))

    # AC-7 — work that serves no criterion.
    board_rows = {m.group(1) for ln in lines if (m := TASK_ROW.match(ln))}
    orphans = sorted(board_rows - covered_rows, key=lambda t: int(t[1:]))
    if orphans:
        problems.append(
            f"{name}: board row(s) {', '.join(orphans)} are referenced by NO criterion (AC-7). "
            f"Either name the criterion each serves, or say in the plan why they serve none — "
            f"work nobody agreed was needed is how a board grows without the bar moving."
        )

    return problems


def _in_scope(path: Path) -> bool:
    m = re.match(r"(\d{4}-\d{2}-\d{2})-", path.name)
    return bool(m) and m.group(1) >= IN_SCOPE_FROM


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--self-test" in args:
        return self_test()

    if not PLANS.is_dir():
        print(f"plan-acceptance-criteria-gate: no {PLANS} directory; nothing to check")
        return 0

    all_plans = sorted(p for p in PLANS.glob("*.md") if p.is_file())
    scoped = [p for p in all_plans if _in_scope(p)]
    skipped = len(all_plans) - len(scoped)

    problems: list[str] = []
    for p in scoped:
        problems.extend(check(p.read_text(encoding="utf-8"), p.name))

    if problems:
        print("plan-acceptance-criteria-gate: FAIL")
        for pr in problems:
            print(f"  - {pr}")
        print(f"\n  ({len(scoped)} plan(s) in scope; {skipped} older than {IN_SCOPE_FROM} skipped)")
        return 1

    print(
        f"plan-acceptance-criteria-gate: OK -- {len(scoped)} plan(s) declare acceptance criteria; "
        f"{skipped} plan(s) predate {IN_SCOPE_FROM} and are out of scope"
    )
    return 0


_HEAD = "## Acceptance criteria\n\n| AC | Must be true | Verified by | Rows | Status |\n|---|---|---|---|---|\n"


def self_test() -> int:
    """Each case is a way a plan can look finished and settle nothing."""
    ok = _HEAD + "| **AC-1** | No unreviewed string ships | `i18n-gate.py` | T1 | ✅ met — gate OK 9/9 |\n\n- [x] **T1** — do it\n"
    cases = [
        ("a well-formed plan passes", ok, False),
        ("no Acceptance criteria section at all FAILS",
         "# Plan\n\n- [ ] **T1** — do a thing\n", True),
        ("a section with no AC rows FAILS", _HEAD + "\n- [ ] **T1** — x\n", True),
        ("duplicate ids FAIL",
         _HEAD + "| **AC-1** | a | `s.py` | T1 | ❌ not met |\n| **AC-1** | b | `s.py` | T1 | ❌ not met |\n- [ ] **T1** — x\n", True),
        ("'reviewed' is not a verification method",
         _HEAD + "| **AC-1** | a | reviewed | T1 | ❌ not met |\n- [ ] **T1** — x\n", True),
        ("'tested' is not a verification method either",
         _HEAD + "| **AC-1** | a | tested | T1 | ❌ not met |\n- [ ] **T1** — x\n", True),
        ("an invented status FAILS",
         _HEAD + "| **AC-1** | a | `s.py` | T1 | mostly fine |\n- [ ] **T1** — x\n", True),
        ("met WITHOUT evidence FAILS",
         _HEAD + "| **AC-1** | a | `s.py` | T1 | ✅ met |\n- [x] **T1** — x\n", True),
        ("waived WITHOUT a waiver FAILS",
         _HEAD + "| **AC-1** | a | `s.py` | T1 | 🅿 waived |\n- [x] **T1** — x\n", True),
        ("waived WITH a named waiver passes",
         _HEAD + "| **AC-1** | a | `s.py` | T1 | 🅿 waived — PO 2026-09-13, out of scope for v0.1.0 |\n- [x] **T1** — x\n", False),
        ("a board row no criterion references FAILS (AC-7)",
         _HEAD + "| **AC-1** | a | `s.py` | T1 | ❌ not met |\n- [ ] **T1** — x\n- [ ] **T2** — orphan\n", True),
        ("'not met' needs no evidence — it claims nothing",
         _HEAD + "| **AC-1** | a | `s.py` | T1 | ❌ not met |\n- [ ] **T1** — x\n", False),
    ]

    failures = 0
    for desc, text, expect in cases:
        got = bool(check(text))
        good = got == expect
        failures += not good
        print(f"  {'ok  ' if good else 'FAIL'} {desc}")

    # The scope predicate must actually exclude and include.
    scope_cases = [("2026-09-12-old-plan.md", False), ("2026-09-13-new-plan.md", True),
                   ("2027-01-01-later.md", True), ("no-date-plan.md", False)]
    for fname, want in scope_cases:
        got = _in_scope(Path(fname))
        good = got == want
        failures += not good
        print(f"  {'ok  ' if good else 'FAIL'} scope: {fname} in-scope={got}")

    total = len(cases) + len(scope_cases)
    print(f"plan-acceptance-criteria-gate --self-test: {'FAIL' if failures else 'OK'} "
          f"({total - failures}/{total})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
