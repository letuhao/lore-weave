"""D-W9-WEBSEARCH / Track D S-PRODUCER — web_search_client relay + degrade contract.

INV-6 neutralization moved to the PRODUCER (provider-registry's ``/internal/web-search``);
this client no longer neutralizes. These tests prove, with a stubbed httpx transport:
  - the client RELAYS the (already-neutralized) producer response into WebSearchHits and
    matches provider-registry's ``/internal/web-search`` request contract;
  - the GRACEFUL-DEGRADE contract still holds after removing local neutralization: a 404 →
    ``error='not_configured'``; any transport error / non-200 / bad-JSON → ``error=
    'unavailable'`` with EMPTY hits, and the call NEVER raises (a web outage must not fail
    the caller — a deconstruct proceeds without the augment).
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


async def test_relays_producer_results_and_request_contract():
    """The producer returns already-neutralized results; the client relays them
    (mapping content→snippet) and posts the correct /internal/web-search request."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Internal-Token")
        import json
        seen["body"] = json.loads(request.content)
        # Producer-shaped, already-neutralized payload (single inert lines, safe URLs).
        return httpx.Response(200, json={
            "answer": "a neutralized answer",
            "results": [
                {"title": "Good Source", "url": "https://ok.example/x", "content": "inert snippet"},
                {"title": "Second", "url": "https://ok.example/y", "content": "more data"},
            ],
        })

    res = await _client(handler).search(user_id=USER, query="q", max_results=5)
    # request contract: /internal/web-search?user_id= + X-Internal-Token + body.
    assert "/internal/web-search" in seen["url"] and str(USER) in seen["url"]
    assert seen["token"] == "tok"
    assert seen["body"] == {"query": "q", "max_results": 5}
    # relayed faithfully: answer + both hits, content mapped to snippet.
    assert res.error is None
    assert res.answer == "a neutralized answer"
    assert len(res.hits) == 2
    assert res.hits[0].url == "https://ok.example/x"
    assert res.hits[0].title == "Good Source"
    assert res.hits[0].snippet == "inert snippet"


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
