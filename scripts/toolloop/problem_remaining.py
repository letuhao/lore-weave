#!/usr/bin/env python3
"""Derive the resolution loop's runstate from the two contracts. Nothing here is typed.

    python scripts/toolloop/problem_remaining.py            # the headline + the next cycle
    python scripts/toolloop/problem_remaining.py --verbose  # every problem, every tool

The predecessor loop learned this the expensive way: a hand-typed progress number always drifts
toward what was true when someone last remembered to edit it. `contracts/tool-deep-dive-ledger.json`
carried `concluded_in_release_surface: 40` for twenty-four batches while its own rows held 198.

So the ONLY inputs are:
  * contracts/tool-resolution-problems.json  — the frozen problem -> tools partition
  * contracts/tool-deep-dive-ledger.json     — the per-tool state, written by gate.py conclude

and the cycle ORDER is recomputed from the ordering rule on every run rather than read from the
`cycle` field. If the file's stored cycle numbers disagree with the rule, this script says so and
exits non-zero: a denominator you can reorder by editing is not a denominator.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"


def order_key(p: dict) -> tuple:
    """The ordering rule, in code. (a) false statements desc, (b) tools desc, (c) id asc."""
    return (-len(p["false_statement_tools"]), -len(p["tools"]), p["id"])


def load() -> tuple[dict, dict]:
    if not PROBLEMS.exists():
        sys.exit(f"missing: {PROBLEMS}")
    if not LEDGER.exists():
        sys.exit(f"missing: {LEDGER}")
    probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    return probs, ledger


def state_of(ledger: dict, tool: str) -> str:
    row = ledger["tools"].get(tool)
    if row is None:
        return "MISSING"
    if row.get("counts_toward_release") is False:
        return "EXCLUDED"
    return row.get("state") or "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="every problem and every tool")
    a = ap.parse_args()

    probs, ledger = load()
    ordered = sorted(probs["problems"], key=order_key)

    # The stored cycle numbers must be the rule's output, not someone's preference.
    stored = [p["id"] for p in sorted(probs["problems"], key=lambda p: p["cycle"])]
    computed = [p["id"] for p in ordered]
    if stored != computed:
        print("ORDERING DRIFT — the stored `cycle` numbers are not what the ordering rule produces.")
        print(f"  stored:   {', '.join(stored)}")
        print(f"  computed: {', '.join(computed)}")
        print("Fix the file, not this script.")
        return 2

    rows = []
    for i, p in enumerate(ordered, 1):
        states = [state_of(ledger, t) for t in p["tools"]]
        done = sum(1 for s in states if s == "proven")
        rows.append((i, p, states, done))

    cleared = [r for r in rows if r[3] == len(r[1]["tools"])]
    blocked_tools = sum(len(p["tools"]) for p in probs["problems"])
    proven_tools = sum(r[3] for r in rows)

    print(
        f"problems={len(rows)} cleared={len(cleared)} remaining={len(rows) - len(cleared)}  |  "
        f"tools_in_denominator={blocked_tools} proven={proven_tools} "
        f"still_blocked={blocked_tools - proven_tools}"
    )
    print()

    for i, p, states, done in rows:
        n = len(p["tools"])
        mark = "CLEARED" if done == n else f"{done}/{n}"
        fs = len(p["false_statement_tools"])
        fs_note = f"  [{fs} tool(s) made a FALSE STATEMENT to the author]" if fs else ""
        print(f"  C{i:<3} {p['id']:<24} {mark:>8}  {p['title']}{fs_note}")
        if a.verbose:
            for t, s in sorted(zip(p["tools"], states)):
                print(f"          {s:<9} {t}")
            print()

    nxt = next((r for r in rows if r[3] < len(r[1]["tools"])), None)
    print()
    if nxt is None:
        print("No problem remains — every tool in the denominator reads `proven`.")
        print("Stopping is legitimate. Check the DQ backlog before you do:")
        for k in probs["deferred_questions_backlog"]["registered_open"]:
            print(f"  open {k}")
        return 0

    i, p, states, done = nxt
    print(f"NEXT — cycle {i}: {p['id']} — {p['title']}")
    print(f"  invariant candidate: {p['invariant_candidate']}")
    if p.get("status"):
        print(f"  status: {p['status']}")
    outstanding = [t for t, s in zip(p["tools"], states) if s != "proven"]
    print(f"  {len(outstanding)} tool(s) to clear: {', '.join(sorted(outstanding))}")
    print()
    print("  A problem is CLEARED only when:")
    for line in probs["cleared_definition"].split(". ("):
        print(f"    {line.strip().rstrip('.')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
