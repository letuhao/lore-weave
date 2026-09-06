#!/usr/bin/env python3
"""No document may call knowledge-service a DERIVED layer of glossary (T44 / T47).

WHY THIS EXISTS
---------------
The claim *"knowledge-service = derived fuzzy/semantic layer"* was written in **three separate
documents** and was false in all three. Measured on the live stack 2026-08-14, knowledge holds
truth glossary **cannot represent**:

    :Event               1184     glossary has no events table
    :EntityStatus          35     of which 0 are glossary-anchored (entity_facts status: 3)
    :Entity unanchored    567

`entity_facts.entity_id` is an FK to `glossary_entities`, so those rows are not merely missing
from the "SSOT" — they are **unwritable** there.

That is not a wording preference. SCOPE-3's contract is *"regenerable from it with no loss"* and
*"derived data is never authored directly"*, so calling the pair SSOT/derived **licenses
rebuilding the KG from glossary** and destroying every one of those rows. The only reason it
never happened is that `jobs/graph_rebuild.py` independently refused to try
(`D-T41-RELATIONS-NOT-REBUILDABLE`) — the code was honest while the standard was not.

WHY A GATE AND NOT JUST THE FIX
-------------------------------
Because it took three files to say one wrong thing, and fixing three files is not a mechanism.
The three were `AGENTS.md` (the entry point every agent reads), `docs/standards/scope-separation.md`
(the rule) and `docs/ARCHITECTURE.md` (the service table) — and AGENTS.md *linked to* the
standard while contradicting it, so a reader who followed the pointer found a rebuttal.

⚠️ **This matches a PHRASE, so it cannot catch a paraphrase**, and pretending otherwise would be
the vacuity this repo keeps cataloguing. What it does catch is the exact sentence coming back —
which is what happens when someone copies a service description from another doc. The paraphrase
case is guarded by SCOPE-3 itself now carrying the measurement, and by this file being cited
from it.

    python scripts/ssot-claim-gate.py
    python scripts/ssot-claim-gate.py --selftest
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Where prose about the services lives. Not the whole repo: a plan quoting its own retraction
#: is history and must stay readable, which is why `docs/plans/` is out of scope below.
SCAN = [os.path.join(ROOT, "AGENTS.md"), os.path.join(ROOT, "CLAUDE.md"),
        os.path.join(ROOT, "docs", "standards"), os.path.join(ROOT, "docs", "ARCHITECTURE.md")]

#: The claim: a line that names knowledge-service AND calls it a derived layer.
#:
#: 🔴 WAS A PROXIMITY REGEX (`knowledge-service\D{0,80}derived\s+fuzzy`) and a bite proved it
#: hollow: moving the two phrases 80 characters apart — or putting a DIGIT between them, since
#: `\D` stops at one — walked straight past it. The window was a number nobody had a reason
#: for. Both phrases ON THE SAME LINE, in any order, is the property that actually describes
#: the defect, and it has no tunable to get wrong.
_SERVICE = re.compile(r"knowledge[- ]service", re.IGNORECASE)
_DERIVED = re.compile(r"derived\s+fuzzy", re.IGNORECASE)


def claims(line: str) -> bool:
    return bool(_SERVICE.search(line) and _DERIVED.search(line))

#: A line may CITE the retired claim while retracting it — that is what SCOPE-3 and AGENTS.md
#: now do. A retraction names itself; the marker is what distinguishes "we no longer say this"
#: from "we say this".
#:
#: 🔴 NARROWED after a bite that FAILED TO GO RED. The first cut also accepted the bare date
#: `until 2026-08-14`, which appears on the very lines that carry the retraction — so a mutation
#: that reinstated the claim on one of those lines was exempted and the gate stayed green. Any
#: line could then have carried the claim forever by keeping a date in it. The markers now have
#: to be an explicit NEGATION of the claim, not merely evidence that a retraction happened
#: nearby.
RETRACTION = re.compile(r"NOT a derived|not an SSOT/derived", re.IGNORECASE)


def offenders(paths: list[str]) -> list[str]:
    found = []
    for target in paths:
        files = []
        if os.path.isdir(target):
            for base, _dirs, names in os.walk(target):
                files += [os.path.join(base, n) for n in names if n.endswith(".md")]
        elif os.path.isfile(target):
            files = [target]
        for path in files:
            with open(path, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if claims(line) and not RETRACTION.search(line):
                        # relpath ACROSS DRIVES raises on Windows, and the selftest writes
                        # its fixtures to the temp dir — which is on C: while the repo is on
                        # D:. Reporting the absolute path is strictly better than crashing.
                        try:
                            rel = os.path.relpath(path, ROOT)
                        except ValueError:
                            rel = path
                        found.append(f"{rel}:{n}")
    return found


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    bad = offenders(SCAN)
    if bad:
        print("[ssot-claim-gate] FAIL — a document calls knowledge-service a DERIVED layer of "
              "glossary:")
        for b in bad:
            print(f"    {b}")
        print("  Measured 2026-08-14: the KG holds 1184 events, 35 statuses (0 anchored) and")
        print("  567 unanchored entities that `entity_facts` cannot even hold. Under SCOPE-3's")
        print("  contract — 'regenerable with no loss' — that wording sanctions destroying them.")
        print("  They are two stores with DISJOINT truth joined by an anchor. See SCOPE-3.")
        return 1
    print("[ssot-claim-gate] OK — no document claims knowledge is derived from glossary "
          f"({len(SCAN)} root(s) scanned; retractions that quote the old wording are allowed).")
    return 0


def selftest() -> int:
    fails = []

    def c(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("ssot-claim-gate · selftest")
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        bad = os.path.join(d, "bad.md")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("**knowledge-service** = derived fuzzy/semantic layer anchored to glossary.\n")
        c("the claim is caught", offenders([bad]) != [])

        # 🔴 The half that keeps this usable: SCOPE-3 and AGENTS.md both QUOTE the retired
        # wording in order to retract it. A gate that failed on those would have to be
        # disabled the day it shipped, which is how gates die.
        ok = os.path.join(d, "ok.md")
        with open(ok, "w", encoding="utf-8") as fh:
            fh.write('This read "knowledge-service = derived fuzzy/semantic layer" until '
                     "2026-08-14; it is NOT a derived layer.\n")
        c("a RETRACTION quoting the old wording is allowed", offenders([ok]) == [])

        neutral = os.path.join(d, "n.md")
        with open(neutral, "w", encoding="utf-8") as fh:
            fh.write("knowledge-service holds the extracted, story-positioned graph.\n")
        c("correct prose is not flagged", offenders([neutral]) == [])

    c("the REAL docs are clean today", offenders(SCAN) == [], str(offenders(SCAN)))

    print("\n  all checks passed" if not fails else f"\n  {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
