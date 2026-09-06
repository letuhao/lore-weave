#!/usr/bin/env python3
"""The denominator for a "it did not reproduce" claim: runs that COULD have shown the trigger.

    python scripts/toolloop/trigger_denominator.py --since 2026-08-28 \
        --tools composition_arc_get,glossary_curation_list,jobs_get,jobs_list

🔴 WHY THIS EXISTS, and it is a mistake I made TWICE IN ONE DAY rather than a hypothetical.

When a defect stops reproducing, the tempting move is to pool every run you happen to have into
its rate. Both of this loop's long-running "needs a live catch" rows got that treatment on
2026-08-30, and both figures were wrong in the same direction:

    D-THE-PERSISTED-PER-PASS-RECORDER…   reported 270 runs, 0 gaps -> "1 in 295"
        the defect is named for the SECOND turn; 197 of those runs were single-turn.
        the trigger-matched population was 15.                        (~18x overstated)

    D-SILENT-TURN-NO-CARD-NO-PROSE       reported 285 runs, 0 -> "9 in 1,148"
        22 of those runs called ANY of the row's 8 trigger tools, and SIX of the eight
        were never called at all.                                     (~13x overstated)

Both notes even carried a prose caveat that the runs "were not chosen to provoke it" — and then
quoted the pooled figure anyway. The caveat is not the fix; the denominator is. A zero over a
population that lacks the trigger measures the POPULATION, not the defect.

THE LEDGER WAS SWEPT FOR OTHERS (2026-08-30) and came back clean: of ten rows pairing a
three-figure run count with a zero finding, eight were already stratified by trigger or were
sentinel sweeps rather than rate claims. The near-miss is worth naming as the POSITIVE example —
D-CLAIMS-DONE-WHILE-ITS-OWN-CARD-IS-STILL-PENDING derives its rate over the 98 runs that ended
with a card pending and a reply, out of 1,516 on disk, and it records a superseded earlier pass
that used the wrong denominator (507) and thereby UNDERSTATED the defect five-fold. Dilution cuts
both ways; the fix is the same one.

WHAT THIS DOES NOT DO. It does not decide whether a trigger list is right. `trigger_tools` is a
claim about the defect that a human makes and that this file takes on faith — see
`unexercised` in the output, which names the trigger tools no run touched, because a denominator
that silently covers two of eight families is the failure this exists to make visible.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
EVAL_GLOB = "docs/eval/toolloop/**/*-raw.json"


def load_runs(since: str) -> list[dict]:
    """Every recorded run from a raw batch file modified on/after `since` (YYYY-MM-DD).

    Dated by FILE MTIME, which is what the ad-hoc scans used and is therefore what reproduces
    their numbers. It is a coarse clock: a file rewritten later moves, and a checkout resets every
    mtime. That is stated rather than hidden — this answers "runs I have on disk from around
    then", not "runs executed on that date", and the two differ.
    """
    out = []
    for f in glob.glob(str(ROOT / EVAL_GLOB), recursive=True):
        p = pathlib.Path(f)
        if _dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d") < since:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.extend(d if isinstance(d, list) else d.get("runs", []))
    return out


def called_tools(run: dict) -> set[str]:
    """Tools this run actually put ON THE WIRE.

    Deliberately NOT `tool_under_test`: that is what the scenario INTENDED, and on the silent-turn
    census it was a trigger tool in 0 of 285 runs while 22 runs called one anyway. What the model
    chose is the thing that could have tripped the defect.
    """
    return {c.get("toolCallName") for c in run.get("tool_calls", [])
            if c.get("type") == "TOOL_CALL_START" and c.get("toolCallName")}


def trigger_matched(runs: list[dict], trigger_tools: set[str]) -> dict:
    """Split `runs` into the population that could have shown the trigger, and the rest."""
    matched, per = [], {}
    for r in runs:
        hit = called_tools(r) & trigger_tools
        if hit:
            matched.append(r)
            for h in hit:
                per[h] = per.get(h, 0) + 1
    return {
        "total": len(runs),
        "matched": len(matched),
        "per_tool": dict(sorted(per.items(), key=lambda kv: -kv[1])),
        "unexercised": sorted(trigger_tools - set(per)),
        "runs": matched,
    }


def format_report(res: dict, trigger_tools: set[str]) -> str:
    """The report deliberately leads with the RATIO, because the raw total is the misleading half."""
    lines = [
        f"runs on disk in the window          : {res['total']}",
        f"  that could have shown the trigger : {res['matched']}",
    ]
    for k, v in res["per_tool"].items():
        lines.append(f"      {k:32s} {v}")
    if res["unexercised"]:
        lines.append(
            f"  🔴 trigger tools NEVER exercised   : {len(res['unexercised'])} of "
            f"{len(trigger_tools)} — {', '.join(res['unexercised'])}"
        )
    if res["matched"] == 0:
        lines.append(
            "  🔴 THE DENOMINATOR IS ZERO. This window says NOTHING about the defect's rate. "
            "Do not quote a zero from it."
        )
    elif res["total"] and res["matched"] * 4 < res["total"]:
        lines.append(
            f"  🔴 the pooled total overstates the sample {res['total'] / res['matched']:.0f}x. "
            f"Quote {res['matched']}, not {res['total']}."
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="only raw files with mtime >= this (YYYY-MM-DD)")
    ap.add_argument("--tools", required=True, help="comma-separated trigger tools for the defect")
    a = ap.parse_args()
    tools = {t.strip() for t in a.tools.split(",") if t.strip()}
    if not tools:
        print("no trigger tools given — there is no denominator to compute", file=sys.stderr)
        return 2
    res = trigger_matched(load_runs(a.since), tools)
    print(format_report(res, tools))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
