#!/usr/bin/env python3
"""discharged-deferral-gate — an OPEN deferral filed under a row the plan has TICKED.

Found by the 2026-08-24 run-state audit, four live instances, and three of them are
contradicted by a number their own gate prints on EVERY run:

    D-AGE-DEFAULT-SPLITS-THE-GRAPH-UNTIL-CLASS-D-MOVES   T54 [x]
        says class (d) 34 must move before AGE can be default.
        `port-adoption-gate` prints: class (d) 32 — NOT an engine blocker since T54c.
        T54c's own heading is "the two-store split is closed".
    D-T42D-GRAPHSTORE-HAS-NO-CALLERS                     T42d [x]
        says zero adopters, 71 binders, floor 11.   Today: 21 adopters, 53 binders.
    D-T25-INDEX-RETIREMENT-BLOCKED-BY-TWO-LIVE-READERS   T46 [x]
        says `vector bypass 4/4 — 2 LIVE readers`.  Today: `bypass 2/2 — no LIVE reader left`.
    D-T42A-PORT-CANNOT-CLOSE-AN-INTERVAL                 T42a [x]
        accepted forever by spec §9.3 — and still wearing an OPEN marker.

WHY THIS IS NOT `stale-deferral-gate`
─────────────────────────────────────
That gate fires when a deferral's own `Retry when` field says it is closed. None of these
four says that. They say *"retry when class (d) moves"*, *"when the floor rises"*, *"when
the two live readers go"* — conditions that CAME TRUE while the prose sat still. The
mechanism each one installed works perfectly: the number is printed on every commit. What
is missing is anything that closes the deferral when the number crosses. **Gates ratchet;
deferrals do not.**

THE RULE, AND WHY IT IS STRUCTURAL RATHER THAN SEMANTIC
───────────────────────────────────────────────────────
Reading each deferral's cited metric and comparing it to its gate's live reading is the
check you would want, and it is not writable: the citations are prose, in four different
shapes, naming numbers that four different gates format four different ways. A gate that
tried would be a keyword heuristic, which is the thing `stale-deferral-gate`'s docstring
already records as measured-unreliable.

So this one asks a question with a yes/no answer:

    a deferral heading that advertises OPEN must not sit inside a row marked `[x]`.

A deferral is an OBLIGATION. The plan is a journal, so a row's span legitimately carries
other rows' evidence — but an obligation filed under a finished row is unfindable, which
is precisely how these four survived. Three fixes are available and all are honest:

    strike it        `~~DEFERRAL~~` + the measurement that discharged it   (the usual one)
    mark it ACCEPTED a permanent limitation, and it must cite the § that accepted it
    move it          under the OPEN row it actually belongs to

⚠️ **The ACCEPTED escape hatch must itself be falsifiable (rule 3).** A bare `ACCEPTED` in
a heading would be a magic word that silences any finding, so it is only honoured when the
heading also carries a `§` citation. Selftest case 7 is that control: `ACCEPTED` with no
section is still reported.

Usage
    python scripts/discharged-deferral-gate.py                 # scan the tracked plans
    python scripts/discharged-deferral-gate.py --file PATH ...
    python scripts/discharged-deferral-gate.py --selftest      # offline, no repo needed
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import os
import re
import sys

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "plan_location", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "plan_location.py"))
_pl = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_pl)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GLOBS = ("docs/plans/*.md",)

#: A plan row and its checkbox. Same shape `plan-progress-block` and `goal-prompt` read, so
#: the three cannot disagree about what a row is.
# `re.MULTILINE` because the selftest's live-plan arm reads the WHOLE file with
# `findall`, while `findings` matches line by line. Without it the whole-file read
# returned 0 rows and every fixture case above stayed green — the arm caught it.
ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*", re.MULTILINE)

#: An OPEN deferral heading. `(?!~~)` rejects a leading strike; `DEFERRAL\s+` rejects the
#: trailing one, because `DEFERRAL~~ ` has no whitespace before the backtick. Both forms are
#: in use in this repo and bite 78 (recorded in `stale-deferral-gate`) is why both are here.
OPEN_HEADING = re.compile(
    r"^\s*#{2,4}\s+(?!~~)(?:[^\w\s]*\s*)?DEFERRAL\s+`(D-[A-Z0-9-]+)`")

#: The permanent-limitation escape, and the citation that keeps it from being a magic word.
ACCEPTED = re.compile(r"\bACCEPTED\b")
SECTION = re.compile(r"§\s*\d")


def _owner_of():
    """`plan-progress-block.owner_of`, imported rather than reimplemented.

    The attribution rule is already audited and selftested there. A second copy is the
    "one home" violation this repo keeps finding, and the two would disagree the first
    time either moved — which is the defect that credited T39 with 16/24 blocks it did
    not own.
    """
    path = os.path.join(ROOT, "scripts", "plan-progress-block.py")
    spec = importlib.util.spec_from_file_location("_ppb_dd", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.owner_of


def findings(text: str, owner_of=None) -> list[tuple[str, str, int]]:
    """`[(deferral id, owning row, line number)]` for every open deferral under a `[x]` row.

    Ownership is POSITIONAL on purpose, and that is the one place this gate departs from
    `owner_of`'s preference for an explicit name. `D-T25-INDEX-RETIREMENT-…` names T25,
    which is open — reading the name would excuse it. But the block physically sits inside
    T46's closed span, which is what made it unfindable. **Where an obligation is FILED is
    the fact this gate is about.**
    """
    lines = text.split("\n")
    state: dict[str, str] = {}
    at: dict[int, str] = {}
    for n, line in enumerate(lines):
        m = ROW_RE.match(line)
        if m:
            state[m.group(2)] = m.group(1)
            at[n] = m.group(2)

    out: list[tuple[str, str, int]] = []
    current: str | None = None
    for n, line in enumerate(lines):
        if n in at:
            current = at[n]
            continue
        m = OPEN_HEADING.match(line)
        if not m or current is None:
            continue
        if state.get(current) != "x":
            continue
        if ACCEPTED.search(line) and SECTION.search(line):
            continue
        out.append((m.group(1), current, n + 1))
    return out


def _selftest() -> int:
    """Every arm, including the controls that stop this from reporting everything."""
    cases: list[tuple[str, str, list[str]]] = [
        ("an OPEN deferral under a TICKED row is reported",
         "- [x] **T54** — done\n### 🔻 DEFERRAL `D-AGE-SPLITS`\n", ["D-AGE-SPLITS"]),
        ("...and the SAME block under an OPEN row is not — that is a deferral doing its job",
         "- [~] **T25** — open\n### 🔻 DEFERRAL `D-AGE-SPLITS`\n", []),
        ("a STRUCK heading under a ticked row is not reported",
         "- [x] **T54** — done\n### ~~DEFERRAL~~ `D-AGE-SPLITS` — discharged\n", []),
        ("...nor the other strike form this repo uses",
         "- [x] **T54** — done\n### ~~🔻 DEFERRAL `D-AGE-SPLITS`~~ — discharged\n", []),
        ("prose that merely MENTIONS a deferral is not a heading",
         "- [x] **T54** — done\nthis DEFERRAL `D-AGE-SPLITS` was discharged by T54c\n", []),
        ("ACCEPTED with a § citation is the permanent-limitation escape",
         "- [x] **T42a** — done\n### 🔻 DEFERRAL `D-INTERVAL` — ACCEPTED, §9.3\n", []),
        ("...but bare ACCEPTED with NO section is still reported — else it is a magic word",
         "- [x] **T42a** — done\n### 🔻 DEFERRAL `D-INTERVAL` — ACCEPTED\n", ["D-INTERVAL"]),
        ("a deferral BEFORE any row belongs to no row and is not guessed at",
         "### 🔻 DEFERRAL `D-EARLY`\n- [x] **T54** — done\n", []),
        ("ownership is POSITIONAL: an id naming an OPEN row does not excuse the filing",
         "- [~] **T25** — open\n- [x] **T46** — done\n### 🔻 DEFERRAL `D-T25-INDEX`\n",
         ["D-T25-INDEX"]),
        ("two open deferrals under one ticked row are both reported",
         "- [x] **T54** — done\n### 🔻 DEFERRAL `D-ONE`\n### 🔻 DEFERRAL `D-TWO`\n",
         ["D-ONE", "D-TWO"]),
        ("a row that is neither [x] nor [~] (untouched) is not treated as closed",
         "- [ ] **T99** — untouched\n### 🔻 DEFERRAL `D-LATER`\n", []),
    ]
    failures = 0
    print("discharged-deferral-gate - selftest (offline)")
    for label, doc, want in cases:
        got = [d for d, _row, _n in findings(doc)]
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {got}")

    # The gate must be able to see the real plan, or every reading above is about fixtures.
    plan = _pl.plan_path()   # live or archived - see plan_location.py
    if os.path.exists(plan):
        with open(plan, encoding="utf-8") as fh:
            rows = len(ROW_RE.findall(fh.read()))
        ok = rows >= 50
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  the real plan still parses ({rows} row(s))")

    print("\n  all checks passed" if not failures else f"\n  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--file", action="append", default=[])
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    paths = args.file or sorted(
        p for pat in DEFAULT_GLOBS for p in glob.glob(os.path.join(ROOT, pat)))
    owner_of = _owner_of()  # imported for the one-home assertion; ownership here is positional
    assert callable(owner_of)

    total = 0
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            hits = findings(fh.read())
        for did, row, line in hits:
            total += 1
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            print(f"discharged-deferral-gate: {rel}:{line}  `{did}` is OPEN inside `{row}`, "
                  f"which is ticked [x]")
    if total:
        print(f"\ndischarged-deferral-gate: FAIL — {total} obligation(s) filed under a row the "
              f"plan says is finished.\n"
              f"  Strike it with the measurement that discharged it, mark it ACCEPTED with the "
              f"§ that accepted it,\n  or move it under the OPEN row it belongs to. A deferral "
              f"nobody can find is how a settled question reads as live.")
        return 1
    print(f"discharged-deferral-gate: OK — {len(paths)} plan(s) scanned, no open deferral "
          f"filed under a ticked row.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
