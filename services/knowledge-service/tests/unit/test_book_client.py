"""Unit tests for the book-service HTTP client.

Uses respx to mock book-service responses. Every failure path must
return a safe default — the caller never sees an exception.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import respx

from app.clients.book_client import BookClient


@pytest_asyncio.fixture
async def bc():
    client = BookClient(
        base_url="http://book-service:8082",
        internal_token="unit-test-token",
        timeout_s=0.5,
    )
    try:
        yield client
    finally:
        await client.aclose()


def _count_url(book_id) -> str:
    return f"http://book-service:8082/internal/books/{book_id}/chapters"


def _chapter_url(book_id, chapter_id) -> str:
    return f"http://book-service:8082/internal/books/{book_id}/chapters/{chapter_id}"


def _revision_url(book_id, chapter_id, revision_id) -> str:
    return (
        f"http://book-service:8082/internal/books/{book_id}"
        f"/chapters/{chapter_id}/revisions/{revision_id}/text"
    )


def _lexical_url(book_id) -> str:
    return f"http://book-service:8082/internal/books/{book_id}/lexical-search"


def _reader_lang_url(book_id) -> str:
    return f"http://book-service:8082/internal/books/{book_id}/reader-language"


# ── get_reader_language (KG-ML M4 resolver) ──────────────────────────


@pytest.mark.asyncio
async def test_get_reader_language_success(bc: BookClient):
    book_id, user_id = uuid4(), uuid4()
    with respx.mock() as mock:
        route = mock.get(_reader_lang_url(book_id)).mock(
            return_value=httpx.Response(200, json={"reader_language": "vi"}),
        )
        out = await bc.get_reader_language(book_id, user_id)
    assert out == "vi"
    assert route.calls.last.request.url.params["user_id"] == str(user_id)


@pytest.mark.asyncio
async def test_get_reader_language_unset_returns_none(bc: BookClient):
    book_id, user_id = uuid4(), uuid4()
    with respx.mock() as mock:
        mock.get(_reader_lang_url(book_id)).mock(
            return_value=httpx.Response(200, json={"reader_language": None}),
        )
        assert await bc.get_reader_language(book_id, user_id) is None


@pytest.mark.asyncio
async def test_get_reader_language_failure_returns_none(bc: BookClient):
    book_id, user_id = uuid4(), uuid4()
    with respx.mock() as mock:
        mock.get(_reader_lang_url(book_id)).mock(return_value=httpx.Response(503))
        assert await bc.get_reader_language(book_id, user_id) is None


# ── get_reading_position (W11-M2 reader spoiler cutoff) ──────────────
def _reading_position_url(book_id) -> str:
    return f"http://book-service:8082/internal/books/{book_id}/reading-position"


@pytest.mark.asyncio
async def test_get_reading_position_success(bc: BookClient):
    book_id, user_id, chapter_id = uuid4(), uuid4(), uuid4()
    with respx.mock() as mock:
        route = mock.get(_reading_position_url(book_id)).mock(
            return_value=httpx.Response(
                200,
                json={"furthest_chapter_id": str(chapter_id), "furthest_sort_order": 7},
            ),
        )
        out = await bc.get_reading_position(book_id, user_id)
    assert out == chapter_id
    assert route.calls.last.request.url.params["user_id"] == str(user_id)


@pytest.mark.asyncio
async def test_get_reading_position_null_is_none(bc: BookClient):
    # The route returns HTTP 200 with null furthest_chapter_id for "no position" —
    # this MUST collapse to None (fail-closed), not be mistaken for a real position.
    book_id, user_id = uuid4(), uuid4()
    with respx.mock() as mock:
        mock.get(_reading_position_url(book_id)).mock(
            return_value=httpx.Response(
                200, json={"furthest_chapter_id": None, "furthest_sort_order": None},
            ),
        )
        assert await bc.get_reading_position(book_id, user_id) is None


@pytest.mark.asyncio
async def test_get_reading_position_failure_is_none(bc: BookClient):
    # Any transport / non-200 failure → None (fail-closed): a reader whose position
    # can't be pinned must window to nothing, never to the whole book.
    book_id, user_id = uuid4(), uuid4()
    with respx.mock() as mock:
        mock.get(_reading_position_url(book_id)).mock(return_value=httpx.Response(503))
        assert await bc.get_reading_position(book_id, user_id) is None


@pytest.mark.asyncio
async def test_get_reading_position_garbled_body_is_none(bc: BookClient):
    # A garbled book-service response must fail CLOSED (None), never 500 a reader
    # tool: a malformed chapter_id (UUID() raises) and a non-dict JSON body (no
    # .get) both collapse to None. /review-impl LOW.
    book_id, user_id = uuid4(), uuid4()
    with respx.mock() as mock:
        mock.get(_reading_position_url(book_id)).mock(
            return_value=httpx.Response(200, json={"furthest_chapter_id": "not-a-uuid"}),
        )
        assert await bc.get_reading_position(book_id, user_id) is None
    with respx.mock() as mock:
        mock.get(_reading_position_url(book_id)).mock(
            return_value=httpx.Response(200, json=["unexpected", "list"]),
        )
        assert await bc.get_reading_position(book_id, user_id) is None


# ── lexical_search (raw-search Phase 2) ──────────────────────────────


@pytest.mark.asyncio
async def test_lexical_search_success(bc: BookClient):
    book_id = uuid4()
    hit = {
        "chapterId": "c1", "surface": "draft", "matchType": "lexical",
        "snippet": "乾坤圈", "location": {"blockIndex": 0},
    }
    with respx.mock() as mock:
        route = mock.get(_lexical_url(book_id)).mock(
            return_value=httpx.Response(200, json={"results": [hit]}),
        )
        out = await bc.lexical_search(book_id, "乾坤圈", limit=5)
    assert out == [hit]
    # query + limit forwarded as query params
    assert route.calls.last.request.url.params["q"] == "乾坤圈"
    assert route.calls.last.request.url.params["limit"] == "5"


@pytest.mark.asyncio
async def test_lexical_search_non_200_returns_none(bc: BookClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_lexical_url(book_id)).mock(return_value=httpx.Response(500))
        assert await bc.lexical_search(book_id, "x") is None


@pytest.mark.asyncio
async def test_lexical_search_transport_error_returns_none(bc: BookClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_lexical_url(book_id)).mock(
            side_effect=httpx.ConnectError("book-service down"),
        )
        assert await bc.lexical_search(book_id, "x") is None


@pytest.mark.asyncio
async def test_lexical_search_forwards_surface(bc: BookClient):
    """D-RAWSEARCH-CANON-WIRING — surface reaches book-service (default canon)
    so the lexical leg honours the same canon gate as the semantic leg."""
    book_id = uuid4()
    with respx.mock() as mock:
        route = mock.get(_lexical_url(book_id)).mock(
            return_value=httpx.Response(200, json={"results": []}),
        )
        await bc.lexical_search(book_id, "x")  # default
        assert route.calls.last.request.url.params["surface"] == "canon"
        await bc.lexical_search(book_id, "x", surface="all")
        assert route.calls.last.request.url.params["surface"] == "all"


# ── list_chapters (D-RAWSEARCH-CANON-WIRING) ─────────────────────────


@pytest.mark.asyncio
async def test_list_chapters_returns_items_and_forwards_status(bc: BookClient):
    book_id = uuid4()
    items = [{"chapter_id": "c1", "sort_order": 1, "editorial_status": "draft"}]
    with respx.mock() as mock:
        route = mock.get(_count_url(book_id)).mock(
            return_value=httpx.Response(200, json={"items": items, "total": 1}),
        )
        out = await bc.list_chapters(book_id, editorial_status="draft")
    assert out == items
    assert route.calls.last.request.url.params["editorial_status"] == "draft"
    assert route.calls.last.request.url.params["limit"] == "100"


@pytest.mark.asyncio
async def test_list_chapters_paginates_past_100_cap(bc: BookClient):
    """book-service clamps page size to 100 → list_chapters must page so a
    >100-chapter book isn't silently truncated."""
    book_id = uuid4()
    page1 = [{"chapter_id": f"c{i}", "sort_order": i} for i in range(100)]
    page2 = [{"chapter_id": f"c{i}", "sort_order": i} for i in range(100, 150)]

    def respond(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        items = page1 if offset == 0 else page2
        return httpx.Response(200, json={"items": items, "total": 150})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=respond)
        out = await bc.list_chapters(book_id)
    assert len(out) == 150  # both pages collected, not capped at 100


