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
    """
    if obs.failed:
        return Outcome.ERROR
    return Outcome.FIRED if cls.detector(obs) else Outcome.QUIET


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

    def verdict(self) -> str:
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
    return ClassResult(code=cls.code, seeded=observe(cls, seeded), control=observe(cls, control))


@dataclass(frozen=True)
class SuiteResult:
    classes: tuple[ClassResult, ...]
    #: (ground_truth_has_defect, detector_fired) pairs, feeding the 2×2.
    confusion: Confusion

    @property
    def detected(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.classes if c.detected)

    @property
    def problems(self) -> tuple[tuple[str, str], ...]:
        return tuple((c.code, c.verdict()) for c in self.classes if not c.detected)

    def summary(self) -> str:
        cm = self.confusion
        return (
            f"{len(self.detected)}/{len(self.classes)} classes detected "
            f"(fired-on-defect {cm.tp}, missed {cm.fn}, "
            f"over-flagged {cm.fp}, correctly-quiet {cm.tn})"
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
