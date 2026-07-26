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


# ── KG-ML M5 (C9) — fetch_entity_display_names ─────────────────────────────
def _display_names_url(book_id: str) -> str:
    return f"http://glossary-service:8088/internal/books/{book_id}/entity-display-names"


@pytest.mark.asyncio
async def test_fetch_entity_display_names_keeps_only_translated(gc: GlossaryClient):
    book_id = uuid4()
    payload = {
        "language": "vi",
        "items": [
            {"entity_id": "g1", "display_name": "Hỏa Ma", "translated": True},
            # untranslated → display_name is the canonical fallback; MUST be dropped
            {"entity_id": "g2", "display_name": "天剑峰", "translated": False},
        ],
    }
    with respx.mock(assert_all_called=True) as mock:
        mock.post(_display_names_url(str(book_id))).respond(200, json=payload)
        names = await gc.fetch_entity_display_names(
            book_id=book_id, entity_ids=["g1", "g2"], language="vi"
        )
    assert names == {"g1": "Hỏa Ma"}  # only the genuinely-translated name


@pytest.mark.asyncio
async def test_fetch_entity_display_names_empty_inputs_skip_call(gc: GlossaryClient):
    # No HTTP call when there's nothing to resolve / no language.
    assert await gc.fetch_entity_display_names(book_id=uuid4(), entity_ids=[], language="vi") == {}
    assert await gc.fetch_entity_display_names(book_id=uuid4(), entity_ids=["g1"], language="") == {}


@pytest.mark.asyncio
async def test_fetch_entity_display_names_error_returns_empty(gc: GlossaryClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.post(_display_names_url(str(book_id))).respond(503)
        names = await gc.fetch_entity_display_names(
            book_id=book_id, entity_ids=["g1"], language="vi"
        )
    assert names == {}


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
async def test_list_entities_forwards_min_frequency(gc: GlossaryClient):
    """min_frequency must be sent as the `min_frequency` query param (the Go
    handler's chapter-appearance gate). Default is 2 (extraction-anchor semantics);
    wiki overrides to 1 to include every entity on a low-chapter book.

    This test used to assert `status=active` was always sent. That param never did
    anything — the handler ignored it. Now that the handler honors it
    (D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM), sending it by default would filter out
    every DRAFT entity (both creation paths insert status='draft'), so the client
    must send NO status unless a caller explicitly opts in.
    """
    book_id = uuid4()
    captured: list[tuple[str, str]] = []

    def capture(request: httpx.Request) -> httpx.Response:
        p = request.url.params
        captured.append((p.get("status") or "", p.get("min_frequency") or ""))
        return httpx.Response(200, json=[])

    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).mock(side_effect=capture)
        await gc.list_entities(book_id)  # default
        await gc.list_entities(book_id, min_frequency=1)  # wiki path

    assert captured == [("", "2"), ("", "1")]


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


# ── mui #1c G-cand — propose_merge_candidates ────────────────────────────────


def _merge_candidates_url(book_id: str) -> str:
    return f"http://glossary-service:8088/internal/books/{book_id}/merge-candidates"


@pytest.mark.asyncio
async def test_propose_merge_candidates_posts_cluster(gc: GlossaryClient):
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured.update(_json.loads(request.content))
        return httpx.Response(200, json={"results": [{"candidate_id": "c1", "status": "proposed"}]})

    with respx.mock() as mock:
        mock.post(_merge_candidates_url(str(book_id))).mock(side_effect=capture)
        out = await gc.propose_merge_candidates(
            book_id,
            candidates=[
                {
                    "member_entity_ids": ["e1", "e2"],
                    "suggested_winner_entity_id": "e1",
                    "score": 0.8,
                    "rationale": "co-occur",
                }
            ],
        )

    assert out == {"results": [{"candidate_id": "c1", "status": "proposed"}]}
    assert captured["candidates"][0]["member_entity_ids"] == ["e1", "e2"]
    assert captured["candidates"][0]["suggested_winner_entity_id"] == "e1"


@pytest.mark.asyncio
async def test_propose_merge_candidates_empty_skips_call(gc: GlossaryClient):
    # No candidates → no HTTP call, returns None (assert_all_called would fail
    # if a request were made against an empty mock router).
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(_merge_candidates_url(str(uuid4())))
        out = await gc.propose_merge_candidates(uuid4(), candidates=[])
    assert out is None
    assert not route.called


