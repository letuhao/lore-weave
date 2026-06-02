"""Back-compat shim — moved to ``loreweave_eval.judge_ensemble`` (track phase Q0).

The multi-judge ensemble (Fleiss κ, bias metrics, majority vote) was lifted into
the shared ``loreweave_eval`` SDK package so BOTH knowledge-service (R&D today)
and learning-service (the online-eval consumer, phase Q4) import the SAME code.
This module re-exports everything from the new home so existing
``tests.quality.judge_ensemble`` / ``quality.judge_ensemble`` imports keep
working unchanged. New code should import from ``loreweave_eval.judge_ensemble``
directly.
"""

from loreweave_eval import judge_ensemble as _moved

globals().update(
    {k: v for k, v in vars(_moved).items() if not k.startswith("__")}
)
del _moved
