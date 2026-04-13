"""Unit tests for the glossary HTTP client.

Use respx to mock glossary-service responses. Every failure path must
return an empty list — never raise — because chat should keep working
when glossary-service is unavailable.
"""

from uuid import uuid4

import httpx
import pytest
import respx

from app.clients.glossary_client import GlossaryClient


def _make_client() -> GlossaryClient:
    return GlossaryClient(
        base_url="http://glossary-service:8088",
        internal_token="unit-test-token",
        timeout_s=0.5,
        retries=1,
    )


def _url_for(book_id: str) -> str:
    return f"http://glossary-service:8088/internal/books/{book_id}/select-for-context"


@pytest.mark.asyncio
async def test_success_returns_parsed_entities():
    book_id = uuid4()
    user_id = uuid4()
    client = _make_client()

    payload = {
        "entities": [
            {
                "entity_id": "aaaaaaaa-0000-0000-0000-000000000001",
                "cached_name": "Alice",
                "cached_aliases": ["Al", "Alicia"],
                "short_description": "A wandering swordsman.",
                "kind_code": "character",
                "is_pinned": True,
                "tier": "pinned",
                "rank_score": 1.0,
            },
            {
                "entity_id": "aaaaaaaa-0000-0000-0000-000000000002",
                "cached_name": "李雲",
                "cached_aliases": ["小李"],
                "short_description": None,
                "kind_code": "character",
                "is_pinned": False,
                "tier": "exact",
                "rank_score": 0.9,
            },
        ],
        "total_tokens_estimate": 15,
    }

    with respx.mock(assert_all_called=True) as mock:
        mock.post(_url_for(str(book_id))).respond(200, json=payload)
        entities = await client.select_for_context(
            user_id=user_id, book_id=book_id, query="Alice"
        )

    assert len(entities) == 2
    assert entities[0].cached_name == "Alice"
    assert entities[0].cached_aliases == ["Al", "Alicia"]
    assert entities[0].is_pinned is True
    assert entities[0].tier == "pinned"
    assert entities[1].cached_name == "李雲"
    assert entities[1].short_description is None

    await client.aclose()


@pytest.mark.asyncio
async def test_timeout_returns_empty_list():
    book_id = uuid4()
    client = _make_client()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).mock(side_effect=httpx.TimeoutException("boom"))
        entities = await client.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert entities == []
    await client.aclose()


@pytest.mark.asyncio
async def test_5xx_retries_then_returns_empty():
    book_id = uuid4()
    client = _make_client()

    with respx.mock() as mock:
        route = mock.post(_url_for(str(book_id))).respond(503, text="down")
        entities = await client.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )
        # retries=1 → one retry → 2 total calls
        assert route.call_count == 2

    assert entities == []
    await client.aclose()


@pytest.mark.asyncio
async def test_4xx_returns_empty_without_retry():
    book_id = uuid4()
    client = _make_client()

    with respx.mock() as mock:
        route = mock.post(_url_for(str(book_id))).respond(401, text="bad token")
        entities = await client.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )
        assert route.call_count == 1

    assert entities == []
    await client.aclose()


@pytest.mark.asyncio
async def test_connection_error_returns_empty():
    book_id = uuid4()
    client = _make_client()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).mock(
            side_effect=httpx.ConnectError("refused")
        )
        entities = await client.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert entities == []
    await client.aclose()


@pytest.mark.asyncio
async def test_malformed_json_returns_empty():
    book_id = uuid4()
    client = _make_client()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(
            200, content=b"not json", headers={"content-type": "application/json"}
        )
        entities = await client.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert entities == []
    await client.aclose()


@pytest.mark.asyncio
async def test_unexpected_shape_returns_empty():
    book_id = uuid4()
    client = _make_client()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(200, json={"not_entities": []})
        entities = await client.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert entities == []
    await client.aclose()


@pytest.mark.asyncio
async def test_internal_token_header_sent():
    book_id = uuid4()
    client = _make_client()

    captured_token: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured_token.append(request.headers.get("X-Internal-Token", ""))
        return httpx.Response(200, json={"entities": []})

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).mock(side_effect=capture)
        await client.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert captured_token == ["unit-test-token"]
    await client.aclose()