@pytest.mark.asyncio
async def test_list_chapters_non_200_returns_none(bc: BookClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(return_value=httpx.Response(503))
        assert await bc.list_chapters(book_id) is None


# ── count_chapters ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_count_chapters_success(bc: BookClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(
            return_value=httpx.Response(200, json={"total": 42}),
        )
        assert await bc.count_chapters(book_id) == 42


@pytest.mark.asyncio
async def test_count_chapters_5xx_returns_none(bc: BookClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(return_value=httpx.Response(503))
        assert await bc.count_chapters(book_id) is None


@pytest.mark.asyncio
async def test_count_chapters_forwards_sort_range_as_query_params(bc: BookClient):
    """D-K16.2-02 — ``from_sort``/``to_sort`` kwargs must arrive at
    book-service as query params, not as body or headers. The estimate
    tests stub the whole client, so this is the only assertion that
    the actual HTTP wire carries the range."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 7})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        result = await bc.count_chapters(book_id, from_sort=10, to_sort=20)

    assert result == 7
    assert captured["query"]["from_sort"] == "10"
    assert captured["query"]["to_sort"] == "20"
    assert captured["query"]["limit"] == "1"


@pytest.mark.asyncio
async def test_count_chapters_omits_sort_params_when_not_set(bc: BookClient):
    """Unset kwargs must NOT materialise on the wire — otherwise
    book-service would see ``from_sort=None`` (string) and reject 400."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 3})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        await bc.count_chapters(book_id)

    assert "from_sort" not in captured["query"]
    assert "to_sort" not in captured["query"]


@pytest.mark.asyncio
async def test_count_chapters_from_sort_only(bc: BookClient):
    """One-sided range (upper unbounded) must omit ``to_sort``."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 5})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        await bc.count_chapters(book_id, from_sort=3)

    assert captured["query"]["from_sort"] == "3"
    assert "to_sort" not in captured["query"]


@pytest.mark.asyncio
async def test_count_chapters_from_sort_zero_sent_not_dropped(bc: BookClient):
    """Regression: ``from_sort=0`` must reach the wire, not be dropped
    as falsy — the handler distinguishes ``None`` (skip filter) from
    ``0`` (filter starting at sort_order 0)."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 2})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        await bc.count_chapters(book_id, from_sort=0, to_sort=0)

    assert captured["query"]["from_sort"] == "0"
    assert captured["query"]["to_sort"] == "0"


@pytest.mark.asyncio
async def test_count_chapters_forwards_editorial_status(bc: BookClient):
    """CM3c — ``editorial_status='published'`` must reach book-service as a
    query param so the preview count gates to canon=published (matching the
    gated rebuild). Unset → param omitted."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 4})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        await bc.count_chapters(book_id, editorial_status="published")
    assert captured["query"]["editorial_status"] == "published"

    captured.clear()
    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        await bc.count_chapters(book_id)
    assert "editorial_status" not in captured["query"]


# ── get_chapter_revision_text (CM3c) ─────────────────────────────────


@pytest.mark.asyncio
async def test_get_chapter_revision_text_success(bc: BookClient):
    book_id, chapter_id, rev_id = uuid4(), uuid4(), str(uuid4())
    with respx.mock() as mock:
        mock.get(_revision_url(book_id, chapter_id, rev_id)).mock(
            return_value=httpx.Response(200, json={"text_content": "pinned canon"}),
        )
        assert await bc.get_chapter_revision_text(book_id, chapter_id, rev_id) == "pinned canon"


@pytest.mark.asyncio
async def test_get_chapter_revision_text_404_returns_none(bc: BookClient):
    """Cross-book/chapter revision id (IDOR-guarded → 404) → None, so the
    caller keeps existing passages rather than wiping canon."""
    book_id, chapter_id, rev_id = uuid4(), uuid4(), str(uuid4())
    with respx.mock() as mock:
        mock.get(_revision_url(book_id, chapter_id, rev_id)).mock(
            return_value=httpx.Response(404),
        )
        assert await bc.get_chapter_revision_text(book_id, chapter_id, rev_id) is None


@pytest.mark.asyncio
async def test_get_chapter_revision_text_empty_returns_none(bc: BookClient):
    book_id, chapter_id, rev_id = uuid4(), uuid4(), str(uuid4())
    with respx.mock() as mock:
        mock.get(_revision_url(book_id, chapter_id, rev_id)).mock(
            return_value=httpx.Response(200, json={"text_content": "   "}),
        )
        assert await bc.get_chapter_revision_text(book_id, chapter_id, rev_id) is None


# ── get_chapter_text (D-K18.3-01) ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_chapter_text_success(bc: BookClient):
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            return_value=httpx.Response(
                200,
                json={
                    "chapter_id": str(chapter_id),
                    "title": "Ch 1",
                    "text_content": "Arthur drew the sword from the stone.",
                },
            ),
        )
        text = await bc.get_chapter_text(book_id, chapter_id)
    assert text == "Arthur drew the sword from the stone."


@pytest.mark.asyncio
async def test_get_chapter_text_missing_field_returns_none(bc: BookClient):
    """Response without text_content → None (ingester treats as skip)."""
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            return_value=httpx.Response(200, json={"chapter_id": str(chapter_id)}),
        )
        assert await bc.get_chapter_text(book_id, chapter_id) is None


@pytest.mark.asyncio
async def test_get_chapter_text_empty_returns_none(bc: BookClient):
    """Empty text_content counts as None so we don't upsert empty passages."""
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            return_value=httpx.Response(200, json={"text_content": "   "}),
        )
        assert await bc.get_chapter_text(book_id, chapter_id) is None


