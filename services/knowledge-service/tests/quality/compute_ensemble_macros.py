"""Back-compat shim — moved to ``loreweave_eval.compute_ensemble_macros`` (Q0).

The per-judge macro P/R/F1 + the DISJOINT median-of-record + bootstrap CI were
lifted into the shared ``loreweave_eval`` SDK package so BOTH knowledge-service
(R&D today) and learning-service (the online-eval consumer, phase Q4) import the
SAME code. This module re-exports everything from the new home so existing
``tests.quality.compute_ensemble_macros`` / ``quality.compute_ensemble_macros``
imports — and ``python -m tests.quality.compute_ensemble_macros <dir>`` — keep
working unchanged. New code should import from
``loreweave_eval.compute_ensemble_macros`` directly.
"""

import sys as _sys

from loreweave_eval import compute_ensemble_macros as _moved

globals().update(
    {k: v for k, v in vars(_moved).items() if not k.startswith("__")}
)
del _moved


if __name__ == "__main__":
    # Preserve `python -m tests.quality.compute_ensemble_macros <variant-dir>`.
    _sys.exit(main())  # type: ignore[name-defined]  # `main` copied above
