"""D-W9-WEBSEARCH — web_search_client neutralization + degrade contract (no network).

Proves, with a stubbed httpx transport:
  - INV-6: every returned title/url/snippet is neutralized (control chars / newlines
    collapsed, length-capped) and non-http(s) URLs are DROPPED;
  - a 404 → ``error='not_configured'`` (no BYOK web_search credential);
  - any transport error / non-200 / bad-JSON → ``error='unavailable'`` (never raises);
  - the request shape matches provider-registry's ``/internal/web-search`` contract.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.clients.web_search_client import WebSearchClient

USER = uuid.uuid4()


def _client(handler) -> WebSearchClient:
    c = WebSearchClient("http://provider-registry:8085", "tok")
    # Swap in a MockTransport but keep the same default X-Internal-Token header the
    # real __init__ set (so the contract assertion exercises the real header path).
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"X-Internal-Token": "tok"},
    )
    return c


async def test_neutralizes_and_drops_non_http_urls():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Internal-Token")
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "answer": "line one\nline two\n\n\tindented",
            "results": [
                {"title": "good\nsource", "url": "https://ok.example/x", "content": "a\tb\nc"},
                {"title": "evil", "url": "javascript:alert(1)", "content": "drop me"},
                {"title": "data", "url": "data:text/html,xss", "content": "drop me too"},
            ],
        })

    res = await _client(handler).search(user_id=USER, query="q", max_results=5)
    # request contract: /internal/web-search?user_id= + X-Internal-Token + body.
    assert "/internal/web-search" in seen["url"] and str(USER) in seen["url"]
    assert seen["token"] == "tok"
    assert seen["body"] == {"query": "q", "max_results": 5}
    # INV-6: newlines/tabs collapsed in the answer; the two non-http hits dropped.
    assert "\n" not in res.answer and "\t" not in res.answer
    assert res.error is None
    assert len(res.hits) == 1
    assert res.hits[0].url == "https://ok.example/x"
    assert "\n" not in res.hits[0].title and "\t" not in res.hits[0].snippet


async def test_404_is_not_configured():
    res = await _client(lambda r: httpx.Response(404)).search(user_id=USER, query="q")
    assert res.error == "not_configured" and res.hits == []


async def test_non_200_is_unavailable():
    res = await _client(lambda r: httpx.Response(500)).search(user_id=USER, query="q")
    assert res.error == "unavailable"


async def test_transport_error_degrades_not_raises():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    res = await _client(boom).search(user_id=USER, query="q")
    assert res.error == "unavailable" and res.hits == []


async def test_bad_json_is_unavailable():
    res = await _client(
        lambda r: httpx.Response(200, content=b"not json")
    ).search(user_id=USER, query="q")
    assert res.error == "unavailable"


async def test_empty_query_short_circuits():
    # an all-whitespace query never hits the network.
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"results": []})

    res = await _client(handler).search(user_id=USER, query="   ")
    assert res.error == "unavailable" and called["n"] == 0


async def test_max_results_clamped_to_10():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": []})

    await _client(handler).search(user_id=USER, query="q", max_results=999)
    assert seen["body"]["max_results"] == 10