@pytest.mark.asyncio
async def test_get_chapter_text_404_returns_none(bc: BookClient):
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            return_value=httpx.Response(404),
        )
        assert await bc.get_chapter_text(book_id, chapter_id) is None


@pytest.mark.asyncio
async def test_get_chapter_text_connection_error_returns_none(bc: BookClient):
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            side_effect=httpx.ConnectError("boom"),
        )
        assert await bc.get_chapter_text(book_id, chapter_id) is None


@pytest.mark.asyncio
async def test_internal_token_header_sent(bc: BookClient):
    book_id = uuid4()
    chapter_id = uuid4()
    captured: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("X-Internal-Token", ""))
        return httpx.Response(200, json={"text_content": "hi"})

    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(side_effect=capture)
        await bc.get_chapter_text(book_id, chapter_id)

    assert captured == ["unit-test-token"]


# ── C6 (D-K19b.3-01 + D-K19e-β-01) — get_chapter_titles ───────────


def _chapter_titles_url() -> str:
    return "http://book-service:8082/internal/chapters/titles"


@pytest.mark.asyncio
async def test_get_chapter_titles_empty_input_skips_network(bc: BookClient):
    """Early-return on empty input — no HTTP call, no respx match."""
    with respx.mock() as mock:
        titles = await bc.get_chapter_titles([])
    assert titles == {}
    # No routes registered → if a call fired, respx would complain.
    # Explicit assertion: no calls landed.
    assert not mock.calls.called


