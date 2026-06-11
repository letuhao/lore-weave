"""Unit tests for the E0 Python grant client (book-service /access).

Security-critical: default-deny parsing, positive-only cache (none never
cached so a fresh grant is never stale-denied), 45s expiry, and fail-closed
on any book-service failure. Uses respx to mock the authority.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import respx

from app.clients.grant_client import GrantClient, GrantLevel, parse_grant_level

BASE = "http://book-service:8082"


def _access_url(book_id) -> str:
    return f"{BASE}/internal/books/{book_id}/access"


@pytest_asyncio.fixture
async def gc():
    client = GrantClient(base_url=BASE, internal_token="itok", timeout_s=0.5)
    try:
        yield client
    finally:
        await client.aclose()


# ── pure level logic ────────────────────────────────────────────────

def test_parse_grant_level_roundtrip_and_default_deny():
    for s, want in [("none", GrantLevel.NONE), ("view", GrantLevel.VIEW),
                    ("edit", GrantLevel.EDIT), ("manage", GrantLevel.MANAGE),
                    ("owner", GrantLevel.OWNER)]:
        assert parse_grant_level(s) is want
    # unknown / empty / cased / future → NONE (default-deny)
    for s in ["", None, "admin", "VIEW", "Owner", "superuser"]:
        assert parse_grant_level(s) is GrantLevel.NONE


def test_at_least_ordering():
    assert GrantLevel.EDIT.at_least(GrantLevel.VIEW)
    assert GrantLevel.EDIT.at_least(GrantLevel.EDIT)
    assert not GrantLevel.EDIT.at_least(GrantLevel.MANAGE)
    assert GrantLevel.OWNER.at_least(GrantLevel.MANAGE)
    assert not GrantLevel.VIEW.at_least(GrantLevel.EDIT)


# ── HTTP resolution ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_access_level_and_lifecycle(gc: GrantClient):
    book, user = uuid4(), uuid4()
    with respx.mock() as mock:
        mock.get(_access_url(book)).mock(return_value=httpx.Response(
            200, json={"grant_level": "edit", "lifecycle_state": "active"}))
        lvl, lifecycle = await gc.resolve_access(book, user)
    assert lvl is GrantLevel.EDIT and lifecycle == "active"


@pytest.mark.asyncio
async def test_resolve_all_levels(gc: GrantClient):
    for s, want in [("none", GrantLevel.NONE), ("view", GrantLevel.VIEW),
                    ("edit", GrantLevel.EDIT), ("manage", GrantLevel.MANAGE),
                    ("owner", GrantLevel.OWNER)]:
        book, user = uuid4(), uuid4()
        with respx.mock() as mock:
            mock.get(_access_url(book)).mock(return_value=httpx.Response(
                200, json={"grant_level": s}))
            assert await gc.resolve_grant(book, user) is want


@pytest.mark.asyncio
async def test_sends_internal_token(gc: GrantClient):
    book, user = uuid4(), uuid4()
    with respx.mock() as mock:
        route = mock.get(_access_url(book)).mock(return_value=httpx.Response(
            200, json={"grant_level": "view"}))
        await gc.resolve_grant(book, user)
    assert route.calls.last.request.headers["X-Internal-Token"] == "itok"
    assert route.calls.last.request.url.params["user_id"] == str(user)


@pytest.mark.asyncio
async def test_positive_cached(gc: GrantClient):
    book, user = uuid4(), uuid4()
    with respx.mock() as mock:
        route = mock.get(_access_url(book)).mock(return_value=httpx.Response(
            200, json={"grant_level": "edit"}))
        for _ in range(3):
            assert await gc.resolve_grant(book, user) is GrantLevel.EDIT
    assert route.call_count == 1  # positive grant cached


@pytest.mark.asyncio
async def test_none_never_cached(gc: GrantClient):
    # A `none` must re-check every call — else a freshly granted user stays denied.
    book, user = uuid4(), uuid4()
    with respx.mock() as mock:
        route = mock.get(_access_url(book)).mock(return_value=httpx.Response(
            200, json={"grant_level": "none"}))
        for _ in range(3):
            assert await gc.resolve_grant(book, user) is GrantLevel.NONE
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_positive_expires_after_ttl(gc: GrantClient):
    book, user = uuid4(), uuid4()
    t = [1000.0]
    gc._now = lambda: t[0]  # type: ignore[assignment]
    with respx.mock() as mock:
        route = mock.get(_access_url(book)).mock(return_value=httpx.Response(
            200, json={"grant_level": "manage"}))
        await gc.resolve_grant(book, user)            # miss → store exp=1000+45
        t[0] = 1000.0 + gc._ttl - 1                    # still valid
        await gc.resolve_grant(book, user)
        assert route.call_count == 1
        t[0] = 1000.0 + gc._ttl + 1                    # expired
        await gc.resolve_grant(book, user)
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_fail_closed_on_5xx(gc: GrantClient):
    book, user = uuid4(), uuid4()
    with respx.mock() as mock:
        mock.get(_access_url(book)).mock(return_value=httpx.Response(503))
        lvl, lifecycle = await gc.resolve_access(book, user)
    assert lvl is GrantLevel.NONE and lifecycle == ""


@pytest.mark.asyncio
async def test_fail_closed_on_transport_error(gc: GrantClient):
    book, user = uuid4(), uuid4()
    with respx.mock() as mock:
        mock.get(_access_url(book)).mock(side_effect=httpx.ConnectError("down"))
        assert await gc.resolve_grant(book, user) is GrantLevel.NONE
