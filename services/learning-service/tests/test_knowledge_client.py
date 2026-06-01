"""Q4b-feed — KnowledgeClient.fetch_run_sample (httpx MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from app.clients.knowledge_client import KnowledgeClient

pytestmark = pytest.mark.asyncio


async def test_returns_json_on_200(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("X-Internal-Token")
        return httpx.Response(200, json={
            "run_id": "r1",
            "items": {"entity": [{"name": "Alice", "kind": "person"}]},
            "source_text": "Alice fell.",
        })

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient

    def _factory(*a, **kw):
        kw["transport"] = transport
        return orig(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    kc = KnowledgeClient(base_url="http://knowledge-service:8092", internal_token="tok")
    out = await kc.fetch_run_sample("r1")
    assert out is not None
    assert out["source_text"] == "Alice fell."
    assert captured["token"] == "tok"
    assert captured["url"].endswith("/internal/extraction/runs/r1/sample")


async def test_returns_none_on_404(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "no sample"})

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: orig(*a, **{**kw, "transport": transport}))
    kc = KnowledgeClient(base_url="http://knowledge-service:8092", internal_token="tok")
    assert await kc.fetch_run_sample("r1") is None


async def test_returns_none_on_5xx(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: orig(*a, **{**kw, "transport": transport}))
    kc = KnowledgeClient(base_url="http://knowledge-service:8092", internal_token="tok")
    assert await kc.fetch_run_sample("r1") is None


async def test_returns_none_on_transport_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: orig(*a, **{**kw, "transport": transport}))
    kc = KnowledgeClient(base_url="http://knowledge-service:8092", internal_token="tok")
    assert await kc.fetch_run_sample("r1") is None  # best-effort: swallow
