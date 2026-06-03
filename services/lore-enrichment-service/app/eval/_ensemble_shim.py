"""Import shim: REUSE the knowledge-service judge-ensemble Fleiss-κ methodology.

The C15 brief LOCKS "reuse the judge-ENSEMBLE methodology" and "Do NOT modify
``services/knowledge-service/tests/quality/`` judge-ensemble code — import/reuse
only". This shim is that import seam: it pulls ``_fleiss_kappa`` +
``_kappa_interpretation`` from ``tests/quality/judge_ensemble.py`` (which is pure
stdlib and imports cleanly standalone) by adding the knowledge-service root to
``sys.path`` if the package is not already importable.

We import the κ MATH only — the lore-enrichment usefulness scorer composes its
own ensemble loop (majority + partial-credit) in ``judge_usefulness.py`` over
proposal verdicts, mirroring the same methodology. No code is copied or edited
in the knowledge-service tree.

Resolution order:
  1. already importable (in-container PYTHONPATH, or monorepo run from root) —
     ``tests.quality.judge_ensemble`` / ``quality.judge_ensemble``;
  2. add ``<repo>/services/knowledge-service`` to ``sys.path`` and import
     ``tests.quality.judge_ensemble``.

If neither resolves (a deployment that does not ship the knowledge-service tree
alongside), we raise a clear ImportError naming the missing dependency rather
than silently re-implementing the math — a re-implementation would risk drifting
from the canonical κ formula the brief says to reuse.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable

__all__ = ["fleiss_kappa", "kappa_interpretation"]


def _resolve() -> tuple[Callable[..., float], Callable[[float], str]]:
    """Load the knowledge-service judge-ensemble κ helpers by FILE PATH.

    We load the module file directly (``importlib.util.spec_from_file_location``)
    rather than by the ``tests.quality.judge_ensemble`` package name: this
    service has its OWN ``tests`` package, so a name-based import would collide
    with it. Loading by path under a private module name reuses the canonical
    κ math without copying it and without touching either ``tests`` namespace.
    """
    # __file__ = services/lore-enrichment-service/app/eval/_ensemble_shim.py
    here = Path(__file__).resolve()
    services_dir = here.parents[3]  # .../services
    candidates = [
        services_dir / "knowledge-service" / "tests" / "quality" / "judge_ensemble.py",
        # in-container layout: PYTHONPATH=/app, quality alongside tests
        Path("/app") / "tests" / "quality" / "judge_ensemble.py",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        mod_name = "_loreenrich_judge_ensemble"
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        # Register BEFORE exec so the module's @dataclass decorators can resolve
        # their own module namespace (dataclasses looks the module up in
        # sys.modules by __module__).
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod._fleiss_kappa, mod._kappa_interpretation

    raise ImportError(
        "knowledge-service judge-ensemble module not found — the C15 eval reuses "
        "its Fleiss-κ methodology by import (LOCKED). Expected at "
        f"{candidates[0]}"
    )


fleiss_kappa, kappa_interpretation = _resolve()
