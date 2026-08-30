#!/usr/bin/env python3
"""A CLOSED deferral must not be named in the handoff as though it were still owed.

The 2026-08-21 handoff block called itself *"the run STOPPED on four decisions, and they are the
whole remaining list"*. Three of the four had closed. Two were deferral ids the plan had already
struck; the third was a task that had landed. A stale blocker list does not merely age — it sends
the next session at work that does not exist, and the plan records the cost in its own words:

    "it is the mechanism that made a settled question read as open for eight days and stopped a
     run on a decision nobody owed."

`deferral-gate` reported this file as **"13 ids, ungoverned"** — it knows the handoff names
deferrals and does not check them. This is that check.

⚠️ **The rule cannot be "a closed id must not appear".** A handoff that RETRACTS a stale item has
to name it to retract it, and deleting the history is how the retraction stops being visible. So
the test is CONTEXTUAL: a closed id may appear, provided the text around it says it is closed.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDOFF = os.path.join(ROOT, "docs", "sessions", "SESSION_HANDOFF.md")
PLAN = os.path.join(
    ROOT, "docs", "plans", "2026-08-09-knowledge-architecture-refactor.md")

_ID = re.compile(r"\bD-[A-Z0-9][A-Z0-9-]{4,}\b")

#: Words that mark a mention as a RETRACTION rather than a live claim. Deliberately generous:
#: a false PASS here costs a stale line, a false FAIL costs someone deleting real history to
#: get the gate green — and that is the worse failure, because the history is the retraction.
_CLOSED_MARKERS = ("closed", "superseded", "retracted", "stale", "landed", "discharged",
                   "no longer", "was wrong", "already", "struck")

#: How far around a mention counts as "the text around it".
_WINDOW = 2


#: The handoff tells its reader to verify the census with a command carrying a TYPED LINE
#: NUMBER: "`sed -n 46p` on the plan for the progress block". True the day it was written, and
#: silently wrong the moment anything is inserted above that line — after which the next reader
#: is handed a random line of a 29 000-line plan and told it is the row census.
#:
#: T48ax. Same class as `makefile-claim-gate`'s typed lint count: a number in prose that nothing
#: re-derives. This is the cheapest possible check of it — follow the instruction and see if it
#: lands where the handoff says.
_SEDLINE = re.compile(r"`sed -n (\d+)p`")
#: What the progress block looks like, so "it landed" is a property and not a line number.
_PROGRESS = re.compile(r"\d+ of \d+ rows done")


def cited_sed_line(handoff_text: str) -> int | None:
    """The line number the handoff tells the reader to print, if it cites one."""
    m = _SEDLINE.search(handoff_text)
    return int(m.group(1)) if m else None


def sed_line_lands(plan_text: str, line_no: int | None) -> bool | None:
    """Does that line actually hold the progress block? None when nothing is cited."""
    if line_no is None:
        return None
    lines = plan_text.split(chr(10))
    if not (1 <= line_no <= len(lines)):
        return False
    return bool(_PROGRESS.search(lines[line_no - 1]))


def closed_ids(plan_text: str) -> set[str]:
    """Deferral ids the PLAN has struck. A struck heading is the plan's own closure marker."""
    return set(re.findall(r"~~DEFERRAL~~ `(D-[A-Z0-9][A-Z0-9-]{4,})`", plan_text))


def stale_mentions(handoff_text: str, closed: set[str]) -> list[tuple[int, str]]:
    """`(line number, id)` for every mention of a CLOSED id whose surrounding lines do not say
    so. Line numbers are 1-based so the output is clickable."""
    lines = handoff_text.split("\n")
    out: list[tuple[int, str]] = []
    for n, line in enumerate(lines):
        for found in _ID.findall(line):
            if found not in closed:
                continue
            lo, hi = max(0, n - _WINDOW), min(len(lines), n + _WINDOW + 1)
            context = " ".join(lines[lo:hi]).lower()
            if not any(m in context for m in _CLOSED_MARKERS):
                out.append((n + 1, found))
    return out


