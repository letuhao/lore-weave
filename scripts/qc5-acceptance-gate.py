#!/usr/bin/env python3
"""qc5-acceptance-gate — score QC-5's acceptance, and refuse to let 1b pass on its own.

Clause 1 of §2.1 was UNSATISFIABLE and it took six runs across two chapters to see why. It
required *">=2 runs with `canon<=3` and at least one attributed violation"*, which can only
happen when the DRAFTER produces a canon violation. It did not, in any of them: chapter 5
(C7) and chapter 12 (C13) both scored `canon_consistency=5` with zero canon violations, so
clause 1 scored 0/6 and the row read as a critic failure. The critic was never the problem —
a passage built to contradict `R1`, through the real prompt with the real six rules, scores
`canon=1` attributed to `R1`, 3/3, zero invented ids (C14).

PO sign-off 2026-08-21 splits it:

    1a  CRITIC CAPABILITY   a PLANTED violation is attributed.      (arm="planted")
    1b  DRAFTER COMPLIANCE  the flow's own prose is canon-clean.    (arm="flow")

1b ALONE IS A CRITERION THAT CANNOT FAIL, and that is this gate's whole reason to exist.
"Zero attributed violations" is exactly what a perfect drafter and a critic that attributes
NOTHING both produce. Read on its own, 1b would have scored a PASS during the very weeks the
critic was inventing rule ids and discarding every finding (`dropped=2 of 2`; `9 discarded
across three runs`). So 1b is scored ONLY when 1a passes in the same measurement, and a 1b
verdict with no `planted` arm is refused rather than assumed. Same shape as
`soak-armed-gate`: a zero meaning "nothing detected" must not be readable as a zero meaning
"nothing to detect".

Input: JSON, a list of run objects.

    {"arm": "planted"|"flow", "canon": int, "attributed": int, "raw": int}

Usage
    python scripts/qc5-acceptance-gate.py --file runs.json
    python scripts/qc5-acceptance-gate.py --selftest        # offline, no stack needed
"""
from __future__ import annotations

import argparse
import json
import sys

PASS, FAIL, UNSCORABLE = "PASS", "FAIL", "UNSCORABLE"

#: §2.1 keeps three runs per arm and majority rule. Measured 2026-08-13: three runs gave
#: severe/warn/ok, so unanimity fails a working pipeline and one run passes a broken one.
MAJORITY = 2
RUNS_PER_ARM = 3


def _clause_1a(planted: list[dict]) -> tuple[str, str]:
    if len(planted) < RUNS_PER_ARM:
        return UNSCORABLE, (
            f"1a needs {RUNS_PER_ARM} planted runs, got {len(planted)} — the critic's ability "
            "to attribute is UNMEASURED, so 1b cannot be read either"
        )
    ok = [r for r in planted if r["canon"] <= 3 and r["attributed"] >= 1]
    if len(ok) >= MAJORITY:
        return PASS, f"{len(ok)}/{len(planted)} planted runs attributed a violation with canon<=3"
    return FAIL, (
        f"only {len(ok)}/{len(planted)} planted runs attributed a violation with canon<=3 — "
        "the critic cannot see a violation that IS there, so a clean flow run proves nothing"
    )


def _clause_1b(flow: list[dict], a_verdict: str) -> tuple[str, str]:
    # The gate's load-bearing line: same flow numbers, opposite verdict, decided by 1a.
    if a_verdict != PASS:
        return UNSCORABLE, (
            f"1a did not pass ({a_verdict}), so 1b is NOT scored: 'zero attributed violations' "
            "is what a canon-clean drafter and a critic that attributes nothing both produce"
        )
    if len(flow) < RUNS_PER_ARM:
        return UNSCORABLE, f"1b needs {RUNS_PER_ARM} flow runs, got {len(flow)}"
    # A finding the critic FOUND and could not attribute is the C10 defect, not compliance.
    dropped = [r for r in flow if r["raw"] > r["attributed"]]
    if dropped:
        return FAIL, (
            f"{len(dropped)}/{len(flow)} flow runs discarded findings they could not attribute "
            "(raw > attributed) — the unattributable-verdict defect, not a clean draft"
        )
    violations = [r for r in flow if r["attributed"] >= 1]
    if violations:
        return FAIL, (
            f"{len(violations)}/{len(flow)} flow runs produced an attributed canon violation — "
            "the drafter contradicted active canon"
        )
    return PASS, (
        f"{len(flow)}/{len(flow)} flow runs are canon-clean, and 1a proves the critic would "
        "have said so"
    )


