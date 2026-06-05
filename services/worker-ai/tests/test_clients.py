"""BookClient.get_chapter_revision_text — the 404-vs-transient contract.

Load-bearing for D-CM3B-DEAD-REVISION-LOOP: the chapters_pending drain marks a
pending row processed when this returns None, so None must mean PERMANENTLY GONE
(404) only — a transient 5xx / network error must RAISE so the job retries
instead of dropping canon.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.clients import BookClient


def _client_with(handler):
    bc = BookClient("http://book-service:8082", "tok", 5.0)
    bc._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"X-Internal-Token": "tok"},
    )
    return bc


@pytest.mark.asyncio
async def test_revision_text_404_returns_none_permanent_gone():
    bc = _client_with(lambda req: httpx.Response(404))
    try:
        assert await bc.get_chapter_revision_text(uuid4(), "ch", "rev") is None
    finally:
        await bc.aclose()


@pytest.mark.asyncio
async def test_revision_text_5xx_raises_transient_not_none():
    # A 5xx must NOT be swallowed to None (that would drain the pending row on a
    # blip and lose canon) — it raises so the job fails + retries.
    bc = _client_with(lambda req: httpx.Response(503))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await bc.get_chapter_revision_text(uuid4(), "ch", "rev")
    finally:
        await bc.aclose()


@pytest.mark.asyncio
async def test_revision_text_network_error_propagates():
    def boom(req):
        raise httpx.ConnectError("connection refused")

    bc = _client_with(boom)
    try:
        with pytest.raises(httpx.ConnectError):
            await bc.get_chapter_revision_text(uuid4(), "ch", "rev")
    finally:
        await bc.aclose()


@pytest.mark.asyncio
async def test_revision_text_200_returns_text():
    bc = _client_with(lambda req: httpx.Response(200, json={"text_content": "hello"}))
    try:
        assert await bc.get_chapter_revision_text(uuid4(), "ch", "rev") == "hello"
    finally:
        await bc.aclose()
