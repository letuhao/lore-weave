"""K16.3 — Unit tests for extraction start endpoint.

The start endpoint runs a multi-step transaction (create job + update
project + transition to running) via raw pool access. Tests mock both
the repos AND the pool to control transaction behavior.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.clients.book_client import BookClient
from app.clients.glossary_client import GlossaryClient
from app.db.repositories.extraction_jobs import ExtractionJob

# Sentinel for "project not found"
_NO_PROJECT = object()
# Sentinel for "no benchmark run yet" — distinct from None which means
# "default (passing benchmark)" in _make_client's kwarg semantics.
_NO_BENCHMARK = object()

_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()
_TEST_BOOK = uuid4()
_TEST_JOB_ID = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _project_stub(book_id: UUID | None = _TEST_BOOK):
    from app.db.models import Project
    return Project(
        project_id=_TEST_PROJECT,
        user_id=_TEST_USER,
        name="Test",
        description="",
        project_type="translation",
        book_id=book_id,
        instructions="",
        extraction_enabled=False,
        extraction_status="disabled",
        extraction_config={},
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _job_stub(**overrides) -> ExtractionJob:
    defaults = dict(
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER,
        project_id=_TEST_PROJECT,
        scope="all",
        scope_range=None,
        status="running",
        llm_model="test-model",
        embedding_model="bge-m3",
        max_spend_usd=Decimal("10.00"),
        items_total=100,
        items_processed=0,
        current_cursor=None,
        cost_spent_usd=Decimal("0"),
        started_at=datetime.now(timezone.utc),
        paused_at=None,
        completed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        error_message=None,
    )
    defaults.update(overrides)
    return ExtractionJob(**defaults)


def _benchmark_run_stub(*, passed: bool = True, model: str = "bge-m3"):
    """K17.9 gate: default to a passing run so existing tests keep
    working without threading a benchmark row through every test."""
    from datetime import datetime as _dt, timezone as _tz
    from app.db.repositories.benchmark_runs import BenchmarkRun
    return BenchmarkRun(
        benchmark_run_id=uuid4(),
        project_id=_TEST_PROJECT,
        embedding_provider_id=None,
        embedding_model=model,
        run_id="existing-passing-run",
        recall_at_3=0.85 if passed else 0.10,
        mrr=0.72 if passed else 0.08,
        avg_score_positive=0.70 if passed else 0.20,
        stddev=0.03,
        negative_control_pass=True,
        passed=passed,
        raw_report={},
        created_at=_dt.now(_tz.utc),
    )


def _make_client(
    *,
    project=None,
    active_jobs: list | None = None,
    insert_side_effect=None,
    job_after_create: ExtractionJob | None = None,
    benchmark=None,  # default: passing run; pass `_NO_BENCHMARK` for None
) -> TestClient:
    """Build a TestClient with all deps overridden.

    Args:
        project: project stub or _NO_PROJECT for 404.
        active_jobs: list returned by jobs_repo.list_active (pre-check).
        insert_side_effect: if set, conn.fetchrow for INSERT raises this
            (e.g. asyncpg.UniqueViolationError for concurrent-start test).
        job_after_create: ExtractionJob returned by jobs_repo.get after commit.
        benchmark: BenchmarkRun stub, _NO_BENCHMARK sentinel (→ returns None),
            or None (→ defaults to a passing run). The K17.9 gate check.
    """
    from app.main import app
    from app.deps import (
        get_benchmark_runs_repo,
        get_book_client,
        get_extraction_jobs_repo,
        get_extraction_pending_repo,
        get_glossary_client,
        get_projects_repo,
    )
    from app.middleware.jwt_auth import get_current_user

    # Resolve project
    if project is _NO_PROJECT:
        repo_return = None
    else:
        repo_return = project if project is not None else _project_stub()

    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=repo_return)
    projects_repo.set_extraction_state = AsyncMock(return_value=repo_return)

    jobs_repo = AsyncMock()
    jobs_repo.list_active = AsyncMock(return_value=active_jobs or [])
    jobs_repo.get = AsyncMock(return_value=job_after_create or _job_stub())

    benchmark_repo = AsyncMock()
    if benchmark is _NO_BENCHMARK:
        benchmark_repo.get_latest = AsyncMock(return_value=None)
    else:
        benchmark_repo.get_latest = AsyncMock(
            return_value=benchmark if benchmark is not None else _benchmark_run_stub(),
        )

    # Mock the pool + connection for the transaction block
    mock_conn = AsyncMock()
    if insert_side_effect is not None:
        mock_conn.fetchrow = AsyncMock(side_effect=insert_side_effect)
    else:
        mock_conn.fetchrow = AsyncMock(return_value={"job_id": _TEST_JOB_ID})
    mock_conn.execute = AsyncMock()

    @asynccontextmanager
    async def mock_transaction():
        yield

    mock_conn.transaction = mock_transaction

    @asynccontextmanager
    async def mock_acquire():
        yield mock_conn

    mock_pool = MagicMock()
    mock_pool.acquire = mock_acquire

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    app.dependency_overrides[get_extraction_pending_repo] = lambda: AsyncMock()
    app.dependency_overrides[get_book_client] = lambda: AsyncMock(spec=BookClient)
    app.dependency_overrides[get_glossary_client] = lambda: AsyncMock(spec=GlossaryClient)
    app.dependency_overrides[get_benchmark_runs_repo] = lambda: benchmark_repo

    client = TestClient(app, raise_server_exceptions=False)
    # Patch the pool at module level so the endpoint's get_knowledge_pool()
    # returns our mock. Lifecycle: started here, stopped in _post_start
    # after the request completes. Each test MUST call _post_start exactly
    # once. If the test file grows, refactor to a fixture-based patch.
    client._pool_patch = patch(
        "app.routers.public.extraction.get_knowledge_pool",
        return_value=mock_pool,
    )
    client._pool_patch.start()
    return client


def _stop_patch(client: TestClient) -> None:
    if hasattr(client, "_pool_patch"):
        client._pool_patch.stop()
        del client._pool_patch


def _post_start(client: TestClient, **overrides):
    body = {
        "scope": "all",
        "llm_model": "test-model",
        "embedding_model": "bge-m3",
        "max_spend_usd": "10.00",
        **overrides,
    }
    resp = client.post(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/start",
        json=body,
    )
    _stop_patch(client)
    return resp


# ── Tests ────────────────────────────────────────────────────────────


def test_start_job_success_returns_201():
    client = _make_client()
    resp = _post_start(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "running"
    assert data["scope"] == "all"
    assert data["job_id"] == str(_TEST_JOB_ID)


def test_start_job_project_not_found_returns_404():
    client = _make_client(project=_NO_PROJECT)
    resp = _post_start(client)
    assert resp.status_code == 404


def test_start_job_active_job_exists_returns_409():
    """Pre-transaction check: list_for_project returns an active job."""
    active = _job_stub(status="running")
    client = _make_client(active_jobs=[active])
    resp = _post_start(client)
    assert resp.status_code == 409
    assert "active extraction job" in resp.json()["detail"]


def test_start_job_concurrent_start_unique_violation_409():
    """Concurrent start: unique partial index rejects the second INSERT."""
    client = _make_client(
        insert_side_effect=asyncpg.UniqueViolationError(
            "duplicate key value violates unique constraint"
        ),
    )
    resp = _post_start(client)
    assert resp.status_code == 409
    assert "concurrent start" in resp.json()["detail"]


def test_start_job_empty_model_rejected():
    client = _make_client()
    resp = _post_start(client, llm_model="")
    assert resp.status_code == 422


def test_start_job_empty_embedding_model_rejected():
    client = _make_client()
    resp = _post_start(client, embedding_model="")
    assert resp.status_code == 422


def test_start_job_negative_max_spend_rejected():
    client = _make_client()
    resp = _post_start(client, max_spend_usd="-5.00")
    assert resp.status_code == 422


def test_start_job_no_max_spend_accepted():
    """max_spend_usd is optional — None means unlimited budget."""
    client = _make_client()
    resp = _post_start(client, max_spend_usd=None)
    assert resp.status_code == 201


def test_start_job_with_scope_range_accepted():
    client = _make_client()
    resp = _post_start(
        client,
        scope="chapters",
        scope_range={"chapter_range": [1, 10]},
    )
    assert resp.status_code == 201


def test_start_job_paused_job_blocks_new_start():
    """A paused job is still active — should block a new start."""
    paused = _job_stub(status="paused")
    client = _make_client(active_jobs=[paused])
    resp = _post_start(client)
    assert resp.status_code == 409


# ── K17.9 benchmark gate ─────────────────────────────────────────────


def test_start_job_no_benchmark_returns_409():
    """K17.9 gate: no benchmark row for the chosen embedding_model →
    reject with 409 and a structured error_code the FE can dispatch on."""
    client = _make_client(benchmark=_NO_BENCHMARK)
    resp = _post_start(client)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error_code"] == "benchmark_missing"
    assert detail["embedding_model"] == "bge-m3"
    assert "no passing benchmark" in detail["message"].lower()
    # User-facing message must NOT leak the internal CLI command
    # (review-impl MED fix).
    assert "python -m eval" not in detail["message"]


def test_start_job_failing_benchmark_returns_409():
    """K17.9 gate: latest benchmark run has passed=False → reject
    with error_code + run_id + metrics so the FE can render a link
    to the failing report."""
    failing = _benchmark_run_stub(passed=False)
    client = _make_client(benchmark=failing)
    resp = _post_start(client)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error_code"] == "benchmark_failed"
    assert detail["run_id"] == "existing-passing-run"  # run_id from the stub
    assert detail["recall_at_3"] == pytest.approx(0.10)
    assert "low-quality" in detail["message"]


def test_start_job_passing_benchmark_succeeds():
    """K17.9 gate: a passing benchmark lets the request through —
    same shape as the existing happy-path test, just making the
    benchmark-row path explicit."""
    passing = _benchmark_run_stub(passed=True)
    client = _make_client(benchmark=passing)
    resp = _post_start(client)
    assert resp.status_code == 201
    assert resp.json()["status"] == "running"
