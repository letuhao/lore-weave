"""Unit tests for the KAL (knowledge-gateway) client (respx).

The X1 migration's load-bearing fix is the roster cursor-DRAIN (D4 / §12.5.2): the
prior glossary path read one page and ignored `next_cursor`, truncating the cast.
These tests assert the client drains `next_cursor` to completion, forwards the
internal token + tenancy header, degrades to the partial-so-far on outage, and
respects the safety cap.
"""

from __future__ import annotations

import json as _json
import uuid

import httpx
import respx

from app.clients.kal_client import KalClient

BASE = "http://knowledge-gateway:3000"
BOOK = uuid.uuid4()
USER = uuid.uuid4()


def _roster_url() -> str:
    return f"{BASE}/v1/kal/books/{BOOK}/roster"


def _client() -> KalClient:
    return KalClient(BASE, "intok")


@respx.mock
async def test_roster_single_page_sends_internal_token_and_user_id():
    e1 = str(uuid.uuid4())
    route = respx.get(_roster_url()).mock(
        return_value=httpx.Response(200, json={"items": [{"entity_id": e1, "name": "Alice"}], "next_cursor": None})
    )
    c = _client()
    try:
        cast = await c.roster(BOOK, user_id=USER)
    finally:
        await c.aclose()
    assert cast == [{"entity_id": e1, "name": "Alice"}]
    req = route.calls.last.request
    assert req.headers["X-Internal-Token"] == "intok"
    assert req.headers["X-User-Id"] == str(USER)


@respx.mock
async def test_roster_drains_next_cursor_to_completion():
    """THE D4 fix: a multi-page roster is followed across `next_cursor` until null —
    the cast is complete-in-aggregate, not truncated at the first page."""
    e1, e2, e3 = (str(uuid.uuid4()) for _ in range(3))
    pages = [
        httpx.Response(200, json={"items": [{"entity_id": e1, "name": "A"}], "next_cursor": "c1"}),
        httpx.Response(200, json={"items": [{"entity_id": e2, "name": "B"}], "next_cursor": "c2"}),
        httpx.Response(200, json={"items": [{"entity_id": e3, "name": "C"}], "next_cursor": None}),
    ]
    route = respx.get(_roster_url()).mock(side_effect=pages)
    c = _client()
    try:
        cast = await c.roster(BOOK, user_id=USER)
    finally:
        await c.aclose()
    assert [e["entity_id"] for e in cast] == [e1, e2, e3]
    # 3 pages fetched; the cursor was threaded forward on pages 2 and 3.
    assert route.call_count == 3
    assert "cursor" not in dict(route.calls[0].request.url.params)
    assert dict(route.calls[1].request.url.params)["cursor"] == "c1"
    assert dict(route.calls[2].request.url.params)["cursor"] == "c2"


@respx.mock
async def test_roster_partial_on_mid_drain_outage():
    """A 5xx mid-drain returns the pages gathered so far (never raises) — the planner
    tolerates a thin roster."""
    e1 = str(uuid.uuid4())
    route = respx.get(_roster_url()).mock(side_effect=[
        httpx.Response(200, json={"items": [{"entity_id": e1, "name": "A"}], "next_cursor": "c1"}),
        httpx.Response(503),
    ])
    c = _client()
    try:
        cast = await c.roster(BOOK, user_id=USER)
    finally:
        await c.aclose()
    assert cast == [{"entity_id": e1, "name": "A"}]
    assert route.call_count == 2


@respx.mock
async def test_roster_empty_on_first_page_outage():
    respx.get(_roster_url()).mock(return_value=httpx.Response(500))
    c = _client()
    try:
        assert await c.roster(BOOK, user_id=USER) == []
        respx.get(_roster_url()).mock(side_effect=httpx.ConnectError("x"))
        assert await c.roster(BOOK, user_id=USER) == []
    finally:
        await c.aclose()


@respx.mock
async def test_roster_skips_malformed_items_and_omits_user_id_when_absent():
    good = str(uuid.uuid4())
    route = respx.get(_roster_url()).mock(
        return_value=httpx.Response(200, json={"items": [
            {"entity_id": good, "name": "Good"},
            {"entity_id": None, "name": "NoId"},
            {"entity_id": str(uuid.uuid4())},  # no name
        ], "next_cursor": None})
    )
    c = _client()
    try:
        cast = await c.roster(BOOK)  # no user_id
    finally:
        await c.aclose()
    assert cast == [{"entity_id": good, "name": "Good"}]
    assert "X-User-Id" not in route.calls.last.request.headers


@respx.mock
async def test_roster_safety_cap_stops_an_endless_cursor():
    """A pathological never-null cursor is bounded by the page cap (no infinite loop)."""
    from app.clients import kal_client

    route = respx.get(_roster_url()).mock(
        return_value=httpx.Response(200, json={"items": [{"entity_id": str(uuid.uuid4()), "name": "X"}],
                                               "next_cursor": "always"})
    )
    c = _client()
    try:
        cast = await c.roster(BOOK, user_id=USER)
    finally:
        await c.aclose()
    assert route.call_count == kal_client._ROSTER_MAX_PAGES
    assert len(cast) == kal_client._ROSTER_MAX_PAGES
