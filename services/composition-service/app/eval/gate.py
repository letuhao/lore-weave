"""The static half of the instrument (spec §S10) — runs in CI, needs no stack.

An eval that only executes against a live stack is an eval that runs nowhere: composition
already had 2,279 lines of harness across nine `scripts/eval_*.py`, none of it automated, and
every failure to run reads as "no stack today" rather than as a gap. So the properties that
can be checked WITHOUT generating anything are checked here, on every commit.

This gate does not measure engine quality. It measures whether the instrument is capable of
measuring — the distinction that matters, because a degenerate suite reports a clean green.

    python -m app.eval.gate          # from services/composition-service
"""
from __future__ import annotations

import sys

from app.eval.defects import DEFECTS, MIN_CLASSES, DefectClass, Observation
from app.eval.suite import score_suite


def _degenerate_detectors() -> list[str]:
    """A detector that answers the same for everything measures nothing.

    Probed with an empty observation and a saturated one rather than by inspecting the
    function: a detector reading fields that no longer exist degrades to a constant, and that
    is invisible in the source.
    """
    empty = Observation(fields={})
    saturated = Observation(fields={
        "status": "checked", "iterations": 9, "scenes_covered": 9,
        "target_words": 900, "actual_words": 1, "finish_reason": "length",
        "unresolved_refs": 3,
    })
    bad: list[str] = []
    for d in DEFECTS:
        try:
            lo, hi = d.detector(empty), d.detector(saturated)
        except Exception as exc:  # a detector that raises cannot report anything
            bad.append(f"{d.code}: detector raised {type(exc).__name__}: {exc}")
            continue
        if lo == hi:
            bad.append(f"{d.code}: detector answered {lo} for BOTH an empty and a saturated "
                       f"observation — it reads nothing that varies")
    return bad


def _shared_detectors() -> list[str]:
    """Two classes sharing one detector are one class wearing two names, and the suite's
    class count — the number MIN_CLASSES gates on — would overstate its coverage."""
    seen: dict[int, str] = {}
    dupes: list[str] = []
    for d in DEFECTS:
        key = id(d.detector)
        if key in seen:
            dupes.append(f"{d.code} shares its detector with {seen[key]}")
        else:
            seen[key] = d.code
    return dupes


def _uncontrolled() -> list[str]:
    """The rule this whole package exists for: a class with no control, or whose control is
    its seeded text, can only ever measure that the detector is reachable."""
    bad: list[str] = []
    for d in DEFECTS:
        if not d.control.strip():
            bad.append(f"{d.code}: no control — a seeded hit alone cannot distinguish a "
                       f"working detector from one that always fires")
        elif d.control.strip() == d.seeded.strip():
            bad.append(f"{d.code}: control is identical to the seeded variant")
        if not d.provenance.strip():
            bad.append(f"{d.code}: no provenance — an invented defect drifts from the engine")
    return bad


def _self_check() -> list[str]:
    """The scorer must actually punish the failure the controls exist to expose.

    Without this the gate would verify the REGISTRY and leave `score_suite` free to report a
    control-firing class as detected — the same bug one layer down.
    """
    cls: DefectClass = DEFECTS[0]
    fires = Observation(fields={"status": "checked", "iterations": 1})
    quiet = Observation(fields={"status": "checked", "iterations": 0})
    bad: list[str] = []

    if not score_suite([(cls, fires, quiet)]).classes[0].detected:
        bad.append("scorer: fired-on-defect + quiet-on-control did not score as detected")
    if score_suite([(cls, fires, fires)]).classes[0].detected:
        bad.append("scorer: a class that ALSO fires on its clean control scored as detected — "
                   "this is exactly the state eval_a2_canon.py cannot distinguish")
    if score_suite([(cls, quiet, quiet)]).classes[0].detected:
        bad.append("scorer: a class that never fired scored as detected")
    errored = score_suite([(cls, Observation(failed=True), quiet)]).classes[0]
    if not errored.errored or errored.detected:
        bad.append("scorer: a FAILED run scored as a real outcome — an outage must not read "
                   "as a clean engine")
    return bad


def main() -> int:
    problems: list[str] = []
    if len(DEFECTS) < MIN_CLASSES:
        problems.append(
            f"the registry carries {len(DEFECTS)} defect class(es); MIN_CLASSES is "
            f"{MIN_CLASSES}. A baseline whose known-defect set is one cannot detect a NEW "
            f"defect a later slice introduces — it can only re-confirm the failure it was "
            f"built around."
        )
    codes = [d.code for d in DEFECTS]
    if len(set(codes)) != len(codes):
        problems.append(f"duplicate defect codes: {sorted({c for c in codes if codes.count(c) > 1})}")
    problems += _uncontrolled() + _shared_detectors() + _degenerate_detectors() + _self_check()

    if problems:
        print("composition eval-gate: the INSTRUMENT is not fit to measure\n")
        for p in problems:
            print(f"  · {p}")
        print("\nThis gate does not score the engine. It checks the suite can tell a working")
        print("detector from one that always fires — a degenerate suite reports a clean green.")
        return 1

    print(f"composition eval-gate: PASS — {len(DEFECTS)} seeded defect class(es), "
          f"each with a control and a distinct non-constant detector.")
    print("  Scored live by app/eval/suite.py; this half asserts only that the instrument "
          "can measure, not that the engine is good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
