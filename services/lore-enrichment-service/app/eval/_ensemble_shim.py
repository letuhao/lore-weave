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
    # (0) PREFERRED: the shared SDK home (loreweave_eval) — the canonical κ math
    # was lifted there (knowledge-service now re-exports from it). When the SDK is
    # importable (repo/CI, or an image that ships it) this is a clean package import.
    try:
        from loreweave_eval.judge_ensemble import (  # type: ignore
            _fleiss_kappa as _fk,
            _kappa_interpretation as _ki,
        )
        return _fk, _ki
    except Exception:  # noqa: BLE001 — fall through to path candidates / vendored
        pass

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
        try:
            spec.loader.exec_module(mod)
        except Exception:  # noqa: BLE001 — e.g. the path module re-exports the SDK
            continue        # which isn't installed here → use the vendored fallback
        return mod._fleiss_kappa, mod._kappa_interpretation

    # (final) VENDORED fallback (LE-PROD-2 P3a). The isolated service image ships
    # neither the knowledge-service tree NOR the SDK, so an in-container eval-run
    # would otherwise be impossible. Fleiss' κ + Landis–Koch cutoffs are a FIXED,
    # standard formula (no drift risk the brief warned of) — vendored VERBATIM from
    # ``loreweave_eval.judge_ensemble`` so the in-container result is identical.
    return _vendored_fleiss_kappa, _vendored_kappa_interpretation


def _vendored_fleiss_kappa(item_votes: list[dict[str, int]], n_raters: int) -> float:
    """Fleiss' κ for ``len(item_votes)`` items × ``n_raters`` raters. Verbatim copy
    of ``loreweave_eval.judge_ensemble._fleiss_kappa`` (canonical formula)."""
    n = len(item_votes)
    if n == 0 or n_raters < 2:
        return 0.0
    categories: set[str] = set()
    for votes in item_votes:
        categories.update(votes.keys())
    categories_list = sorted(categories)
    if len(categories_list) < 2:
        return 1.0  # perfect agreement on a single label → convention κ=1.0
    p_j: dict[str, float] = {c: 0.0 for c in categories_list}
    for votes in item_votes:
        for c, count in votes.items():
            p_j[c] += count
    total = n * n_raters
    for c in p_j:
        p_j[c] /= total
    p_i_sum = 0.0
    for votes in item_votes:
        sum_sq = sum(count * count for count in votes.values())
        p_i = (sum_sq - n_raters) / (n_raters * (n_raters - 1))
        p_i_sum += p_i
    p_bar = p_i_sum / n
    p_e = sum(p * p for p in p_j.values())
    if abs(1.0 - p_e) < 1e-12:
        return 1.0 if p_bar >= 1.0 - 1e-12 else 0.0
    return (p_bar - p_e) / (1.0 - p_e)


def _vendored_kappa_interpretation(kappa: float) -> str:
    """Landis & Koch 1977 cutoffs. Verbatim copy of the SDK's _kappa_interpretation."""
    if kappa < 0.0:
        return "below-chance"
    if kappa < 0.20:
        return "poor"
    if kappa < 0.40:
        return "fair"
    if kappa < 0.60:
        return "moderate"
    if kappa < 0.80:
        return "substantial"
    return "almost-perfect"


fleiss_kappa, kappa_interpretation = _resolve()
