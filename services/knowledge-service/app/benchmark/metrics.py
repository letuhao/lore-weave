"""K17.9 — pure metric functions for the golden-set benchmark.

No I/O, no driver, no embeddings. Each function takes plain data and
returns a float so they can be unit-tested in milliseconds and reused
by both the real harness (when K17.2/K18.3 land) and the scaffold.

Definitions (all standard IR metrics):
  - recall@k: fraction of expected ids appearing anywhere in the top-k.
    Empty expected set is treated as perfect recall (1.0) — the caller
    handles negative-control queries via score thresholds, not recall.
  - MRR: mean reciprocal rank of the FIRST expected id hit, 0.0 if none
    hit. Per-query MRR; aggregate across queries with `mean`.
  - stddev: population standard deviation, 0.0 for <2 samples. Used to
    flag high run-to-run variance (L-CH-09 — ≥3 runs, stddev < 0.05).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence


def hit_at_k(expected: Iterable[str], results: Sequence[str], k: int) -> float:
    """Success@k: 1.0 if ANY expected id appears in the top-k, else 0.0.

    Empty expected set → 1.0 (a negative-control query "succeeds" by
    returning nothing relevant; the caller polices negatives via score
    thresholds / absence, not via hit@k — same convention as recall_at_k).
    """
    if k <= 0:
        raise ValueError("k must be positive")
    expected_set = set(expected)
    if not expected_set:
        return 1.0
    return 1.0 if expected_set & set(results[:k]) else 0.0


def ndcg_at_k(
    graded: Mapping[str, float], results: Sequence[str], k: int
) -> float:
    """Normalized DCG@k over GRADED relevance.

    `graded` maps result id → relevance gain (e.g. 0..3); ids absent from
    the map score 0. DCG = Σ gain_i / log2(i + 2) over the ranked top-k
    (0-based i). IDCG is the DCG of the ideal ordering (gains sorted
    descending). Returns DCG/IDCG, or 0.0 when IDCG == 0 (no positive
    relevance defined for this query).
    """
    if k <= 0:
        raise ValueError("k must be positive")

    def _dcg(gains: Sequence[float]) -> float:
        return sum(g / math.log2(i + 2) for i, g in enumerate(gains[:k]))

    dcg = _dcg([float(graded.get(rid, 0.0)) for rid in results])
    idcg = _dcg(sorted((float(g) for g in graded.values()), reverse=True))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def recall_at_k(expected: Iterable[str], results: Sequence[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    expected_set = set(expected)
    if not expected_set:
        return 1.0
    top_k = set(results[:k])
    hits = len(expected_set & top_k)
    return hits / len(expected_set)


def reciprocal_rank(expected: Iterable[str], results: Sequence[str]) -> float:
    expected_set = set(expected)
    if not expected_set:
        return 1.0
    for idx, rid in enumerate(results, start=1):
        if rid in expected_set:
            return 1.0 / idx
    return 0.0


def mean(samples: Sequence[float]) -> float:
    if not samples:
        return 0.0
    return sum(samples) / len(samples)


def stddev(samples: Sequence[float]) -> float:
    if len(samples) < 2:
        return 0.0
    mu = mean(samples)
    var = sum((s - mu) ** 2 for s in samples) / len(samples)
    return math.sqrt(var)
