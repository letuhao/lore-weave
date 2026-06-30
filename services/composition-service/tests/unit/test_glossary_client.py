"""Unit tests for the glossary internal client (respx)."""

from __future__ import annotations

import uuid

import httpx
import respx

from app.clients.glossary_client import GlossaryClient

BASE = "http://glossary-service:8088"
BOOK = uuid.uuid4()
USER = uuid.uuid4()


async def _client() -> GlossaryClient:
    return GlossaryClient(BASE, "intok")


@respx.mock
async def test_select_for_context_sends_internal_token_and_returns_entities():
    route = respx.post(f"{BASE}/internal/books/{BOOK}/select-for-context").mock(
        return_value=httpx.Response(200, json={"entities": [{"entity_id": "e1", "cached_name": "Kael"}], "total_tokens_estimate": 5})
    )
    c = await _client()
    try:
        ents = await c.select_for_context(BOOK, USER, "kael", max_entities=10)
    finally:
        await c.aclose()
    assert ents == [{"entity_id": "e1", "cached_name": "Kael"}]
    req = route.calls.last.request
    assert req.headers["X-Internal-Token"] == "intok"
    import json as _json
    body = _json.loads(req.content)
    assert body["user_id"] == str(USER) and body["query"] == "kael" and body["max_entities"] == 10


@respx.mock
async def test_select_for_context_degrades_to_empty_on_failure():
    respx.post(f"{BASE}/internal/books/{BOOK}/select-for-context").mock(return_value=httpx.Response(503))
    c = await _client()
    try:
        assert await c.select_for_context(BOOK, USER, "q") == []
        respx.post(f"{BASE}/internal/books/{BOOK}/select-for-context").mock(side_effect=httpx.ConnectError("x"))
        assert await c.select_for_context(BOOK, USER, "q") == []
    finally:
        await c.aclose()
