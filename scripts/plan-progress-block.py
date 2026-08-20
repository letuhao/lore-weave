#!/usr/bin/env python3
"""plan-progress-block — the run state's progress line, DERIVED from the checkboxes.

WHY THIS EXISTS
---------------
The plan under-reported six times (T36 · T38 · T42a, then T42b · T42c · T42d): rows that had
shipped and stayed `[~]`, one of which sent a later session to rebuild work already done.
Walking the plan's history located the moment it started:

    08-09 22:04 → 08-11 04:07   23 rows ticked, each inside the commit that built it
    08-11 21:58                 the CURRENT RUN STATE block lands
    08-12 09:13                 T30 — the last row ever ticked by its own build commit

That block was added to fix a plan with *"four heads, and one told a lie"*. It succeeded, and
in succeeding it created a SECOND representation of "what is done" beside the checkboxes. One
of the two gets read and maintained; the other drifts. `CLAUDE.md` states the rule this breaks:

    guidance that is duplicated goes stale in one copy and then actively misleads.
    One home, one name.

So the fix is not another checker. It is to stop having two copies: the progress line becomes
**generated from the checkboxes**, and the hand-curated `✅ A8 · ✅ T24b · …` tail it replaces
is deleted rather than left beside it.

IT LISTS WHAT IS **OPEN**, NOT WHAT IS DONE, AND THAT IS THE WHOLE DESIGN
------------------------------------------------------------------------
Listing completions would not have caught any of the six. A row that shipped and stayed `[~]`
is simply ABSENT from a done-list, and **nobody notices an absence** — that is exactly how the
old hand-written tail hid the drift for two days, and it was a curated list of recent wins, so
its incompleteness read as normal.

Inverted, the same drift is loud: a row you finished twenty minutes ago sitting in a list
headed **OPEN**, in the block you read to decide what to do next, is jarring. The reader who
can fix it cheapest is the one who just shipped it.

    python scripts/plan-progress-block.py --write     # regenerate in place
    python scripts/plan-progress-block.py --check     # exit 1 if stale (pre-commit)
    python scripts/plan-progress-block.py --selftest
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "plans", "2026-08-09-knowledge-architecture-refactor.md")

BEGIN = "<!-- generated:progress -->"
END = "<!-- /generated:progress -->"

ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*")

#: An EVIDENCE BLOCK inside a row: a `###`/`####` heading carrying a status marker. These are
#: the units work is actually done in — `A1…A9`, `B1…B9`, `BATCH 1…7`, `T37a…T37d`, `HALF 1…3`.
#: 111 of them across the plan.
#:
#: 🔴 THIS IS THE GRANULARITY MISMATCH THAT CAUSED THE UNDER-REPORTING, and it is measurable:
#:
#:     T17    20 blocks, 12 ✅      checkbox [~] the whole time
#:     QC-5   30 blocks, 12 ✅      checkbox [~]
#:     T39    21 blocks, 15 ✅      checkbox [~]
#:
#: Three open rows carry 71 blocks. The plan's unit of ACCOUNTING is the row, so none of that
#: work could move the number: `46 of 66` is unchanged by twelve closed slices in T17. An
#: accounting that cannot register a day's work is one people stop maintaining — and they did,
#: on 08-11. Surfacing the ratio is what lets the count move without the checkbox lying.
SLICE_RE = re.compile(r"^\s*#{3,4}\s*(✅|🔴|🔻|📏|🎯|⏸)\s*(?!~~)")
SLICE_DONE_RE = re.compile(r"^\s*#{3,4}\s*✅")


#: The two named WORKSTREAMS, whose blocks are numbered rather than row-prefixed. Declared in
#: the plan itself — *"Workstream A — T17: the port owns everything"*, *"Workstream B — T38:
#: the KAL grows a detail read"* — so this is a lookup, not a guess.
WORKSTREAM = {"A": "T17", "B": "T38"}
_SERIES_RE = re.compile(r"\b([AB])(\d+)\b")


def owner_of(heading: str, known: list[str], inherited, positional: str):
    """Which ROW an evidence block evidences, and whether it said so itself.

    🔴 **THIS REPLACES POSITIONAL ATTRIBUTION, WHICH WAS MEASURABLY WRONG.** A row used to own
    every block between its checkbox and the next one, and the plan does not store blocks that
    way — it is a chronological journal. Measured 2026-08-14, the 24 blocks credited to `T39`
    broke down as:

        T37 10 · T17 5 · T35 3 · **T39 2** · T24 2 · T25 1 · gate 1

    So `T39` read **16/24** while owning two blocks, and `T17` read **12/20** while owning
    fifteen. This block calls itself *"the only block that answers what next"*, and *"which row
    is largest"* is precisely the query it was being used for — a session picked T17 as "the
    largest genuinely-open row" from a number that was five blocks short, on a row whose own
    spec section says its ceiling should NOT reach zero.

    A block names its own row (`A8`, `T35a`, `T37b-studio`, `QC-5`), so ownership is READ, not
    inferred from where the text happens to sit. Sub-headings that name nothing — a finding
    written under the batch that found it — inherit the last named block, which is where they
    belong. Only a block that names nothing AND follows nothing falls back to position, and
    `render` reports how many did, so the fallback cannot grow unnoticed.
    """
    m = _SERIES_RE.search(heading)
    if m and WORKSTREAM[m.group(1)] in known:
        return WORKSTREAM[m.group(1)], True
    # Longest first: `T42a` must win over `T42`, and `T24b-a` resolves to `T24` — `T24b` is a
    # slice of that row, not a row of its own.
    for rid in sorted(known, key=len, reverse=True):
        if re.search(r"\b" + re.escape(rid), heading):
            return rid, True
    return (inherited or positional), False


def tally(text: str):
    """(done, total, open rows in plan order as `(name, closed, total)`, orphan count).

    Plan order is the queue order, so the open list doubles as "what may be started" — the
    question the run-state block exists to answer.
    """
    lines = text.split("\n")
    rows = [(n, m) for n, m in ((n, ROW_RE.match(l)) for n, l in enumerate(lines)) if m]
    done = sum(1 for _, m in rows if m.group(1) == "x")
    known = [m.group(2) for _, m in rows]

    tot: dict = {}
    cls: dict = {}
    orphans = 0
    positional, inherited = None, None
    at = {n: m.group(2) for n, m in rows}
    for n, line in enumerate(lines):
        if n in at:
            positional = at[n]
            inherited = None          # a new row starts a new chain; ownership must not leak
            continue
        if positional is None or not SLICE_RE.match(line):
            continue
        who, named = owner_of(line, known, inherited, positional)
        if not named and inherited is None:
            # A TRUE fallback: named nothing and followed nothing, so position is all there is.
            # Inheriting is the intended path for a sub-heading and is NOT counted here —
            # lumping the two together would make the reported number noise, and a number that
            # is noise is one nobody reads.
            orphans += 1
        if named:
            inherited = who
        tot[who] = tot.get(who, 0) + 1
        if SLICE_DONE_RE.match(line):
            cls[who] = cls.get(who, 0) + 1

    open_rows = [(m.group(2), cls.get(m.group(2), 0), tot.get(m.group(2), 0))
                 for _, m in rows if m.group(1) == "~"]
    return done, len(rows), open_rows, orphans


def render(text: str) -> str:
    done, total, open_rows, orphans = tally(text)
    parts = [f"`{n}`" + (f" ({c}/{t})" if t else "") for n, c, t in open_rows]
    listed = " · ".join(parts) or "*none — every row is closed.*"
    blocks = sum(t for _, _, t in open_rows)
    closed = sum(c for _, c, t in open_rows)
    return "\n".join([
        BEGIN,
        "<!-- Derived from the checkboxes by scripts/plan-progress-block.py. Do NOT hand-edit:",
        "     a hand-maintained copy of this is what drifted for two days and sent a session",
        "     to rebuild T42b, which had already shipped. Tick the row instead. -->",
        f"**{done} of {total} rows done · {len(open_rows)} open"
        + (f" · {closed} of {blocks} evidence blocks closed inside them.**" if blocks
           else ".**"),
        "",
        f"**OPEN:** {listed}",
        "",
        *([f"> ⚠️ **{orphans} evidence block(s) name no row** and were attributed by POSITION — "
           "the rule that made `T39` read 16/24 while owning 2. Name the row in the heading "
           "(`A11`, `T35d`, `QC-5`) and this number falls to zero.", ""]
          if orphans else []),
        "> `(n/m)` counts **evidence blocks**, not sub-tasks — the `###`/`####` headings a row "
        "has accumulated and how many are ✅. It is a progress signal, not a contract: the row "
        "is done when its own criteria are met, not at `m/m`.",
        ">",
        "> Two things this makes visible that the checkbox cannot. **A row you just finished "
        "appearing here at all** means its box is still `[~]` — an absence from a done-list is "
        "invisible, a presence in an open-list is not. And **a row moving from 12/20 to 13/20** "
        "is a day's work the binary box could not register; that it registered nothing is why "
        "ticking stopped on 08-11.",
        END,
    ])


def replace(text: str) -> str:
    fresh = render(text)
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        return head + fresh + tail
    # First install: land it directly under the RESUME paragraph, which is where the reader
    # already is. Anywhere else and it becomes a second block nobody looks at, which is the
    # failure being fixed.
    lines = text.split("\n")
    i = next((n for n, l in enumerate(lines) if l.startswith("**RESUME:")), None)
    if i is None:
        raise SystemExit("plan-progress-block: no **RESUME:** line to anchor to")
    lines[i + 1:i + 1] = ["", *fresh.split("\n")]
    return "\n".join(lines)


def selftest() -> int:
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    sample = ("**RESUME:** something\n"
              "- [x] **T1** — done\n"
              "- [~] **T2** — open\n"
              "  ### ✅ A1 2026-08-13 — a slice landed\n"
              "  ### ✅ A2 2026-08-13 — another\n"
              "  ### 🔴 A3 — this one is not done\n"
              "- [x] **T3** — done\n"
              "- [~] **T4** — open\n")
    done, total, open_rows, orphans = tally(sample)
    check("counts the checkboxes", (done, total) == (2, 4), f"{done}/{total}")
    check("lists the OPEN rows, in plan order",
          [r[0] for r in open_rows] == ["T2", "T4"], str(open_rows))
    # ④ — the granularity fix. A row whose slices are landing must show movement, or the
    # accounting stays frozen through a day's work exactly as it did for T17 (12 of 20 closed,
    # `46 of 66` unmoved) — which is what made the checkbox feel pointless to maintain.
    check("counts evidence blocks inside an open row", open_rows[0] == ("T2", 2, 3),
          str(open_rows[0]))
    check("a row with no blocks reports none", open_rows[1] == ("T4", 0, 0), str(open_rows[1]))
    check("the ratio is rendered", "(2/3)" in render(sample))
    moved = sample.replace("### 🔴 A3 — this one is not done", "### ✅ A3 2026-08-14 — landed")
    check("closing ONE slice moves the block, with no checkbox change",
          render(moved) != render(sample) and "(3/3)" in render(moved))

    # 🔴 ATTRIBUTION — the defect this file shipped with, reproduced in miniature. `T4`'s row
    # header is the last checkbox in the document, so under the old positional rule it owned
    # every block written after it regardless of whose work they evidenced. In the real plan
    # that made `T39` report 16/24 while owning 2, and `T17` report 12/20 while owning 15.
    journal = ("**RESUME:** something\n"
               "- [~] **T2** — open\n"
               "  ### ✅ T2a — genuinely T2's\n"
               "- [~] **T4** — open, and the last checkbox in the file\n"
               "  ### ✅ T4a — genuinely T4's\n"
               "  ### ✅ T2b — T2's work, written later in the journal\n"
               "  ### 🔴 a finding with no row in its name\n")
    _, _, jrows, jorph = tally(journal)
    by = dict((n, (c, t)) for n, c, t in jrows)
    check("a block is credited to the row it NAMES, not to the one above it",
          by["T2"] == (2, 3), str(by))
    check("the neighbouring row does not absorb it", by["T4"] == (1, 1), str(by))
    # The sub-heading names nothing. It belongs to `T2b`, the block it was written under —
    # which is how a finding recorded beneath the batch that found it stays with that batch.
    check("an unnamed sub-heading INHERITS the last named block",
          by["T2"][1] == 3 and by["T4"][1] == 1, str(by))
    # It inherited, so it is NOT an orphan: nothing in this journal had to guess from position.
    check("inheriting is not counted as a fallback", jorph == 0, str(jorph))

    # And the fallback must still work when nothing has been named yet, or the first block of
    # a row would land on whichever row was named last — leaking across the boundary.
    lead = ("**RESUME:** x\n"
            "- [~] **T2** — open\n"
            "  ### ✅ T2a — named\n"
            "- [~] **T4** — open\n"
            "  ### ✅ an unnamed block, first in its row\n")
    _, _, lrows, lorph = tally(lead)
    check("ownership does not LEAK across a row boundary",
          dict((n, t) for n, c, t in lrows) == {"T2": 1, "T4": 1}, str(lrows))
    check("a true positional fallback IS counted", lorph == 1, str(lorph))
    out = replace(sample)
    check("installs under the RESUME line", out.index(BEGIN) > out.index("**RESUME:**"))
    check("names the open rows in the rendered block", "`T2`" in out and "`T4`" in out)
    # 🔴 The property the whole design turns on: a DONE row must not be listed, and an
    # un-ticked one MUST be. If this ever inverts, the block becomes a done-list again and
    # goes back to hiding exactly the drift it was built to surface.
    check("a finished row is NOT in the open list", "`T1`" not in out and "`T3`" not in out)

    # Regenerating must be idempotent, or `--check` would report stale on an up-to-date plan
    # and the gate would cry wolf until someone disabled it.
    check("regeneration is idempotent", replace(out) == out)

    # And it must actually MOVE when a box is ticked — a block that renders the same either
    # way could not surface anything.
    ticked = sample.replace("- [~] **T2**", "- [x] **T2**")
    check("ticking a box changes the block", render(ticked) != render(sample))

    print(f"\n  {len(fails)} failure(s)" if fails else "\n  all checks passed")
    return 1 if fails else 0


def main() -> int:
    if "--selftest" in sys.argv:
        print("plan-progress-block · selftest")
        return selftest()
    with open(PLAN, encoding="utf-8") as fh:
        text = fh.read()
    fresh = replace(text)
    if "--write" in sys.argv:
        if fresh != text:
            with open(PLAN, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(fresh)
            print("[plan-progress-block] rewrote the progress block")
        else:
            print("[plan-progress-block] already current")
        return 0
    if fresh != text:
        done, total, open_rows, orphans = tally(text)
        print("[plan-progress-block] STALE — the run-state progress block disagrees with the "
              "checkboxes.")
        print(f"    the checkboxes say: {done} of {total} done, {len(open_rows)} open")
        print("    fix: python scripts/plan-progress-block.py --write")
        return 1
    print("[plan-progress-block] OK — the progress block matches the checkboxes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
