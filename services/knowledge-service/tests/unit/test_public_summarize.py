"""K20α — unit tests for the public regenerate endpoints.

Covers the HTTP mapping layer on top of the regen helper:
  - JWT-scoped user_id (body cannot spoof)
  - 200 for `regenerated`, `no_op_similarity`, `no_op_empty_source`
  - 409 for `user_edit_lock` and `regen_concurrent_edit`
  - 422 for `no_op_guardrail`
  - 502 for ProviderError
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.provider_client import ProviderUpstreamError
from app.db.models import Summary
from app.jobs.regenerate_summaries import RegenerationResult


_TEST_USER = uuid4()
_PROJECT_ID = uuid4()


def _summary_stub(version: int = 5, scope_type: str = "global") -> Summary:
    return Summary(
        summary_id=uuid4(),
        user_id=_TEST_USER,
        scope_type=scope_type,  # type: ignore[arg-type]
        scope_id=None if scope_type == "global" else _PROJECT_ID,
        content="regenerated bio",
        token_count=10,
        version=version,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _make_client() -> TestClient:
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.deps import get_provider_client, get_summaries_repo

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_provider_client] = lambda: MagicMock()
    app.dependency_overrides[get_summaries_repo] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=False)


# ── global regenerate ────────────────────────────────────────────────


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_happy_path(mock_regen):
    summary = _summary_stub()
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=summary
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["status"] == "regenerated"
    assert body["summary"]["version"] == 5
    # JWT user_id is what reaches the helper, not anything from the body.
    assert mock_regen.await_args.kwargs["user_id"] == _TEST_USER


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_user_edit_lock_maps_409(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="user_edit_lock", skipped_reason="recent manual edit"
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["error_code"] == "user_edit_lock"
    assert "recent manual edit" in body["detail"]["message"]


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_concurrent_edit_maps_409(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="regen_concurrent_edit", skipped_reason="version bumped"
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "regen_concurrent_edit"


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_guardrail_maps_422(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="no_op_guardrail", skipped_reason="empty_output"
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "regen_guardrail_failed"


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_empty_source_returns_200(mock_regen):
    mock_regen.return_value = RegenerationResult(
        status="no_op_empty_source", skipped_reason="no source"
    )
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "no_op_empty_source"
    assert resp.json()["summary"] is None


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_global_summary", new_callable=AsyncMock)
def test_regenerate_global_provider_error_maps_502(mock_regen):
    mock_regen.side_effect = ProviderUpstreamError("upstream boom")
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["error_code"] == "provider_error"


def test_regenerate_global_rejects_missing_model_ref():
    client = _make_client()
    resp = client.post(
        "/v1/knowledge/me/summary/regenerate",
        json={"model_source": "user_model"},  # model_ref required
    )
    assert resp.status_code == 422


# ── project regenerate ───────────────────────────────────────────────


@patch(
    "app.routers.public.summaries.get_knowledge_pool",
    new=MagicMock(return_value=MagicMock()),
)
@patch("app.routers.public.summaries.regenerate_project_summary", new_callable=AsyncMock)
def test_regenerate_project_passes_project_id(mock_regen):
    summary = _summary_stub(scope_type="project")
    mock_regen.return_value = RegenerationResult(
        status="regenerated", summary=summary
    )
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/projects/{_PROJECT_ID}/summary/regenerate",
        json={"model_source": "user_model", "model_ref": "gpt-4o-mini"},
    )
    assert resp.status_code == 200, resp.json()
    assert mock_regen.await_args.kwargs["project_id"] == _PROJECT_ID
    assert mock_regen.await_args.kwargs["user_id"] == _TEST_USER
