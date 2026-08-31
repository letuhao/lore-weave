#!/usr/bin/env python3
"""stale-deferral-gate — a deferral whose HEADING says open while its BODY says closed.

Found by hand five times on 2026-08-21 (T46h ×4, T46m ×1), and each one had real consequences:

  * `plan-final-verification` refuses a `[x]` QC row whose section "records a deferral", and it
    decides that on the heading. Four stale headings were half of everything blocking QC-5.
  * `deferral-gate` counts them, so the tracked total was wrong.
  * A reader looking for what is left is told to look at work that finished days ago.

The five were not found by a rule. They were found by opening each block and reading its
`Retry when` field, which is slow and — measured — unreliable: a keyword heuristic tried during
T46h flagged three, missed the fourth, and would have swept in a block that genuinely disagrees
with itself. So the rule this gate encodes is deliberately narrow:

    a deferral is STALE when its heading is UNSTRUCK and its `Retry when` field opens with a
    closure statement.

`Retry when` is the field the plan's own convention makes load-bearing — *"a deferral must
declare what would wake it up"* — so a `Retry when` that says "nothing" IS the closure. Other
fields are not consulted on purpose: `Blocker` and `To unblock` routinely contain struck-through
history, and reading those is what made the heuristic sweep in a false positive.

Usage
    python scripts/stale-deferral-gate.py                    # scan the tracked plans
    python scripts/stale-deferral-gate.py --file PATH ...
    python scripts/stale-deferral-gate.py --selftest         # offline, no repo needed
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GLOBS = ("docs/plans/*.md",)

#: An OPEN deferral heading. A closed one is written `~~DEFERRAL~~ \`D-…\`` — this repo's
#: existing convention, and the one the fix applies.
#:
#: ⚠️ TWO REDUNDANT EXCLUSIONS, and bite 78 is how that was learned. `(?!~~)` rejects the
#: LEADING `~~`, and `DEFERRAL\s+\`` rejects the TRAILING one (`DEFERRAL~~ \`` has no
#: whitespace before the backtick). Either alone excludes every struck heading, so mutating
#: either alone is a NO-OP: bite 78 read as "did not fire" three times — first against a
#: separate struck-heading branch that turned out to be dead code and was deleted, then
#: against each of these in turn. Only mutating BOTH reds the selftest (2 checks) and the
#: live scan (7 findings). Recorded because the next reader will otherwise mutate one, see
#: nothing happen, and conclude the guard is decorative.
_OPEN_HEADING = re.compile(r"^\s*#{2,4}\s+(?!~~)(?:[^\w\s]*\s*)?DEFERRAL\s+`(D-[A-Z0-9-]+)`")
_RETRY_ROW = re.compile(r"^\s*\|\s*\*\*Retry when\*\*\s*\|(?P<body>.*)$")

#: Closure phrasings, matched against the START of the `Retry when` body (after stripping any
#: leading struck-through clause, which is how this repo records "the old condition, retired").
#: Anchored at the start so a block that says "…retry when X; note that Y was closed" is NOT
#: swept up — that trailing kind of mention is exactly what produced T46h's false positive.
_CLOSED_OPENERS = (
    r"n/?a\b",
    r"nothing (?:outstanding|left|further|remains)",
    r"closed\b",
    r"done\b",
    r"superseded\b",
    r"no longer",
    r"run \d{4}-\d{2}-\d{2}",
    r"never — ",
    # ── added 2026-08-21, from a MEASURED miss ────────────────────────────────────────────
    # The supersession audit found three cells this gate walked straight past:
    #   `~~The scope question is answered.~~ ✅ **DECIDED BY THE PO 2026-08-13`
    #   `~~The KAL scope question is answered.~~ ✅ **DECIDED BY THE PO 2026-08-13`
    #   `~~The PO decides whether…~~ ✅ **ANSWERED — §1.2`
    # `answered` is safe bare: nothing schedules future work by opening with it.
    #
    # ⚠️ `decided` is NOT safe bare, and that is the point of the qualifier. A live condition can
    # legitimately open *"Decided only after T42 lands."* — a future event, not a closure — and a
    # bare `decided\b` would sweep it in. Requiring an ATTRIBUTION or a DATE after it
    # ("decided by the PO", "decided 2026-08-13") keeps the past-tense closure and rejects the
    # future-tense condition. Fixture `a future condition that OPENS with "Decided"` is the
    # case this was validated against, and it is not one of the three that motivated the rule.
    r"answered\b",
    r"decided\s+(?:by\b|on\b|\d{4}-\d{2}-\d{2})",
)
_CLOSED_RE = re.compile(r"^\W*(?:\*\*)?(?:" + "|".join(_CLOSED_OPENERS) + ")", re.IGNORECASE)
_STRUCK_PREFIX = re.compile(r"^\s*~~.*?~~\s*")


def retry_is_closed(body: str) -> bool:
    """Does this `Retry when` body OPEN with a closure statement?"""
    text = body.strip().lstrip("|").strip()
    # "~~(a) lands.~~ **CLOSED 2026-08-11**" — the retired condition is struck, the closure
    # follows it. T46h's heuristic missed exactly this shape.
    prev = None
    while prev != text:
        prev = text
        text = _STRUCK_PREFIX.sub("", text).strip()
    return bool(_CLOSED_RE.match(text))


def scan(text: str) -> list[tuple[str, str]]:
    """Return [(deferral_id, retry_body)] for every STALE block in `text`."""
    lines = text.splitlines()
    findings: list[tuple[str, str]] = []
    current: str | None = None
    for line in lines:
        m = _OPEN_HEADING.match(line)
        if m:
            current = m.group(1)
            continue
        if current is None:
            continue
        if line.lstrip().startswith("#"):        # a new section ended the block
            current = None
            continue
        r = _RETRY_ROW.match(line)
        if r:
            if retry_is_closed(r.group("body")):
                findings.append((current, r.group("body").strip()[:120]))
            current = None                        # one Retry-when per block
    return findings


_SYNTHETIC: list[tuple[str, str, bool]] = [
    # (name, markdown, expect_stale)
    ("an open deferral with a real retry condition",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | The measurement rule is chosen. |\n", False),
    ("`Retry when` says n/a — closed",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | n/a — closed. Nothing remains. |\n", True),
    # the shape T46h's keyword heuristic MISSED: closure behind a struck-through clause
    ("closure hidden behind a struck-through condition",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | ~~(a) lands.~~ **CLOSED 2026-08-11.** |\n", True),
    ("an already-struck heading is not re-reported",
     "### ~~DEFERRAL~~ `D-X`\n| **Retry when** | n/a — closed. |\n", False),
    # the false positive the heuristic WOULD have swept in: a live condition that merely
    # MENTIONS a closure later in the sentence
    ("a live condition that mentions a closure later",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | Immediately — unlike `D-Y`, which is closed. |\n",
     False),
    ("nothing outstanding",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | Nothing outstanding. No longer blocks QC-5. |\n",
     True),
    ("a RUN date is a closure",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | ~~Whenever the PO wants.~~ RUN 2026-08-11. |\n",
     True),
    # the three shapes the supersession audit MEASURED this gate missing, 2026-08-21
    ("a struck condition followed by an ANSWERED marker",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | ~~The PO decides whether.~~ ✅ **ANSWERED — §1.2** |\n", True),
    ("a struck condition followed by DECIDED BY THE PO",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | ~~The scope question is answered.~~ ✅ **DECIDED BY THE PO 2026-08-13** |\n",
     True),
    ("a bare DECIDED with a date is a closure",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | Decided 2026-08-13 — the port owns everything. |\n", True),
    # THE DISCRIMINATING NEGATIVE, and NOT one of the three above: `decided` opening a FUTURE
    # condition. A bare `decided\b` opener would call this closed and retire a live row.
    ("a future condition that OPENS with `Decided`",
     "### 🔻 DEFERRAL `D-X`\n| **Retry when** | Decided only after T42 lands. |\n", False),
    ("a deferral with no Retry-when row at all is not guessed at",
     "### 🔻 DEFERRAL `D-X`\n| **Blocker** | something closed long ago |\n", False),
    ("a heading inside the block ends it, so a LATER table is not attributed here",
     "### 🔻 DEFERRAL `D-X`\n| **Blocker** | live |\n#### note\n| **Retry when** | n/a |\n", False),
]


def selftest() -> int:
    print("stale-deferral-gate - selftest (offline)")
    bad = 0
    for name, md, want in _SYNTHETIC:
        got = bool(scan(md))
        ok = got == want
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: expected {'STALE' if want else 'open'}, "
              f"got {'STALE' if got else 'open'}")
    # The property the fixtures cannot state: the struck form and the open form of the SAME
    # block must disagree. If they ever agree, the gate has stopped keying on the heading and
    # would either miss every stale block or condemn every closed one.
    body = "| **Retry when** | n/a — closed. |\n"
    open_form = scan("### 🔻 DEFERRAL `D-X`\n" + body)
    struck_form = scan("### ~~DEFERRAL~~ `D-X`\n" + body)
    ok = bool(open_form) and not struck_form
    bad += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  the same body reads STALE open and clean struck")
    print("\n  all checks passed" if not bad else f"\n  {bad} check(s) FAILED")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", action="append", help="a markdown file to scan")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    paths = a.file or [p for g in DEFAULT_GLOBS for p in glob.glob(os.path.join(ROOT, g))]
    total = 0
    scanned = 0
    for path in sorted(paths):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        scanned += 1
        for did, retry in scan(text):
            total += 1
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            print(f"stale-deferral-gate: {rel}: `{did}` is marked OPEN but its Retry-when reads:")
            print(f"    {retry}")
    if total:
        print(f"\nstale-deferral-gate: FAIL — {total} deferral(s) advertise as open while their "
              f"own Retry-when says otherwise.")
        print("  Strike the heading (`### ~~DEFERRAL~~ `D-…``) so `plan-final-verification` and "
              "`deferral-gate` stop counting finished work as blocking.")
        return 1
    print(f"stale-deferral-gate: OK — {scanned} plan(s) scanned, no deferral advertises as open "
          f"while its own Retry-when says it is closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
