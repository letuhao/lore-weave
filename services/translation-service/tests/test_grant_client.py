"""E0-4a grant_client unit tests — mirrors the knowledge-service / Go SDK suite.

Covers: wire-string parse + default-deny; positive-only cache (hit / none-never-
cached / TTL expiry); fail-closed on non-200 + transport error; resolve_grant
wrapper.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.grant_client import GrantClient, GrantLevel, parse_grant_level


def _client(handler, ttl=45.0):
    gc = GrantClient("http://book", "tok", timeout_s=5.0, cache_ttl_s=ttl)
    gc._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return gc


# ── parse / default-deny ──────────────────────────────────────────────────────

def test_parse_grant_level_known():
    assert parse_grant_level("owner") == GrantLevel.OWNER
    assert parse_grant_level("manage") == GrantLevel.MANAGE
    assert parse_grant_level("edit") == GrantLevel.EDIT
    assert parse_grant_level("view") == GrantLevel.VIEW
    assert parse_grant_level("none") == GrantLevel.NONE


def test_parse_grant_level_default_deny():
    for bad in (None, "", "OWNER", "admin", "Edit", "garbage"):
        assert parse_grant_level(bad) == GrantLevel.NONE


def test_at_least_ordering():
    assert GrantLevel.EDIT.at_least(GrantLevel.VIEW)
    assert GrantLevel.OWNER.at_least(GrantLevel.MANAGE)
    assert not GrantLevel.VIEW.at_least(GrantLevel.EDIT)
    assert GrantLevel.EDIT.at_least(GrantLevel.EDIT)


# ── happy path + cache ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_access_returns_level_and_lifecycle():
    def handler(request):
        return httpx.Response(200, json={"grant_level": "edit", "lifecycle_state": "active"})
    gc = _client(handler)
    lvl, lifecycle = await gc.resolve_access(uuid4(), uuid4())
    assert lvl == GrantLevel.EDIT and lifecycle == "active"
    await gc.aclose()


@pytest.mark.asyncio
async def test_positive_grant_is_cached():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"grant_level": "manage", "lifecycle_state": "active"})
    gc = _client(handler)
    book, user = uuid4(), uuid4()
    assert await gc.resolve_grant(book, user) == GrantLevel.MANAGE
    assert await gc.resolve_grant(book, user) == GrantLevel.MANAGE
    assert calls["n"] == 1  # second call served from cache
    await gc.aclose()


@pytest.mark.asyncio
async def test_none_is_never_cached():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"grant_level": "none", "lifecycle_state": ""})
    gc = _client(handler)
    book, user = uuid4(), uuid4()
    assert await gc.resolve_grant(book, user) == GrantLevel.NONE
    assert await gc.resolve_grant(book, user) == GrantLevel.NONE
    assert calls["n"] == 2  # never cached → refetched (so a fresh grant is instant)
    await gc.aclose()


@pytest.mark.asyncio
async def test_cache_expires_after_ttl():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"grant_level": "edit", "lifecycle_state": "active"})
    gc = _client(handler, ttl=45.0)
    t = {"v": 1000.0}
    gc._now = lambda: t["v"]
    book, user = uuid4(), uuid4()
    assert await gc.resolve_grant(book, user) == GrantLevel.EDIT
    t["v"] += 46.0  # past TTL → refetch
    assert await gc.resolve_grant(book, user) == GrantLevel.EDIT
    assert calls["n"] == 2
    await gc.aclose()


# ── fail-closed ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_200_fails_closed_to_none():
    def handler(request):
        return httpx.Response(503, text="down")
    gc = _client(handler)
    assert await gc.resolve_grant(uuid4(), uuid4()) == GrantLevel.NONE
    await gc.aclose()


@pytest.mark.asyncio
async def test_transport_error_fails_closed_to_none():
    def handler(request):
        raise httpx.ConnectError("refused")
    gc = _client(handler)
    assert await gc.resolve_grant(uuid4(), uuid4()) == GrantLevel.NONE
    await gc.aclose()


@pytest.mark.asyncio
async def test_error_is_not_cached():
    state = {"down": True}

    def handler(request):
        if state["down"]:
            return httpx.Response(503)
        return httpx.Response(200, json={"grant_level": "edit", "lifecycle_state": "active"})
    gc = _client(handler)
    book, user = uuid4(), uuid4()
    assert await gc.resolve_grant(book, user) == GrantLevel.NONE
    state["down"] = False  # recover → next call must refetch (error never cached)
    assert await gc.resolve_grant(book, user) == GrantLevel.EDIT
    await gc.aclose()
