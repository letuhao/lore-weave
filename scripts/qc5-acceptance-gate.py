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

#: ~~§2.1 keeps three runs per arm and majority rule. Measured 2026-08-13: three runs gave
#: severe/warn/ok, so unanimity fails a working pipeline and one run passes a broken one.~~
#:
#: **PO §7.3, 2026-08-21 — FIVE runs per arm, majority 3.** The three-run rule was retired by
#: the measurement it produced: chapter 12 scored `1/SEVERE` in run `019ff9d6` and `2/warn` in
#: `019ff9de` on unchanged inputs, so three was the sample size that FAILED to settle the
#: question it was chosen to settle. Temperature is already 0 on the judge (`critic.py:265`);
#: seeding is best-effort and currently unavailable, which a measurement must SAY rather than
#: imply — an unseeded five-run spread is weaker evidence than a seeded one.
#:
#: ⚠️ This number moving makes every THREE-run measurement UNSCORABLE, including QC-5 C17's
#: PASS. That is the intended consequence and not collateral: C17 is unrescored, not wrong,
#: and letting a three-run PASS stand in for a five-run one is the substitution this whole
#: gate exists to refuse. Tracked as `D-QC5-FIVE-RUN-SPREAD-NOT-MEASURED`.
MAJORITY = 3
RUNS_PER_ARM = 5


def _flags(r: dict) -> bool:
    """1a's criterion, in ONE place so the arm and its control cannot be scored differently."""
    return r["canon"] <= 3 and r["attributed"] >= 1


def _clause_1a(planted: list[dict], control: list[dict]) -> tuple[str, str]:
    """The planted arm AND its control. The control is not optional, and 2026-08-21 is why.

    1a used to ask one question: did the planted runs flag it? Measured on chapter 12 with a
    matched control — the SAME draft, differing only by the canon antagonist's name being
    swapped for an invented one — the answer was:

        planted  canon [2,2,2,2,2]  attributed [2,2,2,2,2]     -> 5/5 "PASS"
        control  canon [2,2,2,2,2]  attributed [2,2,2,2,2]     -> 5/5 the SAME

    The criterion was satisfied 5/5 by a draft with NOTHING planted in it. Reading the verdicts
    showed why: both arms cite R1 (a kinship claim) and R3 (a spiritual-energy claim), and
    neither verdict is about the misattribution at all. The critic never saw the plant; the
    draft independently violates two rules, so `canon<=3 and attributed>=1` was true no matter
    what was planted.

    That is rule 3 exactly — *a criterion that cannot fail is not a criterion* — and it had been
    sitting inside the gate written to enforce rule 3. So the control is mandatory: without it
    1a is UNSCORABLE, and if the control satisfies the criterion too, 1a is UNSCORABLE rather
    than PASS, because the number is measuring the draft and not the plant.
    """
    if len(planted) < RUNS_PER_ARM:
        return UNSCORABLE, (
            f"1a needs {RUNS_PER_ARM} planted runs, got {len(planted)} — the critic's ability "
            "to attribute is UNMEASURED, so 1b cannot be read either"
        )
    if len(control) < RUNS_PER_ARM:
        return UNSCORABLE, (
            f"1a needs {RUNS_PER_ARM} `planted_control` runs (the same draft with NOTHING "
            f"planted), got {len(control)} — without them a planted arm that flags cannot be "
            "told from a draft that was going to be flagged anyway (measured 2026-08-21: it "
            "was the second one)"
        )
    ok = [r for r in planted if _flags(r)]
    ctl = [r for r in control if _flags(r)]
    if len(ctl) >= MAJORITY:
        return UNSCORABLE, (
            f"{len(ok)}/{len(planted)} planted runs flagged — but so did {len(ctl)}/"
            f"{len(control)} CONTROL runs with nothing planted. The criterion is measuring the "
            "draft, not the plant, and a pass the control also earns is not a pass"
        )
    if len(ok) >= MAJORITY:
        return PASS, (
            f"{len(ok)}/{len(planted)} planted runs attributed a violation with canon<=3, "
            f"while only {len(ctl)}/{len(control)} control runs did — it discriminates"
        )
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
    # FLOW runs only. Clause 2 is about "the flow produced a perfect score and found nothing";
    # the planted arm and its control are diagnostic passages, not the flow, and a CLEAN
    # control legitimately scores 5/5 with zero findings -- that is what makes it a control.
    # Scanning every arm made the control itself trip the clause, which would have punished
    # the fix for 1a's vacuity with a failure on clause 2.
    bad = [r for r in runs if r.get("arm") == "flow" and r["canon"] == 5 and r["raw"] == 0]
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
    pcontrol = [r for r in runs if r.get("arm") == "planted_control"]
    flow = [r for r in runs if r.get("arm") == "flow"]
    a, a_why = _clause_1a(planted, pcontrol)
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


