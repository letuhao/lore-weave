"""K17.9 — golden-set benchmark harness (scaffold).

The runner is a thin aggregation layer over `metrics.py`. It takes a
`QueryRunner` (Protocol) that returns scored results for a query, walks
the fixture, runs ≥`min_runs` times to compute stddev, and emits a
`BenchmarkReport` that can be serialized to JSON and checked against
the fixture's thresholds.

The Protocol is the seam that lets us ship today: unit tests inject a
`MockQueryRunner`, and when K17.2 (LLM extractor) + K18.3 (Mode 3
selector) land, the real extractor is dropped in behind the same
interface. No harness changes required.
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
