"""K17.9 — golden-set benchmark core (runtime).

D-EMB-EVAL-PKG-01: the runtime portion of the K17.9 harness lives
here (alongside the rest of `app/benchmark/`) so the production
container doesn't have to ship the `eval/` CLI harness directory.

Two drivers living side-by-side:

  - `BenchmarkRunner` (sync): the original scaffold. Takes a
    `QueryRunner` that returns `Sequence[ScoredResult]` synchronously.
    Used by unit tests with in-memory mock runners.
  - `AsyncBenchmarkRunner` (async): drives an `AsyncQueryRunner` that
    has to await embedding + Neo4j I/O. Used by the in-process
    `app/benchmark/runner.py` (the public benchmark endpoint) AND by
    the standalone CLI shell at `eval/run_benchmark.py`.

Threshold gate: `BenchmarkReport.passes_thresholds()` returns True
only when every gate from the yaml is satisfied.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from .metrics import mean, recall_at_k, reciprocal_rank, stddev


# ── Fixture loading ───────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldenQuery:
    q: str
    expected: tuple[str, ...]
    band: str  # "easy" | "hard" | "negative"


@dataclass(frozen=True)
class GoldenSet:
    entities: tuple[dict[str, Any], ...]
    queries: tuple[GoldenQuery, ...]
    thresholds: dict[str, float]


def load_golden_set(path: str | Path) -> GoldenSet:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    queries = tuple(
        GoldenQuery(q=q["q"], expected=tuple(q["expected"]), band=q["band"])
        for q in raw["queries"]
    )
    return GoldenSet(
        entities=tuple(raw["entities"]),
        queries=queries,
        thresholds=dict(raw["thresholds"]),
    )


def _default_golden_path() -> Path:
    # D-EMB-EVAL-PKG-01: golden_set.yaml lives alongside this module
    # in app/benchmark/. Path(__file__).parent resolves to the same
    # directory whether invoked from the in-process runner or from
    # the eval/run_benchmark.py CLI shell.
    return Path(__file__).parent / "golden_set.yaml"


def _default_run_id() -> str:
    from datetime import datetime, timezone
    return "benchmark-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ── QueryRunner seam ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoredResult:
    entity_id: str
    score: float


class QueryRunner(Protocol):
    """Stable interface between the harness and whatever produces
    ranked results for a natural-language query. Real implementation
    lands with K17.2 + K18.3; unit tests use a mock.
    """

    def run(self, query: str) -> Sequence[ScoredResult]: ...  # pragma: no cover


# ── Report ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BenchmarkReport:
    recall_at_3: float
    mrr: float
    avg_score_positive: float
    negative_control_max_score: float
    stddev_recall: float
    stddev_mrr: float
    runs: int
    thresholds: dict[str, float]
    per_query: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def passes_thresholds(self) -> bool:
        t = self.thresholds
        if self.runs < int(t.get("min_runs", 3)):
            return False
        if self.recall_at_3 < t["recall_at_3"]:
            return False
        if self.mrr < t["mrr"]:
            return False
        if self.avg_score_positive < t["avg_score_positive"]:
            return False
        if self.negative_control_max_score > t["negative_control_max_score"]:
            return False
        # Gate on the worse of recall/MRR stddev — spec phrasing
        # "stddev across runs" doesn't name a metric, so we enforce
        # the stricter interpretation: both must be stable.
        if max(self.stddev_recall, self.stddev_mrr) > t["max_stddev"]:
            return False
        return True

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# ── Runner ────────────────────────────────────────────────────────────


class BenchmarkRunner:
    """Sync driver — takes a `QueryRunner` that returns results
    synchronously (typically an in-memory mock)."""

    def __init__(self, golden: GoldenSet, runner: QueryRunner) -> None:
        self.golden = golden
        self.runner = runner

    def _single_pass(self) -> tuple[float, float, float, float, list[dict[str, Any]]]:
        recalls: list[float] = []
        rrs: list[float] = []
        positive_scores: list[float] = []
        negative_scores: list[float] = []
        per_query: list[dict[str, Any]] = []

        for query in self.golden.queries:
            results = list(self.runner.run(query.q))
            ids = [r.entity_id for r in results]

            if query.band == "negative":
                top_score = max((r.score for r in results), default=0.0)
                negative_scores.append(top_score)
                # Recall/MRR are undefined for negatives — the metric
                # is the top score against the negative-control gate.
                per_query.append(
                    {
                        "q": query.q,
                        "band": query.band,
                        "recall_at_3": None,
                        "reciprocal_rank": None,
                        "top_score": top_score,
                        "top_ids": ids[:3],
                    }
                )
            else:
                r3 = recall_at_k(query.expected, ids, 3)
                rr = reciprocal_rank(query.expected, ids)
                recalls.append(r3)
                rrs.append(rr)
                expected_set = set(query.expected)
                hit_scores = [r.score for r in results if r.entity_id in expected_set]
                if hit_scores:
                    positive_scores.append(max(hit_scores))
                per_query.append(
                    {
                        "q": query.q,
                        "band": query.band,
                        "recall_at_3": r3,
                        "reciprocal_rank": rr,
                        "top_ids": ids[:3],
                    }
                )

        return (
            mean(recalls),
            mean(rrs),
            mean(positive_scores),
            max(negative_scores, default=0.0),
            per_query,
        )

    def run(self, runs: int = 3) -> BenchmarkReport:
        if runs < 1:
            raise ValueError("runs must be >= 1")
        recall_samples: list[float] = []
        mrr_samples: list[float] = []
        pos_samples: list[float] = []
        neg_samples: list[float] = []
        last_per_query: list[dict[str, Any]] = []

        for _ in range(runs):
            r3, mrr_v, pos, neg, per_query = self._single_pass()
            recall_samples.append(r3)
            mrr_samples.append(mrr_v)
            pos_samples.append(pos)
            neg_samples.append(neg)
            last_per_query = per_query

        return BenchmarkReport(
            recall_at_3=mean(recall_samples),
            mrr=mean(mrr_samples),
            avg_score_positive=mean(pos_samples),
            negative_control_max_score=max(neg_samples),
            stddev_recall=stddev(recall_samples),
            stddev_mrr=stddev(mrr_samples),
            runs=runs,
            thresholds=dict(self.golden.thresholds),
            per_query=tuple(last_per_query),
        )


# ── Async sibling for real-stack benchmarks ───────────────────────────


class AsyncBenchmarkRunner:
    """Async driver — awaits each query against a runner that has to
    hit real I/O (embedding provider, Neo4j vector index). Mirrors
    `BenchmarkRunner` one-to-one in method shape + aggregation; only
    `_single_pass` / `run` are awaitable. The scoring math is copied
    rather than shared so the two drivers stay decoupled and the
    sync path has zero async overhead for the mock-runner unit tests.
    """

    def __init__(self, golden: GoldenSet, runner: Any) -> None:
        # `runner` is an `AsyncQueryRunner` — typed as `Any` here to
        # avoid a circular import from `mode3_query_runner`.
        self.golden = golden
        self.runner = runner

    async def _single_pass(
        self,
    ) -> tuple[float, float, float, float, list[dict[str, Any]]]:
        recalls: list[float] = []
        rrs: list[float] = []
        positive_scores: list[float] = []
        negative_scores: list[float] = []
        per_query: list[dict[str, Any]] = []

        for query in self.golden.queries:
            results = list(await self.runner.run(query.q))
            ids = [r.entity_id for r in results]

            if query.band == "negative":
                top_score = max((r.score for r in results), default=0.0)
                negative_scores.append(top_score)
                per_query.append(
                    {
                        "q": query.q,
                        "band": query.band,
                        "recall_at_3": None,
                        "reciprocal_rank": None,
                        "top_score": top_score,
                        "top_ids": ids[:3],
                    }
                )
            else:
                r3 = recall_at_k(query.expected, ids, 3)
                rr = reciprocal_rank(query.expected, ids)
                recalls.append(r3)
                rrs.append(rr)
                expected_set = set(query.expected)
                hit_scores = [r.score for r in results if r.entity_id in expected_set]
                if hit_scores:
                    positive_scores.append(max(hit_scores))
                per_query.append(
                    {
                        "q": query.q,
                        "band": query.band,
                        "recall_at_3": r3,
                        "reciprocal_rank": rr,
                        "top_ids": ids[:3],
                    }
                )

        return (
            mean(recalls),
            mean(rrs),
            mean(positive_scores),
            max(negative_scores, default=0.0),
            per_query,
        )

    async def run(self, runs: int = 3) -> BenchmarkReport:
        if runs < 1:
            raise ValueError("runs must be >= 1")
        recall_samples: list[float] = []
        mrr_samples: list[float] = []
        pos_samples: list[float] = []
        neg_samples: list[float] = []
        last_per_query: list[dict[str, Any]] = []

        for _ in range(runs):
            r3, mrr_v, pos, neg, per_query = await self._single_pass()
            recall_samples.append(r3)
            mrr_samples.append(mrr_v)
            pos_samples.append(pos)
            neg_samples.append(neg)
            last_per_query = per_query

        return BenchmarkReport(
            recall_at_3=mean(recall_samples),
            mrr=mean(mrr_samples),
            avg_score_positive=mean(pos_samples),
            negative_control_max_score=max(neg_samples),
            stddev_recall=stddev(recall_samples),
            stddev_mrr=stddev(mrr_samples),
            runs=runs,
            thresholds=dict(self.golden.thresholds),
            per_query=tuple(last_per_query),
        )