@pytest.mark.asyncio
async def test_get_chapter_titles_happy_path(bc: BookClient):
    cid1 = uuid4()
    cid2 = uuid4()
    with respx.mock() as mock:
        mock.post(_chapter_titles_url()).mock(
            return_value=httpx.Response(
                200,
                json={
                    "titles": {
                        str(cid1): "Chapter 1 — Opening Scene",
                        str(cid2): "Chapter 2 — The Duel",
                    },
                },
            ),
        )
        titles = await bc.get_chapter_titles([cid1, cid2])
    assert titles == {
        cid1: "Chapter 1 — Opening Scene",
        cid2: "Chapter 2 — The Duel",
    }


@pytest.mark.asyncio
async def test_get_chapter_titles_partial_response(bc: BookClient):
    """BE drops unknown/inactive chapter_ids from the response map.
    Client must return whatever it got, NOT fabricate entries for the
    missing ones — caller's FE falls back to UUID short for those."""
    cid1 = uuid4()
    cid2 = uuid4()
    with respx.mock() as mock:
        mock.post(_chapter_titles_url()).mock(
            return_value=httpx.Response(
                200,
                # cid2 missing — inactive or nonexistent chapter
                json={"titles": {str(cid1): "Chapter 1 — Opening"}},
            ),
        )
        titles = await bc.get_chapter_titles([cid1, cid2])
    assert titles == {cid1: "Chapter 1 — Opening"}
    assert cid2 not in titles


