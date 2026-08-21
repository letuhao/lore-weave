"""Scorer facade — score a saved judge dump into a structured EvalResult.

This is the single programmatic entry the production consumers call: the online
-eval consumer (track phase Q4) and the DB persistence (Q1 ``DbSink``). It is a
THIN wrapper over ``compute_ensemble_macros`` (the same functions ``main()``
uses), so ``score_dump`` returns exactly the numbers the markdown table prints —
the disjoint median-of-record + bootstrap CI — but as data instead of stdout.

``score_dump`` is parameterized by a ``JudgePanel`` (Q0-0b): the exclusion set
(extractor + filter, to defeat self-reinforcement) is enforced HERE, in code,
not via a manual env step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .calibration import panel_safety
from .compute_ensemble_macros import (
    _median,
    disjoint_median_with_ci,
    load_judge,
)
from .panel import JudgePanel


@dataclass
class JudgeScore:
    """One judge's macro view + its role under the panel."""

    label: str
    uuid: str
    role: str  # independent | extractor | filter
    macro_p: float | None
    macro_r: float | None
    macro_f1: float | None


@dataclass
class EvalResult:
    """The metric-of-record for one scored dump, structured for persistence.

    ``disjoint_median_f1`` is the number that ships (median over judges that are
    NEITHER the extractor NOR the filter); ``full_panel_median_f1`` is kept for
    the historical/self-graded comparison only.
    """

    variant_label: str
    per_judge: list[JudgeScore] = field(default_factory=list)
    full_panel_median_f1: float | None = None
    disjoint_median_f1: float | None = None
    disjoint_ci_low: float | None = None
    disjoint_ci_high: float | None = None
    n_disjoint_judges: int = 0
    n_common_chapters: int = 0
    fleiss_kappa: float | None = None
    n_judges_total: int = 0
    # Q3.5 — anti-self-reinforcement, enforced + visible. False when the
    # metric-of-record panel has <2 disjoint judges or a generator self-grades.
    panel_safe: bool = False
    panel_safety_reason: str = ""
    #: S13 — whether the exclusion set was DEFAULTED and matched nothing. It used to stop at
    #: `PanelSafety` and never reach here, so the one structure built "for persistence" could
    #: not carry the fact at all. `panel_safe` stays True in that case on purpose (see
    #: `panel_safety`), which is exactly why this needs its own field rather than being folded
    #: into it: the panel is safe AS FAR AS ANYONE CAN TELL, and that qualifier is the whole
    #: point.
    exclusion_unverified: bool = False


def metric_of_record_blockers(result: "EvalResult") -> list[str]:
    """Why this number may NOT be quoted as the metric of record. Empty ⇒ it may.

    One place answers the question, because it was previously answered by reading
    `panel_safe` and nothing else — and `panel_safe` is deliberately True for a panel whose
    exclusion set matched nothing. That combination reads as "clean" and means "clean, or a
    self-grader is sitting in this panel ungraded and we cannot tell". A caller checking one
    boolean cannot distinguish them; this function is what makes the distinction reachable.
    """
    blockers: list[str] = []
    if not result.panel_safe:
        blockers.append(result.panel_safety_reason or "panel not safe")
    if result.exclusion_unverified:
        blockers.append(
            "the exclusion set came from defaults and matched NO judge in this run: "
            "`user_model_id`s are per-machine, so this is what a panel from another "
            "deployment looks like — a generator may be self-grading here, unexcluded"
        )
    return blockers


def _read_fleiss(dump_root: Path) -> float | None:
    report = dump_root / "judge_ensemble_report.json"
    if not report.is_file():
        return None
    try:
        return json.loads(report.read_text(encoding="utf-8")).get("fleiss_kappa")
    except (ValueError, OSError):
        return None


def score_dump(
    dump_root: Path,
    panel: JudgePanel,
    *,
    n_boot: int = 2000,
    variant_label: str | None = None,
) -> EvalResult:
    """Score every ``judge_verdicts_*.json`` under ``dump_root`` into an
    ``EvalResult``. Mirrors ``compute_ensemble_macros.main()`` exactly, so the
    aggregate numbers match the printed table.
    """
    dump_root = Path(dump_root)
    files = sorted(dump_root.glob("judge_verdicts_*.json"))
    judges = [load_judge(f) for f in files]

    per_judge = [
        JudgeScore(
            label=j["label"],
            uuid=j["uuid"],
            role=panel.role_of(j["uuid"]),
            macro_p=j["macro_p"],
            macro_r=j["macro_r"],
            macro_f1=j["macro_f1"],
        )
        for j in judges
    ]

    all_f1 = [j["macro_f1"] for j in judges if j["macro_f1"] is not None]
    full_median = _median(all_f1) if all_f1 else None

    disjoint = [j for j in judges if j["uuid"] not in panel.excluded]
    res = disjoint_median_with_ci(disjoint, n_boot=n_boot)

    # S13 — forward whether the exclusion set was DEFAULTED. Without it, a panel whose refs
    # came from another deployment's hardcoded UUIDs reports `safe=True, no generator in
    # panel`, which is exactly what a genuinely clean panel reports.
    safety = panel_safety(
        panel.excluded, [j["uuid"] for j in judges],
        exclusion_is_defaulted=panel.exclusion_is_defaulted,
    )

    return EvalResult(
        variant_label=variant_label or dump_root.name,
        per_judge=per_judge,
        full_panel_median_f1=full_median,
        disjoint_median_f1=res["median_f1"],
        disjoint_ci_low=res["ci_low"],
        disjoint_ci_high=res["ci_high"],
        n_disjoint_judges=res["n_judges"],
        n_common_chapters=res["n_common_chapters"],
        fleiss_kappa=_read_fleiss(dump_root),
        n_judges_total=len(judges),
        panel_safe=safety.safe,
        panel_safety_reason=safety.reason,
        exclusion_unverified=safety.exclusion_unverified,
    )
