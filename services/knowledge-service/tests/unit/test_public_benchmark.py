"""T2-close-1b-FE — unit tests for the PUBLIC
`GET /v1/knowledge/projects/{id}/benchmark-status` endpoint.

Mirrors the internal endpoint's contract, but scoped by JWT. The
K12.4 picker consumes this via the gateway to render its
pass/fail/no-run badge.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.benchmark_runs import BenchmarkRun
from app.deps import get_benchmark_runs_repo, get_projects_repo
from app.main import app
from app.middleware.jwt_auth import get_current_user


_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _project_stub():
    from app.db.models import Project
    now = datetime.now(timezone.utc)
    return Project(
        project_id=_TEST_PROJECT,
        user_id=_TEST_USER,
        name="Test",
        description="",
        project_type="translation",
        book_id=None,
        instructions="",
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model="bge-m3",
        extraction_config={},
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _passing_run(*, model: str = "bge-m3") -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_run_id=uuid4(),
        project_id=_TEST_PROJECT,
        embedding_provider_id=None,
        embedding_model=model,
        run_id="run-passing",
        recall_at_3=0.85,
        mrr=0.72,
        avg_score_positive=0.70,
        stddev=0.03,
        negative_control_pass=True,
        passed=True,
        raw_report={},
        created_at=datetime.now(timezone.utc),
    )


def _client(*, project=..., benchmark=...) -> tuple[TestClient, AsyncMock]:
    """Returns (client, benchmark_repo) so tests can inspect the repo
    mock's call args. Without this closure, calling the override
    factory twice would hand back TWO different mocks — the one the
    request used vs. a fresh one — and assertions on the latter would
    tell us nothing about the former."""
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(
        return_value=_project_stub() if project is ... else project,
    )
    benchmark_repo = AsyncMock()
    benchmark_repo.get_latest = AsyncMock(
        return_value=_passing_run() if benchmark is ... else benchmark,
    )
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_benchmark_runs_repo] = lambda: benchmark_repo
    return TestClient(app, raise_server_exceptions=False), benchmark_repo


def test_public_benchmark_status_returns_passing_row():
    client, _ = _client()
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/benchmark-status",
        params={"embedding_model": "bge-m3"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_run"] is True
    assert body["passed"] is True
    assert body["embedding_model"] == "bge-m3"
    assert body["recall_at_3"] == 0.85


def test_public_benchmark_status_has_run_false_on_no_row():
    """`has_run=False` is a valid 200 — FE renders a neutral
    "Run benchmark" badge, not an error."""
    client, _ = _client(benchmark=None)
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/benchmark-status",
        params={"embedding_model": "bge-m3"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_run"] is False
    assert body["passed"] is None


def test_public_benchmark_status_404_on_cross_user_project():
    """Project doesn't exist OR belongs to another user → 404
    (no existence-leak). Matches the other public endpoints'
    cross-user rule."""
    client, _ = _client(project=None)  # projects_repo.get returns None
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/benchmark-status",
    )
    assert resp.status_code == 404


def test_public_benchmark_status_forwards_embedding_model_filter():
    """Review-impl MED fix: original test called the override factory
    a second time, which spawned a fresh AsyncMock instead of
    inspecting the one the request used — asserted nothing. Now the
    closure-backed _client returns the same repo mock the request
    will see, and we assert on its await_args directly.

    Omitting the model → repo.get_latest called with embedding_model=None.
    """
    client, benchmark_repo = _client(benchmark=None)
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/benchmark-status",
        # no embedding_model param
    )
    assert resp.status_code == 200
    # The key assertion — the None default actually flows through.
    benchmark_repo.get_latest.assert_awaited_once()
    call_args = benchmark_repo.get_latest.await_args
    # Third positional / embedding_model kwarg must be None.
    if "embedding_model" in call_args.kwargs:
        assert call_args.kwargs["embedding_model"] is None
    else:
        assert call_args.args[2] is None


def test_public_benchmark_status_forwards_model_when_set():
    """With ?embedding_model=bge-m3 → repo.get_latest receives "bge-m3".
    Catches a regression in the query-param plumbing."""
    client, benchmark_repo = _client(benchmark=None)
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/benchmark-status",
        params={"embedding_model": "bge-m3"},
    )
    assert resp.status_code == 200
    call_args = benchmark_repo.get_latest.await_args
    if "embedding_model" in call_args.kwargs:
        assert call_args.kwargs["embedding_model"] == "bge-m3"
    else:
        assert call_args.args[2] == "bge-m3"


def test_public_benchmark_status_failed_run_visible():
    """A failing benchmark surfaces as has_run=True + passed=False
    — the FE renders a red badge + a 'See report' link. Hiding this
    behind has_run=False would mask the quality regression the
    benchmark exists to catch."""
    failing = _passing_run()
    # Mutate to failing — frozen dataclass, so rebuild.
    failing = BenchmarkRun(
        benchmark_run_id=failing.benchmark_run_id,
        project_id=failing.project_id,
        embedding_provider_id=None,
        embedding_model=failing.embedding_model,
        run_id="run-failing",
        recall_at_3=0.10,
        mrr=0.08,
        avg_score_positive=0.20,
        stddev=0.02,
        negative_control_pass=True,
        passed=False,
        raw_report={},
        created_at=failing.created_at,
    )
    client, _ = _client(benchmark=failing)
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/benchmark-status",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_run"] is True
    assert body["passed"] is False
    assert body["recall_at_3"] == 0.10
    assert body["run_id"] == "run-failing"
