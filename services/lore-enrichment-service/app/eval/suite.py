"""Eval suite loader + weighted aggregation + baseline-diff (RAID C15).

MIRRORS the climate-eval pattern (``scripts/climate_eval.py`` +
``eval/climate-eval-suite.toml`` + ``eval/baselines/*.json``) in SEPARATE files:
a TOML suite carries the per-sub-score ``[weights]`` + ``[regression]``
thresholds + the gate threshold; a versioned baseline JSON freezes a reference
scorecard; ``diff_against_baseline`` reports per-sub-score regressions vs that
baseline. NEVER edits the climate files — this is the enrichment namespace.

The composite is a weighted sum of the five sub-scores (each 0..100), matching
the climate ``composite_score`` shape. The GATE threshold (``[gate].min_composite``)
is what C16/C17 read: an eval run with ``composite >= min_composite`` AND no
regression AND an acceptable judge ensemble ``passes`` → P2/P3 may activate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

__all__ = [
    "SUBSCORE_KEYS",
    "EvalSuite",
    "Scorecard",
    "BaselineDiff",
    "load_suite",
    "composite_score",
    "diff_against_baseline",
]

#: The five weighted sub-scores (cultural-fidelity), in fixed order.
SUBSCORE_KEYS: tuple[str, ...] = (
    "schema", "canon", "anachronism", "provenance", "usefulness",
)


@dataclass(frozen=True)
class EvalSuite:
    """Parsed enrichment-eval suite TOML."""

    version: str
    weights: dict[str, float]
    regression: dict[str, float]
    gate: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Fail loud on a malformed suite (missing/unknown sub-score weight,
        weights not summing to ~1.0). Catches a hand-edit that would silently
        skew the composite."""
        missing = [k for k in SUBSCORE_KEYS if k not in self.weights]
        if missing:
            raise ValueError(f"suite weights missing sub-scores: {missing}")
        unknown = [k for k in self.weights if k not in SUBSCORE_KEYS]
        if unknown:
            raise ValueError(f"suite weights has unknown sub-scores: {unknown}")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"suite weights must sum to 1.0, got {total}")
        if "min_composite" not in self.gate:
            raise ValueError("suite [gate] missing min_composite")


@dataclass(frozen=True)
class Scorecard:
    """The aggregate result of one eval run over a proposal set.

    ``subscores`` are the MEAN per-sub-score across all scored proposals (0..100);
    ``composite`` the weighted sum. ``fleiss_kappa`` / ``kappa_interpretation``
    surface the judge-ensemble agreement on the subjective usefulness sub-score.
    ``passed`` reflects the GATE decision computed by :class:`~app.eval.gate`.
    """

    suite_version: str
    baseline_version: str | None
    n_proposals: int
    subscores: dict[str, float]
    composite: float
    fleiss_kappa: float | None
    kappa_interpretation: str
    judge_ensemble_acceptable: bool
    passed: bool
    issues: list[str] = field(default_factory=list)
    per_proposal: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "suite_version": self.suite_version,
            "baseline_version": self.baseline_version,
            "n_proposals": self.n_proposals,
            "subscores": self.subscores,
            "composite": self.composite,
            "fleiss_kappa": self.fleiss_kappa,
            "kappa_interpretation": self.kappa_interpretation,
            "judge_ensemble_acceptable": self.judge_ensemble_acceptable,
            "passed": self.passed,
            "issues": self.issues,
            "per_proposal": self.per_proposal,
        }


@dataclass(frozen=True)
class BaselineDiff:
    """Per-sub-score + composite delta vs a frozen baseline scorecard."""

    composite_delta: float
    subscore_deltas: dict[str, float]
    regressions: list[str]  # human-readable regression notes (threshold-crossing)
    regressed: bool


def load_suite(path: Path) -> EvalSuite:
    """Load + validate the enrichment-eval suite TOML."""
    with path.open("rb") as f:
        raw = tomllib.load(f)
    suite = EvalSuite(
        version=str(raw.get("version", "enrichment-v0")),
        weights={k: float(v) for k, v in (raw.get("weights") or {}).items()},
        regression={k: float(v) for k, v in (raw.get("regression") or {}).items()},
        gate=dict(raw.get("gate") or {}),
        raw=raw,
    )
    suite.validate()
    return suite


def composite_score(subscores: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted sum of the five sub-scores (mirror climate composite_score)."""
    return round(
        sum(weights[k] * float(subscores.get(k, 0.0)) for k in SUBSCORE_KEYS),
        2,
    )


def diff_against_baseline(
    subscores: dict[str, float],
    composite: float,
    baseline: dict[str, Any],
    regression: dict[str, float],
) -> BaselineDiff:
    """Diff a scorecard against a frozen baseline JSON. A regression is flagged
    when the composite drops by more than ``composite_max_regression`` OR any
    sub-score drops by more than ``subscore_max_regression`` (climate
    baseline-diff semantics, enrichment namespace).
    """
    base_sub = baseline.get("subscores") or {}
    base_comp = float(baseline.get("composite", 0.0))
    comp_delta = round(composite - base_comp, 2)

    sub_deltas: dict[str, float] = {}
    regressions: list[str] = []

    comp_max_reg = regression.get("composite_max_regression", 5.0)
    sub_max_reg = regression.get("subscore_max_regression", 10.0)

    if comp_delta <= -comp_max_reg:
        regressions.append(
            f"composite regressed {comp_delta:+.2f} (> {comp_max_reg} threshold)"
        )

    for k in SUBSCORE_KEYS:
        cur = float(subscores.get(k, 0.0))
        prev = float(base_sub.get(k, 0.0))
        d = round(cur - prev, 1)
        sub_deltas[k] = d
        if d <= -sub_max_reg:
            regressions.append(f"{k} regressed {d:+.1f} (> {sub_max_reg} threshold)")

    return BaselineDiff(
        composite_delta=comp_delta,
        subscore_deltas=sub_deltas,
        regressions=regressions,
        regressed=bool(regressions),
    )
