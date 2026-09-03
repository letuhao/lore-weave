#!/usr/bin/env python3
"""Emit the /goal condition for FINISHING THE EVIDENCE — three streams, queue derived at emit time.

The owner picked three things (2026-09-02): finish the soft-evidence sweep, build DQ-T76 Wave 1,
and run the DQ-T88 on-path A/B.

WHY A GENERATOR. Two predecessors went stale inside a day and both cost real work:
  - the /goal queue kept naming rows that were already finished, because it was a pasted snapshot;
  - the soft-evidence bucket was derived from the WRONG predicate twice -- first from raw call
    counts (which is not what gate.is_gate_backed asks) and then without excluding legacy tools,
    which spent 15 live runs measuring deprecated code.
Both are fixed HERE rather than in the emitted text, so the fix survives the next emit.

Usage:
    python scripts/toolloop/goal_prompt_finish_the_evidence.py           # emit
    python scripts/toolloop/goal_prompt_finish_the_evidence.py --check   # budget + completeness
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
CATALOG = ROOT / "contracts" / "tool-catalog-cache.json"
BUDGET = 4000


def _under_test() -> set:
    """Tools some GATE-READY file puts UNDER TEST — the only thing that can be cited.

    Reads the batch artefact's top-level `tools` array, which is exactly what
    `gate._tools_in_batch` reads. Anything else is a proxy, and the proxy cost a false row.
    """
    out = set()
    for p in glob.glob(str(ROOT / "docs" / "eval" / "toolloop" / "*" / "*.json")):
        if p.endswith("-raw.json"):
            continue
        try:
            d = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict):
            for x in (d.get("tools") or []):
                if isinstance(x, dict) and x.get("tool"):
                    out.add(x["tool"])
    return out


def derive() -> dict:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    legacy = {k for k, v in cat.items()
              if isinstance(v, dict) and (v.get("meta") or {}).get("visibility") == "legacy"}

    soft = sorted(k for k, v in led["tools"].items()
                  if isinstance(v, dict) and v.get("state") == "proven"
                  and v.get("evidence_class") != "gate-backed"
                  and k not in legacy)
    citable = _under_test()

    q = led.get("deferred_questions") or {}
    t76 = q.get("DQ-T76") or {}
    t88 = q.get("DQ-T88") or {}
    return {
        "soft": soft,
        "citable_now": [t for t in soft if t in citable],
        "t76_wave1_done": any(k.startswith("wave1_") for k in t76),
        "t88_ab_done": any("ab_" in k or "AB_" in k for k in t88),
        "gate_backed": sum(1 for v in led["tools"].values()
                           if isinstance(v, dict) and v.get("evidence_class") == "gate-backed"),
    }


def build() -> str:
    d = derive()
    n = len(d["soft"])
    nxt = (d["citable_now"] or d["soft"] or ["(nothing — all three streams are done)"])[0]
    t76 = "DONE" if d["t76_wave1_done"] else "NOT STARTED"
    t88 = "DONE" if d["t88_ab_done"] else "NOT STARTED"

    return f"""/goal FINISH THE EVIDENCE — three streams, in contracts/tool-deep-dive-ledger.json.

OBJECTIVE. (1) Every `proven` tool row is gate-backed. (2) DQ-T76 Wave 1 is built and measured. (3) DQ-T88's on-path A/B is run and the flag is adopted or left off ON THE NUMBERS. {d['gate_backed']} rows are gate-backed; {n} are not. Wave 1: {t76}. A/B: {t88}.

UNIT. ONE tool row, or ONE wave, or ONE A/B arm per cycle. Order is yours.

METHOD.
 STREAM 1 — the {n} soft rows. Each needs a cycle of its OWN: a scenario naming the tool, a falsifier, K=5. A tool is CITABLE only when a gate-ready file's top-level `tools` array lists it — being CALLED in someone else's batch is not enough, and citing that way produced the only row in 207 that claimed gate-backed and failed the definition. Write the scenario from the tool's DECLARED synonyms and check the prompt against `answerable_tools` BEFORE running: a paraphrase that reorders a synonym surfaces nothing, and a fixture that does not match the shipped declaration tests the fixture. Exclude legacy tools — a sweep already spent 15 live runs on deprecated code.
 STREAM 2 — DQ-T76 Wave 1, per docs/specs/2026-09-02-remove-ids-from-the-model-surface.md: `source_entity_id` (supplier on the wire 9%) plus the ten zero-supplier arguments. Accept BOTH forms, id wins when both arrive, and SAY which won. NOT the ~100%-supplied arguments — the plan says they are the low-value half.
 STREAM 3 — DQ-T88's A/B. Set the flag on the REAL service via compose, not `docker compose run` (that container is on the network but the gateway routes by service name, so a previous attempt measured a stopped service). Needs a MULTI-TURN scenario where a prior turn's result actually matters.

EVIDENCE. K=5 is the bar; a row proven weaker must SAY SO on the row. Proven by a RUN, never by code looking right. Re-derive every number — a ledger claim is a lead. Count DISTINCT toolCallId (these files emit TOOL_CALL_START twice per call). Stratify before pooling. Check a guard can actually go RED before trusting it: three guards this month went green against the defect they were written for, two of them matching their own explanatory prose.

STOP. Ends when `gate.py audit` is clean AND no `proven` row carries a pre-gate evidence_class AND Wave 1 and the A/B are both stamped on their questions. NOTHING ELSE ENDS IT. One row is ONE CYCLE, never the run: when one lands, open the next IN THE SAME TURN.
NEVER STOP FOR: asking which order; a finished cycle; a green suite; a long report. Reporting is not progress. A turn that has not moved a row MUST END IN A TOOL CALL.
NEVER: weaken a bar to fit, cite a file that does not put the tool under test, or stamp a ruling without checking the code. When a control refutes your own claim, WITHDRAW IT and record what misled you. Every fix states what it does NOT cover.
SPEND. LOCAL MODEL ONLY, $0. A PAID run needs the owner's yes and its CALL COUNT stated first.
SAFETY. Never write to the dogfood book; one throwaway fixture per scenario, torn down. Auth only via /v1/auth/login with docs/dev/LOCAL_TEST_ENV.md. SELECT before any DML, and refuse a delete whose keep-set is empty. An open DQ gets a RECOMMENDATION and is DECIDED BY THE OWNER.

QUEUE, derived by scripts/toolloop/goal_prompt_finish_the_evidence.py.
  {n} soft row(s) · Wave 1 {t76} · A/B {t88}

NEXT. {nxt}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = build()
    d = derive()
    print(f"[{len(text)} / {BUDGET} chars]")
    if a.check:
        if len(text) > BUDGET:
            print(f"REFUSED: over budget by {len(text) - BUDGET}. Shorten the SOURCE — STOP sits "
                  f"above QUEUE so a trim never costs the brakes.")
            return 1
        left = len(d["soft"]) + (not d["t76_wave1_done"]) + (not d["t88_ab_done"])
        print(f"CHECK: {len(d['soft'])} soft row(s); Wave 1 "
              f"{'done' if d['t76_wave1_done'] else 'outstanding'}; A/B "
              f"{'done' if d['t88_ab_done'] else 'outstanding'}. "
              f"{'Nothing left.' if not left else 'Work remains.'}")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
