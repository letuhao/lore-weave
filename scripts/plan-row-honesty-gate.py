#!/usr/bin/env python3
"""plan-row-honesty-gate — find plan rows that are DONE but still marked `[~]`.

WHY THIS EXISTS
---------------
`plan-final-verification.py` enforces one direction: a `[~]` row must cite a decision, so a
task cannot stay open without one. Nothing enforced the OTHER direction, and on 2026-08-14
three rows were found finished-but-unticked in a single hand scan:

    T36    three halves DONE, deferral retracted 2026-08-11, bites pasted
    T38    migration target 10 -> 3 call sites, gate pinned at 3/3
    T42a   the conformance suite it exists to create, grown 40 -> 82 rules

This is the same disease as the four stale RESUME pointers this plan was restructured to
fix, running the other way: **a plan that UNDER-reports its own state sends the next session
looking for work that is already done.** One session read `[~]` as authoritative and planned
three batches that did not need doing.

WHAT IT DOES, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------
It is a WARNING gate, exit 0 always by default. It cannot know that a row is complete — only
that the row's own block reads like it. Ticking a box is a judgement about evidence, and a
gate that failed the build over one would push people to tick boxes to get green, which is
the exact failure it is trying to prevent. `--strict` exits 1 for a caller that wants it.

The heuristic is deliberately crude and its crudeness is stated: count completion markers
against owed markers inside each `[~]` block. A row with many of the first and none of the
second is worth a HUMAN look, nothing more. It found 3 of 26 rows and both false positives
it produced (QC-3, and T42a's narrative "not yet") were resolved by reading the block — which
is the intended workflow, not a defect.

    python scripts/plan-row-honesty-gate.py [--strict] [--selftest]
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "plans", "2026-08-09-knowledge-architecture-refactor.md")

#: Phrases that mean "this shipped". Evidence-shaped, not mood-shaped: a green suite count and
#: a struck deferral are facts, whereas "looks good" is not.
#:
#: ⚠️ 2026-08-14 — THIS VOCABULARY WAS TOO NARROW AND THE GATE WENT BLIND ON ITS OWN CLASS.
#: `T42b` shipped 2026-08-12 with a 9/9 image smoke and its row stayed `[~]` for two days,
#: until a RESUME pointer sent a session to build it again. This gate ran clean the whole time
#: — it scored the row `done=0`. The block says finished twice and the pattern caught neither:
#:
#:     "### ✅ DONE 2026-08-12 — one image now holds graph + vectors"   needed **bold**
#:     "[pgk-smoke] image=…  passed=9 failed=0"                        needed "9 passed"
#:
#: Both are ordinary spellings. A gate that recognises exactly one dialect of "done" reports
#: on how its rows are PUNCTUATED, not on whether they are finished — and it reports clean,
#: which is the worst direction for a gate whose whole purpose is catching under-reporting.
#: Widening it took the flagged count 0 → 5 of 23, and the first one checked was real.
DONE_RE = re.compile(
    r"\*\*DONE\.?\*\*"
    r"|✅ ?\*{0,2}(?:DONE|CLOSED|BUILT|SHIPPED)"   # bold OPTIONAL — this is the T42b miss
    r"|✅ \*\*"
    r"|CLOSED \d{4}-\d{2}-\d{2}"
    r"|\d+ passed|passed=\d+"                     # both orders — this is the other T42b miss
    r"|failed=0"
    r"|RETRACTED|DISCHARGED",
    re.I,
)
#: Phrases that mean "something is still owed". Any ONE of these outweighs a pile of the
#: above, because a block that names outstanding work is telling you the row is open.
OWED_RE = re.compile(
    r"⬜|still owed|owes|NOT built|not started|⛔|remains|OWED",
    re.I,
)
#: Stripped BEFORE the owed count. `Unfinished, not undecided` is boilerplate on EVERY `[~]`
#: row — it is part of the 📐 DECIDED template, and it says the same thing about a row that
#: has not been started and one that shipped last Tuesday. Counting a constant as evidence
#: made `MAX_OWED = 1` mean zero in practice: every row arrived with its whole tolerance
#: already spent, so a single genuine owed-marker anywhere silenced the row for good.
BOILERPLATE_RE = re.compile(r"Unfinished, not undecided")
#: A row needs this many completion markers before it is worth mentioning. Set from the
#: observed data: the three real finds carried 8, 13 and 18; the rows correctly left open
#: carried 0-2. Three is comfortably below the floor of the true positives.
MIN_DONE = 3
#: More than this many owed-markers and the block is openly describing outstanding work.
MAX_OWED = 1

ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*")


def scan(text: str) -> list[tuple[str, int, int]]:
    """Return `(row_name, done_markers, owed_markers)` for each SUSPECT `[~]` row."""
    lines = text.split("\n")
    rows = [(n, m) for n, l in enumerate(lines) if (m := ROW_RE.match(l))]
    out: list[tuple[str, int, int]] = []
    for idx, (n, m) in enumerate(rows):
        if m.group(1) != "~":
            continue
        end = rows[idx + 1][0] if idx + 1 < len(rows) else len(lines)
        block = BOILERPLATE_RE.sub("", "\n".join(lines[n:end]))
        done = len(DONE_RE.findall(block))
        owed = len(OWED_RE.findall(block))
        if done >= MIN_DONE and owed <= MAX_OWED:
            out.append((m.group(2), done, owed))
    return out


def markers(text: str, row: str) -> list[str]:
    """The done-markers that flagged one row, so the report says WHY rather than just a count.
    A bare number sends the reader back to the plan to guess what the gate saw."""
    lines = text.split("\n")
    rows = [(n, m) for n, l in enumerate(lines) if (m := ROW_RE.match(l))]
    for idx, (n, m) in enumerate(rows):
        if m.group(2) != row:
            continue
        end = rows[idx + 1][0] if idx + 1 < len(rows) else len(lines)
        block = BOILERPLATE_RE.sub("", "\n".join(lines[n:end]))
        return sorted({s.strip() for s in DONE_RE.findall(block)})
    return []


def selftest() -> int:
    """Non-vacuous in BOTH directions: it must flag a finished-looking open row, and must NOT
    flag one that names outstanding work. A gate that only proved it can fire would not show
    it can stay quiet, and a noisy honesty gate gets ignored — which is worse than absent."""
    finished = (
        "- [~] **TX** — a task\n"
        "  ✅ **DONE.** shipped, 4228 passed, its deferral RETRACTED and DISCHARGED\n"
        "- [x] **TY** — next\n"
    )
    open_row = (
        "- [~] **TZ** — a task\n"
        "  ✅ **DONE.** half of it, 4228 passed, RETRACTED\n"
        "  ⬜ the other half is still owed and NOT built\n"
        "- [x] **TY** — next\n"
    )
    ticked = "- [x] **TW** — done\n  ✅ **DONE.** 4228 passed, RETRACTED, DISCHARGED\n"

    # 🔴 THE T42b REGRESSION, both spellings. Neither uses bold, and the suite count reads
    # `passed=9` rather than `9 passed`. The gate scored this block `done=0` for two days
    # while the row it describes had shipped, and a RESUME pointer sent a session to build
    # it again. If either of these stops being recognised, that recurs.
    unbolded = (
        "- [~] **TU** — a task\n"
        "  ### ✅ DONE 2026-08-12 — one image now holds graph + vectors\n"
        "  [pgk-smoke] image=loreweave/postgres-knowledge:18  passed=9 failed=0\n"
        "- [x] **TY** — next\n"
    )
    # The boilerplate every `[~]` row carries. It must NOT count as owed work: when it did,
    # `MAX_OWED = 1` meant zero, and one stray word anywhere in a long block silenced the row.
    boiler_only = (
        "- [~] **TB** — a task\n"
        "  📐 **DECIDED** — §6.2. Unfinished, not undecided.\n"
        "  ✅ **DONE.** shipped, 4228 passed, its deferral RETRACTED and DISCHARGED\n"
        "- [x] **TY** — next\n"
    )

    a = [r[0] for r in scan(finished)]
    b = [r[0] for r in scan(open_row)]
    c = [r[0] for r in scan(ticked)]
    d = [r[0] for r in scan(unbolded)]
    e = [r[0] for r in scan(boiler_only)]
    ok = True
    if d != ["TU"]:
        print("  SELFTEST FAIL: the T42b spellings (unbolded ✅ DONE / passed=N) were missed: "
              f"{d}")
        ok = False
    if e != ["TB"]:
        print(f"  SELFTEST FAIL: template boilerplate was counted as owed work: {e}")
        ok = False
    if a != ["TX"]:
        print(f"  SELFTEST FAIL: a finished-looking [~] row was not flagged: {a}")
        ok = False
    if b:
        print(f"  SELFTEST FAIL: a row that NAMES outstanding work was flagged: {b}")
        ok = False
    if c:
        print(f"  SELFTEST FAIL: an already-ticked [x] row was flagged: {c}")
        ok = False
    print("[plan-row-honesty-gate] SELFTEST "
          + ("PASS — flags a finished-looking open row (bolded AND the unbolded/`passed=N` "
             "spellings that once went blind), ignores template boilerplate, and stays quiet "
             "on a row that names owed work and on an already-ticked row" if ok else "FAIL"))
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if not os.path.exists(PLAN):
        print(f"[plan-row-honesty-gate] SKIP — no plan at {PLAN}")
        return 0
    with open(PLAN, encoding="utf-8") as fh:
        text = fh.read()
    suspects = scan(text)

    if not suspects:
        print("[plan-row-honesty-gate] OK — no `[~]` row reads as finished")
        return 0

    print(f"[plan-row-honesty-gate] {len(suspects)} `[~]` row(s) READ AS FINISHED — "
          f"open the block and decide:")
    for name, done, owed in suspects:
        seen = ", ".join(markers(text, name)[:4])
        print(f"    {name:<8} completion-markers={done:<3} owed-markers={owed}   saw: {seen}")
    print("\n  This is a WARNING, not a verdict: the gate cannot know a row is complete, only")
    print("  that its own block reads like it. Tick it, or add the sentence that says what is")
    print("  still owed — a row that names its remainder stops being flagged, which is the")
    print("  point. Under-reporting sends the next session after work that is already done.")
    return 1 if "--strict" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())
