"""T2-close-1b — unit tests for the internal benchmark-status router.

Uses TestClient + dependency_overrides pattern from the other
internal-router tests. The `require_internal_token` middleware is
either satisfied via the X-Internal-Token header or bypassed in
tests that deliberately exercise the auth path.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.benchmark_runs import BenchmarkRun
from app.deps import get_benchmark_runs_repo
from app.main import app


# Matches tests/conftest.py setdefault on INTERNAL_SERVICE_TOKEN.
_INTERNAL_TOKEN_HEADER = {"X-Internal-Token": "default_test_token"}


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _passing_run(*, model: str = "bge-m3", run_id: str = "run-2026-01") -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_run_id=uuid4(),
        project_id=uuid4(),
        embedding_provider_id=None,
        embedding_model=model,
        run_id=run_id,
        recall_at_3=0.85,
        mrr=0.72,
        avg_score_positive=0.70,
        stddev=0.03,
        negative_control_pass=True,
        passed=True,
        raw_report={},
        created_at=datetime.now(timezone.utc),
    )


def test_benchmark_status_returns_has_run_true_when_row_exists():
    repo = AsyncMock()
    repo.get_latest = AsyncMock(return_value=_passing_run())
    app.dependency_overrides[get_benchmark_runs_repo] = lambda: repo

    client = TestClient(app, raise_server_exceptions=False)
    project_id = uuid4()
    user_id = uuid4()
    resp = client.get(
        f"/internal/projects/{project_id}/benchmark-status",
        params={"user_id": str(user_id), "embedding_model": "bge-m3"},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_run"] is True
    assert body["passed"] is True
    assert body["embedding_model"] == "bge-m3"
    assert body["recall_at_3"] == 0.85


def test_benchmark_status_surfaces_gate_failures_from_raw_report():
    """R2 (D-JOURNEY-KG-BENCHMARK-UX): a non-passing run carries its named gates
    out of the stored raw_report so the FE badge can distinguish inconclusive
    (insufficient_runs) from a real quality fail. Empty raw_report → []."""
    run = _passing_run()
    failing = BenchmarkRun(
        benchmark_run_id=run.benchmark_run_id,
        project_id=run.project_id,
        embedding_provider_id=None,
        embedding_model="bge-m3",
        run_id="run-fail",
        recall_at_3=1.0,  # perfect recall — but...
        mrr=1.0,
        avg_score_positive=0.7,
        stddev=0.0,
        negative_control_pass=True,
        passed=False,  # ...not passing, ONLY because of too few runs
        raw_report={"gate_failures": ["insufficient_runs"]},
        created_at=run.created_at,
    )
    repo = AsyncMock()
    repo.get_latest = AsyncMock(return_value=failing)
    app.dependency_overrides[get_benchmark_runs_repo] = lambda: repo

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        f"/internal/projects/{uuid4()}/benchmark-status",
        params={"user_id": str(uuid4())},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["passed"] is False
    assert body["gate_failures"] == ["insufficient_runs"]
    assert body["recall_at_3"] == 1.0  # the badge must NOT say "low-quality" here


def test_gate_failures_from_raw_is_defensive():
    from app.routers.internal_benchmark import gate_failures_from_raw

    assert gate_failures_from_raw({"gate_failures": ["low_recall", "low_mrr"]}) == [
        "low_recall", "low_mrr",
    ]
    assert gate_failures_from_raw({}) == []
    assert gate_failures_from_raw(None) == []
    assert gate_failures_from_raw({"gate_failures": "oops-not-a-list"}) == []


def test_benchmark_status_returns_has_run_false_when_empty():
    """No-run-yet is a valid 200 response (not a 404) — the FE
    renders a 'Run benchmark' CTA for this state."""
    repo = AsyncMock()
    repo.get_latest = AsyncMock(return_value=None)
    app.dependency_overrides[get_benchmark_runs_repo] = lambda: repo

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        f"/internal/projects/{uuid4()}/benchmark-status",
        params={"user_id": str(uuid4()), "embedding_model": "bge-m3"},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_run"] is False
    assert body["passed"] is None
    assert body["recall_at_3"] is None


def test_benchmark_status_requires_internal_token():
    """Missing / wrong X-Internal-Token → 401 from the shared
    middleware. Same rule as every /internal/* endpoint."""
    repo = AsyncMock()
    repo.get_latest = AsyncMock(return_value=None)
    app.dependency_overrides[get_benchmark_runs_repo] = lambda: repo

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        f"/internal/projects/{uuid4()}/benchmark-status",
        params={"user_id": str(uuid4())},
        # no token header
    )
    assert resp.status_code == 401


def test_benchmark_status_forwards_embedding_model_filter():
    """Omitting embedding_model → repo.get_latest called with None.
    Catches a regression that dropped the query-param plumbing."""
    repo = AsyncMock()
    repo.get_latest = AsyncMock(return_value=None)
    app.dependency_overrides[get_benchmark_runs_repo] = lambda: repo

    client = TestClient(app, raise_server_exceptions=False)
    client.get(
        f"/internal/projects/{uuid4()}/benchmark-status",
        params={"user_id": str(uuid4())},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert repo.get_latest.await_args.args[-1] is None  # embedding_model arg


def test_benchmark_status_failed_run_surfaces_passed_false():
    """A failing benchmark still returns has_run=True — the FE shows
    the red badge + a 'See report' link. Returning has_run=False
    here would hide a failing model behind the 'no run yet' banner."""
    failing = BenchmarkRun(
        benchmark_run_id=uuid4(),
        project_id=uuid4(),
        embedding_provider_id=None,
        embedding_model="nomic-embed-code",  # known-bad for natural language
        run_id="run-failing",
        recall_at_3=0.10,
        mrr=0.08,
        avg_score_positive=0.20,
        stddev=0.02,
        negative_control_pass=True,
        passed=False,
        raw_report={},
        created_at=datetime.now(timezone.utc),
    )
    repo = AsyncMock()
    repo.get_latest = AsyncMock(return_value=failing)
    app.dependency_overrides[get_benchmark_runs_repo] = lambda: repo

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        f"/internal/projects/{uuid4()}/benchmark-status",
        params={"user_id": str(uuid4())},
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_run"] is True
    assert body["passed"] is False
    assert body["recall_at_3"] == 0.10
