"""K19a.6 — Unit tests for POST /extraction/disable.

Covers the non-destructive disable path. Contrast with:
- test_extraction_delete_graph.py (destructive: deletes graph + disables)
- test_extraction_embedding_model.py (destructive: deletes graph + switches model)

The disable endpoint preserves the graph so it stays queryable from
chat/wiki flows while no new content is ingested. Idempotent short-
circuit means re-calling on an already-disabled project is a no-op.
"""

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


def _project_stub(*, extraction_enabled=True, extraction_status="ready"):
    from app.db.models import Project
    return Project(
        project_id=_TEST_PROJECT,
        user_id=_TEST_USER,
        name="Test",
        description="",
        project_type="translation",
        book_id=_TEST_BOOK,
        instructions="",
        extraction_enabled=extraction_enabled,
        extraction_status=extraction_status,
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
    active_jobs: list | None = None,
):
    from app.main import app
    from app.deps import get_extraction_jobs_repo, get_projects_repo
    from app.middleware.jwt_auth import get_current_user

    if project is _NO_PROJECT:
        repo_return = None
    else:
        repo_return = project if project is not None else _project_stub()

    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=repo_return)
    projects_repo.set_extraction_state = AsyncMock(return_value=repo_return)

    jobs_repo = AsyncMock()
    jobs_repo.list_active = AsyncMock(return_value=active_jobs or [])

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_extraction_jobs_repo] = lambda: jobs_repo

    return TestClient(app, raise_server_exceptions=False), projects_repo


def _url():
    return f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/disable"


# ── Tests ────────────────────────────────────────────────────────────


def test_disable_success_flips_state_and_preserves_graph():
    """Happy path: extraction_enabled=true + no active job → flip to
    disabled, return graph_preserved=true, repo.set_extraction_state
    called with enabled=False + status='disabled'."""
    client, repo = _make_client()
    resp = client.post(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == str(_TEST_PROJECT)
    assert data["extraction_status"] == "disabled"
    assert data["graph_preserved"] is True

    repo.set_extraction_state.assert_called_once_with(
        _TEST_USER, _TEST_PROJECT,
        extraction_enabled=False,
        extraction_status="disabled",
    )


def test_disable_project_not_found_returns_404():
    client, _ = _make_client(project=_NO_PROJECT)
    resp = client.post(_url())
    assert resp.status_code == 404
    assert resp.json()["detail"] == "project not found"


def test_disable_active_job_returns_409():
    """User must cancel a running job before disabling — prevents
    leaving a zombie job with no project-level tracking."""
    active = _job_stub(status="running")
    client, repo = _make_client(active_jobs=[active])
    resp = client.post(_url())
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "cancel it first" in detail
    assert str(_TEST_JOB_ID) in detail
    # Critical: repo must NOT be called when a 409 fires.
    repo.set_extraction_state.assert_not_called()


def test_disable_paused_job_returns_409():
    """list_active() includes 'paused' — disabling a paused-job project
    would orphan the job state. Force the user to cancel first."""
    paused = _job_stub(status="paused")
    client, _ = _make_client(active_jobs=[paused])
    resp = client.post(_url())
    assert resp.status_code == 409


def test_disable_already_disabled_is_idempotent_noop():
    """Re-calling disable on a project where extraction_enabled=false
    returns 200 with message='already disabled' and does NOT touch the
    repo — makes the endpoint safe to retry."""
    already_off = _project_stub(extraction_enabled=False, extraction_status="disabled")
    client, repo = _make_client(project=already_off)
    resp = client.post(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["extraction_status"] == "disabled"
    assert data["graph_preserved"] is True
    assert data.get("message") == "already disabled"
    repo.set_extraction_state.assert_not_called()
