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

TWO signals, either sufficient, and the second exists because the first was not enough:

  1. MARKER COUNT — completion phrases against owed phrases inside the block. Crude on
     purpose, and dialect-bound however wide the word list gets.
  2. COMPLETION HEADING — a `### ✅ DONE …` inside an open row. Structural: it does not care
     how the sentence is punctuated.

A row that trips either, and names no outstanding work, is worth a HUMAN look — nothing more.

🔴 **AND IT MISSED THREE ROWS ON ITS FIRST REAL TEST, which is why signal 2 exists.** Signal 1
was calibrated on the three rows above, all of which wrote `✅ **BOLD**` and `N passed`; the
selftest fixtures were written in that dialect too. `T42b`/`T42c`/`T42d` shipped 2026-08-12
writing `✅ DONE <date>` and `passed=N`, scored **0 and 2**, and sat `[~]` for two days while
this gate reported OK — until a RESUME pointer sent a session to rebuild `T42b`. **A detector
fitted to the examples that motivated it, and validated against those same examples, is green
by construction.** Signal 2 is backtested against the plan at the commit that ADDED this gate,
where it flags T42b and T42c and this gate said OK.

The false positives are the intended workflow, not a defect: they are resolved by reading the
block, and a row that then names its remainder stops being flagged.

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

#: ── THE STRUCTURAL SIGNAL, and it exists because counting words was the wrong instrument ──
#: A completion HEADING inside an open row. `### ✅ DONE 2026-08-12` is the author declaring
#: the row finished; whether they bolded it is not information about the work.
#:
#: 🔴 WHY THIS IS SEPARATE FROM THE MARKER COUNT ABOVE. That count was calibrated on the three
#: rows that motivated the gate (T36 · T38 · T42a) — the docstring says so: *"the three real
#: finds carried 8, 13 and 18"*, and `MIN_DONE = 3` was read off that distribution. All three
#: happened to write `✅ **BOLD**` and `N passed`. The selftest fixtures were then written in
#: that same dialect, so the gate proved it could fire on the vocabulary it already knew. The
#: rows it went on to miss wrote `✅ DONE <date>` and `passed=N` and scored **0 and 2**.
#:
#: A detector fitted to the examples that motivated it, validated against those same examples,
#: is green by construction — the same shape as an eval whose smallest attainable p-value sits
#: above its own alpha. Widening the word list only buys the next dialect; keying on the
#: STRUCTURE of the claim does not care which words are in it.
#:
#: Backtested rather than asserted: run against the plan at `cd8b1be8f` — the commit that
#: ADDED this gate, where it reported `OK — no [~] row reads as finished` — this signal flags
#: T42b and T42c, both of which had shipped ~20 hours earlier.
#:
#: `(?!~~)` skips struck-through headings: `~~### DEFERRAL …~~ — DISCHARGED` is a retracted
#: block, not a completion claim.
COMPLETION_HEADING_RE = re.compile(
    r"^\s*#{3,}\s*(?!~~).*?(?:✅|DONE|CLOSED|SHIPPED)", re.I,
)
#: ── SIGNAL 3 · THE AUTHORING MOMENT (`--staged`) ─────────────────────────────────────────
#: A **row-level** completion claim: `### ✅ DONE 2026-08-12`, where "done" IS the whole claim
#: and it carries a date. Distinguished from a SLICE claim — `### ✅ B4 2026-08-13 — second
#: consumer migrated`, `### ✅ BATCH 5 …`, `### ✅ A8 … facts_for ships` — which says a piece
#: landed while the row stays open, and is completely legitimate.
#:
#: That distinction is the whole reason this signal is usable at all. Measured across all 183
#: commits that ever touched the plan:
#:
#:     "adds ANY ✅ heading, touches no checkbox"        -> 68 commits   unusable as a gate
#:     "adds ✅ DONE/CLOSED <date>, touches no checkbox" ->  5 commits   ALL FIVE ARE REAL
#:
#: The five are `T38` (08-11) and `T42a`/`T42b`/`T42c`/`T42d` (08-12) — five of the six rows
#: that shipped and sat `[~]`, each caught **in the commit that shipped it** rather than days
#: later by a hand scan. Requiring the DATE is what removes the last two false positives: the
#: T43 sub-deferral closures write `#### ✅ CLOSED — the mapping is built` with none.
#:
#: WHY THIS IS THE ONE THAT MATTERS. Ticking used to happen inside the building commit — 23
#: rows between 08-09 and 08-11 — and stopped when the plan grew a second, better-maintained
#: head. This gate is the only signal that fires while the author is still in the file with
#: the context to act. Every other signal here reports on a plan that is already wrong.
ROW_DONE_CLAIM_RE = re.compile(
    r"^\s*#{3,}\s*✅\s*(?:DONE|CLOSED)\s+\d{4}-\d{2}-\d{2}", re.I,
)

