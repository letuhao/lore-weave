"""loreweave_vecmath — shared pure-stdlib vector-similarity math.

Promoted from independently-maintained near-duplicate cosine-similarity
implementations, each carrying an inline "promote to a shared lib if a
3rd/4th site appears" comment:

  - lore-enrichment-service/app/retrieval/store.py::cosine_similarity
  - composition-service/app/db/repositories/references.py::_cosine
  - composition-service/app/db/repositories/motif_retrieve.py::_cosine
    (its own docstring said "Copy of references.py:_cosine ... If a 3rd
    cosine site appears, F0 promotes this to db/repositories/_vec.py")
  - knowledge-service/app/context/selectors/passages.py::_cosine / _norm

Chat-service's new embedding-backed tool/skill search is the 4th independent
*site* (beyond composition-service's own two internal copies) that triggered
the promotion — see
docs/plans/2026-07-07-mcp-discovery-and-reliability-hardening.md design item 2.

Two call shapes, both pure stdlib (no numpy — matches every existing site's
convention; this is a low-volume in-process fallback over corpora the
platform does NOT put in pgvector, so it stays a dependency-free primitive):

  - `cosine_similarity(a, b)` — computes both norms inline in one pass.
    Fits a one-shot / infrequent comparison (e.g. ranking N candidates
    against a single query vector).
  - `l2_norm(v)` + `cosine_similarity_prenormed(a, na, b, nb)` — a hot-loop
    variant that takes PRE-COMPUTED norms so an O(N^2) comparison loop
    (e.g. MMR diversification) doesn't recompute the same vector's norm on
    every pairwise comparison.

Both variants return 0.0 for a degenerate (empty/zero-magnitude/mismatched-
length) input rather than raising — a corrupted or placeholder embedding
must never crash a retrieval path; it just ranks last / is treated as
"not similar".
"""
from __future__ import annotations

import math
from typing import Sequence

__all__ = [
    "cosine_similarity",
    "l2_norm",
    "cosine_similarity_prenormed",
]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two equal-length vectors, in [-1.0, 1.0].

    Computes both norms inline in a single pass over `a`/`b`. Returns 0.0
    (never raises) if either vector is empty/all-zero (undefined direction)
    or the lengths differ (an incomparable pair — e.g. an embedding-model-ref
    drift), so a degraded vector never crashes a search — it only ranks last.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def l2_norm(v: Sequence[float]) -> float:
    """L2 norm of a vector.

    Split out from `cosine_similarity_prenormed` so a caller running an
    O(N^2) comparison loop (e.g. MMR diversification) can precompute each
    vector's norm ONCE and amortize it across the loop instead of recomputing
    it on every pairwise comparison.
    """
    return math.sqrt(sum(x * x for x in v))


def cosine_similarity_prenormed(
    a: Sequence[float], na: float, b: Sequence[float], nb: float
) -> float:
    """Cosine similarity given PRE-COMPUTED L2 norms `na`, `nb` (from
    `l2_norm`).

    Hot-loop variant: skips recomputing norms AND skips the dimension-
    mismatch/emptiness guard `cosine_similarity` does, since a caller using
    this form has already validated both vectors come from the same
    embedding space (e.g. both loaded under one project's configured
    embedding model/dimension). Returns 0.0 for a zero-magnitude vector
    rather than raising — the conservative call for a degenerate vector is
    "not redundant" (MMR) / "no similarity" (rank), never a crash.
    """
    if na == 0.0 or nb == 0.0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (na * nb)
