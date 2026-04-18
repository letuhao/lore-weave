"""K16.8 — Unit tests for delete-graph endpoint."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
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
        extraction_status="ready",
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
    return f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/graph"


# ── Tests ────────────────────────────────────────────────────────────


@patch("app.routers.public.extraction.neo4j_session")
@patch("app.routers.public.extraction.app_settings")
def test_delete_graph_success(mock_settings, mock_neo4j):
    mock_settings.neo4j_uri = "bolt://localhost:7687"

    # Mock Neo4j session that returns delete counts
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"deleted": 10})
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client, repo = _make_client()
    resp = client.delete(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes_deleted"] == 40  # 4 labels × 10 each
    assert data["extraction_status"] == "disabled"

    repo.set_extraction_state.assert_called_once_with(
        _TEST_USER, _TEST_PROJECT,
        extraction_enabled=False,
        extraction_status="disabled",
    )


def test_delete_graph_project_not_found():
    client, _ = _make_client(project=_NO_PROJECT)
    resp = client.delete(_url())
    assert resp.status_code == 404


def test_delete_graph_active_job_returns_409():
    active = _job_stub(status="running")
    client, _ = _make_client(active_jobs=[active])
    resp = client.delete(_url())
    assert resp.status_code == 409
    assert "cancel it first" in resp.json()["detail"]


def test_delete_graph_paused_job_returns_409():
    paused = _job_stub(status="paused")
    client, _ = _make_client(active_jobs=[paused])
    resp = client.delete(_url())
    assert resp.status_code == 409


@patch("app.routers.public.extraction.app_settings")
def test_delete_graph_neo4j_not_configured_returns_503(mock_settings):
    mock_settings.neo4j_uri = ""
    client, _ = _make_client()
    resp = client.delete(_url())
    assert resp.status_code == 503


@patch("app.routers.public.extraction.neo4j_session")
@patch("app.routers.public.extraction.app_settings")
def test_delete_graph_neo4j_error_returns_500_project_unchanged(mock_settings, mock_neo4j):
    """If Neo4j fails mid-delete, project state is NOT updated (fail-safe)."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"

    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=RuntimeError("Neo4j connection lost"))
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client, repo = _make_client()
    resp = client.delete(_url())
    assert resp.status_code == 500

    # Project state should NOT have been updated
    repo.set_extraction_state.assert_not_called()
