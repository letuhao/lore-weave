"""C12b-a — unit tests for the PUBLIC
``POST /v1/knowledge/projects/{id}/benchmark-run`` endpoint.

Focus:
  - 404 on cross-user / missing project
  - 409 for each typed error_code from the runner
  - 422 for runs out of range
  - 200 happy path with default runs=3 and explicit runs=5

The runner itself is swapped out — these tests only check the router
layer's contract (dependency wiring, status codes, error mapping,
request/response shape). Service-level behaviour is covered in
``test_benchmark_runner_service.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.benchmark.runner import (
    BenchmarkAlreadyRunningError,
    BenchmarkRunResult,
    FixtureLoadIncompleteError,
    NoEmbeddingModelError,
    NotBenchmarkProjectError,
    UnknownEmbeddingModelError,
)
from app.db.models import Project
from app.deps import get_projects_repo
from app.main import app
from app.middleware.jwt_auth import get_current_user

_USER = uuid4()
_PROJECT = uuid4()


def _project(*, embedding_model: str | None = "bge-m3") -> Project:
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
        embedding_dimension=1024 if embedding_model else None,
        extraction_config={},
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _result() -> BenchmarkRunResult:
    return BenchmarkRunResult(
        run_id="benchmark-20260424T120000Z",
        embedding_model="bge-m3",
        passed=True,
        recall_at_3=0.82,
        mrr=0.71,
        avg_score_positive=0.66,
        negative_control_max_score=0.30,
        stddev_recall=0.02,
        stddev_mrr=0.03,
        runs=3,
    )


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client_with(*, project=..., run_return=..., run_raises=None):
    """Wire FastAPI overrides + patch ``run_project_benchmark`` inside
    the router's local import. Returns (TestClient, run_mock)."""
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(
        return_value=_project() if project is ... else project,
    )

    run_mock = AsyncMock()
    if run_raises is not None:
        run_mock.side_effect = run_raises
    else:
        run_mock.return_value = _result() if run_return is ... else run_return

    # Router does local imports of ``run_project_benchmark`` and
    # ``get_embedding_client`` inside the handler body — local imports
    # resolve at call-time so we rebind on the source modules.
    # ``get_knowledge_pool`` is imported at module-top in extraction.py
    # so it must be rebound inside that module's namespace.
    import app.benchmark.runner as runner_module
    import app.clients.embedding_client as embedding_client_module
    import app.routers.public.extraction as extraction_module

    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo

    runner_module.run_project_benchmark = run_mock
    embedding_client_module.get_embedding_client = lambda: AsyncMock()
    extraction_module.get_knowledge_pool = lambda: AsyncMock()

    client = TestClient(app, raise_server_exceptions=False)
    return client, run_mock


@pytest.fixture(autouse=True)
def _restore_patches():
    # Snapshot the REAL symbols before the test tampers with them.
    # Reading them back from the source module after-the-fact is
    # circular once a test has rebound them, so we stash at test-
    # setup time and restore at teardown.
    import app.benchmark.runner as runner_module
    import app.clients.embedding_client as embedding_client_module
    import app.routers.public.extraction as extraction_module

    real_run = runner_module.run_project_benchmark
    real_ec = embedding_client_module.get_embedding_client
    real_pool = extraction_module.get_knowledge_pool

    yield

    runner_module.run_project_benchmark = real_run
    embedding_client_module.get_embedding_client = real_ec
    extraction_module.get_knowledge_pool = real_pool


def test_post_benchmark_run_404_on_missing_project():
    client, _ = _client_with(project=None)
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={"runs": 3},
    )
    assert resp.status_code == 404


def test_post_benchmark_run_409_no_embedding_model():
    client, _ = _client_with(run_raises=NoEmbeddingModelError("x"))
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "no_embedding_model"


def test_post_benchmark_run_409_unknown_embedding_model():
    client, _ = _client_with(run_raises=UnknownEmbeddingModelError("x"))
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "unknown_embedding_model"


def test_post_benchmark_run_409_not_benchmark_project():
    client, _ = _client_with(run_raises=NotBenchmarkProjectError("x"))
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "not_benchmark_project"


def test_post_benchmark_run_409_already_running():
    client, _ = _client_with(run_raises=BenchmarkAlreadyRunningError("x"))
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "benchmark_already_running"


def test_post_benchmark_run_502_on_fixture_incomplete():
    """Review-impl LOW #4: partial fixture load (embedder flake)
    surfaces as 502 ``embedding_provider_flake`` — NOT a false-negative
    200 with ``passed=False`` that would look like a retrieval
    regression in the UI."""
    client, _ = _client_with(run_raises=FixtureLoadIncompleteError("6/10"))
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["error_code"] == "embedding_provider_flake"


@pytest.mark.parametrize("bad_runs", [0, -1, 6, 99])
def test_post_benchmark_run_422_runs_out_of_range(bad_runs):
    client, _ = _client_with()
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={"runs": bad_runs},
    )
    assert resp.status_code == 422


def test_post_benchmark_run_200_happy_path_default_runs():
    client, run_mock = _client_with()
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={},  # no runs → default 3
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "benchmark-20260424T120000Z"
    assert body["embedding_model"] == "bge-m3"
    assert body["passed"] is True
    assert body["recall_at_3"] == 0.82
    assert body["runs"] == 3

    run_mock.assert_awaited_once()
    call = run_mock.await_args
    assert call.kwargs["runs"] == 3
    assert call.kwargs["user_id"] == _USER
    assert call.kwargs["project_id"] == _PROJECT


def test_post_benchmark_run_200_forwards_explicit_runs():
    custom = BenchmarkRunResult(
        run_id="benchmark-x", embedding_model="bge-m3", passed=True,
        recall_at_3=0.8, mrr=0.7, avg_score_positive=0.6,
        negative_control_max_score=0.3, stddev_recall=0.02,
        stddev_mrr=0.03, runs=5,
    )
    client, run_mock = _client_with(run_return=custom)
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
        json={"runs": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["runs"] == 5
    assert run_mock.await_args.kwargs["runs"] == 5


def test_post_benchmark_run_200_without_body():
    """Body is optional — curl without ``-d`` should still succeed
    with defaults. Matches FastAPI's ``body: T | None = None`` pattern."""
    client, run_mock = _client_with()
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT}/benchmark-run",
    )
    assert resp.status_code == 200
    assert run_mock.await_args.kwargs["runs"] == 3
