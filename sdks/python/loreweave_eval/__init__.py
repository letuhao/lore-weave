"""loreweave_eval — production-grade extraction-quality scoring.

Lifted from ``knowledge-service/tests/quality/`` (track phase Q0) so the same
mature scorer (cycles 72–74) can be imported by BOTH knowledge-service (R&D
today) and learning-service (the online-eval consumer, phase Q4) and write to
a database instead of only the filesystem.

Package API:
  - ``JudgePanel`` / ``panel_from_env``  — the judge-ensemble + exclusion config
  - ``score_dump`` → ``EvalResult``      — score a saved dump into structured data
  - ``EvalSink`` / ``FileSink``          — the persistence seam (DbSink = Q1, in
                                            learning-service)
  - ``JudgeLLMClient``                   — the injected-client Protocol (the seam)

Submodules (import explicitly for the lower-level functions):
  ``eval_harness`` · ``llm_judge`` · ``judge_ensemble`` · ``compute_ensemble_macros``

``score_dump`` / ``FileSink`` are exposed lazily (PEP 562 ``__getattr__``) so
``import loreweave_eval`` stays cheap and ``python -m
loreweave_eval.compute_ensemble_macros`` runs without a runpy double-import
warning; ``JudgePanel`` and the client Protocol are lightweight and eager.
"""

from __future__ import annotations

from ._client import JudgeJob, JudgeLLMClient
from .panel import (
    DEFAULT_EXTRACTOR_REF,
    DEFAULT_FILTER_REF,
    JudgePanel,
    panel_from_env,
)

__all__ = [
    # eager (lightweight)
    "JudgeJob",
    "JudgeLLMClient",
    "JudgePanel",
    "panel_from_env",
    "DEFAULT_EXTRACTOR_REF",
    "DEFAULT_FILTER_REF",
    # lazy (pull in the scorer, which imports compute_ensemble_macros)
    "EvalResult",
    "JudgeScore",
    "score_dump",
    "EvalSink",
    "FileSink",
    # calibration (Q3.5) — pure, but lazy to keep import loreweave_eval cheap
    "calibrate_judge",
    "JudgeCalibration",
    "panel_safety",
    "PanelSafety",
    "cohen_kappa",
    "balanced_accuracy",
]

_LAZY = {
    "EvalResult": ("scorer", "EvalResult"),
    "JudgeScore": ("scorer", "JudgeScore"),
    "score_dump": ("scorer", "score_dump"),
    "EvalSink": ("sinks", "EvalSink"),
    "FileSink": ("sinks", "FileSink"),
    "calibrate_judge": ("calibration", "calibrate_judge"),
    "JudgeCalibration": ("calibration", "JudgeCalibration"),
    "panel_safety": ("calibration", "panel_safety"),
    "PanelSafety": ("calibration", "PanelSafety"),
    "cohen_kappa": ("calibration", "cohen_kappa"),
    "balanced_accuracy": ("calibration", "balanced_accuracy"),
}


def __getattr__(name: str):  # PEP 562 — lazy submodule re-exports
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    mod, attr = target
    return getattr(importlib.import_module(f"{__name__}.{mod}"), attr)
