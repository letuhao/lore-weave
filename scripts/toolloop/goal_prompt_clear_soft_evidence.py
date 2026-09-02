#!/usr/bin/env python3
"""Emit the /goal condition for CLEARING THE SOFT EVIDENCE, with a queue derived at emit time.

WHY A GENERATOR RATHER THAN A TYPED LIST. The predecessor goal's queue went stale inside a day
-- its pasted snapshot still named `D-A-LISTING-TOOL-RETURNS-EVERYTHING-WITH-NO-INDEX-TIER` and
`DQ-T5` as outstanding when both were finished, and the Stop hook kept re-serving them. A queue
that is READ FROM THE LEDGER at emit time cannot do that: an item that gets finished leaves the
queue by itself.

THE THREE BUCKETS ARE NOT A TASTE, THEY ARE THE COST MODEL. Every live run serialises on one
local GPU, so what decides the plan is which rows need one:

    from_disk   already called >=5 times in a recorded batch  -> re-verify off disk, no GPU
    partial     called 1-4 times                              -> one short batch may cross the bar
    live        never called in any recorded batch            -> a K=5 arm each

Usage:
    python scripts/toolloop/goal_prompt_clear_soft_evidence.py            # emit
    python scripts/toolloop/goal_prompt_clear_soft_evidence.py --check    # budget + completeness
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
BUDGET = 4000


def _citable_tools() -> set:
    """Tools a GATE-READY file puts UNDER TEST -- the only thing that can be cited.

    🔴 THIS REPLACES A RAW-CALL-COUNT BUCKET, AND THE DIFFERENCE COST A FALSE LEDGER ROW. The
    first version asked "was this tool CALLED >=5 times in a recorded batch?" That is not what
    `gate.is_gate_backed` asks. It reads the gate-ready artefact's top-level `tools` array -- the
    tools a batch was TESTING -- and a tool merely reached during someone else's scenario is not
    in it.

    composition_reference_list is the instance: called 5/5 in c-reflist1, absent from that file's
    `tools` array (the batch was testing its CONSUMER), and I cited it anyway. It was the only
    row in 207 claiming `gate-backed` and failing the definition -- exactly the shortcut gate.py's
    own docstring names.

    So the bucket is derived from the SAME predicate the audit applies, not from a proxy.
    """
    out = set()
    for path in glob.glob(str(ROOT / "docs" / "eval" / "toolloop" / "*" / "*.json")):
        if path.endswith("-raw.json"):
            continue
        try:
            d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for x in (d.get("tools") or []):
            if isinstance(x, dict) and x.get("tool"):
                out.add(x["tool"])
    return out


def derive() -> dict:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    citable = _citable_tools()

    soft = {k: v for k, v in led["tools"].items()
            if isinstance(v, dict)
            and v.get("evidence_class") not in ("gate-backed",)
            and v.get("state") == "proven"}

    buckets = {"from_disk": [], "partial": [], "live": []}
    for name in sorted(soft):
        # from_disk means CITABLE: some gate-ready file already puts this tool under test.
        # Everything else needs a cycle of its own; `partial` is retained as a bucket name but
        # is now always empty, because the predicate is binary -- a file either lists the tool
        # or it does not. Kept rather than removed so the emitted text stays stable.
        buckets["from_disk" if name in citable else "live"].append(name)

    # A ruling that commissioned work and carries no `built_*`/`shipped_*` stamp. The rule is
    # SHARED with goal_prompt_all_defects rather than re-implemented, because the two generators
    # disagreeing about what "unbuilt" means is how a work stream goes missing.
    #
    # 🔴 THE BOUND IS THE STAMP CONVENTION'S START DATE, and both failure modes are on record.
    # Too narrow (one hardcoded round key) hid DQ-T76/T88/T90 while --check said "nothing is
    # ruled-unbuilt". Too wide (a bare "answer_" prefix) reported 34, pulling in pre-convention
    # rulings whose remedies shipped before the stamp existed -- and backfilling those "would
    # have asserted two dozen builds nobody re-verified".
    from goal_prompt_all_defects import ruled_unbuilt          # noqa: E402
    unbuilt = [name for name, _ in ruled_unbuilt(led)]

    return {"buckets": buckets, "unbuilt": sorted(unbuilt),
            "gate_backed": sum(1 for v in led["tools"].values()
                               if isinstance(v, dict) and v.get("evidence_class") == "gate-backed")}


def build() -> str:
    d = derive()
    b = d["buckets"]
    n_soft = sum(len(v) for v in b.values())
    nxt = (b["from_disk"] or b["partial"] or b["live"] or ["(nothing)"])[0]

    return f"""/goal CLEAR THE SOFT EVIDENCE, in contracts/tool-deep-dive-ledger.json.

