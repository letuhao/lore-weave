"""K20.4 — unit tests for the internal summarize endpoint.

Covers the routing + validator layer; business logic is tested in
`test_regenerate_summaries.py`. These tests patch the regen helpers
module-level so we can assert the router passes the right args and
maps the returned `RegenerationResult` straight onto the response.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.jobs.regenerate_summaries import RegenerationResult


_TOKEN = "test-internal-token"
_USER_ID = uuid4()
_PROJECT_ID = uuid4()


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setattr(
        "app.middleware.internal_auth.settings.internal_service_token",
        _TOKEN,
        raising=False,
    )
    yield


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _make_client() -> TestClient:
    from app.main import app
    from app.deps import get_provider_client, get_summaries_repo

    app.dependency_overrides[get_provider_client] = lambda: MagicMock()
    app.dependency_overrides[get_summaries_repo] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=False)


def _auth_headers() -> dict[str, str]:
    return {"X-Internal-Token": _TOKEN}


def test_summarize_rejects_missing_token():
    client = _make_client()
    resp = client.post(
        "/internal/summarize",
        json={
            "user_id": str(_USER_ID),
            "scope_type": "global",
            "model_ref": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 401


def test_summarize_rejects_project_without_scope_id():
    client = _make_client()
    resp = client.post(
        "/internal/summarize",
        headers=_auth_headers(),
        json={
            "user_id": str(_USER_ID),
            "scope_type": "project",
            "model_ref": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 422


def test_summarize_rejects_global_with_scope_id():
    client = _make_client()
    resp = client.post(
        "/internal/summarize",
        headers=_auth_headers(),
        json={
            "user_id": str(_USER_ID),
            "scope_type": "global",
            "scope_id": str(_PROJECT_ID),
            "model_ref": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 422


@patch(
    "app.routers.internal_summarize.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.internal_summarize.regenerate_global_summary", new_callable=AsyncMock)
def test_summarize_global_dispatches_helper(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="no_op_empty_source", skipped_reason="no source"
    )
    client = _make_client()
    resp = client.post(
        "/internal/summarize",
        headers=_auth_headers(),
        json={
            "user_id": str(_USER_ID),
            "scope_type": "global",
            "model_source": "user_model",
            "model_ref": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["status"] == "no_op_empty_source"
    mock_regen.assert_awaited_once()
    kwargs = mock_regen.await_args.kwargs
    assert kwargs["model_ref"] == "gpt-4o-mini"
    assert str(kwargs["user_id"]) == str(_USER_ID)


@patch(
    "app.routers.internal_summarize.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.internal_summarize.regenerate_project_summary", new_callable=AsyncMock)
def test_summarize_project_dispatches_helper(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="user_edit_lock", skipped_reason="recent manual edit"
    )
    client = _make_client()
    resp = client.post(
        "/internal/summarize",
        headers=_auth_headers(),
        json={
            "user_id": str(_USER_ID),
            "scope_type": "project",
            "scope_id": str(_PROJECT_ID),
            "model_source": "user_model",
            "model_ref": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["status"] == "user_edit_lock"
    assert mock_regen.await_args.kwargs["project_id"] == _PROJECT_ID
