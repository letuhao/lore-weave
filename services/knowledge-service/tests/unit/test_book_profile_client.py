"""Unit tests for the BookProfileClient (wiki-llm M1, option A).

respx-mocks lore-enrichment. The contract: every failure path returns the
NEUTRAL profile (never raises), and a TTL cache serves repeat reads of the same
book without a 2nd HTTP call — but a FAILED read is not cached, so it retries.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import respx

from app.clients.book_profile_client import (
    NEUTRAL_PROFILE,
    BookProfileClient,
)

LE = "http://lore-enrichment-service:8093"


@pytest_asyncio.fixture
async def bpc():
    client = BookProfileClient(
        base_url=LE,
        internal_token="unit-test-token",
        timeout_s=0.5,
        cache_ttl_s=60.0,
    )
    try:
        yield client
    finally:
        await client.aclose()


def _url(book_id) -> str:
    return f"{LE}/internal/lore-enrichment/books/{book_id}/profile"


def _populated_body() -> dict:
    return {
        "book_id": "x", "worldview": "Shang-Zhou xianxia", "language": "zh",
        "era_policy": "no firearms", "voice": "epic",
        "anachronism_markers": [{"term": "枪", "reason": "anachronism"}],
        "anachronism_enabled": True, "dimension_overrides": {},
        "profile_source": "manual",
    }


@pytest.mark.asyncio
async def test_get_profile_populated(bpc: BookProfileClient):
    book = uuid4()
    with respx.mock() as mock:
        mock.get(_url(book)).mock(return_value=httpx.Response(200, json=_populated_body()))
        p = await bpc.get_profile(book)
    assert p.worldview == "Shang-Zhou xianxia"
    assert p.language == "zh"
    assert p.era_policy == "no firearms"
    assert p.voice == "epic"
    assert p.anachronism_markers == (("枪", "anachronism"),)
    assert p.anachronism_enabled is True


@pytest.mark.asyncio
async def test_get_profile_unset_neutral_shape(bpc: BookProfileClient):
    # LE returns the neutral view (no row) — language auto, empty worldview.
    book = uuid4()
    body = {"language": "auto", "worldview": "", "era_policy": None, "voice": None,
            "anachronism_markers": [], "profile_source": "manual"}
    with respx.mock() as mock:
        mock.get(_url(book)).mock(return_value=httpx.Response(200, json=body))
        p = await bpc.get_profile(book)
    assert p == NEUTRAL_PROFILE


@pytest.mark.asyncio
async def test_cache_hit_skips_second_call(bpc: BookProfileClient):
    book = uuid4()
    with respx.mock() as mock:
        route = mock.get(_url(book)).mock(
            return_value=httpx.Response(200, json=_populated_body())
        )
        p1 = await bpc.get_profile(book)
        p2 = await bpc.get_profile(book)
    assert p1 == p2
    assert route.call_count == 1  # 2nd read served from cache


@pytest.mark.asyncio
async def test_5xx_returns_neutral_not_cached(bpc: BookProfileClient):
    book = uuid4()
    with respx.mock() as mock:
        route = mock.get(_url(book))
        # First read 503 → neutral, NOT cached; second read 200 → real profile.
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=_populated_body()),
        ]
        p1 = await bpc.get_profile(book)
        p2 = await bpc.get_profile(book)
    assert p1 == NEUTRAL_PROFILE  # degraded, never raised
    assert route.call_count == 2  # failure not cached → retried
    assert p2.worldview == "Shang-Zhou xianxia"  # recovered read picked up


@pytest.mark.asyncio
async def test_malformed_typed_200_degrades_to_neutral(bpc: BookProfileClient):
    # A 200 whose fields have the WRONG types (LE contract drift / a bug) must
    # NOT crash generation — the client degrades to neutral. This pins the
    # load-bearing "never raises" invariant, which otherwise relies on
    # pydantic.ValidationError subclassing ValueError (version-dependent).
    book = uuid4()
    bad = {"worldview": ["not", "a", "string"], "era_policy": 5, "voice": {"x": 1},
           "anachronism_markers": "not-a-list", "language": 7}
    with respx.mock() as mock:
        mock.get(_url(book)).mock(return_value=httpx.Response(200, json=bad))
        p = await bpc.get_profile(book)
    # worldview/language str-coerce (no crash); era_policy/voice raise→caught→neutral.
    assert p == NEUTRAL_PROFILE


@pytest.mark.asyncio
async def test_timeout_returns_neutral(bpc: BookProfileClient):
    book = uuid4()
    with respx.mock() as mock:
        mock.get(_url(book)).mock(side_effect=httpx.ConnectTimeout("boom"))
        p = await bpc.get_profile(book)
    assert p == NEUTRAL_PROFILE


@pytest.mark.asyncio
async def test_expired_cache_refetches(bpc: BookProfileClient):
    book = uuid4()
    bpc._cache_ttl_s = 0.0  # everything expires immediately
    with respx.mock() as mock:
        route = mock.get(_url(book)).mock(
            return_value=httpx.Response(200, json=_populated_body())
        )
        await bpc.get_profile(book)
        await bpc.get_profile(book)
    assert route.call_count == 2  # TTL=0 → no cache reuse
