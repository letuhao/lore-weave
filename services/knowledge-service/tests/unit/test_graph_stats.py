"""K19a.4 — Unit tests for GET /v1/knowledge/projects/{id}/graph-stats."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

_NO_PROJECT = object()
_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()
_TEST_BOOK = uuid4()
_EXTRACTED_AT = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)


def _project_stub(last_extracted_at=_EXTRACTED_AT):
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
        last_extracted_at=last_extracted_at,
        is_archived=False,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_client(*, project=_project_stub()):
    from app.main import app
    from app.deps import get_projects_repo
    from app.middleware.jwt_auth import get_current_user

    repo_return = None if project is _NO_PROJECT else project

    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=repo_return)

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo

    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _url():
    return f"/v1/knowledge/projects/{_TEST_PROJECT}/graph-stats"


def _mock_neo4j(record_value):
    """Build a patched neo4j_session context manager that returns the
    given `record_value` from result.single().
    """
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value=record_value)
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


@patch("app.routers.public.extraction.neo4j_session")
def test_graph_stats_happy_path(mock_neo4j_session):
    mock_neo4j_session.return_value = _mock_neo4j(
        {
            "entity_count": 150,
            "fact_count": 420,
            "event_count": 38,
            "passage_count": 900,
        }
    )
    client = next(_make_client())
    resp = client.get(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == str(_TEST_PROJECT)
    assert data["entity_count"] == 150
    assert data["fact_count"] == 420
    assert data["event_count"] == 38
    assert data["passage_count"] == 900
    # Project.last_extracted_at is passed through as ISO-8601 UTC.
    assert data["last_extracted_at"] is not None
    assert data["last_extracted_at"].startswith("2026-04-19T12:00:00")


@patch("app.routers.public.extraction.neo4j_session")
def test_graph_stats_empty_graph_returns_zeros(mock_neo4j_session):
    mock_neo4j_session.return_value = _mock_neo4j(
        {"entity_count": 0, "fact_count": 0, "event_count": 0, "passage_count": 0}
    )
    client = next(_make_client())
    resp = client.get(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_count"] == 0
    assert data["fact_count"] == 0
    assert data["event_count"] == 0
    assert data["passage_count"] == 0


@patch("app.routers.public.extraction.neo4j_session")
def test_graph_stats_null_last_extracted_at_passes_through(mock_neo4j_session):
    mock_neo4j_session.return_value = _mock_neo4j(
        {"entity_count": 0, "fact_count": 0, "event_count": 0, "passage_count": 0}
    )
    client = next(_make_client(project=_project_stub(last_extracted_at=None)))
    resp = client.get(_url())
    assert resp.status_code == 200
    assert resp.json()["last_extracted_at"] is None


def test_graph_stats_project_not_found_returns_404():
    client = next(_make_client(project=_NO_PROJECT))
    resp = client.get(_url())
    assert resp.status_code == 404
    assert resp.json()["detail"] == "project not found"


@patch("app.routers.public.extraction.neo4j_session")
def test_graph_stats_handles_missing_cypher_record(mock_neo4j_session):
    # Defensive: if result.single() returns None for some reason, the
    # handler should still return a 200 with zeros + the project's
    # last_extracted_at — never 500.
    mock_neo4j_session.return_value = _mock_neo4j(None)
    client = next(_make_client())
    resp = client.get(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_count"] == 0
    assert data["fact_count"] == 0
    assert data["last_extracted_at"] is not None


@patch("app.routers.public.extraction.neo4j_session")
def test_graph_stats_handles_null_count_values(mock_neo4j_session):
    # Defensive: Cypher SUM over empty sets can return None in some
    # versions. The int(... or 0) guard should make this safe.
    mock_neo4j_session.return_value = _mock_neo4j(
        {
            "entity_count": None,
            "fact_count": None,
            "event_count": None,
            "passage_count": None,
        }
    )
    client = next(_make_client())
    resp = client.get(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_count"] == 0
    assert data["fact_count"] == 0