#: A row needs this many completion markers before it is worth mentioning. Set from the
#: observed data: the three real finds carried 8, 13 and 18; the rows correctly left open
#: carried 0-2. Three is comfortably below the floor of the true positives.
MIN_DONE = 3
#: More than this many owed-markers and the block is openly describing outstanding work.
MAX_OWED = 1

ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*")


def scan(text: str) -> list[tuple[str, int, int]]:
    """Return `(row_name, done_markers, owed_markers)` for each SUSPECT `[~]` row.

    TWO independent signals, either sufficient. The marker count is the original heuristic and
    it is dialect-bound however wide the word list gets; the completion HEADING is structural
    and does not care how the sentence is punctuated. Keeping both means a row that declares
    itself finished in prose OR in a heading is caught, and neither signal has to anticipate
    the other's blind spot.
    """
    lines = text.split("\n")
    rows = [(n, m) for n, l in enumerate(lines) if (m := ROW_RE.match(l))]
    out: list[tuple[str, int, int]] = []
    for idx, (n, m) in enumerate(rows):
        if m.group(1) != "~":
            continue
        end = rows[idx + 1][0] if idx + 1 < len(rows) else len(lines)
        raw = lines[n:end]
        block = BOILERPLATE_RE.sub("", "\n".join(raw))
        done = len(DONE_RE.findall(block))
        owed = len(OWED_RE.findall(block))
        heading = any(COMPLETION_HEADING_RE.match(line) for line in raw)
        if owed <= MAX_OWED and (done >= MIN_DONE or heading):
            out.append((m.group(2), done, owed))
    return out


def scan_staged(post: str, added: set[str]) -> list[tuple[str, str]]:
    """`[~]` rows to which THIS commit adds a row-level completion claim.

    `post` is the staged post-image; `added` the set of added lines. Matching on the heading
    TEXT rather than on diff line numbers: line arithmetic across a 9 000-line file with
    multiple hunks is the kind of thing that silently drifts, and the heading is unique enough
    to key on.

    A row that names outstanding work is exempt — a slice landing inside an openly-unfinished
    row is normal, and is the case that made the un-dated variant of this signal unusable.
    """
    lines = post.split("\n")
    rows = [(n, m) for n, l in enumerate(lines) if (m := ROW_RE.match(l))]
    out: list[tuple[str, str]] = []
    for idx, (n, m) in enumerate(rows):
        if m.group(1) != "~":
            continue
        end = rows[idx + 1][0] if idx + 1 < len(rows) else len(lines)
        raw = lines[n:end]
        if OWED_RE.search(BOILERPLATE_RE.sub("", "\n".join(raw))):
            continue
        for line in raw:
            if ROW_DONE_CLAIM_RE.match(line) and line.strip() in added:
                out.append((m.group(2), line.strip()))
                break
    return out


