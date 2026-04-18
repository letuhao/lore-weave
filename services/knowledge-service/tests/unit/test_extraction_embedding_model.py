"""K16.10 — Unit tests for change embedding model endpoint."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.extraction_jobs import ExtractionJob

_NO_PROJECT = object()
_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _project_stub(embedding_model="bge-m3"):
    from app.db.models import Project
    return Project(
        project_id=_TEST_PROJECT, user_id=_TEST_USER, name="Test",
        description="", project_type="translation", book_id=uuid4(),
        instructions="", extraction_enabled=True, extraction_status="ready",
        extraction_config={}, embedding_model=embedding_model,
        estimated_cost_usd=Decimal("0"), actual_cost_usd=Decimal("0"),
        is_archived=False, version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_client(*, project=None, active_jobs=None):
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


def _url(confirm=False):
    base = f"/v1/knowledge/projects/{_TEST_PROJECT}/embedding-model"
    return f"{base}?confirm=true" if confirm else base


def _body(model="text-embedding-3-small"):
    return {"embedding_model": model}


# ── Tests ────────────────────────────────────────────────────────────


def test_without_confirm_returns_warning():
    client, _ = _make_client()
    resp = client.put(_url(confirm=False), json=_body())
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_required"] == "confirm"
    assert data["current_model"] == "bge-m3"
    assert data["new_model"] == "text-embedding-3-small"
    assert "warning" in data


@patch("app.routers.public.extraction.neo4j_session")
@patch("app.routers.public.extraction.app_settings")
def test_with_confirm_deletes_graph_and_updates_model(mock_settings, mock_neo4j):
    mock_settings.neo4j_uri = "bolt://localhost:7687"

    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"deleted": 5})
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client, repo = _make_client()
    resp = client.put(_url(confirm=True), json=_body())
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_model"] == "text-embedding-3-small"
    assert data["nodes_deleted"] == 20  # 4 labels × 5
    assert data["extraction_status"] == "disabled"

    repo.set_extraction_state.assert_called_once_with(
        _TEST_USER, _TEST_PROJECT,
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model="text-embedding-3-small",
    )


def test_project_not_found_returns_404():
    client, _ = _make_client(project=_NO_PROJECT)
    resp = client.put(_url(), json=_body())
    assert resp.status_code == 404


def test_active_job_returns_409():
    from app.db.repositories.extraction_jobs import ExtractionJob
    active = ExtractionJob(
        job_id=uuid4(), user_id=_TEST_USER, project_id=_TEST_PROJECT,
        scope="all", status="running", llm_model="m", embedding_model="e",
        items_processed=0, cost_spent_usd=Decimal("0"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    client, _ = _make_client(active_jobs=[active])
    resp = client.put(_url(), json=_body())
    assert resp.status_code == 409


def test_empty_model_rejected():
    client, _ = _make_client()
    resp = client.put(_url(), json=_body(model=""))
    assert resp.status_code == 422


@patch("app.routers.public.extraction.app_settings")
def test_confirm_without_neo4j_returns_503(mock_settings):
    mock_settings.neo4j_uri = ""
    client, _ = _make_client()
    resp = client.put(_url(confirm=True), json=_body())
    assert resp.status_code == 503
