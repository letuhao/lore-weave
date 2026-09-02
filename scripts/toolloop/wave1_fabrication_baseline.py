#!/usr/bin/env python3
"""DQ-T76 Wave 1's BAR — the fabricated-id rate on the arguments Wave 1 touched.

The plan (docs/specs/2026-09-02-remove-ids-from-the-model-surface.md §3) sets the bar:

    "fabricated-id rate, measured before and after on the same corpus. Not 'the tools now take
     names'." ... STRATIFIED BY ARGUMENT — a pooled rate across waves would measure which tools
     the batches happened to run, the error this loop has now made three times.

    "Wave 1 passes when `source_entity_id`'s fabrication rate falls AND its call volume does not
     ... A rate that falls because nobody called the tool is not a pass."

WHAT COUNTS AS A FABRICATION HERE, stated because the word has been over-claimed on this loop
before. NOT "the call failed" — that is an OUTCOME, and reading an outcome as a property is the
error that killed the UUID-version rule. Two things are counted separately:

  WRONG-FAMILY  the value is a well-formed UUID that the tool REJECTED as not a graph node
                (KG_ENDPOINT_NOT_NODE). This is the measured c-kgedge3 defect: on 3 of 3 calls
                the model passed GLOSSARY entity ids where NODE ids were required.
  MISSING       the argument was owed and absent.

And the DENOMINATOR is calls that passed the argument at all — not runs, not turns.

Usage:  python scripts/toolloop/wave1_fabrication_baseline.py [--since 2026-09-02]
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
WAVE1_ARGS = ("source_entity_id", "target_entity_id")
TOOL = "kg_propose_edge"
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def scan(since: str | None) -> dict:
    stat = collections.defaultdict(collections.Counter)
    batches = set()
    for path in sorted(glob.glob(str(ROOT / "docs" / "eval" / "toolloop" / "*" / "*-raw.json"))):
        day = pathlib.Path(path).parent.name
        if since and day < since:
            continue
        try:
            recs = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(recs, list):
            continue
        for r in recs:
            if not isinstance(r, dict):
                continue
            # DISTINCT toolCallId — these files emit TOOL_CALL_START twice per call.
            ids = {c.get("toolCallId"): c.get("toolCallName")
                   for c in (r.get("tool_calls") or [])
                   if isinstance(c, dict) and c.get("type") == "TOOL_CALL_START"
                   and c.get("toolCallId")}
            args_by_id = r.get("_args") or {}
            res_by_id = {x.get("id"): (x.get("content") or "")
                         for x in (r.get("results") or [])}
            for cid, tool in ids.items():
                if tool != TOOL:
                    continue
                batches.add(pathlib.Path(path).name)
                try:
                    a = json.loads(args_by_id.get(cid) or "{}")
                except Exception:
                    a = {}
                content = res_by_id.get(cid) or ""
                for arg in WAVE1_ARGS:
                    v = a.get(arg)
                    s = stat[arg]
                    if v is None:
                        s["missing"] += 1
                        s["calls"] += 1
                        continue
                    s["calls"] += 1
                    s["passed_a_value"] += 1
                    if isinstance(v, str) and UUID_RE.match(v):
                        s["uuid"] += 1
                        if "KG_ENDPOINT_NOT_NODE" in content:
                            s["wrong_family"] += 1
                    else:
                        s["non_uuid"] += 1
                # Wave 1's new form: did the caller use a NAME?
                for arg in ("source_name", "target_name"):
                    if a.get(arg):
                        stat[arg]["calls"] += 1
    return {"stat": stat, "batches": sorted(batches)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None,
                    help="only batches from this day onward (YYYY-MM-DD), e.g. the AFTER window")
    a = ap.parse_args()
    d = scan(a.since)
    stat = d["stat"]
    label = f"since {a.since}" if a.since else "WHOLE CORPUS (the BEFORE baseline)"
    print(f"DQ-T76 Wave 1 bar — {TOOL}, {label}")
    print(f"batches contributing: {len(d['batches'])}")
    if not stat:
        print("\nNO CALLS in this window — a rate over zero calls is not a measurement, and a "
              "'pass' derived from one would be exactly the failure the plan warns about "
              "('a rate that falls because nobody called the tool is not a pass').")
        return 0
    print(f"\n{'argument':<20}{'calls':>7}{'value':>7}{'uuid':>6}{'wrong-family':>14}"
          f"{'missing':>9}   rate")
    for arg in WAVE1_ARGS:
        s = stat.get(arg, collections.Counter())
        n = s["calls"]
        wf = s["wrong_family"]
        rate = (wf / s["passed_a_value"]) if s["passed_a_value"] else 0.0
        print(f"{arg:<20}{n:>7}{s['passed_a_value']:>7}{s['uuid']:>6}{wf:>14}"
              f"{s['missing']:>9}   {rate:.1%}")
    print(f"\nWAVE 1's NEW FORM (a name instead of an id):")
    for arg in ("source_name", "target_name"):
        print(f"   {arg:<18}{stat.get(arg, collections.Counter())['calls']:>5} call(s)")
    print("\nPASS CONDITION (the plan's, restated): the wrong-family rate FALLS and the call "
          "volume does NOT. Both halves, or it is not a pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