def _clause_2(runs: list[dict], a_verdict: str) -> tuple[str, str]:
    """A clean 5/5 with NOTHING found — the defect signature, unless the critic is PROVEN live.

    ⚠️ Clause 2 has the same vacuity as 1b, pointing the other way, and the 2026-08-21 re-run is
    what exposed it. After an author added `R7` the drafter complied and three flow runs scored
    `canon=5, raw=0` — byte-identical to the shape this clause was written to catch. It cannot
    tell "found nothing because there was nothing" from "found nothing because it is broken",
    so as written it PUNISHES the canon-clean draft the architecture exists to produce.

    Two independent things must be shown before a 5/5-with-nothing-found is believable, and 1a
    is only ONE of them:

      (i)  1a — the critic can attribute a violation that IS there.
      (ii) a `flow_control` run — the critic is live IN THE FLOW, not merely below the seam.

    (ii) is not redundant. 1a drives the judge directly with no drafter, so it stays green for a
    flow that never calls the critic at all: every run would report `raw=0` and read as a
    perfectly canon-clean book. The control is the same flow, same chapter, demonstrably
    producing findings — in the real measurement, the PRE-R7 runs at raw 3 / 6 / 2.

    Without BOTH, the original teeth stay exactly as they were.
    """
    bad = [r for r in runs if r["canon"] == 5 and r["raw"] == 0]
    if not bad:
        return PASS, "no run produced 5/5 with zero raw findings"
    control = [r for r in runs if r.get("arm") == "flow_control" and r["raw"] >= 1]
    if a_verdict == PASS and control:
        return PASS, (
            f"{len(bad)} run(s) scored 5/5 with nothing found, and that is READABLE here: 1a "
            f"shows the critic attributes, and {len(control)} flow_control run(s) show it "
            "producing findings in the same flow"
        )
    missing = []
    if a_verdict != PASS:
        missing.append(f"1a is {a_verdict}")
    if not control:
        missing.append("no flow_control run shows the critic finding anything in the flow")
    return FAIL, (
        f"{len(bad)} run(s) produced 5/5 with zero raw findings and the critic is not proven "
        f"live ({'; '.join(missing)}) — indistinguishable from the defect signature"
    )


def score(runs: list[dict]) -> tuple[str, list[tuple[str, str, str]]]:
    planted = [r for r in runs if r.get("arm") == "planted"]
    flow = [r for r in runs if r.get("arm") == "flow"]
    a, a_why = _clause_1a(planted)
    b, b_why = _clause_1b(flow, a)
    c, c_why = _clause_2(runs, a)
    rows = [
        ("1a critic capability", a, a_why),
        ("1b drafter compliance", b, b_why),
        ("2  no vacuous 5/5", c, c_why),
    ]
    overall = (
        PASS if all(v == PASS for _, v, _ in rows)
        else FAIL if any(v == FAIL for _, v, _ in rows)
        else UNSCORABLE
    )
    return overall, rows


def _planted(canon=1, attributed=1, raw=1):
    return {"arm": "planted", "canon": canon, "attributed": attributed, "raw": raw}


def _flow(canon=4, attributed=0, raw=0):
    return {"arm": "flow", "canon": canon, "attributed": attributed, "raw": raw}


def _control(canon=5, attributed=0, raw=3):
    """The same flow, demonstrably producing findings. In the real measurement these are the
    PRE-R7 runs at raw 3 / 6 / 2 — the critic alive in the flow, before the canon changed."""
    return {"arm": "flow_control", "canon": canon, "attributed": attributed, "raw": raw}


