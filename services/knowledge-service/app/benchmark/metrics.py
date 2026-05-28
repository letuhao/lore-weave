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
from collections.abc import Iterable, Sequence


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