def staged_mode() -> int:
    import subprocess

    rel = os.path.relpath(PLAN, ROOT).replace("\\", "/")
    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8").stdout

    diff = git("diff", "--cached", "-U0", "--", rel)
    if not diff.strip():
        return 0
    added = {l[1:].strip() for l in diff.split("\n")
             if l.startswith("+") and not l.startswith("+++")}
    post = git("show", f":{rel}")
    if not post:
        return 0
    hits = scan_staged(post, added)
    if not hits:
        print("[plan-row-honesty-gate] staged: OK — no row-level completion claim lands on an "
              "open row")
        return 0
    print("[plan-row-honesty-gate] STAGED: this commit declares a row DONE and leaves its box "
          "open:")
    for name, heading in hits:
        print(f"    - [~] **{name}**   <-  {heading[:88]}")
    print("\n  Ticking used to happen in the commit that did the work — 23 rows did, and then")
    print("  it stopped, and six rows shipped `[~]`. One of them sent a later session to")
    print("  rebuild work that had already landed. You are in the file right now; the next")
    print("  reader is not.\n")
    print("  Do ONE of:")
    print("    * tick the box            - [~] -> - [x]")
    print("    * say what is still owed  add a ⬜ sentence naming the remainder")
    print("    * name the SLICE          '### ✅ B4 2026-08-13 — …' instead of '✅ DONE <date>'")
    print("      (a slice landing inside an openly-unfinished row is normal and not flagged)")
    return 1


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

    # 🔴 A THIRD DIALECT, deliberately sharing no vocabulary with either of the two above —
    # no bold, no "N passed", no "passed=N", no RETRACTED/DISCHARGED. Only the structure of
    # the claim: a completion HEADING inside an open row. Written this way ON PURPOSE, because
    # the previous selftest reused the exact dialect of the three rows that motivated the gate
    # and therefore only ever proved it could fire on what it already knew.
    third_dialect = (
        "- [~] **TD** — a task\n"
        "  ### ✅ Shipped 2026-08-20 — the thing works and here is how we know\n"
        "  It runs against the real service and the numbers agree.\n"
        "- [x] **TY** — next\n"
    )
    # A struck-through heading is a RETRACTED block, not a completion claim.
    struck = (
        "- [~] **TS** — a task\n"
        "  ### ~~DEFERRAL `D-X`~~ — superseded, kept for the record\n"
        "  the work itself has not started\n"
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
    f = [r[0] for r in scan(third_dialect)]
    if f != ["TD"]:
        print("  SELFTEST FAIL: a completion HEADING in an unseen dialect was missed — the "
              f"gate is fitted to its examples again: {f}")
        ok = False
    g = [r[0] for r in scan(struck)]
    if g:
        print(f"  SELFTEST FAIL: a struck-through (retracted) heading read as completion: {g}")
        ok = False

    # ── signal 3, the authoring moment. Both directions, and the SLICE case is the one that
    # decides whether this gate is usable at all: 68 commits add a ✅ heading while touching no
    # checkbox, and only 5 add a DATED row-level one. Flagging the other 63 would make it noise.
    post = (
        "- [~] **TP** — a task\n"
        "  ### ✅ DONE 2026-08-12 — the image ships and the smoke proves it\n"
        "- [~] **TQ** — another\n"
        "  ### ✅ B4 2026-08-13 — second consumer migrated, the gate shrinks\n"
        "- [~] **TR** — a third\n"
        "  ### ✅ DONE 2026-08-12 — shipped\n"
        "  ⬜ but the Kuzu half is still owed\n"
        "- [x] **TY** — next\n"
    )
    all_added = {l.strip() for l in post.split("\n")}
    h = [n for n, _ in scan_staged(post, all_added)]
    if h != ["TP"]:
        print(f"  SELFTEST FAIL: staged signal wrong. want ['TP'] (row-level claim on an open "
              f"row); a SLICE heading and a row naming its remainder must NOT fire: {h}")
        ok = False
    # An unchanged block must not fire: the claim has to be ADDED by this commit, or every
    # later commit touching the plan would be blocked by a heading someone else wrote.
    i = [n for n, _ in scan_staged(post, set())]
    if i:
        print(f"  SELFTEST FAIL: staged signal fired on a heading this commit did not add: {i}")
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
          + ("PASS — flags a finished-looking open row across THREE dialects (bolded, the "
             "unbolded/`passed=N` pair that once went blind, and a heading-only one sharing no "
             "vocabulary with either), ignores template boilerplate and struck-through "
             "headings, and stays quiet on a row that names owed work and on a ticked row"
             if ok else "FAIL"))
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if "--staged" in sys.argv:
        return staged_mode()
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
        seen = ", ".join(markers(text, name)[:4]) or "a ✅ completion HEADING (structural)"
        print(f"    {name:<8} completion-markers={done:<3} owed-markers={owed}   saw: {seen}")
    print("\n  This is a WARNING, not a verdict: the gate cannot know a row is complete, only")
    print("  that its own block reads like it. Tick it, or add the sentence that says what is")
    print("  still owed — a row that names its remainder stops being flagged, which is the")
    print("  point. Under-reporting sends the next session after work that is already done.")
    return 1 if "--strict" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())