def selftest() -> int:
    print("handoff-staleness-gate - selftest (offline)")
    ok = True

    plan = "### ~~DEFERRAL~~ `D-GONE-AWAY` — CLOSED 2026-01-01\n### DEFERRAL `D-STILL-OPEN`\n"
    assert closed_ids(plan) == {"D-GONE-AWAY"}
    print("  PASS  a struck heading is read as CLOSED; an unstruck one is not")

    # The case the gate exists for.
    bad = "Four things need a person:\n1. `D-GONE-AWAY` — a spend call.\n"
    if stale_mentions(bad, {"D-GONE-AWAY"}) != [(2, "D-GONE-AWAY")]:
        print("  FAIL  a CLOSED id presented as owed was not reported"); ok = False
    else:
        print("  PASS  a CLOSED id presented as owed is reported, with its line")

    # The case that must NOT fire — validated on the opposite of what motivated the gate
    # (rule 3): the retraction has to be allowed, or the cure is deleting the history.
    good = "| `D-GONE-AWAY` — a spend call | **CLOSED 2026-08-21**, adjudicated SUPERSEDED |\n"
    if stale_mentions(good, {"D-GONE-AWAY"}):
        print("  FAIL  a RETRACTION naming the id was reported; the only way to satisfy this "
              "gate would be to delete the retraction, which is the history"); ok = False
    else:
        print("  PASS  a retraction may name the id it retracts")

    # An OPEN id is never this gate's business, however it is phrased.
    if stale_mentions("1. `D-STILL-OPEN` — a design call.\n", {"D-GONE-AWAY"}):
        print("  FAIL  an OPEN deferral was reported"); ok = False
    else:
        print("  PASS  an open deferral is not reported")

    # The marker must be NEAR the mention, not anywhere in the file.
    far = ("1. `D-GONE-AWAY` — a spend call.\n" + "filler\n" * 8 + "that one was CLOSED\n")
    if not stale_mentions(far, {"D-GONE-AWAY"}):
        print("  FAIL  a 'closed' eight lines away satisfied the check; the window is not "
              "doing anything and any file mentioning the word would pass"); ok = False
    else:
        print("  PASS  the closure marker must be NEAR the mention")

    print("\n  all checks passed" if ok else "\n  FAILURES above")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    with open(PLAN, encoding="utf-8", errors="replace") as fh:
        plan = fh.read()
    with open(HANDOFF, encoding="utf-8", errors="replace") as fh:
        handoff = fh.read()
    closed = closed_ids(plan)
    stale = stale_mentions(handoff, closed)
    if stale:
        print("[handoff-staleness-gate] FAIL — the handoff names CLOSED deferral(s) without "
              "saying they are closed:\n")
        for line_no, ident in stale:
            print(f"    SESSION_HANDOFF.md:{line_no}  {ident}")
        print("\n  Either mark the mention as closed/superseded/retracted, or remove it. A")
        print("  blocker list that names a settled question sends the next session at work")
        print("  that does not exist — the plan records eight days lost to exactly this.")
        return 1
    cited = cited_sed_line(handoff)
    lands = sed_line_lands(plan, cited)
    if lands is False:
        print(f"[handoff-staleness-gate] FAIL — the handoff tells its reader to run "
              f"`sed -n {cited}p` on the plan for the progress block, and that line does not "
              f"hold it. A typed line number in prose points somewhere else the moment anything "
              f"is inserted above it, and the next reader takes whatever it prints as the "
              f"census.")
        return 1
    print(f"[handoff-staleness-gate] OK — {len(_ID.findall(handoff))} deferral mention(s) in the "
          f"handoff, {len(closed)} closed id(s) known from the plan, 0 presented as still owed"
          + (f"; `sed -n {cited}p` still lands on the progress block" if lands else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