@pytest.mark.asyncio
async def test_get_chapter_titles_5xx_returns_empty_dict(bc: BookClient):
    """Graceful degrade: any non-200 → {} (not None, not exception).
    Enricher semantics depend on this — it iterates the empty dict."""
    cid = uuid4()
    with respx.mock() as mock:
        mock.post(_chapter_titles_url()).mock(
            return_value=httpx.Response(503),
        )
        titles = await bc.get_chapter_titles([cid])
    assert titles == {}


@pytest.mark.asyncio
async def test_get_chapter_titles_timeout_returns_empty_dict(bc: BookClient):
    cid = uuid4()
    with respx.mock() as mock:
        mock.post(_chapter_titles_url()).mock(
            side_effect=httpx.TimeoutException("simulated"),
        )
        titles = await bc.get_chapter_titles([cid])
    assert titles == {}


@pytest.mark.asyncio
async def test_get_chapter_titles_malformed_uuid_in_response_skipped(bc: BookClient):
    """Defensive: if BE drifts and returns a non-UUID key, that entry
    is skipped. Valid entries in the same response still land."""
    cid = uuid4()
    with respx.mock() as mock:
        mock.post(_chapter_titles_url()).mock(
            return_value=httpx.Response(
                200,
                json={
                    "titles": {
                        str(cid): "Chapter 3 — Valid",
                        "not-a-uuid": "Garbage — Should Skip",
                    },
                },
            ),
        )
        titles = await bc.get_chapter_titles([cid])
    assert titles == {cid: "Chapter 3 — Valid"}


@pytest.mark.asyncio
async def test_get_chapter_titles_body_shape(bc: BookClient):
    """Lock the request body: POST with JSON {chapter_ids: [str, ...]}.
    A regression sending query params or renaming the field would
    silently make the handler see an empty list."""
    cid1 = uuid4()
    cid2 = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content)
        captured["method"] = request.method
        return httpx.Response(200, json={"titles": {}})

    with respx.mock() as mock:
        mock.post(_chapter_titles_url()).mock(side_effect=capture)
        await bc.get_chapter_titles([cid1, cid2])

    assert captured["method"] == "POST"
    assert captured["body"] == {"chapter_ids": [str(cid1), str(cid2)]}
