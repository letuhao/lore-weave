"""Unit tests for the glossary HTTP client.

Use respx to mock glossary-service responses. Every failure path must
return an empty list — never raise — because chat should keep working
when glossary-service is unavailable.

K4-I8: the `gc` fixture (glossary client) handles teardown so the
underlying httpx.AsyncClient gets aclose'd even if a test fails. Tests
no longer need to call `await client.aclose()` manually.
"""

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import respx

from app.clients.glossary_client import GlossaryClient


@pytest_asyncio.fixture
async def gc():
    """Yield a GlossaryClient and aclose it after the test, even on
    failure. Replaces the manual `await client.aclose()` pattern that
    leaked the connection pool whenever a test assertion blew up."""
    client = GlossaryClient(
        base_url="http://glossary-service:8088",
        internal_token="unit-test-token",
        timeout_s=0.5,
        retries=1,
    )
    try:
        yield client
    finally:
        await client.aclose()


def _url_for(book_id: str) -> str:
    return f"http://glossary-service:8088/internal/books/{book_id}/select-for-context"


@pytest.mark.asyncio
async def test_success_returns_parsed_entities(gc: GlossaryClient):
    book_id = uuid4()
    user_id = uuid4()

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
        entities = await gc.select_for_context(
            user_id=user_id, book_id=book_id, query="Alice"
        )

    assert len(entities) == 2
    assert entities[0].cached_name == "Alice"
    assert entities[0].cached_aliases == ["Al", "Alicia"]
    assert entities[0].is_pinned is True
    assert entities[0].tier == "pinned"
    assert entities[1].cached_name == "李雲"
    assert entities[1].short_description is None


@pytest.mark.asyncio
async def test_timeout_returns_empty_list(gc: GlossaryClient):
    book_id = uuid4()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).mock(side_effect=httpx.TimeoutException("boom"))
        entities = await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert entities == []


@pytest.mark.asyncio
async def test_5xx_retries_then_returns_empty(gc: GlossaryClient):
    book_id = uuid4()

    with respx.mock() as mock:
        route = mock.post(_url_for(str(book_id))).respond(503, text="down")
        entities = await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )
        # retries=1 → one retry → 2 total calls
        assert route.call_count == 2

    assert entities == []


@pytest.mark.asyncio
async def test_4xx_returns_empty_without_retry(gc: GlossaryClient):
    book_id = uuid4()

    with respx.mock() as mock:
        route = mock.post(_url_for(str(book_id))).respond(401, text="bad token")
        entities = await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )
        assert route.call_count == 1

    assert entities == []


@pytest.mark.asyncio
async def test_connection_error_returns_empty(gc: GlossaryClient):
    book_id = uuid4()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).mock(
            side_effect=httpx.ConnectError("refused")
        )
        entities = await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert entities == []


@pytest.mark.asyncio
async def test_malformed_json_returns_empty(gc: GlossaryClient):
    book_id = uuid4()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(
            200, content=b"not json", headers={"content-type": "application/json"}
        )
        entities = await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert entities == []


@pytest.mark.asyncio
async def test_unexpected_shape_returns_empty(gc: GlossaryClient):
    book_id = uuid4()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(200, json={"not_entities": []})
        entities = await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert entities == []


@pytest.mark.asyncio
async def test_init_glossary_client_idempotent(monkeypatch):
    """K4-I1: calling init_glossary_client twice must NOT leak the
    previous client's connection pool. The function returns the
    existing instance on the second call."""
    from app.clients import glossary_client as mod
    from app.config import settings

    # Save state so we don't pollute other tests.
    original = mod._client
    try:
        mod._client = None
        monkeypatch.setattr(settings, "internal_service_token", "test")
        monkeypatch.setattr(settings, "glossary_service_url", "http://x:1")
        first = mod.init_glossary_client()
        second = mod.init_glossary_client()
        assert first is second, "double-init must return the same instance"
    finally:
        if mod._client is not None and mod._client is not original:
            await mod._client.aclose()
        mod._client = original


@pytest.mark.asyncio
async def test_5xx_failure_logs_only_once_per_call(gc: GlossaryClient, caplog):
    """K4-I4: a failed call (5xx + retries exhausted) must produce
    exactly ONE warning log line, not one per attempt."""
    import logging

    book_id = uuid4()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="down")
        with caplog.at_level(logging.WARNING, logger="app.clients.glossary_client"):
            entities = await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )

    assert entities == []
    unavailable_logs = [
        r for r in caplog.records
        if "unavailable" in r.getMessage()
    ]
    assert len(unavailable_logs) == 1, (
        f"expected 1 'unavailable' log, got {len(unavailable_logs)}: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_internal_token_header_sent(gc: GlossaryClient):
    book_id = uuid4()
    captured_token: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured_token.append(request.headers.get("X-Internal-Token", ""))
        return httpx.Response(200, json={"entities": []})

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).mock(side_effect=capture)
        await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert captured_token == ["unit-test-token"]


# ── K11.10 list_entities HTTP-level coverage ─────────────────────────
# GlossaryClient.list_entities was added for K11.10 but never had
# direct HTTP tests until the K13.0 review-impl sweep exposed the gap.


def _known_entities_url(book_id: str) -> str:
    return (
        f"http://glossary-service:8088/internal/books/{book_id}/known-entities"
    )


@pytest.mark.asyncio
async def test_list_entities_success_returns_list(gc: GlossaryClient):
    book_id = uuid4()
    payload = [
        {"entity_id": "a", "name": "Arthur", "kind_code": "person", "aliases": ["Art"]},
        {"entity_id": "b", "name": "Merlin", "kind_code": "person", "aliases": []},
    ]
    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).mock(
            return_value=httpx.Response(200, json=payload),
        )
        out = await gc.list_entities(book_id)

    assert out == payload


@pytest.mark.asyncio
async def test_list_entities_forwards_status_filter(gc: GlossaryClient):
    """status_filter must be sent as the `status` query param — the Go
    handler at extraction_handler.go looks for that exact key.
    """
    book_id = uuid4()
    captured_params: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured_params.append(request.url.params.get("status") or "")
        return httpx.Response(200, json=[])

    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).mock(side_effect=capture)
        await gc.list_entities(book_id, status_filter="inactive")

    assert captured_params == ["inactive"]


@pytest.mark.asyncio
async def test_list_entities_5xx_returns_none(gc: GlossaryClient):
    """5xx must be treated as a soft failure — caller falls back to
    no-anchor extraction rather than crashing the job.
    """
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).mock(
            return_value=httpx.Response(500),
        )
        out = await gc.list_entities(book_id)

    assert out is None


@pytest.mark.asyncio
async def test_list_entities_connection_error_returns_none(gc: GlossaryClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).mock(
            side_effect=httpx.ConnectError("boom"),
        )
        out = await gc.list_entities(book_id)

    assert out is None


@pytest.mark.asyncio
async def test_list_entities_internal_token_and_trace_id_sent(gc: GlossaryClient):
    from app.logging_config import trace_id_var

    book_id = uuid4()
    captured: list[tuple[str, str]] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured.append(
            (
                request.headers.get("X-Internal-Token", ""),
                request.headers.get("X-Trace-Id", ""),
            )
        )
        return httpx.Response(200, json=[])

    token = trace_id_var.set("trace-abc")
    try:
        with respx.mock() as mock:
            mock.get(_known_entities_url(str(book_id))).mock(side_effect=capture)
            await gc.list_entities(book_id)
    finally:
        trace_id_var.reset(token)

    assert captured == [("unit-test-token", "trace-abc")]