@pytest.mark.asyncio
async def test_propose_merge_candidates_5xx_returns_none(gc: GlossaryClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.post(_merge_candidates_url(str(book_id))).respond(503)
        out = await gc.propose_merge_candidates(
            book_id, candidates=[{"member_entity_ids": ["e1", "e2"]}]
        )
    assert out is None


@pytest.mark.asyncio
async def test_propose_merge_candidates_connection_error_returns_none(gc: GlossaryClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.post(_merge_candidates_url(str(book_id))).mock(
            side_effect=httpx.ConnectError("boom")
        )
        out = await gc.propose_merge_candidates(
            book_id, candidates=[{"member_entity_ids": ["e1", "e2"]}]
        )
    assert out is None


# ── D-ANCHOR-PRELOAD-50-CAP + D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM ──────────


def _known_entities_url(book_id: str) -> str:
    return f"http://glossary-service:8088/internal/books/{book_id}/known-entities"


@pytest.mark.asyncio
async def test_list_entities_omits_status_unless_asked(gc: GlossaryClient):
    """The handler historically IGNORED `status`; now that it honors it, sending
    `status=active` by default would filter out every draft entity (both creation
    paths insert status='draft'). Default must send NO status param."""
    book_id = uuid4()
    with respx.mock() as mock:
        route = mock.get(_known_entities_url(str(book_id))).respond(200, json=[])
        await gc.list_entities(book_id)
    assert "status" not in route.calls[0].request.url.params

    with respx.mock() as mock:
        route = mock.get(_known_entities_url(str(book_id))).respond(200, json=[])
        await gc.list_entities(book_id, status_filter="active")
    assert route.calls[0].request.url.params["status"] == "active"


@pytest.mark.asyncio
async def test_list_entities_passes_offset_and_alive(gc: GlossaryClient):
    book_id = uuid4()
    with respx.mock() as mock:
        route = mock.get(_known_entities_url(str(book_id))).respond(200, json=[])
        await gc.list_entities(
            book_id, min_frequency=0, limit=500, offset=1000, include_dead=True,
        )
    params = route.calls[0].request.url.params
    assert params["min_frequency"] == "0"
    assert params["limit"] == "500"
    assert params["offset"] == "1000"
    assert params["alive"] == "false"  # handler: alive != "false" ⇒ require alive


@pytest.mark.asyncio
async def test_list_all_entities_pages_until_short_page(gc: GlossaryClient):
    """Walks every page — the un-paged call silently stopped at the handler's
    default limit of 50 (D-ANCHOR-PRELOAD-50-CAP)."""
    book_id = uuid4()
    page1 = [{"entity_id": f"e{i}", "name": f"N{i}"} for i in range(3)]
    page2 = [{"entity_id": "e3", "name": "N3"}]  # short ⇒ last page
    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        rows, truncated = await gc.list_all_entities(book_id, page_size=3)
    assert [r["entity_id"] for r in rows] == ["e0", "e1", "e2", "e3"]
    assert truncated is False


@pytest.mark.asyncio
async def test_list_all_entities_reports_truncation_at_max_pages(gc: GlossaryClient):
    """Hitting the runaway guard must REPORT truncation, never silently under-read."""
    book_id = uuid4()
    full = [{"entity_id": f"e{i}", "name": f"N{i}"} for i in range(2)]
    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).mock(
            return_value=httpx.Response(200, json=full)
        )
        rows, truncated = await gc.list_all_entities(book_id, page_size=2, max_pages=2)
    assert len(rows) == 4
    assert truncated is True


@pytest.mark.asyncio
async def test_list_all_entities_first_page_failure_returns_none(gc: GlossaryClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).respond(503)
        assert await gc.list_all_entities(book_id) is None


@pytest.mark.asyncio
async def test_list_all_entities_later_page_failure_is_honest_partial(gc: GlossaryClient):
    """A mid-walk failure returns what we got with truncated=True — never a
    silent short read presented as complete."""
    book_id = uuid4()
    page1 = [{"entity_id": f"e{i}", "name": f"N{i}"} for i in range(2)]
    with respx.mock() as mock:
        mock.get(_known_entities_url(str(book_id))).mock(
            side_effect=[httpx.Response(200, json=page1), httpx.Response(503)]
        )
        rows, truncated = await gc.list_all_entities(book_id, page_size=2)
    assert len(rows) == 2
    assert truncated is True
