"""K16.5 — Unit tests for job status + project job list endpoints."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.extraction_jobs import ExtractionJob

_NO_PROJECT = object()
_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()
_TEST_BOOK = uuid4()
_TEST_JOB_ID = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _project_stub():
    from app.db.models import Project
    return Project(
        project_id=_TEST_PROJECT,
        user_id=_TEST_USER,
        name="Test",
        description="",
        project_type="translation",
        book_id=_TEST_BOOK,
        instructions="",
        extraction_enabled=True,
        extraction_status="building",
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
        items_processed=42,
        current_cursor=None,
        cost_spent_usd=Decimal("1.50"),
        started_at=datetime(2026, 4, 18, 10, 0, 0, tzinfo=timezone.utc),
        paused_at=None,
        completed_at=None,
        created_at=datetime(2026, 4, 18, 9, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 18, 10, 5, 0, tzinfo=timezone.utc),
        error_message=None,
    )
    defaults.update(overrides)
    return ExtractionJob(**defaults)


def _setup_overrides(*, job=None, jobs_list=None, project=None):
    from app.main import app
    from app.deps import get_extraction_jobs_repo, get_projects_repo
    from app.middleware.jwt_auth import get_current_user

    jobs_repo = AsyncMock()
    jobs_repo.get = AsyncMock(return_value=job)
    jobs_repo.list_for_project = AsyncMock(return_value=jobs_list or [])

    if project is _NO_PROJECT:
        proj_return = None
    else:
        proj_return = project if project is not None else _project_stub()
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=proj_return)

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo

    return TestClient(app, raise_server_exceptions=False)


def _setup_list_all_overrides(*, all_jobs=None):
    """K19b.1 helper — wires list_all_for_user and returns both the
    client and the mock so the test can inspect call kwargs."""
    from app.main import app
    from app.deps import get_extraction_jobs_repo
    from app.middleware.jwt_auth import get_current_user

    jobs_repo = AsyncMock()
    jobs_repo.list_all_for_user = AsyncMock(return_value=all_jobs or [])

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo

    return TestClient(app, raise_server_exceptions=False), jobs_repo


# ── GET /v1/knowledge/extraction/jobs/{job_id} ──────────────────────


def test_get_job_returns_200_with_etag():
    job = _job_stub()
    client = _setup_overrides(job=job)
    resp = client.get(f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == str(_TEST_JOB_ID)
    assert data["items_processed"] == 42
    assert "ETag" in resp.headers
    assert resp.headers["ETag"].startswith('W/"')


def test_get_job_not_found_returns_404():
    client = _setup_overrides(job=None)
    resp = client.get(f"/v1/knowledge/extraction/jobs/{uuid4()}")
    assert resp.status_code == 404


def test_get_job_304_when_etag_matches():
    job = _job_stub()
    client = _setup_overrides(job=job)
    # First request to get the ETag
    resp1 = client.get(f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}")
    etag = resp1.headers["ETag"]
    # Second request with If-None-Match
    resp2 = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}",
        headers={"If-None-Match": etag},
    )
    assert resp2.status_code == 304


def test_get_job_200_when_etag_stale():
    job = _job_stub()
    client = _setup_overrides(job=job)
    resp = client.get(
        f"/v1/knowledge/extraction/jobs/{_TEST_JOB_ID}",
        headers={"If-None-Match": 'W/"0"'},
    )
    assert resp.status_code == 200


# ── GET /v1/knowledge/projects/{id}/extraction/jobs ─────────────────


def test_list_jobs_returns_200():
    jobs = [_job_stub(status="complete"), _job_stub(status="running")]
    client = _setup_overrides(jobs_list=jobs)
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/jobs",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_jobs_empty_project_returns_empty():
    client = _setup_overrides(jobs_list=[])
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/jobs",
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_jobs_project_not_found_returns_404():
    client = _setup_overrides(project=_NO_PROJECT)
    resp = client.get(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/jobs",
    )
    assert resp.status_code == 404


# ── K19b.1: GET /v1/knowledge/extraction/jobs ─────────────────────────


def test_list_all_jobs_active_returns_200():
    jobs = [_job_stub(status="running"), _job_stub(status="pending")]
    client, repo = _setup_list_all_overrides(all_jobs=jobs)
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=active")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    repo.list_all_for_user.assert_awaited_once_with(
        _TEST_USER, status_group="active", limit=50
    )


def test_list_all_jobs_history_returns_200_with_custom_limit():
    jobs = [_job_stub(status="complete")]
    client, repo = _setup_list_all_overrides(all_jobs=jobs)
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=history&limit=25")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    repo.list_all_for_user.assert_awaited_once_with(
        _TEST_USER, status_group="history", limit=25
    )


def test_list_all_jobs_missing_status_group_returns_422():
    client, _repo = _setup_list_all_overrides()
    resp = client.get("/v1/knowledge/extraction/jobs")
    assert resp.status_code == 422


def test_list_all_jobs_invalid_status_group_returns_422():
    client, _repo = _setup_list_all_overrides()
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=bogus")
    assert resp.status_code == 422


def test_list_all_jobs_limit_out_of_range_returns_422():
    client, _repo = _setup_list_all_overrides()
    # le=200 on the Query validator
    resp_too_big = client.get(
        "/v1/knowledge/extraction/jobs?status_group=active&limit=500"
    )
    assert resp_too_big.status_code == 422
    # ge=1 on the Query validator
    resp_too_small = client.get(
        "/v1/knowledge/extraction/jobs?status_group=active&limit=0"
    )
    assert resp_too_small.status_code == 422


def test_list_all_jobs_empty_returns_empty_array():
    client, _repo = _setup_list_all_overrides(all_jobs=[])
    resp = client.get("/v1/knowledge/extraction/jobs?status_group=history")
    assert resp.status_code == 200
    assert resp.json() == []
