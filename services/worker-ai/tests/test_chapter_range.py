"""S2 (D-K16.2-02b) — the extraction runner honours scope_range.chapter_range.

Previously only the cost-estimate ranged; the runner processed the whole book.
`_enumerate_chapters` now filters published chapters by `lo <= sort_order <= hi`.
"""

from uuid import uuid4

from app.runner import _enumerate_chapters
from app.clients import ChapterInfo

BOOK = uuid4()


class _FakeBookClient:
    def __init__(self, chapters):
        self._chapters = chapters

    async def list_chapters(self, book_id, editorial_status=None):
        return self._chapters


def _ch(cid, sort):
    # revision_id non-None so the published-revision gate keeps it.
    return ChapterInfo(chapter_id=cid, title="", sort_order=sort, revision_id="rev")


CHAPTERS = [_ch("a", 1), _ch("b", 5), _ch("c", 10), _ch("d", 15)]


async def test_range_keeps_inclusive_window():
    out = await _enumerate_chapters(
        _FakeBookClient(CHAPTERS), BOOK, None, {"chapter_range": [5, 10]},
    )
    assert [c.chapter_id for c in out] == ["b", "c"]


async def test_no_range_returns_all():
    out = await _enumerate_chapters(_FakeBookClient(CHAPTERS), BOOK, None, None)
    assert [c.chapter_id for c in out] == ["a", "b", "c", "d"]


async def test_empty_scope_range_dict_returns_all():
    out = await _enumerate_chapters(_FakeBookClient(CHAPTERS), BOOK, None, {})
    assert len(out) == 4


async def test_range_excludes_out_of_window():
    out = await _enumerate_chapters(
        _FakeBookClient(CHAPTERS), BOOK, None, {"chapter_range": [11, 99]},
    )
    assert [c.chapter_id for c in out] == ["d"]


async def test_range_boundaries_inclusive():
    out = await _enumerate_chapters(
        _FakeBookClient(CHAPTERS), BOOK, None, {"chapter_range": [1, 15]},
    )
    assert len(out) == 4
