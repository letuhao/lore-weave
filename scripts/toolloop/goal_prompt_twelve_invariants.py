#!/usr/bin/env python
"""Emit the /goal condition for the twelve open invariants, with the QUEUE derived.

🔴 WHY A GENERATOR AND NOT A TYPED LIST. The predecessor's goal held its resume pointer at T17
for ten consecutive batches because the item was typed and the work had finished. A queue that
cannot notice its own completion sends every session at the same finished thing. So the twelve
are read from `contracts/tool-resolution-problems.json` at emit time, filtered by the SAME
`_definition_complete` the stop-gate uses -- one definition, one home. A problem that closes
leaves this queue by itself.

The ORDER is the ledger's own `cycle`, which is damage-ordered (false statements to the author
first). It is not re-sorted here: a second ordering rule would be a second answer to a question
the ledger already answers.

Usage:
    python scripts/toolloop/goal_prompt_twelve_invariants.py           # emit
    python scripts/toolloop/goal_prompt_twelve_invariants.py --check   # budget + queue sanity
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"
BUDGET = 4000


def _stopgate():
    """The stop-gate module, imported by path so its definition is the only one."""
    spec = importlib.util.spec_from_file_location(
        "problem_remaining", pathlib.Path(__file__).with_name("problem_remaining.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def open_problems() -> list[dict]:
    """Every problem whose tools all read proven and which still fails the CLEARED definition."""
    gate = _stopgate()
    rows = json.loads(PROBLEMS.read_text(encoding="utf-8"))["problems"]
    out = []
    for p in sorted(rows, key=lambda r: r["cycle"]):
        ok, why = gate._definition_complete(p)
        if ok:
            continue
        out.append({"id": p["id"], "cycle": p["cycle"], "tools": len(p.get("tools", [])),
                    "why": re.sub(r"\s+", " ", why)[:80],
                    "invariant": re.sub(r"\s+", " ", p.get("invariant_candidate", ""))})
    return out


def render(rows: list[dict]) -> str:
    q = "\n".join(f"{r['cycle']}. {r['id']} ({r['tools']}t) — {r['why']}" for r in rows)
    return f"""/goal OBJECTIVE — every one of the {len(rows)} problems below has its invariant ENFORCED at one chokepoint, not merely diagnosed. Done = `cd scripts/toolloop && python problem_remaining.py` exits 0, which requires each problem's status to begin CLEARED and to carry a `cleared_note` saying what its fix does NOT cover.

UNIT — ONE problem. Not one tool: every tool already reads proven, and no tool run can close any of these.

METHOD — per problem: (1) state the invariant in one sentence; (2) find the ONE chokepoint where violating it becomes impossible — if there are two, you have two invariants; (3) build it; (4) write the `cleared_note` FIRST, before declaring it done, because naming what the fix does not cover is what stops the next reader over-reading it.

Do NOT re-ask a DQ. DQ-T31/T32/T33/T35/T36/T41 are ANSWERED; statuses naming them as blockers are stale. Build the ruling AS WORDED — if it cannot be built, come back with the measurement showing why, never a substituted mechanism.
P15: chase the residual in LM Studio's logs (on since ~2026-09-01) before accepting a noise floor.
EMPTY IS NOT CLEARED: P6/P11/P16 emptied by re-attribution still need enforcement — an unenforced invariant can recur silently.

EVIDENCE — a falsifier proven RED on an ORIGINAL instance, then green; the WHOLE owning suite green, never a subset; a real run through the real path where the invariant is observable. A guard that has never been seen failing is not a guard. Record a refuted attempt as refuted — four of P5's fix hypotheses were measured and refuted, and that record is why nobody retried them.

STOP — `problem_remaining.py` exits 0 AND a report naming, per problem, the invariant, its chokepoint, and its falsifier. NEVER: delete a historical field to satisfy a checker (fix the checker); mark CLEARED without a `cleared_note`; relocate a tool to empty a problem; quote a tool count as if it were an invariant count.

QUEUE — derived by scripts/toolloop/goal_prompt_twelve_invariants.py, in the ledger's damage order:
{q}

NEXT — cycle {rows[0]['cycle']}: {rows[0]['id']}."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    rows = open_problems()
    if not rows:
        print("QUEUE IS EMPTY — problem_remaining.py should exit 0. Do not emit a goal.")
        return 1
    text = render(rows)
    if a.check:
        print(f"open problems : {len(rows)}")
        print(f"characters    : {len(text)} / {BUDGET}")
        if len(text) > BUDGET:
            print(f"OVER BUDGET by {len(text) - BUDGET} — shorten the SOURCE, never cut upward "
                  "from the bottom: QUEUE is last so it absorbs the loss, but STOP must survive.")
            return 1
        print("within budget; every open problem is in the queue")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
