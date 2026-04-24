"""C12c-a — Unit tests for POST /internal/extraction/glossary-sync-entity.

Thin router-layer coverage:
  - auth: missing / wrong / correct X-Internal-Token
  - happy create (K15.11 helper returns action='created')
  - happy update (helper returns action='updated')
  - 422 on malformed payload
  - 502 on Neo4j exception (boundary handler)

The K15.11 helper itself is covered by test_glossary_sync.py; here we
swap it for a mock and only verify wire-contract plumbing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


_TEST_TOKEN = "default_test_token"


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _body(**overrides):
    defaults = {
        "user_id": str(uuid4()),
        "project_id": str(uuid4()),
        "glossary_entity_id": str(uuid4()),
        "name": "Alice",
        "kind": "character",
        "aliases": ["Al"],
        "short_description": "The protagonist",
    }
    defaults.update(overrides)
    return defaults


def _post(client: TestClient, body, token=_TEST_TOKEN):
    headers = {"X-Internal-Token": token} if token else {}
    return client.post(
        "/internal/extraction/glossary-sync-entity",
        json=body,
        headers=headers,
    )


# ── auth ────────────────────────────────────────────────────────────


def test_missing_token_returns_401():
    client = _client()
    r = _post(client, _body(), token=None)
    assert r.status_code == 401


def test_wrong_token_returns_401():
    client = _client()
    r = _post(client, _body(), token="nope")
    assert r.status_code == 401


# ── happy paths ─────────────────────────────────────────────────────


@patch("app.routers.internal_extraction.sync_glossary_entity_to_neo4j")
@patch("app.routers.internal_extraction.neo4j_session")
def test_create_returns_action_created(mock_sess_ctx, mock_sync):
    # neo4j_session is an async context manager — mock both enter/exit.
    mock_session = AsyncMock()
    mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

    gid = uuid4()
    mock_sync.return_value = {
        "glossary_entity_id": str(gid),
        "action": "created",
        "canonical_name": "alice",
    }

    client = _client()
    body = _body(glossary_entity_id=str(gid), name="Alice")
    r = _post(client, body)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["glossary_entity_id"] == str(gid)
    assert data["action"] == "created"
    assert data["canonical_name"] == "alice"
    mock_sync.assert_awaited_once()
    # Confirm wire → helper kwarg threading.
    call_kwargs = mock_sync.await_args.kwargs
    assert call_kwargs["name"] == "Alice"
    assert call_kwargs["kind"] == "character"
    assert call_kwargs["aliases"] == ["Al"]


@patch("app.routers.internal_extraction.sync_glossary_entity_to_neo4j")
@patch("app.routers.internal_extraction.neo4j_session")
def test_update_returns_action_updated(mock_sess_ctx, mock_sync):
    mock_session = AsyncMock()
    mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

    gid = uuid4()
    mock_sync.return_value = {
        "glossary_entity_id": str(gid),
        "action": "updated",
        "canonical_name": "merlin",
    }

    client = _client()
    r = _post(client, _body(glossary_entity_id=str(gid), name="Merlin"))

    assert r.status_code == 200, r.text
    assert r.json()["action"] == "updated"


# ── validation ──────────────────────────────────────────────────────


def test_missing_name_returns_422():
    client = _client()
    body = _body()
    del body["name"]
    r = _post(client, body)
    assert r.status_code == 422


def test_empty_name_returns_422():
    client = _client()
    r = _post(client, _body(name=""))
    assert r.status_code == 422


def test_invalid_uuid_returns_422():
    client = _client()
    r = _post(client, _body(glossary_entity_id="not-a-uuid"))
    assert r.status_code == 422


# ── error path ──────────────────────────────────────────────────────


@patch("app.routers.internal_extraction.sync_glossary_entity_to_neo4j")
@patch("app.routers.internal_extraction.neo4j_session")
def test_neo4j_failure_returns_502(mock_sess_ctx, mock_sync):
    mock_session = AsyncMock()
    mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_sync.side_effect = RuntimeError("neo4j connection refused")

    client = _client()
    r = _post(client, _body())

    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["error_code"] == "neo4j_error"
    # /review-impl LOW#4 — 502 message is opaque (no raw exception
    # text echoed across the service boundary). The full traceback
    # lives in server logs via logger.exception.
    assert detail["message"] == "failed to merge glossary entity"
    assert "connection refused" not in detail["message"]
