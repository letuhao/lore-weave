"""Unit tests for the book-service prose client (respx-mocked httpx)."""

from __future__ import annotations

import uuid

import httpx
import pytest
import respx

from app.clients.book_client import BookClient, BookClientError

BASE = "http://book-service:8082"
BOOK = uuid.uuid4()
CH = uuid.uuid4()


async def _client() -> BookClient:
    return BookClient(BASE)


@respx.mock
async def test_owns_book_true_false_and_forwards_jwt():
    route = respx.get(f"{BASE}/v1/books/{BOOK}").mock(return_value=httpx.Response(200, json={"book_id": str(BOOK)}))
    c = await _client()
    try:
        assert await c.owns_book(BOOK, "jwt") is True
        assert route.calls.last.request.headers["Authorization"] == "Bearer jwt"
        respx.get(f"{BASE}/v1/books/{BOOK}").mock(return_value=httpx.Response(404, json={"error": "BOOK_NOT_FOUND"}))
        assert await c.owns_book(BOOK, "jwt") is False
    finally:
        await c.aclose()


@respx.mock
async def test_get_draft_returns_body_and_version():
    respx.get(f"{BASE}/v1/books/{BOOK}/chapters/{CH}/draft").mock(
        return_value=httpx.Response(200, json={"chapter_id": str(CH), "body": {"x": 1}, "draft_version": 7})
    )
    c = await _client()
    try:
        draft = await c.get_draft(BOOK, CH, "jwt")
    finally:
        await c.aclose()
    assert draft["draft_version"] == 7 and draft["body"] == {"x": 1}


@respx.mock
async def test_patch_draft_sends_expected_version_and_maps_409():
    route = respx.patch(f"{BASE}/v1/books/{BOOK}/chapters/{CH}/draft").mock(
        return_value=httpx.Response(200, json={"draft_version": 8})
    )
    c = await _client()
    try:
        out = await c.patch_draft(BOOK, CH, "jwt", body={"d": 1}, expected_draft_version=7, commit_message="m")
        assert out["draft_version"] == 8
        sent = route.calls.last.request
        import json as _json
        payload = _json.loads(sent.content)
        assert payload["expected_draft_version"] == 7
        assert payload["body"] == {"d": 1} and payload["commit_message"] == "m"
        # 409 conflict surfaces the book-service error code
        respx.patch(f"{BASE}/v1/books/{BOOK}/chapters/{CH}/draft").mock(
            return_value=httpx.Response(409, json={"error": "CHAPTER_DRAFT_CONFLICT", "message": "stale draft version"})
        )
        with pytest.raises(BookClientError) as ei:
            await c.patch_draft(BOOK, CH, "jwt", body={}, expected_draft_version=1)
        assert ei.value.status == 409 and ei.value.code == "CHAPTER_DRAFT_CONFLICT"
    finally:
        await c.aclose()


@respx.mock
async def test_list_revisions_for_base_revision_id():
    rev = str(uuid.uuid4())
    respx.get(f"{BASE}/v1/books/{BOOK}/chapters/{CH}/revisions").mock(
        return_value=httpx.Response(200, json={"items": [{"revision_id": rev}], "total": 1})
    )
    c = await _client()
    try:
        out = await c.list_revisions(BOOK, CH, "jwt", limit=1)
    finally:
        await c.aclose()
    assert out["items"][0]["revision_id"] == rev


@respx.mock
async def test_get_chapter_sort_orders_uses_internal_token():
    ch1, ch2 = uuid.uuid4(), uuid.uuid4()
    route = respx.post(f"{BASE}/internal/chapters/sort-orders").mock(
        return_value=httpx.Response(200, json={"sort_orders": {str(ch1): 3, str(ch2): 7}})
    )
    c = BookClient(BASE, "intok")
    try:
        out = await c.get_chapter_sort_orders([ch1, ch2])
    finally:
        await c.aclose()
    assert out == {str(ch1): 3, str(ch2): 7}
    req = route.calls.last.request
    assert req.headers["X-Internal-Token"] == "intok"
    assert "Authorization" not in req.headers
    import json as _json
    assert set(_json.loads(req.content)["chapter_ids"]) == {str(ch1), str(ch2)}


async def test_get_chapter_sort_orders_empty_input_skips_call():
    c = BookClient(BASE, "intok")
    try:
        assert await c.get_chapter_sort_orders([]) == {}  # no route registered → no call
    finally:
        await c.aclose()


@respx.mock
async def test_get_chapter_sort_orders_degrades_to_empty():
    respx.post(f"{BASE}/internal/chapters/sort-orders").mock(side_effect=httpx.ConnectError("down"))
    c = BookClient(BASE, "intok")
    try:
        assert await c.get_chapter_sort_orders([uuid.uuid4()]) == {}
    finally:
        await c.aclose()


@respx.mock
async def test_transport_error_becomes_502():
    respx.get(f"{BASE}/v1/books/{BOOK}/chapters/{CH}/draft").mock(side_effect=httpx.ConnectError("down"))
    c = await _client()
    try:
        with pytest.raises(BookClientError) as ei:
            await c.get_draft(BOOK, CH, "jwt")
        assert ei.value.status == 502
    finally:
        await c.aclose()
