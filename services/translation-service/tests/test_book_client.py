"""book_client.get_chapter_blocks HTTP-status handling (T2-M1 LOW-1, confirmed live).

A chapter with an orphaned translation row (deleted in book-service → 404) must yield
[] (no segments), not raise; a 5xx still raises (transient)."""
import httpx
import pytest

from app import book_client


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=httpx.Request("GET", "http://x"), response=self)  # type: ignore[arg-type]


class _Client:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        return self._resp


def _patch(monkeypatch, resp):
    monkeypatch.setattr(book_client.httpx, "AsyncClient", lambda *a, **k: _Client(resp))


@pytest.mark.asyncio
async def test_404_returns_empty(monkeypatch):
    _patch(monkeypatch, _Resp(404))
    assert await book_client.get_chapter_blocks("b", "c") == []


@pytest.mark.asyncio
async def test_200_returns_blocks(monkeypatch):
    _patch(monkeypatch, _Resp(200, {"blocks": [{"block_index": 0, "text_content": "x"}]}))
    blocks = await book_client.get_chapter_blocks("b", "c")
    assert blocks == [{"block_index": 0, "text_content": "x"}]


@pytest.mark.asyncio
async def test_500_raises(monkeypatch):
    _patch(monkeypatch, _Resp(500))
    with pytest.raises(httpx.HTTPStatusError):
        await book_client.get_chapter_blocks("b", "c")
