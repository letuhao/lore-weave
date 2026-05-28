"""K17.9 unit tests — metrics + harness scaffold.

Acceptance (scaffold slice):
  - metrics.recall_at_k / reciprocal_rank / stddev math is correct
  - BenchmarkRunner drives a mock QueryRunner through ≥3 passes
  - passes_thresholds() enforces every gate independently
  - golden_set.yaml loads and parses into the expected shapes
"""

from __future__ import annotations

import pytest

from app.benchmark.core import (
    BenchmarkRunner,
    GoldenQuery,
    GoldenSet,
    ScoredResult,
    _default_golden_path,
    load_golden_set,
)
from app.benchmark.metrics import mean, recall_at_k, reciprocal_rank, stddev


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


FIXTURE_PATH = _default_golden_path()


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
    assert report.stddev_mrr == 0.0
    assert report.passes_thresholds() is True


def test_negative_query_per_row_has_no_recall():
    golden = _tiny_golden()
    report = BenchmarkRunner(golden, _PerfectRunner(golden)).run(runs=3)
    neg = next(row for row in report.per_query if row["band"] == "negative")
    assert neg["recall_at_3"] is None
    assert neg["reciprocal_rank"] is None
    assert neg["top_score"] == pytest.approx(0.1)


class _MrrFlakyRunner:
    """Recall stays perfect, but MRR swings between passes.

    Every pass surfaces the expected hit inside the top-3 (recall@3
    = 1.0 every pass) but at different ranks on different passes —
    the kind of flakiness a recall-only stddev gate would miss.
    Flakiness is pass-level: `_calls_per_pass` tracks when a full
    pass over the golden set has completed, then the rank flips.
    """

    def __init__(self, positives_per_pass: int = 2) -> None:
        self._calls = 0
        self._positives_per_pass = positives_per_pass

    def run(self, query: str):
        if query == "q3":  # negative query — doesn't count toward pass tally
            return [ScoredResult(entity_id="noise", score=0.1)]
        pass_index = self._calls // self._positives_per_pass
        self._calls += 1
        expected = "a" if query == "q1" else "b"
        if pass_index % 2 == 0:
            return [ScoredResult(entity_id=expected, score=0.9)]
        return [
            ScoredResult(entity_id="x", score=0.85),
            ScoredResult(entity_id="y", score=0.80),
            ScoredResult(entity_id=expected, score=0.75),
        ]


def test_stddev_mrr_catches_flakiness_recall_misses():
    golden = _tiny_golden()
    report = BenchmarkRunner(golden, _MrrFlakyRunner()).run(runs=3)
    assert report.recall_at_3 == 1.0
    assert report.stddev_recall == 0.0  # recall-only gate would pass
    assert report.stddev_mrr > 0.05      # MRR stddev catches it
    assert report.passes_thresholds() is False


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


# ── D-EMB-BENCHMARK-CAL-01: per-dimension threshold overrides ─────────


def test_golden_set_loads_thresholds_by_dimension_with_int_keys():
    """The shipped YAML has a 1024 override entry; load_golden_set must
    coerce the YAML key to int (YAML safe_load already does this for
    numeric keys, but the loader's defensive normalization protects
    future entries that may end up quoted in the YAML)."""
    gs = load_golden_set(FIXTURE_PATH)
    assert 1024 in gs.thresholds_by_dimension
    assert isinstance(list(gs.thresholds_by_dimension.keys())[0], int)
    # The bge-m3 override raises only the negative-control ceiling.
    assert gs.thresholds_by_dimension[1024]["negative_control_max_score"] == 0.70


def _negative_at(score: float) -> "type":
    """Factory for a QueryRunner that mirrors `_PerfectRunner` on
    positives but emits a single negative hit at the configured
    score — used to land precisely between flat-default and
    per-dim threshold ceilings."""

    class _R:
        def __init__(self, golden: GoldenSet) -> None:
            self._by_q = {q.q: q for q in golden.queries}

        def run(self, query: str):
            gq = self._by_q[query]
            if gq.band == "negative":
                return [ScoredResult(entity_id="noise", score=score)]
            return [ScoredResult(entity_id=eid, score=0.9) for eid in gq.expected]

    return _R


def _tiny_golden_with_1024_override() -> GoldenSet:
    """Tiny golden with `negative_control_max_score` 0.50 (flat) +
    1024-dim override 0.70 — mirrors the shipped YAML's shape."""
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
        thresholds_by_dimension={
            1024: {"negative_control_max_score": 0.70},
        },
    )


def test_runner_applies_per_dimension_override_for_matching_dim():
    """negative_control_max_score=0.65 sits between flat (0.50) and
    1024 override (0.70). With dimension=1024 the override applies and
    the run passes; the persisted thresholds reflect the 0.70 ceiling
    so the gate decision is traceable."""
    golden = _tiny_golden_with_1024_override()
    Runner = _negative_at(0.65)
    report = BenchmarkRunner(golden, Runner(golden), dimension=1024).run(runs=3)
    assert report.negative_control_max_score == pytest.approx(0.65)
    # Merged thresholds — record what actually gated this run.
    assert report.thresholds["negative_control_max_score"] == 0.70
    # The other 5 keys inherit from flat.
    assert report.thresholds["recall_at_3"] == 0.75
    assert report.passes_thresholds() is True


def test_runner_falls_back_to_flat_for_unknown_dimension():
    """The same 0.65 negative-control score blows past the flat 0.50
    ceiling when no dimension is supplied — fallback path."""
    golden = _tiny_golden_with_1024_override()
    Runner = _negative_at(0.65)
    report = BenchmarkRunner(golden, Runner(golden), dimension=None).run(runs=3)
    assert report.thresholds["negative_control_max_score"] == 0.50
    assert report.passes_thresholds() is False


def test_runner_falls_back_to_flat_for_dim_without_override():
    """dimension=1536 has no override entry → flat thresholds apply."""
    golden = _tiny_golden_with_1024_override()
    Runner = _negative_at(0.65)
    report = BenchmarkRunner(golden, Runner(golden), dimension=1536).run(runs=3)
    assert report.thresholds["negative_control_max_score"] == 0.50
    assert report.passes_thresholds() is False


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
