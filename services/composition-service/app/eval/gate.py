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

from pathlib import Path

from app.eval.defects import (
    DEFECTS, MIN_CLASSES, MIN_SCORABLE, DefectClass, Observation,
)
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


_APP = Path(__file__).resolve().parents[1]


def _engine_emits(key: str) -> bool:
    """Does the service mention this observation key anywhere outside app/eval?

    A crude check on purpose. It cannot prove the engine PRODUCES the field, but zero
    occurrences across the whole service proves it does not — and that is the case that
    matters, because a detector reading an absent key is permanently quiet, and quiet on a
    seeded defect scores as MISSED. "The engine has this defect" and "the instrument cannot
    see" would be the same output.
    """
    needle = f'"{key}"'
    alt = f"'{key}'"
    for p in _APP.rglob("*.py"):
        s = p.as_posix()
        if "/eval/" in s or "__pycache__" in s:
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if needle in body or alt in body:
            return True
    return False


def _blindness() -> list[str]:
    """Two directions, and the second is the one that keeps this honest over time.

    · A class NOT declared blind whose detector reads a key the service never mentions is
      silently blind — the state the whole registry shipped in.
    · A class declared blind whose keys are ALL present now has a stale block, and leaving it
      would permanently exclude a class the instrument could actually score.
    """
    bad: list[str] = []
    for d in DEFECTS:
        absent = [k for k in d.reads if not _engine_emits(k)]
        if not d.reads:
            bad.append(f"{d.code}: declares no `reads`, so nothing can check whether the "
                       f"engine emits what its detector consumes")
        elif d.blocked_on and not absent:
            bad.append(f"{d.code}: declared blocked_on, but the service now mentions every "
                       f"key it reads ({', '.join(d.reads)}) — lift the block or correct it")
        elif not d.blocked_on and absent:
            bad.append(f"{d.code}: reads {', '.join(absent)}, which the service never "
                       f"mentions — the detector would be permanently quiet and every run "
                       f"would score MISSED. Declare `blocked_on` or fix the key.")
    return bad


def _undriveable() -> list[str]:
    """A class that is NOT blind but has no live seeder measures nothing either.

    `blocked_on` covers "the engine emits no field for this". It does NOT cover "the field
    exists, the detector is fine, and nobody wrote the seeding" — and the first live run found
    exactly that: `gone_cast_asserted_active` scored `error/error` while the gate reported it
    SCORABLE. Scorable and driveable are different properties, and only one of them was
    checked.
    """
    from app.eval.driver import LiveDriver

    seeders = set(LiveDriver(token="", model_ref="")._seeders())
    return [d.code for d in DEFECTS if not d.blocked_on and d.code not in seeders]


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
    scorable = [d for d in DEFECTS if not d.blocked_on]
    if len(scorable) < MIN_SCORABLE:
        problems.append(
            f"only {len(scorable)} class(es) are SCORABLE (the rest are blind on fields the "
            f"engine does not emit); MIN_SCORABLE is {MIN_SCORABLE}. A registry can look "
            f"broad and measure almost nothing."
        )
    undriveable = _undriveable()
    if undriveable:
        problems.append(
            f"declared SCORABLE but no live seeder: {', '.join(undriveable)}. `blocked_on` "
            f"covers 'the engine emits no such field'; it does not cover 'nobody wrote the "
            f"seeding'. Such a class scores error/error on every live run while this gate "
            f"counts it toward MIN_SCORABLE — the exact gap the first live run exposed."
        )
    problems += (_uncontrolled() + _shared_detectors() + _degenerate_detectors()
                 + _blindness() + _self_check())

    if problems:
        print("composition eval-gate: the INSTRUMENT is not fit to measure\n")
        for p in problems:
            print(f"  · {p}")
        print("\nThis gate does not score the engine. It checks the suite can tell a working")
        print("detector from one that always fires — a degenerate suite reports a clean green.")
        return 1

    blind = [d for d in DEFECTS if d.blocked_on]
    print(f"composition eval-gate: PASS — {len(DEFECTS)} seeded defect class(es), "
          f"each with a control and a distinct non-constant detector.")
    print(f"  {len(DEFECTS) - len(blind)} SCORABLE · {len(blind)} blind on a field the engine "
          f"does not emit yet:")
    for d in blind:
        print(f"    · {d.code} — reads {', '.join(d.reads)}")
    print("  Scored live by app/eval/suite.py; this half asserts only that the instrument "
          "can measure, not that the engine is good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
