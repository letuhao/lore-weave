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
    monkeypatch.setattr(book_client, "build_internal_client", lambda *a, **k: _Client(resp))


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


# ── #36 — real per-chapter sizes for the extraction cost estimate ─────────────


class _PagedClient:
    """Mock httpx client that serves a list of pages by ?offset and records params."""

    def __init__(self, pages):
        self._pages = pages  # list[(status, payload)]
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        self.calls.append(params or {})
        idx = (params or {}).get("offset", 0) // book_client._CHAPTER_LIST_PAGE
        status, payload = self._pages[idx] if idx < len(self._pages) else (200, {"items": []})
        return _Resp(status, payload)


def _patch_paged(monkeypatch, pages):
    client = _PagedClient(pages)
    monkeypatch.setattr(book_client, "build_internal_client", lambda *a, **k: client)
    return client


@pytest.mark.asyncio
async def test_word_counts_filters_to_requested_ids(monkeypatch):
    _patch_paged(monkeypatch, [(200, {"items": [
        {"chapter_id": "c1", "word_count_estimate": 1500},
        {"chapter_id": "c2", "word_count_estimate": 9000},
        {"chapter_id": "other", "word_count_estimate": 5},  # not requested → dropped
    ]})])
    got = await book_client.get_chapter_word_counts("b", ["c1", "c2"])
    assert got == {"c1": 1500, "c2": 9000}


@pytest.mark.asyncio
async def test_word_counts_paginates_until_all_found(monkeypatch):
    page1 = (200, {"items": [{"chapter_id": f"x{i}", "word_count_estimate": 1}
                             for i in range(book_client._CHAPTER_LIST_PAGE)]})  # full page, none wanted
    page2 = (200, {"items": [{"chapter_id": "target", "word_count_estimate": 4242}]})
    client = _patch_paged(monkeypatch, [page1, page2])
    got = await book_client.get_chapter_word_counts("b", ["target"])
    assert got == {"target": 4242}
    assert [c.get("offset") for c in client.calls] == [0, book_client._CHAPTER_LIST_PAGE]


@pytest.mark.asyncio
async def test_word_counts_best_effort_empty_on_error(monkeypatch):
    _patch_paged(monkeypatch, [(500, {})])  # raise_for_status → caught → {}
    assert await book_client.get_chapter_word_counts("b", ["c1"]) == {}


@pytest.mark.asyncio
async def test_word_counts_empty_input_no_call(monkeypatch):
    client = _patch_paged(monkeypatch, [(200, {"items": []})])
    assert await book_client.get_chapter_word_counts("b", []) == {}
    assert client.calls == []  # never hit the network for an empty selection


@pytest.mark.asyncio
async def test_build_chapters_meta_uses_real_sizes_and_defaults_missing(monkeypatch):
    async def fake_counts(book_id, chapter_ids):
        return {"c1": 1500, "c2": 0}  # c2 has 0 (→ default), c3 absent (→ default)

    monkeypatch.setattr(book_client, "get_chapter_word_counts", fake_counts)
    meta = await book_client.build_chapters_meta("b", ["c1", "c2", "c3"])
    assert meta == [
        {"chapter_id": "c1", "text_length": 1500 * book_client._WORD_COUNT_TO_TEXT_LENGTH},
        {"chapter_id": "c2", "text_length": book_client._DEFAULT_CHAPTER_TEXT_LENGTH},
        {"chapter_id": "c3", "text_length": book_client._DEFAULT_CHAPTER_TEXT_LENGTH},
    ]


@pytest.mark.asyncio
async def test_build_chapters_meta_all_default_on_fetch_failure(monkeypatch):
    async def boom(book_id, chapter_ids):
        return {}  # get_chapter_word_counts already degraded to {}

    monkeypatch.setattr(book_client, "get_chapter_word_counts", boom)
    meta = await book_client.build_chapters_meta("b", ["a", "b"])
    assert all(m["text_length"] == book_client._DEFAULT_CHAPTER_TEXT_LENGTH for m in meta)
    assert [m["chapter_id"] for m in meta] == ["a", "b"]  # order preserved
