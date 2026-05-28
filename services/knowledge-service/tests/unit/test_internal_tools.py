"""K21.3 — unit tests for POST /internal/tools/execute.

`execute_tool` is mocked, so these verify the endpoint's own job:
internal-token auth, request validation, the always-200 envelope vs.
503-on-infra-failure split, and that the trusted envelope scope is
forwarded into the ToolContext. Executor behaviour itself is covered
by test_tool_executor.py. Mirrors the mock-the-repo-layer pattern of
test_drawers_api.py so it runs without Neo4j.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.tools.executor import ToolResult

# Matches conftest.py's INTERNAL_SERVICE_TOKEN default.
_TOKEN = "default_test_token"
_AUTH = {"X-Internal-Token": _TOKEN}
_USER = str(uuid4())
_PROJECT = str(uuid4())

_EXEC = "app.routers.internal_tools.execute_tool"


@pytest.fixture
def client():
    from app.deps import (
        get_embedding_client,
        get_pending_facts_repo,
        get_projects_repo,
    )
    from app.main import app

    # The executor is mocked in every test, so these deps are never
    # exercised — stub them so DI doesn't reach for a real DB pool.
    app.dependency_overrides[get_projects_repo] = lambda: MagicMock()
    app.dependency_overrides[get_pending_facts_repo] = lambda: MagicMock()
    app.dependency_overrides[get_embedding_client] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _body(**over) -> dict:
    body = {
        "user_id": _USER,
        "project_id": _PROJECT,
        "session_id": "sess-1",
        "tool_name": "memory_search",
        "tool_args": {"query": "x"},
    }
    body.update(over)
    return body


# ── auth ──────────────────────────────────────────────────────────────


def test_missing_token_rejected(client):
    resp = client.post("/internal/tools/execute", json=_body())
    assert resp.status_code == 401


def test_bad_token_rejected(client):
    resp = client.post("/internal/tools/execute", json=_body(),
                        headers={"X-Internal-Token": "wrong"})
    assert resp.status_code == 401


# ── envelope ──────────────────────────────────────────────────────────


def test_success_envelope(client):
    mock = AsyncMock(return_value=ToolResult(
        success=True, result={"hits": [], "count": 0}))
    with patch(_EXEC, mock):
        resp = client.post("/internal/tools/execute", json=_body(), headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json() == {
        "success": True, "result": {"hits": [], "count": 0}, "error": None,
    }


def test_tool_error_envelope_is_still_200(client):
    """A tool-level failure is success=False at HTTP 200 — never a 5xx."""
    mock = AsyncMock(return_value=ToolResult(
        success=False, error="unknown tool: 'bogus'"))
    with patch(_EXEC, mock):
        resp = client.post("/internal/tools/execute",
                            json=_body(tool_name="bogus", tool_args={}),
                            headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["result"] is None
    assert "unknown tool" in body["error"]


def test_infra_error_returns_503(client):
    """An exception out of the executor is an infrastructure failure —
    503, so the caller retries rather than treating it as a refusal."""
    mock = AsyncMock(side_effect=RuntimeError("neo4j connection lost"))
    with patch(_EXEC, mock):
        resp = client.post("/internal/tools/execute", json=_body(), headers=_AUTH)
    assert resp.status_code == 503


def test_envelope_scope_forwarded_to_executor(client):
    mock = AsyncMock(return_value=ToolResult(success=True, result={}))
    with patch(_EXEC, mock):
        client.post(
            "/internal/tools/execute",
            json=_body(tool_name="memory_remember",
                       tool_args={"fact_text": "f", "fact_type": "decision"}),
            headers=_AUTH,
        )
    ctx, tool_name, tool_args = mock.call_args.args
    assert tool_name == "memory_remember"
    assert tool_args == {"fact_text": "f", "fact_type": "decision"}
    assert str(ctx.user_id) == _USER
    assert str(ctx.project_id) == _PROJECT
    assert ctx.session_id == "sess-1"


# ── request validation ────────────────────────────────────────────────


def test_missing_session_id_is_422(client):
    body = _body()
    del body["session_id"]
    resp = client.post("/internal/tools/execute", json=body, headers=_AUTH)
    assert resp.status_code == 422


def test_empty_session_id_is_422(client):
    resp = client.post("/internal/tools/execute",
                        json=_body(session_id=""), headers=_AUTH)
    assert resp.status_code == 422


def test_null_project_id_accepted(client):
    """A no-project chat omits project_id — the endpoint accepts null
    and passes it through (per-tool null handling is design D3)."""
    mock = AsyncMock(return_value=ToolResult(success=True, result={"found": False}))
    with patch(_EXEC, mock):
        resp = client.post(
            "/internal/tools/execute",
            json=_body(project_id=None, tool_name="memory_recall_entity",
                       tool_args={"entity_name": "Kai"}),
            headers=_AUTH,
        )
    assert resp.status_code == 200
    ctx, _, _ = mock.call_args.args
    assert ctx.project_id is None


# ── GET /internal/tools/definitions (K21-B D1) ────────────────────────


def test_definitions_requires_internal_token(client):
    """The whole /internal/* surface is internal-token gated — the
    definitions endpoint is no exception even though schemas aren't
    secret."""
    resp = client.get("/internal/tools/definitions")
    assert resp.status_code == 401


def test_definitions_bad_token_rejected(client):
    resp = client.get("/internal/tools/definitions",
                       headers={"X-Internal-Token": "wrong"})
    assert resp.status_code == 401


def test_definitions_returns_all_five_tool_schemas(client):
    """D1 — the endpoint serves TOOL_DEFINITIONS verbatim so
    chat-service can fetch the OpenAI tool schemas single-sourced."""
    resp = client.get("/internal/tools/definitions", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"tools"}
    tools = body["tools"]
    assert len(tools) == 5
    # The five Cycle A memory tools, in definition order.
    names = [t["function"]["name"] for t in tools]
    assert names == [
        "memory_search",
        "memory_recall_entity",
        "memory_timeline",
        "memory_remember",
        "memory_forget",
    ]
    # Every entry is an OpenAI function-calling schema.
    for t in tools:
        assert t["type"] == "function"
        fn = t["function"]
        assert {"name", "description", "parameters"} <= set(fn)
        assert fn["parameters"]["type"] == "object"


def test_definitions_matches_source_list(client):
    """Defends against the endpoint silently transforming or
    re-shaping the schemas — it must return TOOL_DEFINITIONS exactly."""
    from app.tools.definitions import TOOL_DEFINITIONS

    resp = client.get("/internal/tools/definitions", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["tools"] == TOOL_DEFINITIONS
