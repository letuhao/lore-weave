#!/usr/bin/env python3
"""Build a re-run scenario file from the LIVE runstate. Nothing about the set is typed.

    python scripts/toolloop/build_rerun_set.py --out scripts/toolloop/scenarios-rebaseline.json
    python scripts/toolloop/build_rerun_set.py --problem P5-SIBLING-WINS --out /tmp/c3.json
    python scripts/toolloop/build_rerun_set.py --exclude-problem P3-NAME-TO-ID --out …

🔴 WHY THIS EXISTS. `scenarios-rebaseline.json` was written once, by hand, as "every still-blocked
tool outside cycle 2's eight". Within the day it was wrong: `composition_generate` moved P3 -> P5 on
its measured cause, so the file both MISSED a tool it should now cover and DUPLICATED five that
another file already had. A hand-listed denominator drifts toward what was true when someone last
remembered to edit it — which is the exact failure `problem_remaining.py` exists to prevent for the
progress number, and it applies just as much to the work list.

So the set comes from the two contracts, every time:
  * `contracts/tool-resolution-problems.json` — the frozen problem -> tools partition
  * `contracts/tool-deep-dive-ledger.json`    — the per-tool state, written only by `gate.py conclude`

and the SCENARIOS come from whatever file on disk declares that `tool_under_test`, carried over
UNEDITED. A re-run must measure the same request the original conclusion was drawn from; a prompt I
rewrite for the re-run measures a different question and answers it convincingly.

IT REFUSES RATHER THAN GUESSES. A blocked tool with no scenario on disk is an error, not a silent
omission — an incomplete work list that looks complete is how a denominator quietly shrinks. And
duplicate `tool_under_test` entries are rejected, because a batch that measures one tool twice
reports two different answers for it and the reader cannot tell which is the tool's.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
SCEN_DIR = ROOT / "scripts" / "toolloop"


#: Files this script itself PRODUCES. They must never be read back in, or the generator sources its
#: own output and a scenario chosen once is chosen forever.
GENERATED = ("scenarios-rebaseline.json", "scenarios-c3-run.json", "scenarios-c3-close.json",
             "scenarios-c2-motif.json")


def scenario_index() -> dict[str, tuple[str, dict]]:
    """tool -> (file, scenario). Later files win, so a carried-over copy beats the original.

    🔴 TWO WAYS THIS PICKED THE WRONG SCENARIO, both measured 2026-08-23 on `tool_load`.

    (1) IT READ ITS OWN OUTPUT. scenarios-rebaseline.json sorts last, so once generated it became
    the source for the next build — `_carried_from: scenarios-rebaseline.json`, a scenario chosen
    once and then chosen forever, with the original file unable to correct it.

    (2) "LAST FILE WINS" IS ALPHABETICAL, NOT SEMANTIC. `scenarios-dqt3.json` sorts after
    `scenarios-batch3.json`, so tool_load was carried with the DQ-T3 prompt — "Load the tool called
    glossary_book_sync_apply BY NAME and tell me exactly what arguments it takes" — which instructs
    the model to use tool_load. P10-TOOL-LOAD asks the opposite question: "What exactly do you need
    from me to add a new character? Check the real requirements, don't guess", where the whole point
    is whether the model reaches for the schema UNPROMPTED. The re-run measured 5/5 called and it
    says nothing about the problem, because the prompt gave the answer away.

    A tie-break that decides WHICH QUESTION gets asked is not a tie-break. Generated files are
    excluded here; choosing between two genuine scenarios for one tool still needs a human, and the
    file each tool was taken from is stamped on it so the choice is visible.
    """
    idx: dict[str, tuple[str, dict]] = {}
    for f in sorted(SCEN_DIR.glob("scenarios-*.json")):
        if f.name in GENERATED:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            t = s.get("tool_under_test")
            if t:
                idx[t] = (f.name, s)
    return idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--problem", action="append", default=[],
                    help="only these problem ids (repeatable)")
    ap.add_argument("--exclude-problem", action="append", default=[],
                    help="skip these problem ids (repeatable)")
    ap.add_argument("--note", default="", help="prepended to the file's _note")
    a = ap.parse_args()

    probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))["tools"]
    idx = scenario_index()

    wanted: list[tuple[str, str]] = []
    for p in probs["problems"]:
        if a.problem and p["id"] not in a.problem:
            continue
        if p["id"] in a.exclude_problem:
            continue
        for t in p["tools"]:
            if (ledger.get(t) or {}).get("state") != "proven":
                wanted.append((p["id"], t))

    dupes = [t for t, n in collections.Counter(t for _, t in wanted).items() if n > 1]
    if dupes:
        print("REFUSED — the partition put a tool in more than one problem, so this set would "
              "measure it twice and report two answers for it:")
        for t in dupes:
            print(f"  {t}")
        return 2

    missing = [t for _, t in wanted if t not in idx]
    if missing:
        print("REFUSED — blocked tool(s) with NO scenario on disk. A work list that silently omits "
              "them looks complete and is not:")
        for t in missing:
            print(f"  {t}")
        return 2

    out = {
        "_note": ((a.note + "\n\n") if a.note else "") + (
            "GENERATED by scripts/toolloop/build_rerun_set.py from the live runstate — the tool set "
            "is DERIVED from contracts/tool-resolution-problems.json + the ledger's per-tool state, "
            "never typed. Scenarios are carried over UNEDITED from the file that declares each "
            "tool_under_test, because a re-run must measure the same request the original "
            "conclusion was drawn from."),
        "scenarios": [],
    }
    for pid, t in sorted(wanted):
        fn, s = idx[t]
        s = dict(s)
        s["_carried_from"] = fn
        s["_problem"] = pid
        out["scenarios"].append(s)

    pathlib.Path(a.out).write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    by = collections.Counter(pid for pid, _ in wanted)
    print(f"wrote {a.out} with {len(out['scenarios'])} scenario(s)")
    for pid, n in sorted(by.items()):
        print(f"  {pid:24} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
