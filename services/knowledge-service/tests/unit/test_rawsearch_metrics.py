"""P3-EVAL E2 — unit tests for the raw-search eval metric additions.

Covers `hit_at_k` (success@k) and `ndcg_at_k` (graded NDCG). Pure
functions, no I/O — mirrors the style of the existing benchmark
`metrics.py` (recall_at_k / reciprocal_rank).
"""

from __future__ import annotations

import math

import pytest

from app.benchmark.metrics import hit_at_k, ndcg_at_k


# ── hit_at_k ─────────────────────────────────────────────────────────


def test_hit_at_k_hit_in_top_k():
    assert hit_at_k(["a"], ["x", "a", "y"], 3) == 1.0


def test_hit_at_k_present_but_below_cutoff():
    # 'a' is at rank 3 (index 2) — outside top-2 → miss.
    assert hit_at_k(["a"], ["x", "y", "a"], 2) == 0.0


def test_hit_at_k_miss():
    assert hit_at_k(["a"], ["x", "y", "z"], 3) == 0.0


def test_hit_at_k_any_of_several_expected():
    assert hit_at_k(["a", "b"], ["z", "b"], 5) == 1.0


def test_hit_at_k_empty_expected_is_success():
    # negative-control convention: nothing expected → 1.0
    assert hit_at_k([], ["x", "y"], 5) == 1.0


def test_hit_at_k_k_larger_than_results():
    assert hit_at_k(["a"], ["a"], 10) == 1.0


def test_hit_at_k_rejects_nonpositive_k():
    with pytest.raises(ValueError):
        hit_at_k(["a"], ["a"], 0)


# ── ndcg_at_k ────────────────────────────────────────────────────────


def test_ndcg_perfect_ordering_is_1():
    graded = {"a": 3.0, "b": 2.0, "c": 1.0}
    assert ndcg_at_k(graded, ["a", "b", "c"], 3) == pytest.approx(1.0)


def test_ndcg_reversed_ordering_less_than_1():
    graded = {"a": 3.0, "b": 2.0, "c": 1.0}
    val = ndcg_at_k(graded, ["c", "b", "a"], 3)
    assert 0.0 < val < 1.0


def test_ndcg_empty_graded_is_0():
    assert ndcg_at_k({}, ["a", "b"], 3) == 0.0


def test_ndcg_no_relevant_in_results_is_0():
    # graded defines positives but none surface in results → DCG 0, IDCG>0
    assert ndcg_at_k({"a": 3.0}, ["x", "y"], 3) == 0.0


def test_ndcg_truncates_at_k():
    graded = {"a": 3.0, "b": 3.0}
    # only the first result counts at k=1; ideal@1 is one gain=3 → 1.0
    assert ndcg_at_k(graded, ["a", "b"], 1) == pytest.approx(1.0)


def test_ndcg_partial_gain_value():
    # single relevant doc at rank 2 (index 1): DCG = 1/log2(3),
    # IDCG (ideal at rank 1) = 1/log2(2) = 1.0 → ratio = 1/log2(3)
    graded = {"a": 1.0}
    val = ndcg_at_k(graded, ["x", "a", "y"], 3)
    assert val == pytest.approx(1.0 / math.log2(3))


def test_ndcg_unlisted_ids_score_zero_gain():
    graded = {"a": 2.0}
    # 'b','c' contribute 0 gain; only 'a' at rank1 → DCG=2, IDCG=2 → 1.0
    assert ndcg_at_k(graded, ["a", "b", "c"], 3) == pytest.approx(1.0)


def test_ndcg_rejects_nonpositive_k():
    with pytest.raises(ValueError):
        ndcg_at_k({"a": 1.0}, ["a"], 0)
