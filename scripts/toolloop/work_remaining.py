#!/usr/bin/env python
"""Is there executable work left in the tool loop? Exit 1 if yes — so a STOP can be refused.

🔴 WHY THIS IS A SCRIPT AND NOT A SENTENCE IN THE GOAL. The goal already says "context is not a
stop condition", and that sentence did not hold — because a written rule is something I can
reason around ("this batch is large", "the window is nearly full", "better to hand off cleanly"),
and every one of those reads as prudence in the moment.

A stop is the one action that cannot be undone by the next turn, so it is the one that should have
to justify itself against evidence rather than against a feeling. This script is that evidence.
It answers ONE question from the ledger and the working tree, and it does not know or care how
much context remains:

    exit 0  -> every derived tool has a terminal conclusion; stopping is legitimate.
    exit 1  -> tools remain unconcluded, or the working tree has uncommitted loop work.

Wire it into a Stop hook. Then "I am running low on context" stops being a reason and becomes what
it actually is: an implementation detail of a conversation that the harness already summarises and
hands forward.

Usage:
    python scripts/toolloop/work_remaining.py         # human-readable
    python scripts/toolloop/work_remaining.py --quiet # exit code only
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
TERMINAL = ("proven", "blocked")


def _ledger_state() -> tuple[int, int, list[str]]:
    if not LEDGER.exists():
        return 0, 0, [], 0
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    tools = data.get("tools") or {}
    declared = (data.get("denominator") or {}).get("federated_tools") or 0
    # 🔴 THE DENOMINATOR IS THE RELEASE SURFACE, NOT THE CATALOGUE. Owner's decision 2026-08-14:
    # ship every NON-DEPRECATED tool, because they were built for the workflows and the platform
    # cannot release without them. A deprecated tool (visibility=legacy / superseded_by) is
    # abandoned after its migration, so counting it inflates the work AND the progress. Re-derived:
    # 315 federated, 117 deprecated, 198 shippable — the remaining count fell 280 -> 168 purely by
    # measuring the right set.
    in_surface = {n for n, t in tools.items() if t.get("counts_toward_release") is not False}
    concluded = [n for n in in_surface if tools[n].get("state") in TERMINAL]
    in_flight = [n for n in in_surface if tools[n].get("state") not in TERMINAL]
    # 🔴 REPORT THE SPLIT, NOT JUST THE COUNT. 30 of the first 35 conclusions were recorded before
    # the gate existed — one tool per cycle, as detailed LIVE/DATA/FALSIFIER prose in the ledger
    # row. That is real work and it is not being discarded, but nothing can RE-VERIFY it without
    # re-running the tool, and a single headline number quietly presents it as the same kind of
    # fact as a conclusion the gate can re-check on demand. Two different things should not share
    # one number.
    backed = [n for n in concluded if tools[n].get("evidence_class") == "gate-backed"]
    return declared, len(concluded), in_flight, len(backed)


def _uncommitted() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    declared, concluded, in_flight, backed = _ledger_state()
    dirty = _uncommitted()
    remaining = max(declared - concluded, 0)

    reasons = []
    if in_flight:
        reasons.append(f"{len(in_flight)} tool(s) touched but NOT terminally concluded: "
                       f"{', '.join(sorted(in_flight)[:5])}")
    if remaining:
        reasons.append(f"{remaining} of {declared} declared tools have no conclusion")
    if dirty:
        reasons.append(f"{len(dirty)} uncommitted file(s) — loop work that would be lost")

    if not a.quiet:
        print(f"declared={declared} concluded={concluded} "
              f"(gate-backed={backed}, pre-gate prose={concluded - backed}) "
              f"remaining={remaining} in_flight={len(in_flight)} dirty={len(dirty)}")
        for r in reasons:
            print(f"  - {r}")
        if reasons:
            print("\nWORK REMAINS. Context pressure is not a stop condition: the harness "
                  "summarises and hands the summary forward, so a compacted window continues the "
                  "task rather than ending it. Derive the next batch and continue.")
        else:
            print("\nNo executable work remains — stopping is legitimate.")
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
