#!/usr/bin/env python3
"""Which conclusions do NOT rest on this loop's own evidence? Derived, never typed.

    python scripts/toolloop/stale_conclusions.py
    python scripts/toolloop/stale_conclusions.py --since 2026-08-22   # only files newer than this

🔴 WHY THIS EXISTS. `problem_remaining.py` reports every tool in a final state and it is right — 65
of 65 read `proven` or `blocked`. That number is true of the ledger's `state` field and says nothing
about WHEN the state was decided. Five tools were carried straight through the resolution loop on
conclusions drawn by the PREDECESSOR loop, two of them with no `evidence_file` at all, and the
per-cycle counter could not tell the difference. It reported all-final while a third of the
still-blocked tools had never been re-measured.

That is the same defect this loop opened with, one level up: a progress number that agrees with
itself. `recompute_progress` fixed it for the COUNTS; nothing was checking the counts' PROVENANCE.

WHAT IT READS, and both are the contracts rather than my memory:
  * the ledger's per-tool `state` and `evidence_file`
  * the mtime of the evidence file each tool points at

A conclusion is STALE when its evidence file is missing, empty, or older than the loop's own
re-measurement. It is not an error — a stale conclusion may still be correct — but it must be
VISIBLE, because "every tool is final" and "every tool was measured" are different claims and only
one of them is being made.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"

#: The resolution loop started here. A conclusion resting on evidence older than this was drawn by
#: the predecessor loop, whatever its state field says.
DEFAULT_SINCE = "2026-08-22"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=DEFAULT_SINCE,
                    help=f"evidence older than this date is stale (default {DEFAULT_SINCE})")
    a = ap.parse_args()
    cutoff = _dt.datetime.fromisoformat(a.since).timestamp()

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))["tools"]
    probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    owner = {t: p["id"] for p in probs["problems"] for t in p["tools"]}

    fresh, stale, missing = [], [], []
    for tool, pid in sorted(owner.items()):
        row = ledger.get(tool) or {}
        state = row.get("state")
        if state not in ("proven", "blocked"):
            continue
        ev = (row.get("evidence_file") or "").strip()
        if not ev:
            missing.append((pid, tool, state, "no evidence_file at all"))
            continue
        p = ROOT / ev
        if not p.exists():
            missing.append((pid, tool, state, f"evidence file not on disk: {ev}"))
            continue
        (fresh if p.stat().st_mtime >= cutoff else stale).append(
            (pid, tool, state, pathlib.Path(ev).name))

    total = len(fresh) + len(stale) + len(missing)
    print(f"conclusions in the denominator: {total}")
    print(f"  resting on THIS loop's evidence (>= {a.since}): {len(fresh)}")
    print(f"  resting on OLDER evidence:                      {len(stale)}")
    print(f"  with no usable evidence file:                   {len(missing)}\n")

    for label, rows in (("NO USABLE EVIDENCE", missing), ("OLDER EVIDENCE", stale)):
        if not rows:
            continue
        print(f"{label}:")
        for pid, tool, state, why in rows:
            print(f"  {pid:22} {tool:32} {state:8} {why}")
        print()

    if stale or missing:
        print("A stale conclusion is NOT an error — it may still be correct. It is a claim about")
        print("behaviour that was never re-measured, and 'every tool is final' does not mean")
        print("'every tool was measured'. Only one of those is being asserted by the counter.")
    else:
        print("Every conclusion rests on this loop's own evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
