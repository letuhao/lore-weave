"""C13 — glossary pinning (worker-ai half).

Covers:
  1. GlossaryClient.fetch_entities_by_ids — returns the entity NAMES from the
     /internal/books/{book_id}/entities/by-ids select-for-context shape, reusing
     the X-Internal-Token header (no new secret). Empty input / non-200 / decode
     failure degrade to [] (the runner runs un-pinned, never blocks).
  2. _decode_pinned — JSONB normalisation (str | list | None).

These are the units the cycle brief requires: "fetch_entities_by_ids returns
names; known_entities non-empty when a pinned set is present" — the second half
(runner wiring) is asserted by the live-smoke + the decoupled/sync code paths
that now pass `pinned_names` into known_entities.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.clients import GlossaryClient


def _glossary_with(handler) -> GlossaryClient:
    gc = GlossaryClient("http://glossary-service:8211", "tok", 5.0)
    gc._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"X-Internal-Token": "tok"},
    )
    return gc


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_returns_names():
    book_id = uuid4()
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["token"] = req.headers.get("X-Internal-Token")
        captured["body"] = req.content
        # select-for-context row shape: name is `cached_name`.
        return httpx.Response(200, json={"items": [
            {"entity_id": "e1", "cached_name": "PanGu", "kind_code": "deity"},
            {"entity_id": "e2", "cached_name": "Nuwa", "kind_code": "deity"},
        ]})

    gc = _glossary_with(handler)
    names = await gc.fetch_entities_by_ids(book_id, ["e1", "e2"])

    assert names == ["PanGu", "Nuwa"]
    # Hits the SAME internal endpoint the knowledge-service selector uses.
    assert f"/internal/books/{book_id}/entities/by-ids" in captured["url"]
    # Reuses the existing X-Internal-Token — NO new secret.
    assert captured["token"] == "tok"
    assert b"e1" in captured["body"] and b"e2" in captured["body"]


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_empty_input_no_call():
    called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"items": []})

    gc = _glossary_with(handler)
    assert await gc.fetch_entities_by_ids(uuid4(), []) == []
    assert called["n"] == 0  # short-circuits, no HTTP call


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_non_200_degrades_to_empty():
    gc = _glossary_with(lambda req: httpx.Response(503))
    assert await gc.fetch_entities_by_ids(uuid4(), ["e1"]) == []


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_drops_blank_names():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [
            {"entity_id": "e1", "cached_name": "  "},   # blank → dropped
            {"entity_id": "e2", "cached_name": "Kai"},
            {"entity_id": "e3"},                          # missing → dropped
        ]})

    gc = _glossary_with(handler)
    assert await gc.fetch_entities_by_ids(uuid4(), ["e1", "e2", "e3"]) == ["Kai"]


@pytest.mark.asyncio
async def test_fetch_entities_by_ids_network_error_degrades_to_empty():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    gc = _glossary_with(handler)
    assert await gc.fetch_entities_by_ids(uuid4(), ["e1"]) == []


def test_decode_pinned_normalises_jsonb():
    from app.runner import _decode_pinned

    # NULL ⇒ None (no pins).
    assert _decode_pinned(None) is None
    # raw JSON str (asyncpg JSONB codec) ⇒ list[str].
    assert _decode_pinned('["e1", "e2"]') == ["e1", "e2"]
    # already-decoded list ⇒ list[str] (stringified).
    assert _decode_pinned(["e1", "e2"]) == ["e1", "e2"]
    # malformed JSON ⇒ None (job runs un-pinned, never crashes the poll loop).
    assert _decode_pinned("{not json") is None
    # non-list JSON ⇒ None.
    assert _decode_pinned('"e1"') is None
