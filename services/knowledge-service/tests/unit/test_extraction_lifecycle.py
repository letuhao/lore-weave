"""K16.4 — Unit tests for pause/resume/cancel extraction endpoints.

Tests the state-transition logic. Each endpoint: verify project →
find active job → validate transition → update status.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

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


def _make_client(
    *,
    project=None,
    active_job: ExtractionJob | None = None,
    updated_job: ExtractionJob | None = None,
) -> tuple[TestClient, AsyncMock]:
    """Returns (TestClient, projects_repo_mock) so tests can assert
    on set_extraction_state calls."""
    from app.main import app
    from app.deps import (
        get_extraction_jobs_repo,
        get_projects_repo,
    )
    from app.middleware.jwt_auth import get_current_user

    if project is _NO_PROJECT:
        repo_return = None
    else:
        repo_return = project if project is not None else _project_stub()

    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=repo_return)
    projects_repo.set_extraction_state = AsyncMock(return_value=repo_return)

    # active_job=None means no active jobs → list_active returns []
    active_list = [active_job] if active_job is not None else []
    jobs_repo = AsyncMock()
    jobs_repo.list_active = AsyncMock(return_value=active_list)
    jobs_repo.update_status = AsyncMock(
        return_value=updated_job or (active_job if active_job else _job_stub()),
    )

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo

    return TestClient(app, raise_server_exceptions=False), projects_repo


def _url(action: str) -> str:
    return f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/{action}"


# ── Pause ────────────────────────────────────────────────────────────


def test_pause_running_job_returns_200():
    running = _job_stub(status="running")
    paused = _job_stub(status="paused")
    client, repo = _make_client(active_job=running, updated_job=paused)
    resp = client.post(_url("pause"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


def test_pause_updates_project_status():
    running = _job_stub(status="running")
    paused = _job_stub(status="paused")
    client, repo = _make_client(active_job=running, updated_job=paused)
    client.post(_url("pause"))
    repo.set_extraction_state.assert_called_once_with(
        _TEST_USER, _TEST_PROJECT,
        extraction_enabled=True,
        extraction_status="paused",
    )


def test_pause_already_paused_returns_409():
    paused = _job_stub(status="paused")
    client, _ = _make_client(active_job=paused)
    resp = client.post(_url("pause"))
    assert resp.status_code == 409


def test_pause_no_active_job_returns_404():
    client, _ = _make_client(active_job=None)
    resp = client.post(_url("pause"))
    assert resp.status_code == 404


def test_pause_project_not_found_returns_404():
    client, _ = _make_client(project=_NO_PROJECT)
    resp = client.post(_url("pause"))
    assert resp.status_code == 404


# ── Resume ───────────────────────────────────────────────────────────


def test_resume_paused_job_returns_200():
    paused = _job_stub(status="paused")
    resumed = _job_stub(status="running")
    client, repo = _make_client(active_job=paused, updated_job=resumed)
    resp = client.post(_url("resume"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_resume_updates_project_status():
    paused = _job_stub(status="paused")
    resumed = _job_stub(status="running")
    client, repo = _make_client(active_job=paused, updated_job=resumed)
    client.post(_url("resume"))
    repo.set_extraction_state.assert_called_once_with(
        _TEST_USER, _TEST_PROJECT,
        extraction_enabled=True,
        extraction_status="building",
    )


def test_resume_running_job_returns_409():
    running = _job_stub(status="running")
    client, _ = _make_client(active_job=running)
    resp = client.post(_url("resume"))
    assert resp.status_code == 409


def test_resume_no_active_job_returns_404():
    client, _ = _make_client(active_job=None)
    resp = client.post(_url("resume"))
    assert resp.status_code == 404


# ── Cancel ───────────────────────────────────────────────────────────


def test_cancel_running_job_returns_200():
    running = _job_stub(status="running")
    cancelled = _job_stub(status="cancelled")
    client, _ = _make_client(active_job=running, updated_job=cancelled)
    resp = client.post(_url("cancel"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_updates_project_status_to_disabled():
    running = _job_stub(status="running")
    cancelled = _job_stub(status="cancelled")
    client, repo = _make_client(active_job=running, updated_job=cancelled)
    client.post(_url("cancel"))
    repo.set_extraction_state.assert_called_once_with(
        _TEST_USER, _TEST_PROJECT,
        extraction_enabled=False,
        extraction_status="disabled",
    )


def test_cancel_paused_job_returns_200():
    paused = _job_stub(status="paused")
    cancelled = _job_stub(status="cancelled")
    client, _ = _make_client(active_job=paused, updated_job=cancelled)
    resp = client.post(_url("cancel"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_no_active_job_returns_404():
    client, _ = _make_client(active_job=None)
    resp = client.post(_url("cancel"))
    assert resp.status_code == 404


def test_cancel_pending_job_returns_200():
    pending = _job_stub(status="pending")
    cancelled = _job_stub(status="cancelled")
    client, _ = _make_client(active_job=pending, updated_job=cancelled)
    resp = client.post(_url("cancel"))
    assert resp.status_code == 200
