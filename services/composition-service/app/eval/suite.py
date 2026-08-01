"""Scoring for the seeded-defect suite (spec §S10).

A class is DETECTED only when its detector fires on the seeded variant **and stays quiet on
the control**. That is the whole difference between this and a hit count: the existing
harness reports "5/5 detected" for a working canon loop and for an engine that revises every
scene unconditionally, because it never runs the clean variant.

Reuses `loreweave_eval.calibration.confusion` rather than re-deriving a 2×2 — that module
already models "ground truth vs. what the judge said", which is exactly this shape with
"seeded" as ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass

from loreweave_eval.calibration import Confusion, confusion

from app.eval.defects import DefectClass, Observation, Outcome


def observe(cls: DefectClass, obs: Observation) -> Outcome:
    """Reduce one engine result to an outcome.

    An ERROR is deliberately its own outcome. Folding a failed run into QUIET would score an
    outage as a detector that correctly stayed silent — and on the seeded variant that reads
    as a MISS, on the control as a PASS. Either way the number is fiction.

    A BLIND class (`blocked_on`) and an observation MISSING a key the detector declares it
    reads both resolve to ERROR for the same reason: `dict.get` returns None, the detector
    goes quiet, and quiet-on-a-seeded-defect scores as MISSED — i.e. "the engine has this
    defect" when the truth is "the instrument cannot see it". A false negative dressed as a
    finding is the worst output this suite could produce, so the two are made loud instead.
    """
    if cls.blocked_on:
        return Outcome.ERROR
    if obs.failed:
        return Outcome.ERROR
    absent = [k for k in cls.reads if k not in obs.fields]
    if absent:
        return Outcome.ERROR
    return Outcome.FIRED if cls.detector(obs) else Outcome.QUIET


def missing_fields(cls: DefectClass, obs: Observation) -> list[str]:
    """Declared reads the observation did not supply — the typo/drift hole a freeform
    `dict[str, object]` leaves open."""
    return [k for k in cls.reads if k not in obs.fields]


@dataclass(frozen=True)
class ClassResult:
    code: str
    seeded: Outcome
    control: Outcome

    @property
    def detected(self) -> bool:
        """Fired where the defect is, quiet where it is not. Both halves required."""
        return self.seeded is Outcome.FIRED and self.control is Outcome.QUIET

    @property
    def over_flagged(self) -> bool:
        """Fired on the CONTROL — the failure mode the old harness could not see."""
        return self.control is Outcome.FIRED

    @property
    def missed(self) -> bool:
        return self.seeded is Outcome.QUIET

    @property
    def errored(self) -> bool:
        return Outcome.ERROR in (self.seeded, self.control)

    #: Why this class scored nothing, when it scored nothing. Distinguishing "the instrument
    #: is blind here" from "the run failed" from "the engine missed it" is the whole point —
    #: all three previously looked like MISSED.
    blocked_on: str = ""

    def verdict(self) -> str:
        if self.blocked_on:
            return f"BLIND — not scored; the engine emits nothing to read ({self.blocked_on})"
        if self.errored:
            return "ERROR — a run failed; this class scored nothing"
        if self.detected:
            return "detected"
        if self.over_flagged and self.missed:
            return "INVERTED — quiet on the defect, fired on the clean control"
        if self.over_flagged:
            return "OVER-FLAGS — fired on the clean control, so the seeded hit proves nothing"
        return "MISSED — did not fire on the seeded defect"


def score_class(cls: DefectClass, seeded: Observation, control: Observation) -> ClassResult:
    return ClassResult(
        code=cls.code,
        seeded=observe(cls, seeded),
        control=observe(cls, control),
        blocked_on=cls.blocked_on,
    )


@dataclass(frozen=True)
class SuiteResult:
    classes: tuple[ClassResult, ...]
    #: (ground_truth_has_defect, detector_fired) pairs, feeding the 2×2.
    confusion: Confusion

    @property
    def detected(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.classes if c.detected)

    @property
    def blind(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.classes if c.blocked_on)

    @property
    def problems(self) -> tuple[tuple[str, str], ...]:
        return tuple((c.code, c.verdict()) for c in self.classes if not c.detected)

    def summary(self) -> str:
        # The denominator is the SCORABLE classes, not every registered one. Dividing by all
        # of them would let adding a blind class quietly lower the score, and dividing the
        # other way would let it quietly raise it; both hide the blindness in an average.
        cm = self.confusion
        scorable = [c for c in self.classes if not c.blocked_on]
        blind = f" · {len(self.blind)} BLIND (not scored)" if self.blind else ""
        return (
            f"{len(self.detected)}/{len(scorable)} scorable classes detected "
            f"(fired-on-defect {cm.tp}, missed {cm.fn}, "
            f"over-flagged {cm.fp}, correctly-quiet {cm.tn}){blind}"
        )


def score_suite(runs: list[tuple[DefectClass, Observation, Observation]]) -> SuiteResult:
    """Score every class. `runs` is (class, seeded-observation, control-observation).

    The confusion pairs use ground truth = "this variant HAS the defect", so a control that
    fires lands in `fp` — visible as a number rather than absent from the report, which is
    the entire point of adding controls.
    """
    results: list[ClassResult] = []
    pairs: list[tuple[bool, bool]] = []
    for cls, seeded, control in runs:
        r = score_class(cls, seeded, control)
        results.append(r)
        # An errored run contributes NO pair: scoring it either way invents a data point.
        if r.seeded is not Outcome.ERROR:
            pairs.append((True, r.seeded is Outcome.FIRED))
        if r.control is not Outcome.ERROR:
            pairs.append((False, r.control is Outcome.FIRED))
    return SuiteResult(classes=tuple(results), confusion=confusion(pairs))