def selftest() -> int:
    print("qc5-acceptance-gate - selftest (offline)")
    bad = 0

    def check(name, runs, want):
        nonlocal bad
        got, _rows = score(runs)
        ok = got == want
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: expected {want}, got {got}")

    signed_off = [_planted(), _planted(), _planted(), _flow(), _flow(), _flow()]
    check("the signed-off shape: 1a 3/3 and a canon-clean flow", signed_off, PASS)

    # THE REGRESSION THIS GATE EXISTS FOR. Identical flow arm, 1a removed.
    check("the SAME clean flow with NO planted arm is unscorable",
          [r for r in signed_off if r["arm"] == "flow"], UNSCORABLE)

    check("a critic that misses the planted violation fails 1a",
          [_planted(canon=5, attributed=0, raw=1)] * 3 + [_flow()] * 3, FAIL)

    # The C7/C13 history: flow runs that FOUND things and attributed none.
    check("flow runs that discard what they found fail 1b",
          [_planted()] * 3 + [_flow(canon=4, attributed=0, raw=3)] * 3, FAIL)

    # ── clause 2: the 2026-08-21 re-run's finding, both directions ───────────
    check("clause 2 fires on a vacuous 5/5 when only 1a backs it (no flow control)",
          [_planted()] * 3 + [_flow(canon=5, attributed=0, raw=0)] * 3, FAIL)
    check("the SAME 5/5 runs pass once a flow_control shows the critic live",
          [_planted()] * 3 + [_flow(canon=5, attributed=0, raw=0)] * 3 + [_control()], PASS)
    check("a flow_control that itself found NOTHING does not license the 5/5",
          [_planted()] * 3 + [_flow(canon=5, attributed=0, raw=0)] * 3
          + [_control(raw=0)], FAIL)
    check("clause 2 keeps its ORIGINAL teeth when 1a fails, control or not",
          [_planted(canon=5, attributed=0, raw=1)] * 3
          + [_flow(canon=5, attributed=0, raw=0)] * 3 + [_control()], FAIL)

    # Majority, not unanimity.
    check("1a passes on 2 of 3 planted runs",
          [_planted(), _planted(), _planted(canon=5, attributed=0, raw=1)] + [_flow()] * 3, PASS)
    check("1a fails on 1 of 3",
          [_planted(), _planted(canon=5, attributed=0, raw=1),
           _planted(canon=5, attributed=0, raw=1)] + [_flow()] * 3, FAIL)

    # The property no single fixture pins: 1a decides how the SAME 1b input reads.
    #
    # This is asserted on the 1b CLAUSE ROW, not on the overall verdict. Checking `overall`
    # alone does not pin it: with no planted arm 1a is already UNSCORABLE, which drags the
    # overall verdict there whatever 1b said — so a 1b that had stopped consulting 1a
    # entirely still produced the expected overall answer. Bite 61 landed exactly there and
    # the selftest stayed green, which is this file's own defect class caught in itself.
    flow_only = [_flow()] * 3
    with_a_overall, with_a_rows = score([_planted()] * 3 + flow_only)
    without_a_overall, without_a_rows = score(flow_only)
    b_with = next(v for n, v, _ in with_a_rows if n.startswith("1b"))
    b_without = next(v for n, v, _ in without_a_rows if n.startswith("1b"))
    ok = (
        with_a_overall == PASS and without_a_overall == UNSCORABLE
        and b_with == PASS and b_without == UNSCORABLE
    )
    bad += not ok
    print(
        f"  {'PASS' if ok else 'FAIL'}  the 1b CLAUSE itself reads {b_with}/{b_without} "
        f"with/without a planted arm"
    )

    print("\n  all checks passed" if not bad else f"\n  {bad} check(s) FAILED")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", help="JSON list of run records")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.file:
        ap.error("one of --file or --selftest is required")
    runs = json.load(open(a.file, encoding="utf-8"))
    overall, rows = score(runs)
    for name, verdict, why in rows:
        print(f"[qc5-acceptance] {name:24s} {verdict:11s} {why}")
    print(f"[qc5-acceptance] QC-5 => {overall}")
    return 0 if overall == PASS else 1


if __name__ == "__main__":
    sys.exit(main())
