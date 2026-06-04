"""Unit tests for the JWT-forwarding knowledge client (respx-mocked httpx)."""

from __future__ import annotations

import uuid

import httpx
import respx

from app.clients.knowledge_client import KnowledgeClient

BOOK = uuid.uuid4()
BASE = "http://knowledge-service:8092"
URL = f"{BASE}/v1/knowledge/projects"


async def _client() -> KnowledgeClient:
    return KnowledgeClient(BASE)


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
