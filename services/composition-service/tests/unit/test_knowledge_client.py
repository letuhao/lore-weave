"""Unit tests for the JWT-forwarding knowledge client (respx-mocked httpx)."""

from __future__ import annotations

import uuid

import httpx
import respx

from app.clients.knowledge_client import KnowledgeClient

BOOK = uuid.uuid4()
BASE = "http://knowledge-service:8092"
URL = f"{BASE}/v1/knowledge/projects"


PROJECT = uuid.uuid4()
USER = uuid.uuid4()


async def _client() -> KnowledgeClient:
    return KnowledgeClient(BASE, "intok")


@respx.mock
async def test_forwards_bearer_and_returns_items():
    route = respx.get(URL).mock(
        return_value=httpx.Response(200, json={"items": [{"project_id": "x"}], "next_cursor": None})
    )
    c = await _client()
    try:
        items = await c.list_projects_for_book(BOOK, "jwt-token")
    finally:
        await c.aclose()
    assert items == [{"project_id": "x"}]
    sent = route.calls.last.request
    # Forwards the user JWT (NOT an internal token) and the book_id filter.
    assert sent.headers["Authorization"] == "Bearer jwt-token"
    assert "X-Internal-Token" not in sent.headers
    assert sent.url.params["book_id"] == str(BOOK)
    assert sent.url.params["limit"] == "100"


@respx.mock
async def test_non_200_returns_none():
    respx.get(URL).mock(return_value=httpx.Response(401, json={"detail": "no"}))
    c = await _client()
    try:
        assert await c.list_projects_for_book(BOOK, "jwt") is None
    finally:
        await c.aclose()


@respx.mock
async def test_transport_error_returns_none():
    respx.get(URL).mock(side_effect=httpx.ConnectError("down"))
    c = await _client()
    try:
        assert await c.list_projects_for_book(BOOK, "jwt") is None
    finally:
        await c.aclose()


async def test_empty_bearer_returns_none_without_calling():
    # No respx route registered → if it tried to call, it would raise.
    c = await _client()
    try:
        assert await c.list_projects_for_book(BOOK, "") is None
    finally:
        await c.aclose()


# ── M4 packer-lens methods ──────────────────────────────────────────────

@respx.mock
async def test_build_context_uses_internal_token():
    route = respx.post(f"{BASE}/internal/context/build").mock(
        return_value=httpx.Response(200, json={"context": "c", "token_count": 3})
    )
    c = await _client()
    try:
        out = await c.build_context(USER, project_id=PROJECT, message="hi")
    finally:
        await c.aclose()
    assert out["context"] == "c"
    req = route.calls.last.request
    assert req.headers["X-Internal-Token"] == "intok"
    assert "Authorization" not in req.headers
    import json as _json
    body = _json.loads(req.content)
    assert body["user_id"] == str(USER) and body["project_id"] == str(PROJECT)


@respx.mock
async def test_timeline_always_sends_project_id_and_cutoff():
    route = respx.get(f"{BASE}/v1/knowledge/timeline").mock(
        return_value=httpx.Response(200, json={"events": [{"chronological_order": 5, "title": "E"}], "total": 1})
    )
    c = await _client()
    try:
        events = await c.timeline("jwt", project_id=PROJECT, before_chronological=10)
    finally:
        await c.aclose()
    assert events == [{"chronological_order": 5, "title": "E"}]
    params = route.calls.last.request.url.params
    assert params["project_id"] == str(PROJECT)  # A1: never omitted
    assert params["before_chronological"] == "10"
    assert route.calls.last.request.headers["Authorization"] == "Bearer jwt"


@respx.mock
async def test_get_entity_and_search_drawers():
    respx.get(f"{BASE}/v1/knowledge/entities/e1").mock(
        return_value=httpx.Response(200, json={"entity": {"id": "e1"}, "relations": []})
    )
    route = respx.get(f"{BASE}/v1/knowledge/drawers/search").mock(
        return_value=httpx.Response(200, json={"hits": [{"source_id": "s", "chapter_index": None, "raw_score": 0.8}], "embedding_model": "m"})
    )
    c = await _client()
    try:
        ent = await c.get_entity("jwt", "e1")
        hits = await c.search_drawers("jwt", project_id=PROJECT, query="q")
    finally:
        await c.aclose()
    assert ent["entity"]["id"] == "e1"
    assert hits[0]["raw_score"] == 0.8 and hits[0]["chapter_index"] is None
    assert route.calls.last.request.url.params["project_id"] == str(PROJECT)  # required


@respx.mock
async def test_lenses_degrade_to_empty_on_failure():
    respx.get(f"{BASE}/v1/knowledge/timeline").mock(return_value=httpx.Response(500))
    respx.get(f"{BASE}/v1/knowledge/drawers/search").mock(side_effect=httpx.ConnectError("x"))
    respx.get(f"{BASE}/v1/knowledge/entities/e1").mock(return_value=httpx.Response(404))
    respx.post(f"{BASE}/internal/context/build").mock(return_value=httpx.Response(503))
    c = await _client()
    try:
        assert await c.timeline("jwt", project_id=PROJECT) == []
        assert await c.search_drawers("jwt", project_id=PROJECT, query="q") == []
        assert await c.get_entity("jwt", "e1") is None
        assert await c.build_context(USER, project_id=PROJECT) is None
    finally:
        await c.aclose()


@respx.mock
async def test_fact_for_check_uses_internal_token_and_glossary_ids():
    """A2-S3 — fact_for_check POSTs glossary cast ids with the internal token."""
    route = respx.post(
        f"{BASE}/internal/projects/{PROJECT}/fact-for-check"
    ).mock(return_value=httpx.Response(200, json={
        "at_order": 5000000,
        "entities": [{"entity_id": "e1", "glossary_entity_id": "g1", "status": "gone"}],
        "relations": [], "events": [],
    }))
    c = await _client()
    try:
        out = await c.fact_for_check(
            project_id=PROJECT, at_order=5000000, glossary_entity_ids=["g1"])
    finally:
        await c.aclose()
    assert out["entities"][0]["status"] == "gone"
    req = route.calls.last.request
    assert req.headers["X-Internal-Token"] == "intok"
    assert "Authorization" not in req.headers
    import json as _json
    body = _json.loads(req.content)
    assert body["glossary_entity_ids"] == ["g1"] and body["at_order"] == 5000000


@respx.mock
async def test_fact_for_check_degrades_to_none():
    respx.post(f"{BASE}/internal/projects/{PROJECT}/fact-for-check").mock(
        return_value=httpx.Response(503))
    c = await _client()
    try:
        out = await c.fact_for_check(
            project_id=PROJECT, at_order=1, glossary_entity_ids=["g1"])
    finally:
        await c.aclose()
    assert out is None


async def test_fact_for_check_no_ids_returns_none_without_call():
    c = await _client()
    try:
        assert await c.fact_for_check(project_id=PROJECT, at_order=1) is None
    finally:
        await c.aclose()
