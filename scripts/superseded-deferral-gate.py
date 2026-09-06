#!/usr/bin/env python3
"""superseded-deferral-gate — a spec says a deferral is replaced; the plan still lists it as open.

Two documents own two halves of one fact. A deferral is OPEN because a plan heading says so; it
is CLOSED because a spec section says `*Replaces `D-…`*`. Nothing joined them, and
`plan-final-verification` decides "this section records a deferral" on the HEADING — so a spec
could retire a deferral and the plan would keep blocking a finished row forever.

Measured 2026-08-21: 29 deferrals declared replaced by a spec, **16 still unstruck**.

WHY THIS IS NOT "STRIKE EVERY HEADING WITH A REPLACES LINE". Four of the sixteen were
mis-citations. §3.1 claims to replace `D-T42D-GRAPHSTORE-HAS-NO-CALLERS`; §3.1 wires
`VectorStore` and the deferral is about `GraphStore`. §1.1 claims
`D-T42A-PORT-CANNOT-CLOSE-AN-INTERVAL` while growing a fact READ against a deferral about the
WRITE path. A blanket rule would have closed four live rows and read as tidying up. So a
`Replaces` line is treated as a CLAIM, and every claim is adjudicated by hand in

    docs/specs/2026-08-21-deferral-supersession-ledger.md

The gate enforces the adjudication, it does not perform it: an un-adjudicated pair FAILS, and a
pair adjudicated `SUPERSEDED` whose plan heading is still unstruck FAILS with the strike to make.
`MIS-CITED`, `OPEN` and `PARTIAL` are recorded reasons to leave a heading alone — this gate is
why those four rows survive a future sweep.

Usage
    python scripts/superseded-deferral-gate.py
    python scripts/superseded-deferral-gate.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN_GLOB = "docs/plans/*.md"
SPEC_GLOB = "docs/specs/*.md"
LEDGER = "docs/specs/2026-08-21-deferral-supersession-ledger.md"

_DEFERRAL = re.compile(r"`(D-[A-Z0-9-]+)`")
#: The plan's OPEN-heading shape. Both exclusions are load-bearing; see stale-deferral-gate.
_OPEN_HEADING = re.compile(r"^\s*#{2,4}\s+(?!~~)(?:[^\w\s]*\s*)?DEFERRAL\s+`(D-[A-Z0-9-]+)`")
#: A spec's supersession claim. Deliberately loose on surrounding punctuation (`*Replaces …*`,
#: `_Replaces …_`, a bare sentence) because the repo already writes it three ways.
_REPLACES = re.compile(r"\breplaces\b", re.IGNORECASE)
#: A ledger row: | `D-X` | VERDICT | … |
_LEDGER_ROW = re.compile(r"^\s*\|\s*`(D-[A-Z0-9-]+)`\s*\|\s*([A-Z-]+)\s*\|")

VERDICTS = {"SUPERSEDED", "MIS-CITED", "PARTIAL", "OPEN"}
#: The STRUCK form. Needed because one id can appear BOTH ways in one file, and that is not
#: hypothetical: `D-QC5-ATTRIBUTION-CHANNEL-UNWIRED` sat struck-and-closed at plan line 7100
#: and open at 7159 for eight days. Every reader who searched the id found whichever came
#: first. That duplicate is what made a settled question look open and stopped a run on a
#: decision nobody owed -- the single most expensive documentation defect this plan has hit.
_STRUCK_HEADING = re.compile(r"^\s*#{2,4}\s+~~DEFERRAL~~\s+`(D-[A-Z0-9-]+)`")

#: The only verdict that demands an edit. The other three are reasons to leave a heading open.
_DEMANDS_STRIKE = "SUPERSEDED"


def claims(spec_text: str) -> set[str]:
    """Deferral ids a spec declares replaced. Only ids on a line that says `replaces`."""
    out: set[str] = set()
    for line in spec_text.splitlines():
        if _REPLACES.search(line):
            out.update(_DEFERRAL.findall(line))
    return out


def open_headings(plan_text: str) -> set[str]:
    return {m.group(1) for line in plan_text.splitlines() if (m := _OPEN_HEADING.match(line))}


def struck_headings(plan_text: str) -> set[str]:
    return {m.group(1) for line in plan_text.splitlines() if (m := _STRUCK_HEADING.match(line))}


def contradictions(plan_text: str) -> list[str]:
    """Ids this file states twice, in opposite states. One id, one state."""
    return sorted(open_headings(plan_text) & struck_headings(plan_text))

def ledger_verdicts(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for line in text.splitlines() if (m := _LEDGER_ROW.match(line))}


def adjudicate(claimed: set[str], still_open: set[str], verdicts: dict[str, str]):
    """Return (unadjudicated, must_strike, bad_verdict) — the three failure shapes."""
    pairs = claimed & still_open
    unadjudicated = sorted(p for p in pairs if p not in verdicts)
    must_strike = sorted(p for p in pairs if verdicts.get(p) == _DEMANDS_STRIKE)
    bad_verdict = sorted(p for p in pairs if p in verdicts and verdicts[p] not in VERDICTS)
    return unadjudicated, must_strike, bad_verdict


_SYNTHETIC = [
    # (name, claimed, still_open, verdicts, expect_ok)
    ("an unstruck heading a spec claims to replace, with no ledger row",
     {"D-A"}, {"D-A"}, {}, False),
    ("the same pair, adjudicated SUPERSEDED but never struck",
     {"D-A"}, {"D-A"}, {"D-A": "SUPERSEDED"}, False),
    ("adjudicated SUPERSEDED and the heading IS struck",
     {"D-A"}, set(), {"D-A": "SUPERSEDED"}, True),
    # THE DISCRIMINATING CASE — the one a blanket "strike it" rule gets wrong. `D-T42D` is
    # claimed by a section about a DIFFERENT port; the heading must survive, and the gate must
    # be satisfied by the recorded reason rather than by an edit.
    ("a MIS-CITED claim leaves the heading open and still passes",
     {"D-A"}, {"D-A"}, {"D-A": "MIS-CITED"}, True),
    ("PARTIAL likewise — half closed, a named residue open",
     {"D-A"}, {"D-A"}, {"D-A": "PARTIAL"}, True),
    ("OPEN likewise — the spec was policy, not closure",
     {"D-A"}, {"D-A"}, {"D-A": "OPEN"}, True),
    ("a typo'd verdict is not silently treated as adjudicated",
     {"D-A"}, {"D-A"}, {"D-A": "SUPERCEDED"}, False),
    ("an open deferral no spec mentions is none of this gate's business",
     set(), {"D-B"}, {}, True),
    ("a claim whose heading was never in any plan is not invented",
     {"D-C"}, set(), {}, True),
]


def selftest() -> int:
    print("superseded-deferral-gate - selftest (offline)")
    bad = 0
    for name, claimed, still_open, verdicts, want_ok in _SYNTHETIC:
        u, s, b = adjudicate(claimed, still_open, verdicts)
        ok = (not u and not s and not b) == want_ok
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    # The property no fixture states: SUPERSEDED and MIS-CITED must DISAGREE on the same pair.
    # If they ever agree the verdict column has stopped being read, and the gate either demands
    # a strike on every mis-citation or accepts every stale heading.
    sup = adjudicate({"D-A"}, {"D-A"}, {"D-A": "SUPERSEDED"})
    mis = adjudicate({"D-A"}, {"D-A"}, {"D-A": "MIS-CITED"})
    ok = bool(sup[1]) and not mis[1]
    bad += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  SUPERSEDED demands a strike where MIS-CITED does not")
    # The duplicate-state check, on the exact shape that cost this plan eight days.
    dup = ("### ~~DEFERRAL~~ `D-A` — closed" + chr(10) + "### 🔻 DEFERRAL `D-A`" + chr(10))
    one = ("### ~~DEFERRAL~~ `D-A` — closed" + chr(10) + "### 🔻 DEFERRAL `D-B`" + chr(10))
    ok = contradictions(dup) == ["D-A"] and contradictions(one) == []
    bad += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  an id that is both struck and open is a contradiction")
    # And the ledger the live scan depends on must actually parse — an unreadable ledger would
    # make every pair 'unadjudicated' and the gate would fail for the wrong reason.
    path = os.path.join(ROOT, LEDGER)
    parsed = ledger_verdicts(open(path, encoding="utf-8").read()) if os.path.exists(path) else {}
    ok = len(parsed) >= 1 and set(parsed.values()) <= VERDICTS
    bad += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  the real ledger parses ({len(parsed)} row(s))")
    print("\n  all checks passed" if not bad else f"\n  {bad} check(s) FAILED")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        return selftest()

    def _read(p):
        return open(p, encoding="utf-8", errors="replace").read()

    claimed: set[str] = set()
    for p in glob.glob(os.path.join(ROOT, SPEC_GLOB)):
        if os.path.basename(p) == os.path.basename(LEDGER):
            continue                      # the ledger QUOTES ids; it does not claim them
        claimed |= claims(_read(p))
    contra: list[tuple[str, str]] = []
    still_open: set[str] = set()
    for p in glob.glob(os.path.join(ROOT, PLAN_GLOB)):
        plan_text = _read(p)
        still_open |= open_headings(plan_text)
        contra += [(os.path.relpath(p, ROOT).replace("\\", "/"), d)
                   for d in contradictions(plan_text)]
    ledger_path = os.path.join(ROOT, LEDGER)
    verdicts = ledger_verdicts(_read(ledger_path)) if os.path.exists(ledger_path) else {}

    u, s, b = adjudicate(claimed, still_open, verdicts)
    for d in u:
        print(f"superseded-deferral-gate: `{d}` — a spec says it is replaced, the plan still "
              f"lists it as OPEN, and no ledger row says which document is wrong.")
    for d in s:
        print(f"superseded-deferral-gate: `{d}` — adjudicated SUPERSEDED but its plan heading "
              f"is still unstruck. Strike it: ### ~~DEFERRAL~~ `{d}`")
    for d in b:
        print(f"superseded-deferral-gate: `{d}` — ledger verdict {verdicts[d]!r} is not one of "
              f"{sorted(VERDICTS)}.")
    for rel, d in contra:
        print(f"superseded-deferral-gate: {rel}: `{d}` appears BOTH struck and open in the same "
              f"file. One id, one state -- strike the live one or give the residue its own id.")
    if u or s or b or contra:
        print(f"\nsuperseded-deferral-gate: FAIL — {len(u) + len(s) + len(b) + len(contra)} unresolved. "
              f"Adjudicate in {LEDGER}.")
        return 1
    print(f"superseded-deferral-gate: OK — {len(claimed)} supersession claim(s), "
          f"{len(claimed & still_open)} still-open pair(s), all adjudicated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
