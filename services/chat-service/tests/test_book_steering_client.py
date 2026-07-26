"""RAID C1 (DR-C1) — degrade-contract tests for the book-steering client.

Mirrors test_knowledge_client.py: an ``httpx.MockTransport`` is injected via
the constructor's ``transport=`` kwarg (no monkey-patching httpx). EVERY
failure path must return ``[]`` — never raise into the chat turn.
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

from app.client.book_steering_client import (  # noqa: E402
    BookSteeringClient,
    close_book_steering_client,
    get_book_steering_client,
    init_book_steering_client,
)

BOOK_ID = "0d0b7c1e-0000-7000-8000-000000000001"


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> BookSteeringClient:
    return BookSteeringClient(
        base_url="http://book-service:8082",
        internal_token="unit-test-token",
        timeout_s=0.5,
        transport=httpx.MockTransport(handler),
    )


def _items(items: list) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": items})
    return handler


class TestGetSteering:
    @pytest.mark.asyncio
    async def test_success_returns_items(self):
        entries = [{"id": "1", "name": "tone", "body": "wry", "inclusion_mode": "always", "match_pattern": None}]
        client = _make_client(_items(entries))
        try:
            out = await client.get_steering(BOOK_ID)
        finally:
            await client.aclose()
        assert out == entries

    @pytest.mark.asyncio
    async def test_sends_internal_token_and_book_scoped_path(self):
        seen: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen["url"] = str(req.url)
            seen["token"] = req.headers.get("X-Internal-Token")
            return httpx.Response(200, json={"items": []})

        client = _make_client(handler)
        try:
            await client.get_steering(BOOK_ID)
        finally:
            await client.aclose()
        assert seen["url"].endswith(f"/internal/books/{BOOK_ID}/steering")
        assert seen["token"] == "unit-test-token"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 404, 422, 500, 503])
    async def test_non_200_degrades_to_empty(self, status):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status, text="nope")

        client = _make_client(handler)
        try:
            assert await client.get_steering(BOOK_ID) == []
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_transport_error_degrades_to_empty(self):
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("book-service down")

        client = _make_client(handler)
        try:
            assert await client.get_steering(BOOK_ID) == []
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_timeout_degrades_to_empty(self):
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow")

        client = _make_client(handler)
        try:
            assert await client.get_steering(BOOK_ID) == []
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_undecodable_body_degrades_to_empty(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not json {{")

        client = _make_client(handler)
        try:
            assert await client.get_steering(BOOK_ID) == []
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_unexpected_shape_degrades_to_empty(self):
        client = _make_client(lambda _: httpx.Response(200, json={"rows": [1, 2]}))
        try:
            assert await client.get_steering(BOOK_ID) == []
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_malformed_items_are_dropped_not_fatal(self):
        entries = [
            "junk",
            {"name": 7, "body": "x"},
            {"id": "1", "name": "tone", "body": "wry", "inclusion_mode": "always", "match_pattern": None},
        ]
        client = _make_client(_items(entries))
        try:
            out = await client.get_steering(BOOK_ID)
        finally:
            await client.aclose()
        assert [e["name"] for e in out] == ["tone"]

    @pytest.mark.asyncio
    async def test_empty_book_id_short_circuits(self):
        def handler(_: httpx.Request) -> httpx.Response:  # pragma: no cover — must not be reached
            raise AssertionError("no request expected for empty book_id")

        client = _make_client(handler)
        try:
            assert await client.get_steering("") == []
        finally:
            await client.aclose()


class TestSingleton:
    @pytest.mark.asyncio
    async def test_init_is_idempotent_and_close_resets(self):
        await close_book_steering_client()  # ensure clean slate
        a = init_book_steering_client()
        b = init_book_steering_client()
        assert a is b
        assert get_book_steering_client() is a
        await close_book_steering_client()
        c = get_book_steering_client()
        assert c is not a
        await close_book_steering_client()
