"""T5 (D2/A3) — degrade-contract + cache tests for the known-entities client.

Mirrors test_book_steering_client: an injected ``httpx.MockTransport``. EVERY
failure path returns ``frozenset()`` (the gate reads empty as bias-to-include); a
success is cached per TTL (a second call does NOT hit the network).
"""
from __future__ import annotations

import os
from typing import Callable

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.client.known_entities_client import KnownEntitiesClient  # noqa: E402

BOOK_ID = "0d0b7c1e-0000-7000-8000-000000000001"

ROWS = [
    {"entity_id": "1", "name": "Lâm Uyển", "kind_code": "character", "aliases": ["Uyển Nhi"], "frequency": 40},
    {"entity_id": "2", "name": "The Black Spire", "kind_code": "location", "aliases": [], "frequency": 12},
    {"entity_id": "3", "name": "", "kind_code": "character", "aliases": ["ghost"], "frequency": 1},  # nameless
]


def _make_client(handler: Callable[[httpx.Request], httpx.Response], ttl: float = 300.0) -> KnownEntitiesClient:
    return KnownEntitiesClient(
        base_url="http://glossary-service:8088",
        internal_token="unit-test-token",
        timeout_s=0.5,
        cache_ttl_s=ttl,
        transport=httpx.MockTransport(handler),
    )


class TestSuccess:
    @pytest.mark.asyncio
    async def test_builds_lowercased_name_and_alias_set(self):
        client = _make_client(lambda _: httpx.Response(200, json=ROWS))
        try:
            toks = await client.get_known_entity_tokens(BOOK_ID)
        finally:
            await client.aclose()
        assert "lâm uyển" in toks
        assert "uyển nhi" in toks           # alias included
        assert "the black spire" in toks
        assert "ghost" in toks              # alias of a nameless row still usable
        # names are lowercased; nothing empty
        assert "" not in toks

    @pytest.mark.asyncio
    async def test_short_ascii_junk_tokens_dropped(self):
        # a 1-2 char ASCII entity/alias ("I","a","of") — junk min_freq=1 surfaces —
        # would \b-match a common word and fire the gate spuriously → dropped. CJK
        # short names are kept.
        rows = [
            {"entity_id": "1", "name": "I", "kind_code": "c", "aliases": ["a", "of"], "frequency": 1},
            {"entity_id": "2", "name": "Dracula", "kind_code": "c", "aliases": [], "frequency": 5},
            {"entity_id": "3", "name": "万", "kind_code": "c", "aliases": [], "frequency": 1},
        ]
        client = _make_client(lambda _: httpx.Response(200, json=rows))
        try:
            toks = await client.get_known_entity_tokens(BOOK_ID)
        finally:
            await client.aclose()
        assert "dracula" in toks
        assert "万" in toks               # non-ASCII 1-char name kept
        assert not ({"i", "a", "of"} & toks)  # short ASCII junk dropped

    @pytest.mark.asyncio
    async def test_second_call_is_cached_no_network(self):
        calls = {"n": 0}

        def handler(_: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=ROWS)

        client = _make_client(handler)
        try:
            a = await client.get_known_entity_tokens(BOOK_ID)
            b = await client.get_known_entity_tokens(BOOK_ID)
        finally:
            await client.aclose()
        assert a == b
        assert calls["n"] == 1  # cached; the second call did not hit the network

    @pytest.mark.asyncio
    async def test_expired_cache_refetches(self):
        calls = {"n": 0}

        def handler(_: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=ROWS)

        client = _make_client(handler, ttl=-1.0)  # already expired
        try:
            await client.get_known_entity_tokens(BOOK_ID)
            await client.get_known_entity_tokens(BOOK_ID)
        finally:
            await client.aclose()
        assert calls["n"] == 2


class TestDegrade:
    @pytest.mark.asyncio
    async def test_non_200_returns_empty(self):
        client = _make_client(lambda _: httpx.Response(500, text="boom"))
        try:
            assert await client.get_known_entity_tokens(BOOK_ID) == frozenset()
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_transport_error_returns_empty(self):
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        client = _make_client(handler)
        try:
            assert await client.get_known_entity_tokens(BOOK_ID) == frozenset()
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_failure_not_cached_self_heals(self):
        state = {"fail": True}

        def handler(_: httpx.Request) -> httpx.Response:
            if state["fail"]:
                return httpx.Response(503, text="starting")
            return httpx.Response(200, json=ROWS)

        client = _make_client(handler)
        try:
            assert await client.get_known_entity_tokens(BOOK_ID) == frozenset()
            state["fail"] = False
            toks = await client.get_known_entity_tokens(BOOK_ID)  # retried, not pinned empty
        finally:
            await client.aclose()
        assert "lâm uyển" in toks

    @pytest.mark.asyncio
    async def test_empty_book_id_returns_empty(self):
        client = _make_client(lambda _: httpx.Response(200, json=ROWS))
        try:
            assert await client.get_known_entity_tokens("") == frozenset()
        finally:
            await client.aclose()
