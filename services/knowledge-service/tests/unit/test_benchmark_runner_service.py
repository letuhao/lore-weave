"""C12b-a — unit tests for ``app/benchmark/runner.run_project_benchmark``.

Covers the validation ladder (no model → unknown model → unsupported
dim → not-benchmark → already-running → fixture-incomplete), happy-
path call-order through fixture loader / harness / persist, and
regression locks on the empty-project guard:

  - ``KNOWN_SOURCE_TYPES`` still matches every literal ``source_type``
    passed to ``upsert_passage`` in the real ingestion paths (drift
    lock — review-impl finding MED #1).
  - ``benchmark_entity`` stays OUT of ``KNOWN_SOURCE_TYPES`` so
    re-runs on the same benchmark project don't self-block
    (invariant lock — review-impl finding LOW #3).
  - ``_REAL_PASSAGE_COUNT_CYPHER`` carries the tenant + scope
    clauses a typo would silently drop (cypher lock — review-impl
    finding LOW #5).

The orchestrator is designed to be driver-less via monkeypatch so
tests don't need a live Neo4j or Postgres.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.benchmark import runner as runner_module
from app.benchmark.runner import (
    BenchmarkAlreadyRunningError,
    BenchmarkRunError,
    BenchmarkRunResult,
    FixtureLoadIncompleteError,
    NoEmbeddingModelError,
    NotBenchmarkProjectError,
    UnknownEmbeddingModelError,
    run_project_benchmark,
)
from app.db.models import Project
from app.db.neo4j_repos.passages import KNOWN_SOURCE_TYPES
from eval.fixture_loader import BENCHMARK_SOURCE_TYPE


_USER = uuid4()
_PROJECT = uuid4()


def _project(
    *,
    embedding_model: str | None = "bge-m3",
    embedding_dimension: int | None = 1024,
) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id=_PROJECT,
        user_id=_USER,
        name="Benchmark",
        description="",
        project_type="translation",
        book_id=None,
        instructions="",
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        extraction_config={},
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=now,
        updated_at=now,
    )


@dataclass
class _FakeReport:
    """Duck-typed stand-in for ``BenchmarkReport``.

    We don't import the real one because constructing it with
    thresholds is awkward and ``run_project_benchmark`` only calls
    ``passes_thresholds()`` and reads fields we control here."""

    recall_at_3: float = 0.82
    mrr: float = 0.71
    avg_score_positive: float = 0.66
    negative_control_max_score: float = 0.30
    stddev_recall: float = 0.02
    stddev_mrr: float = 0.03
    runs: int = 3

    def passes_thresholds(self) -> bool:
        return True


class _FakeAsyncRunner:
    """Returned by ``AsyncBenchmarkRunner`` patch — captures the ``runs``
    kwarg so tests can assert it propagated."""

    last_runs: int | None = None

    def __init__(self, golden: Any, runner: Any) -> None:  # noqa: ARG002
        self.golden = golden

    async def run(self, runs: int = 3) -> _FakeReport:
        _FakeAsyncRunner.last_runs = runs
        return _FakeReport(runs=runs)


def _fake_projects_repo(project: Project | None) -> AsyncMock:
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=project)
    return repo


@pytest.fixture(autouse=True)
def _isolate_locks():
    runner_module._reset_locks_for_tests()
    _FakeAsyncRunner.last_runs = None
    yield
    runner_module._reset_locks_for_tests()


def _patch_happy_path(monkeypatch):
    """Monkeypatch the runner module so the orchestrator doesn't try
    to hit Neo4j or Postgres. Returns a SimpleNamespace of the mocks
    so each test can assert on them."""
    call_order: list[str] = []

    async def _fake_has_real(user_id: str, project_id: str) -> bool:
        call_order.append("has_real_passages")
        return False

    async def _fake_load(*args, **kwargs):
        call_order.append("load_fixture")
        return len(kwargs.get("golden", SimpleNamespace(entities=[])).entities) \
            if "golden" in kwargs else 1

    async def _fake_persist(*args, **kwargs):
        call_order.append("persist")
        return uuid4()

    def _fake_load_golden_set(path):
        call_order.append("load_golden_yaml")
        return SimpleNamespace(entities=[{"id": "e1"}])

    # Neo4j session context manager — yields a sentinel; the fake
    # load/run consumers accept any session and ignore it.
    class _FakeSession:
        async def __aenter__(self):
            return SimpleNamespace(name="fake-session")

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(runner_module, "_has_real_passages", _fake_has_real)
    monkeypatch.setattr(runner_module, "load_golden_set_as_passages", _fake_load)
    monkeypatch.setattr(runner_module, "persist_benchmark_report", _fake_persist)
    monkeypatch.setattr(runner_module, "load_golden_set", _fake_load_golden_set)
    monkeypatch.setattr(runner_module, "AsyncBenchmarkRunner", _FakeAsyncRunner)
    monkeypatch.setattr(runner_module, "neo4j_session", lambda: _FakeSession())
    # Mode3QueryRunner ctor is called but the runner object is only
    # used by AsyncBenchmarkRunner which we've swapped; stub ctor.
    monkeypatch.setattr(
        runner_module, "Mode3QueryRunner",
        lambda *a, **kw: SimpleNamespace(),
    )
    return SimpleNamespace(call_order=call_order)


@pytest.mark.asyncio
async def test_raises_no_embedding_model_when_project_has_none():
    repo = _fake_projects_repo(_project(embedding_model=None, embedding_dimension=None))
    with pytest.raises(NoEmbeddingModelError):
        await run_project_benchmark(
            user_id=_USER, project_id=_PROJECT, runs=3,
            pool=AsyncMock(), projects_repo=repo,
            embedding_client=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_raises_no_embedding_model_when_dim_missing():
    """embedding_model set but embedding_dimension None (shouldn't
    happen under current projects_repo.update logic, but the guard
    defends-in-depth against drift)."""
    repo = _fake_projects_repo(_project(embedding_model="bge-m3", embedding_dimension=None))
    with pytest.raises(NoEmbeddingModelError):
        await run_project_benchmark(
            user_id=_USER, project_id=_PROJECT, runs=3,
            pool=AsyncMock(), projects_repo=repo,
            embedding_client=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_raises_unknown_embedding_model_when_not_in_map():
    repo = _fake_projects_repo(
        _project(embedding_model="fantasy-model-v9", embedding_dimension=1024),
    )
    with pytest.raises(UnknownEmbeddingModelError):
        await run_project_benchmark(
            user_id=_USER, project_id=_PROJECT, runs=3,
            pool=AsyncMock(), projects_repo=repo,
            embedding_client=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_raises_unknown_embedding_model_when_dim_unsupported():
    """nomic-embed-text is in the map at dim 768 but 768 isn't in
    SUPPORTED_PASSAGE_DIMS — we should surface as 409 not a late
    ValueError from upsert_passage."""
    repo = _fake_projects_repo(
        _project(embedding_model="nomic-embed-text", embedding_dimension=768),
    )
    with pytest.raises(UnknownEmbeddingModelError):
        await run_project_benchmark(
            user_id=_USER, project_id=_PROJECT, runs=3,
            pool=AsyncMock(), projects_repo=repo,
            embedding_client=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_raises_not_benchmark_project_when_real_passages_exist(monkeypatch):
    repo = _fake_projects_repo(_project())

    async def _has_real(user_id: str, project_id: str) -> bool:
        return True

    monkeypatch.setattr(runner_module, "_has_real_passages", _has_real)

    with pytest.raises(NotBenchmarkProjectError):
        await run_project_benchmark(
            user_id=_USER, project_id=_PROJECT, runs=3,
            pool=AsyncMock(), projects_repo=repo,
            embedding_client=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_raises_already_running_when_sentinel_held(monkeypatch):
    """Concurrent POSTs for the same project serialise via the
    ``_running`` sentinel set. The first call marks the project busy;
    a second call that arrives before the first releases sees the
    sentinel and 409s. Review-impl MED #2 — this replaces an earlier
    ``asyncio.Lock`` pattern whose atomicity was fragile to refactor."""
    repo = _fake_projects_repo(_project())
    _patch_happy_path(monkeypatch)

    # Pre-mark the sentinel as held, mimicking an in-flight benchmark.
    key = runner_module._try_mark_running(_USER, _PROJECT)
    assert key is not None  # sanity — fresh isolate_locks fixture
    try:
        with pytest.raises(BenchmarkAlreadyRunningError):
            await run_project_benchmark(
                user_id=_USER, project_id=_PROJECT, runs=3,
                pool=AsyncMock(), projects_repo=repo,
                embedding_client=AsyncMock(),
            )
    finally:
        runner_module._mark_done(key)


@pytest.mark.asyncio
async def test_sentinel_cleared_after_successful_run(monkeypatch):
    """After a happy path completes, the sentinel MUST be cleared so a
    second run on the same project succeeds. Otherwise every project
    would 409-forever after its first run."""
    repo = _fake_projects_repo(_project())
    _patch_happy_path(monkeypatch)

    await run_project_benchmark(
        user_id=_USER, project_id=_PROJECT, runs=3,
        pool=AsyncMock(), projects_repo=repo,
        embedding_client=AsyncMock(),
    )
    # Sentinel should be clear — a second call must succeed.
    key = runner_module._try_mark_running(_USER, _PROJECT)
    assert key is not None


@pytest.mark.asyncio
async def test_sentinel_cleared_after_fixture_incomplete_raise(monkeypatch):
    """Regression: the ``try/finally`` around the in-flight work must
    clear the sentinel even when ``FixtureLoadIncompleteError`` fires
    — otherwise a provider flake would permanently 409 the project."""
    repo = _fake_projects_repo(_project())
    ctx = _patch_happy_path(monkeypatch)

    # Make fixture loader return a partial count.
    async def _partial_load(*args, **kwargs):
        ctx.call_order.append("load_fixture")
        return 0  # expected=1, loaded=0

    monkeypatch.setattr(runner_module, "load_golden_set_as_passages", _partial_load)

    with pytest.raises(FixtureLoadIncompleteError):
        await run_project_benchmark(
            user_id=_USER, project_id=_PROJECT, runs=3,
            pool=AsyncMock(), projects_repo=repo,
            embedding_client=AsyncMock(),
        )
    # Even after the raise, sentinel is clear.
    key = runner_module._try_mark_running(_USER, _PROJECT)
    assert key is not None


@pytest.mark.asyncio
async def test_fixture_incomplete_does_not_persist(monkeypatch):
    """Critical contract: an incomplete fixture must NOT land a run in
    ``project_embedding_benchmark_runs`` — a false-negative row would
    confuse the FE badge and obscure the real cause (provider flake)."""
    repo = _fake_projects_repo(_project())
    ctx = _patch_happy_path(monkeypatch)

    async def _partial_load(*args, **kwargs):
        ctx.call_order.append("load_fixture")
        return 0

    monkeypatch.setattr(runner_module, "load_golden_set_as_passages", _partial_load)

    with pytest.raises(FixtureLoadIncompleteError):
        await run_project_benchmark(
            user_id=_USER, project_id=_PROJECT, runs=3,
            pool=AsyncMock(), projects_repo=repo,
            embedding_client=AsyncMock(),
        )
    assert "persist" not in ctx.call_order


@pytest.mark.asyncio
async def test_happy_path_calls_load_run_persist_in_order(monkeypatch):
    repo = _fake_projects_repo(_project())
    ctx = _patch_happy_path(monkeypatch)

    result = await run_project_benchmark(
        user_id=_USER, project_id=_PROJECT, runs=3,
        pool=AsyncMock(), projects_repo=repo,
        embedding_client=AsyncMock(),
    )

    assert isinstance(result, BenchmarkRunResult)
    assert result.runs == 3
    assert result.embedding_model == "bge-m3"
    assert result.passed is True
    # Order: empty-project check → load-yaml → fixture-load → persist.
    assert ctx.call_order == [
        "has_real_passages",
        "load_golden_yaml",
        "load_fixture",
        "persist",
    ]


@pytest.mark.asyncio
async def test_runs_parameter_forwarded_to_async_runner(monkeypatch):
    repo = _fake_projects_repo(_project())
    _patch_happy_path(monkeypatch)

    await run_project_benchmark(
        user_id=_USER, project_id=_PROJECT, runs=5,
        pool=AsyncMock(), projects_repo=repo,
        embedding_client=AsyncMock(),
    )

    assert _FakeAsyncRunner.last_runs == 5


@pytest.mark.asyncio
async def test_defensive_404_when_project_none():
    """Router should 404 first, but the orchestrator still guards —
    we raise BenchmarkRunError (base class) so a router bug doesn't
    silently leak into a 500 with a confusing stack."""
    repo = _fake_projects_repo(None)
    with pytest.raises(BenchmarkRunError):
        await run_project_benchmark(
            user_id=_USER, project_id=_PROJECT, runs=3,
            pool=AsyncMock(), projects_repo=repo,
            embedding_client=AsyncMock(),
        )


# ── Regression locks on the empty-project guard ─────────────────────


def test_benchmark_source_type_not_in_known_set():
    """Invariant: ``benchmark_entity`` must NEVER join
    ``KNOWN_SOURCE_TYPES``. Doing so would make the guard fire on
    re-runs (second-run 409), because fixture passages from the first
    run would be counted as "real". Review-impl LOW #3 pin.
    """
    assert BENCHMARK_SOURCE_TYPE == "benchmark_entity"
    assert BENCHMARK_SOURCE_TYPE not in KNOWN_SOURCE_TYPES


def test_known_source_types_cover_every_real_upsert_passage_callsite():
    """Regression lock (review-impl MED #1):

    Greps ``app/extraction/passage_ingester.py`` — the ONLY real-data
    producer of ``:Passage`` nodes today — and asserts every literal
    ``source_type=<...>`` kwarg is in ``KNOWN_SOURCE_TYPES``. If a
    future PR adds a new passage producer (e.g. ``source_type="note"``
    via a K14.5 expansion) without extending ``KNOWN_SOURCE_TYPES``,
    the empty-project guard in ``_has_real_passages`` silently becomes
    a no-op and a benchmark run would pollute the user's real project.

    We scan the literal source to catch drift at test-time, before
    the bug reaches users.
    """
    ingester_path = (
        Path(__file__).resolve().parent.parent.parent
        / "app" / "extraction" / "passage_ingester.py"
    )
    text = ingester_path.read_text(encoding="utf-8")
    # Match ``source_type="chapter"`` style literals passed as kwargs.
    literals = set(re.findall(r'source_type\s*=\s*"([^"]+)"', text))
    # Every literal used by real ingestion must be known to the guard.
    assert literals, "expected source_type=\"...\" literals in passage_ingester"
    unknown = literals - set(KNOWN_SOURCE_TYPES)
    assert not unknown, (
        f"passage_ingester writes source_type values not in "
        f"KNOWN_SOURCE_TYPES: {unknown}. Extend KNOWN_SOURCE_TYPES in "
        f"app/db/neo4j_repos/passages.py so the empty-project guard in "
        f"app/benchmark/runner.py catches them."
    )


def test_real_passage_count_cypher_has_safety_clauses():
    """Regression lock (review-impl LOW #5):

    Every unit test mocks ``_has_real_passages``; the Cypher literal
    itself is otherwise untested. A typo like ``p.source_type = $real_types``
    (``=`` instead of ``IN``) would silently return no rows, making
    the guard a no-op. Pin the three clauses that matter: tenant
    filter, project scope, and the source-type IN list.
    """
    cypher = runner_module._REAL_PASSAGE_COUNT_CYPHER
    assert "p.user_id = $user_id" in cypher, \
        "tenant filter missing from _REAL_PASSAGE_COUNT_CYPHER"
    assert "p.project_id = $project_id" in cypher, \
        "project scope missing from _REAL_PASSAGE_COUNT_CYPHER"
    assert "p.source_type IN $real_types" in cypher, \
        "source_type IN list missing from _REAL_PASSAGE_COUNT_CYPHER"
