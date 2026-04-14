"""K17.9 unit tests — metrics + harness scaffold.

Acceptance (scaffold slice):
  - metrics.recall_at_k / reciprocal_rank / stddev math is correct
  - BenchmarkRunner drives a mock QueryRunner through ≥3 passes
  - passes_thresholds() enforces every gate independently
  - golden_set.yaml loads and parses into the expected shapes
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.metrics import mean, recall_at_k, reciprocal_rank, stddev
from eval.run_benchmark import (
    BenchmarkRunner,
    GoldenQuery,
    GoldenSet,
    ScoredResult,
    load_golden_set,
)


# ── metrics ───────────────────────────────────────────────────────────


def test_recall_at_k_full_hit():
    assert recall_at_k({"a", "b"}, ["a", "b", "x"], 3) == 1.0


def test_recall_at_k_partial():
    assert recall_at_k({"a", "b"}, ["a", "x", "y"], 3) == 0.5


def test_recall_at_k_miss():
    assert recall_at_k({"a"}, ["x", "y", "z"], 3) == 0.0


def test_recall_at_k_respects_k():
    # "b" is at position 4, so recall@3 should miss it.
    assert recall_at_k({"a", "b"}, ["a", "x", "y", "b"], 3) == 0.5


def test_recall_at_k_empty_expected_is_perfect():
    assert recall_at_k(set(), ["x"], 3) == 1.0


def test_recall_at_k_rejects_zero_k():
    with pytest.raises(ValueError):
        recall_at_k({"a"}, ["a"], 0)


def test_reciprocal_rank_first_hit():
    assert reciprocal_rank({"b"}, ["a", "b", "c"]) == pytest.approx(0.5)


def test_reciprocal_rank_first_position():
    assert reciprocal_rank({"a"}, ["a", "b", "c"]) == 1.0


def test_reciprocal_rank_miss():
    assert reciprocal_rank({"z"}, ["a", "b", "c"]) == 0.0


def test_reciprocal_rank_empty_expected():
    assert reciprocal_rank(set(), ["a"]) == 1.0


def test_mean_empty():
    assert mean([]) == 0.0


def test_mean_basic():
    assert mean([1.0, 2.0, 3.0]) == 2.0


def test_stddev_lt_two_samples():
    assert stddev([]) == 0.0
    assert stddev([1.0]) == 0.0


def test_stddev_constant_samples():
    assert stddev([0.5, 0.5, 0.5]) == 0.0


def test_stddev_known_value():
    # Population stddev of [1, 2, 3] is sqrt(2/3).
    assert stddev([1.0, 2.0, 3.0]) == pytest.approx(0.81649658, rel=1e-6)


# ── fixture load ──────────────────────────────────────────────────────


FIXTURE_PATH = Path(__file__).parents[2] / "eval" / "golden_set.yaml"


def test_golden_set_loads():
    gs = load_golden_set(FIXTURE_PATH)
    assert len(gs.entities) == 10
    assert len(gs.queries) == 20  # 12 easy + 6 hard + 2 negative
    assert sum(1 for q in gs.queries if q.band == "easy") == 12
    assert sum(1 for q in gs.queries if q.band == "hard") == 6
    assert sum(1 for q in gs.queries if q.band == "negative") == 2


def test_golden_set_thresholds_match_spec():
    gs = load_golden_set(FIXTURE_PATH)
    assert gs.thresholds["recall_at_3"] == 0.75
    assert gs.thresholds["mrr"] == 0.65
    assert gs.thresholds["avg_score_positive"] == 0.60
    assert gs.thresholds["negative_control_max_score"] == 0.50
    assert gs.thresholds["max_stddev"] == 0.05
    assert gs.thresholds["min_runs"] == 3


def test_negative_queries_have_empty_expected():
    gs = load_golden_set(FIXTURE_PATH)
    for q in gs.queries:
        if q.band == "negative":
            assert q.expected == ()


# ── harness with mock runner ──────────────────────────────────────────


class _PerfectRunner:
    """Returns the first expected entity at rank 1 with score 0.9.

    For negative queries, returns a single low-score hit so the
    negative-control check passes.
    """

    def __init__(self, golden: GoldenSet) -> None:
        self._by_q = {q.q: q for q in golden.queries}

    def run(self, query: str):
        gq = self._by_q[query]
        if gq.band == "negative":
            return [ScoredResult(entity_id="noise", score=0.1)]
        return [ScoredResult(entity_id=eid, score=0.9) for eid in gq.expected]


class _BrokenRunner:
    """Always returns a wrong, high-scoring negative hit."""

    def run(self, query: str):
        return [ScoredResult(entity_id="wrong", score=0.99)]


def _tiny_golden() -> GoldenSet:
    return GoldenSet(
        entities=(),
        queries=(
            GoldenQuery(q="q1", expected=("a",), band="easy"),
            GoldenQuery(q="q2", expected=("b",), band="hard"),
            GoldenQuery(q="q3", expected=(), band="negative"),
        ),
        thresholds={
            "recall_at_3": 0.75,
            "mrr": 0.65,
            "avg_score_positive": 0.60,
            "negative_control_max_score": 0.50,
            "max_stddev": 0.05,
            "min_runs": 3,
        },
    )


def test_runner_perfect_passes_thresholds():
    golden = _tiny_golden()
    report = BenchmarkRunner(golden, _PerfectRunner(golden)).run(runs=3)
    assert report.runs == 3
    assert report.recall_at_3 == 1.0
    assert report.mrr == 1.0
    assert report.avg_score_positive == pytest.approx(0.9)
    assert report.negative_control_max_score == pytest.approx(0.1)
    assert report.stddev_recall == 0.0
    assert report.passes_thresholds() is True


def test_runner_broken_fails_thresholds():
    golden = _tiny_golden()
    report = BenchmarkRunner(golden, _BrokenRunner()).run(runs=3)
    # Wrong hits → recall 0, MRR 0, negative control blown past 0.5.
    assert report.recall_at_3 == 0.0
    assert report.mrr == 0.0
    assert report.negative_control_max_score == pytest.approx(0.99)
    assert report.passes_thresholds() is False


def test_runner_rejects_too_few_runs_for_threshold():
    golden = _tiny_golden()
    report = BenchmarkRunner(golden, _PerfectRunner(golden)).run(runs=1)
    # All metrics perfect but runs < min_runs → must fail.
    assert report.runs == 1
    assert report.passes_thresholds() is False


def test_runner_rejects_zero_runs():
    golden = _tiny_golden()
    with pytest.raises(ValueError):
        BenchmarkRunner(golden, _PerfectRunner(golden)).run(runs=0)


def test_report_to_json_is_serializable():
    import json

    golden = _tiny_golden()
    report = BenchmarkRunner(golden, _PerfectRunner(golden)).run(runs=3)
    payload = report.to_json()
    # Round-trip through json to catch any non-serializable field.
    dumped = json.dumps(payload)
    assert "recall_at_3" in dumped
    assert "per_query" in dumped


def test_per_query_records_top_ids():
    golden = _tiny_golden()
    report = BenchmarkRunner(golden, _PerfectRunner(golden)).run(runs=3)
    q1 = next(row for row in report.per_query if row["q"] == "q1")
    assert q1["top_ids"] == ["a"]
    assert q1["recall_at_3"] == 1.0
    assert q1["reciprocal_rank"] == 1.0
