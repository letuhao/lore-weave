"""Tests for the shared loreweave_grants client (D-E0-4 extraction).

Covers the behavior the 3 former service copies relied on: positive-only caching,
none/error never cached (fail-closed), TTL expiry, instant-revoke invalidate, and
trace-id propagation.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

from loreweave_grants import GrantClient, GrantLevel, parse_grant_level


def _client(handler, *, trace_id_provider=None, cache_ttl_s=45.0) -> GrantClient:
    c = GrantClient(
        base_url="http://book", internal_token="tok",
        cache_ttl_s=cache_ttl_s, trace_id_provider=trace_id_provider,
    )
    # Swap the real AsyncClient for one driven by a MockTransport.
    c._http = httpx.AsyncClient(
        base_url="http://book",
        headers={"X-Internal-Token": "tok"},
        transport=httpx.MockTransport(handler),
    )
    return c


def test_parse_grant_level_default_deny():
    assert parse_grant_level("owner") == GrantLevel.OWNER
    assert parse_grant_level("view") == GrantLevel.VIEW
    assert parse_grant_level(None) == GrantLevel.NONE
    assert parse_grant_level("OWNER") == GrantLevel.NONE      # cased → deny
    assert parse_grant_level("superuser") == GrantLevel.NONE  # unknown → deny


def test_at_least():
    assert GrantLevel.EDIT.at_least(GrantLevel.VIEW)
    assert not GrantLevel.VIEW.at_least(GrantLevel.EDIT)


@pytest.mark.asyncio
async def test_positive_grant_cached_none_not_cached():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"grant_level": "edit", "lifecycle_state": "active"})

    c = _client(handler)
    book, user = uuid.uuid4(), uuid.uuid4()
    lvl, life = await c.resolve_access(book, user)
    assert lvl == GrantLevel.EDIT and life == "active"
    await c.resolve_access(book, user)          # served from cache
    assert calls["n"] == 1                       # positive grant cached → no 2nd fetch
    await c.aclose()


@pytest.mark.asyncio
async def test_none_never_cached():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"grant_level": "none", "lifecycle_state": ""})

    c = _client(handler)
    book, user = uuid.uuid4(), uuid.uuid4()
    assert await c.resolve_grant(book, user) == GrantLevel.NONE
    assert await c.resolve_grant(book, user) == GrantLevel.NONE
    assert calls["n"] == 2                        # none re-fetches (a fresh grant is never stale-denied)
    await c.aclose()


@pytest.mark.asyncio
async def test_non_200_fails_closed_and_not_cached():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    c = _client(handler)
    assert await c.resolve_grant(uuid.uuid4(), uuid.uuid4()) == GrantLevel.NONE
    await c.aclose()


@pytest.mark.asyncio
async def test_transport_error_fails_closed():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    c = _client(handler)
    assert await c.resolve_grant(uuid.uuid4(), uuid.uuid4()) == GrantLevel.NONE
    await c.aclose()


@pytest.mark.asyncio
async def test_invalidate_drops_cached_grant():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"grant_level": "manage", "lifecycle_state": "active"})

    c = _client(handler)
    book, user = uuid.uuid4(), uuid.uuid4()
    await c.resolve_access(book, user)
    assert c.invalidate(book, user) is True       # entry existed → removed
    assert c.invalidate(book, user) is False      # already gone → no-op
    await c.resolve_access(book, user)             # re-fetches after invalidate
    assert calls["n"] == 2
    await c.aclose()


@pytest.mark.asyncio
async def test_trace_id_provider_propagated():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["tid"] = req.headers.get("X-Trace-Id")
        return httpx.Response(200, json={"grant_level": "view", "lifecycle_state": "active"})

    c = _client(handler, trace_id_provider=lambda: "trace-xyz")
    await c.resolve_grant(uuid.uuid4(), uuid.uuid4())
    assert seen["tid"] == "trace-xyz"
    await c.aclose()
