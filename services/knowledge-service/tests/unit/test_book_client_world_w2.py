"""G4 (W2) — BookClient.list_world_books status mapping (httpx MockTransport).

Membership is load-bearing for the world rollup, so this call does NOT
degrade-to-None like the cost-estimate calls: 404 → WorldNotFound (a world the
user doesn't own → the endpoint 404s), transport/5xx → BookServiceUnavailable
(→ the endpoint 503s). This locks that mapping without a live book-service.
"""
from uuid import uuid4

import httpx
import pytest

from app.clients.book_client import (
    BookClient,
    BookServiceUnavailable,
    WorldNotFound,
)


def _client(handler) -> BookClient:
    c = BookClient(base_url="http://book", internal_token="tok", timeout_s=5)
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"X-Internal-Token": "tok"},
    )
    return c


@pytest.mark.asyncio
async def test_200_returns_items_with_internal_token_and_user_scope():
    wid, uid, b1, b2 = uuid4(), uuid4(), uuid4(), uuid4()

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == f"/internal/worlds/{wid}/books"
        assert req.url.params["user_id"] == str(uid)
        assert req.headers["X-Internal-Token"] == "tok"
        return httpx.Response(200, json={"items": [
            {"book_id": str(b1)}, {"book_id": str(b2)},
        ]})

    items = await _client(handler).list_world_books(wid, uid)
    assert [i["book_id"] for i in items] == [str(b1), str(b2)]


@pytest.mark.asyncio
async def test_404_raises_world_not_found():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "world not found"})

    with pytest.raises(WorldNotFound):
        await _client(handler).list_world_books(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_5xx_raises_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    with pytest.raises(BookServiceUnavailable):
        await _client(handler).list_world_books(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_transport_error_raises_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(BookServiceUnavailable):
        await _client(handler).list_world_books(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_malformed_body_raises_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    with pytest.raises(BookServiceUnavailable):
        await _client(handler).list_world_books(uuid4(), uuid4())
