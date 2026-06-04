"""Judge calibration + panel-safety (track phase Q3.5).

Before an LLM judge is trusted as the metric-of-record, it must agree with the
ONE ground truth we actually have — human corrections. This module computes that
agreement (raw agreement, balanced accuracy, Cohen's kappa) over paired
``(human_says_correct, judge_says_correct)`` labels and gates a judge on it.

It also formalizes the anti-self-reinforcement rule in code (not a manual env
step): ``panel_safety`` flags a panel whose metric-of-record set has fewer than
two judges, or in which a judge IS the extractor/filter that produced the output
(a model grading its own work — measured at ~4-5pp inflation). The scorer surfaces
this on every ``EvalResult`` so a self-reinforcing run is visible, not silent.

Pure functions — no I/O. Pair construction (corrections vs per-item judge
verdicts) is the caller's job (phase Q4, when per-item verdicts are persisted).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

# A label pair: (human_says_correct, judge_says_correct). Human is ground truth;
# the "positive" class is "the item is correct".
Pair = tuple[bool, bool]


@dataclass
class Confusion:
    """Counts with the HUMAN as ground truth, positive = "item is correct"."""

    tp: int = 0  # human correct, judge correct (agree: good)
    tn: int = 0  # human incorrect, judge incorrect (agree: bad)
    fp: int = 0  # human incorrect, judge correct (judge MISSED the error)
    fn: int = 0  # human correct, judge incorrect (judge OVER-flagged)

    @property
    def n(self) -> int:
        return self.tp + self.tn + self.fp + self.fn


def confusion(pairs: Iterable[Pair]) -> Confusion:
    c = Confusion()
    for human, judge in pairs:
        if human and judge:
            c.tp += 1
        elif (not human) and (not judge):
            c.tn += 1
        elif (not human) and judge:
            c.fp += 1
        else:  # human and not judge
            c.fn += 1
    return c


def raw_agreement(pairs: Sequence[Pair]) -> float | None:
    """Fraction of pairs where human and judge agree. None when no pairs."""
    if not pairs:
        return None
    agree = sum(1 for h, j in pairs if h == j)
    return agree / len(pairs)


def balanced_accuracy(pairs: Sequence[Pair]) -> float | None:
    """(sensitivity + specificity) / 2, human as truth.

    Returns None when EITHER class (human-correct / human-incorrect) is absent —
    balanced accuracy is undefined without both, and a judge that has only ever
    seen one class cannot be trusted (gate fails on None).
    """
    c = confusion(pairs)
    pos = c.tp + c.fn  # human-correct items
    neg = c.tn + c.fp  # human-incorrect items
    if pos == 0 or neg == 0:
        return None
    sensitivity = c.tp / pos  # judge agrees on the good items
    specificity = c.tn / neg  # judge agrees on the bad items
    return (sensitivity + specificity) / 2.0


def cohen_kappa(pairs: Sequence[Pair]) -> float | None:
    """Cohen's kappa for the paired binary labels. None when undefined
    (no pairs, or expected agreement == 1 i.e. a degenerate single-class panel)."""
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for h, j in pairs if h == j) / n
    p_h = sum(1 for h, _ in pairs if h) / n
    p_j = sum(1 for _, j in pairs if j) / n
    pe = p_h * p_j + (1 - p_h) * (1 - p_j)
    if pe >= 1.0:  # one class only on both sides — kappa undefined
        return None
    return (po - pe) / (1 - pe)


@dataclass
class JudgeCalibration:
    """One judge's agreement with human corrections + the trust gate verdict."""

    judge_label: str
    n_pairs: int
    raw_agreement: float | None
    balanced_accuracy: float | None
    cohen_kappa: float | None
    passed: bool
    min_balanced_accuracy: float
    min_kappa: float
    confusion: dict


def calibrate_judge(
    judge_label: str,
    pairs: Sequence[Pair],
    *,
    min_balanced_accuracy: float = 0.75,
    min_kappa: float = 0.4,
) -> JudgeCalibration:
    """Calibrate a judge against human-correction ground truth. ``passed`` is the
    Q3.5 trust gate: balanced accuracy AND kappa both clear their thresholds
    (defaults: 0.75 balanced accuracy, 0.4 = "moderate" kappa). A degenerate set
    (undefined metric) does NOT pass."""
    ba = balanced_accuracy(pairs)
    kappa = cohen_kappa(pairs)
    passed = (
        ba is not None
        and kappa is not None
        and ba >= min_balanced_accuracy
        and kappa >= min_kappa
    )
    c = confusion(pairs)
    return JudgeCalibration(
        judge_label=judge_label,
        n_pairs=len(pairs),
        raw_agreement=raw_agreement(pairs),
        balanced_accuracy=ba,
        cohen_kappa=kappa,
        passed=passed,
        min_balanced_accuracy=min_balanced_accuracy,
        min_kappa=min_kappa,
        confusion={"tp": c.tp, "tn": c.tn, "fp": c.fp, "fn": c.fn},
    )


# ── Panel safety (anti-self-reinforcement, enforced in code) ──────────


@dataclass
class PanelSafety:
    """Whether a scored run's metric-of-record panel is trustworthy.

    ``safe`` is False when fewer than two judges remain after excluding the
    extractor/filter (the disjoint median collapses), or when a generator model
    appears AS a judge (self-grading). The scorer attaches this to every
    EvalResult so a self-reinforcing run is visible, not silent.
    """

    n_judges: int
    n_disjoint_judges: int
    generators_in_panel: list[str] = field(default_factory=list)
    safe: bool = False
    reason: str = ""


def panel_safety(excluded_refs: Iterable[str], judge_uuids: Sequence[str]) -> PanelSafety:
    """Assess a panel given the exclusion set (extractor + filter refs from a
    JudgePanel) and the judge UUIDs actually used. ``excluded_refs`` is normally
    ``panel.excluded``."""
    excluded = {r for r in excluded_refs if r}
    generators_in_panel = [u for u in judge_uuids if u in excluded]
    disjoint = [u for u in judge_uuids if u not in excluded]
    n_disjoint = len(disjoint)
    if generators_in_panel:
        safe = False
        reason = (
            f"{len(generators_in_panel)} judge(s) are the extractor/filter "
            "(self-grading) — excluded from the metric of record"
        )
    elif n_disjoint < 2:
        safe = False
        reason = f"only {n_disjoint} disjoint judge(s) — need >= 2 for a robust median"
    else:
        safe = True
        reason = f"{n_disjoint} disjoint judges, no generator in panel"
    return PanelSafety(
        n_judges=len(judge_uuids),
        n_disjoint_judges=n_disjoint,
        generators_in_panel=generators_in_panel,
        safe=safe,
        reason=reason,
    )
