"""K19c.4 — unit tests for the user-entities public endpoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_repos.entities import Entity


_TEST_USER = uuid4()
_TEST_ENTITY_ID = "ent-abc123"


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _entity_stub(
    name: str = "Coffee drinker",
    canonical_id: str = _TEST_ENTITY_ID,
    project_id: str | None = None,
) -> Entity:
    return Entity(
        id=canonical_id,
        user_id=str(_TEST_USER),
        project_id=project_id,
        name=name,
        canonical_name=name.lower(),
        kind="preference",
        aliases=[name],
        canonical_version=1,
        source_types=["chat_turn"],
        confidence=0.9,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _make_client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return TestClient(app, raise_server_exceptions=False)


@patch("app.routers.public.entities.list_user_entities", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_user_entities_happy(mock_list):
    mock_list.return_value = [_entity_stub("Coffee drinker"), _entity_stub("Short sentences")]
    client = _make_client()
    resp = client.get("/v1/knowledge/me/entities?scope=global")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["entities"]) == 2
    assert body["entities"][0]["name"] == "Coffee drinker"
    mock_list.assert_awaited_once()
    assert mock_list.await_args.kwargs["scope"] == "global"
    assert mock_list.await_args.kwargs["limit"] == 50


@patch("app.routers.public.entities.list_user_entities", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_user_entities_invalid_scope_rejected(mock_list):
    mock_list.return_value = []
    client = _make_client()
    # FastAPI Literal validation
    resp = client.get("/v1/knowledge/me/entities?scope=project")
    assert resp.status_code == 422


@patch("app.routers.public.entities.list_user_entities", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_user_entities_limit_out_of_range_rejected(mock_list):
    mock_list.return_value = []
    client = _make_client()
    # le=ENTITIES_MAX_LIMIT=200
    assert client.get("/v1/knowledge/me/entities?limit=500").status_code == 422
    # ge=1
    assert client.get("/v1/knowledge/me/entities?limit=0").status_code == 422


@patch("app.routers.public.entities.archive_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_archive_user_entity_happy(mock_archive):
    mock_archive.return_value = _entity_stub()
    client = _make_client()
    resp = client.delete(f"/v1/knowledge/me/entities/{_TEST_ENTITY_ID}")
    assert resp.status_code == 204
    mock_archive.assert_awaited_once()
    kwargs = mock_archive.await_args.kwargs
    assert kwargs["canonical_id"] == _TEST_ENTITY_ID
    assert kwargs["reason"] == "user_archived"
    assert kwargs["user_id"] == str(_TEST_USER)


@patch("app.routers.public.entities.archive_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_archive_user_entity_not_found(mock_archive):
    """archive_entity returns None when entity doesn't exist or is
    already archived; router translates to 404."""
    mock_archive.return_value = None
    client = _make_client()
    resp = client.delete(f"/v1/knowledge/me/entities/{_TEST_ENTITY_ID}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "entity not found"