OBJECTIVE. Every `proven` tool row is gate-backed, and every ruling that specifies work is built. DONE = no row left with evidence_class 'prose-note (pre-gate)', and every answered DQ carrying a 2026-09 ruling carries a `built_*` stamp. {d['gate_backed']} rows are already gate-backed; {n_soft} are not.

UNIT. ONE tool row, or ONE ruling, per cycle. Order is yours -- cheapest-first is fine, but never batch a live sweep on a platform you have not just proven healthy: the batch then measures the platform.

METHOD, and the buckets ARE the method because every live run serialises on ONE local GPU:
  from_disk ({len(b['from_disk'])}) -- already called >=5x in a recorded batch. RE-VERIFY OFF DISK. No GPU. Cite the batch, restamp the verdict with call_outcome.py, never type it. A tool proven inside its CONSUMER's batch is the common case (composition_reference_list) -- the evidence is there, filed under another name.
  partial ({len(b['partial'])}) -- 1-4 recorded calls. One short arm may cross the bar; re-measure before assuming it needs a full one.
  live ({len(b['live'])}) -- never called anywhere. K=5, real provider, throwaway fixture, CONCURRENCY 1, ONE arm per background task. Parallel batches starve the GPU and every run dies of no_output_timeout, which reads as a refuted remedy.

EVIDENCE. K=5 is THE BAR and it is not negotiable down: it is what all {d['gate_backed']} existing rows were held to, and '1/5 called' is a different finding from '0/5'. A row proven at a weaker bar must SAY SO on the row. Proven by a RUN, never by code looking right. Re-derive every number; a ledger claim is a lead, not a fact. Count DISTINCT toolCallId -- these files emit TOOL_CALL_START twice per call. Stratify before pooling; a rate across two eras with different batch composition measures the composition.

STOP. Ends when `gate.py audit` is clean AND no `proven` row carries a pre-gate evidence_class AND every 2026-09 ruling is stamped built. NOTHING ELSE ENDS IT. One row is ONE CYCLE, never the run: when a row lands, open the next IN THE SAME TURN.
NEVER STOP FOR: asking which order; a finished cycle; a green suite; a long report. Reporting is not progress. A turn that has not moved a row MUST END IN A TOOL CALL.
NEVER: weaken a bar to fit, fabricate a row from a tool's mere presence on a wire, or mark gate-backed without a cited file that exists. When a control refutes your own claim, WITHDRAW IT and record what misled you. Every fix states what it does NOT cover.
SPEND. LOCAL MODEL ONLY, $0. A PAID run needs the owner's yes and its CALL COUNT stated first.
SAFETY. Never write to the dogfood book; one throwaway fixture per scenario, torn down. Auth only via /v1/auth/login with docs/dev/LOCAL_TEST_ENV.md. SELECT before any DML. An open DQ gets a RECOMMENDATION and is DECIDED BY THE OWNER.

QUEUE, derived by scripts/toolloop/goal_prompt_clear_soft_evidence.py.
  {len(b['from_disk'])} from_disk (no GPU) | {len(b['partial'])} partial | {len(b['live'])} live (K=5 each)
  {len(d['unbuilt'])} ruling(s) unstamped -- BUILD it, or VERIFY it already shipped and
  stamp `built_*` with that evidence. An unstamped ruling is not proof of an unbuilt one:
  the stamp convention post-dates several. Never stamp without checking the code.

NEXT. {nxt}  (from_disk -- start where the GPU is not needed)
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = build()
    d = derive()
    n = len(text)
    if a.check:
        print(f"[{n} / {BUDGET} chars]")
        if n > BUDGET:
            print(f"REFUSED: over budget by {n - BUDGET}. Shorten the SOURCE, never cut upward "
                  f"from the bottom -- STOP sits above QUEUE so the brakes survive a trim.")
            return 1
        tot = sum(len(v) for v in d["buckets"].values())
        print(f"CHECK: {tot} soft row(s) queued, {len(d['unbuilt'])} unbuilt ruling(s). "
              f"{'Nothing left — the goal is already met.' if not tot and not d['unbuilt'] else 'Work remains.'}")
        return 0
    print(f"[{n} / {BUDGET} chars]")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