def _pctl(canon=5, attributed=0, raw=0):
    """The matched control: the SAME draft with nothing planted. A 1a that does not check
    this cannot tell "the critic caught the plant" from "the draft was dirty anyway"."""
    return {"arm": "planted_control", "canon": canon, "attributed": attributed, "raw": raw}


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

    signed_off = [_planted()] * RUNS_PER_ARM + [_pctl()] * RUNS_PER_ARM + [_flow()] * RUNS_PER_ARM
    check(f"the signed-off shape: 1a {RUNS_PER_ARM}/{RUNS_PER_ARM} and a canon-clean flow", signed_off, PASS)

    # THE REGRESSION THIS GATE EXISTS FOR. Identical flow arm, 1a removed.
    check("the SAME clean flow with NO planted arm is unscorable",
          [r for r in signed_off if r["arm"] == "flow"], UNSCORABLE)

    check("a critic that misses the planted violation fails 1a",
          [_planted(canon=5, attributed=0, raw=1)] * RUNS_PER_ARM + [_pctl()] * RUNS_PER_ARM + [_flow()] * RUNS_PER_ARM, FAIL)

    # The C7/C13 history: flow runs that FOUND things and attributed none.
    check("flow runs that discard what they found fail 1b",
          [_planted()] * RUNS_PER_ARM + [_pctl()] * RUNS_PER_ARM + [_flow(canon=4, attributed=0, raw=3)] * RUNS_PER_ARM, FAIL)

    # ── clause 2: the 2026-08-21 re-run's finding, both directions ───────────
    check("clause 2 fires on a vacuous 5/5 when only 1a backs it (no flow control)",
          [_planted()] * RUNS_PER_ARM + [_pctl()] * RUNS_PER_ARM + [_flow(canon=5, attributed=0, raw=0)] * RUNS_PER_ARM, FAIL)
    check("the SAME 5/5 runs pass once a flow_control shows the critic live",
          [_planted()] * RUNS_PER_ARM + [_pctl()] * RUNS_PER_ARM + [_flow(canon=5, attributed=0, raw=0)] * RUNS_PER_ARM
          + [_control()], PASS)
    check("a flow_control that itself found NOTHING does not license the 5/5",
          [_planted()] * RUNS_PER_ARM + [_pctl()] * RUNS_PER_ARM + [_flow(canon=5, attributed=0, raw=0)] * RUNS_PER_ARM
          + [_control(raw=0)], FAIL)
    check("clause 2 keeps its ORIGINAL teeth when 1a fails, control or not",
          [_planted(canon=5, attributed=0, raw=1)] * RUNS_PER_ARM + [_pctl()] * RUNS_PER_ARM
          + [_flow(canon=5, attributed=0, raw=0)] * RUNS_PER_ARM + [_control()], FAIL)

    # Majority, not unanimity — and the threshold MOVED with §7.3, so these pin 3-of-5 and
    # 2-of-5 rather than the old 2-of-3. A fixture left at the old ratio would keep passing
    # while asserting a rule nobody uses.
    check(f"1a passes on {MAJORITY} of {RUNS_PER_ARM} planted runs",
          [_planted()] * MAJORITY + [_planted(canon=5, attributed=0, raw=1)] * (RUNS_PER_ARM - MAJORITY)
          + [_pctl()] * RUNS_PER_ARM + [_flow()] * RUNS_PER_ARM, PASS)
    check(f"1a fails on {MAJORITY - 1} of {RUNS_PER_ARM}",
          [_planted()] * (MAJORITY - 1) + [_planted(canon=5, attributed=0, raw=1)] * (RUNS_PER_ARM - MAJORITY + 1)
          + [_pctl()] * RUNS_PER_ARM + [_flow()] * RUNS_PER_ARM, FAIL)

    # ── C24 2026-08-21: the case that put a control in 1a at all ────────────────────────
    # MEASURED, not imagined. Chapter 12, five runs each, the two passages differing only by
    # the canon antagonist's name being swapped for an invented one:
    #     planted canon [2,2,2,2,2] attributed [2,2,2,2,2]
    #     control canon [2,2,2,2,2] attributed [2,2,2,2,2]   <- IDENTICAL
    # Both cite R1 and R3, and neither verdict is about the misattribution. 1a scored 5/5 on a
    # draft that was going to be flagged anyway.
    check("1a is UNSCORABLE when the CONTROL flags exactly as often as the plant",
          [_planted(canon=2, attributed=2, raw=2)] * RUNS_PER_ARM
          + [_pctl(canon=2, attributed=2, raw=2)] * RUNS_PER_ARM
          + [_flow()] * RUNS_PER_ARM, UNSCORABLE)
    # ...and the discriminating twin: the SAME planted numbers, a control that stays clean.
    # If these two ever agree, the control column has stopped being read.
    check("...and PASSES with the same planted arm once the control stays clean",
          [_planted(canon=2, attributed=2, raw=2)] * RUNS_PER_ARM
          + [_pctl()] * RUNS_PER_ARM + [_flow()] * RUNS_PER_ARM, PASS)
    check("1a with NO control at all is UNSCORABLE, not a pass",
          [_planted()] * RUNS_PER_ARM + [_flow()] * RUNS_PER_ARM, UNSCORABLE)

    # ── §7.3's CONSEQUENCE, made executable ─────────────────────────────────────────────
    # A three-run measurement no longer scores. This is the fixture that stops QC-5 C17's
    # three-run PASS from being reused as if it were a five-run one — the substitution this
    # gate exists to refuse, and the reason the constant above is not just a bigger number.
    check("a THREE-run measurement is now UNSCORABLE, not a PASS",
          [_planted()] * 3 + [_pctl()] * 3 + [_flow()] * 3, UNSCORABLE)

    # The property no single fixture pins: 1a decides how the SAME 1b input reads.
    #
    # This is asserted on the 1b CLAUSE ROW, not on the overall verdict. Checking `overall`
    # alone does not pin it: with no planted arm 1a is already UNSCORABLE, which drags the
    # overall verdict there whatever 1b said — so a 1b that had stopped consulting 1a
    # entirely still produced the expected overall answer. Bite 61 landed exactly there and
    # the selftest stayed green, which is this file's own defect class caught in itself.
    flow_only = [_flow()] * RUNS_PER_ARM
    with_a_overall, with_a_rows = score([_planted()] * RUNS_PER_ARM + [_pctl()] * RUNS_PER_ARM
                                        + flow_only)
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
