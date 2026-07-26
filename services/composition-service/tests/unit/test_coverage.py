"""The shared coverage diff (28 OQ-4/NC-1) — ONE computation, two consumers
(24 H1.3's PH21 tray + 28 AN-4's `composition_diagnostics` source 5).

`diff_coverage` is pure, so the set-difference semantics, the OUT-5 cap, and the
forward-compatibility with 27-V2-A3's CHECK swap are all provable without a DB.
The degraded path (book-service down ⇒ absent, never zero) is proven at the route
in `test_plan_overlay.py` and again here at the helper.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.clients.book_client import BookClientError
from app.services.coverage import UNPLANNED_CAP, compute_coverage, diff_coverage


def _ch(cid, order, title="t"):
    return {"chapter_id": str(cid), "title": title, "sort_order": order}


# ── the diff itself ───────────────────────────────────────────────────────────


def test_unplanned_is_the_book_chapters_no_spec_node_points_at():
    planned, orphan = uuid4(), uuid4()
    cov = diff_coverage([_ch(planned, 1), _ch(orphan, 2, "Chương 41")], {planned})
    assert [c["chapter_id"] for c in cov.unplanned] == [str(orphan)]
    assert cov.unplanned[0]["title"] == "Chương 41"
    assert cov.unplanned_count == 1
    assert cov.degraded is False


def test_fully_planned_book_has_an_empty_tray():
    a, b = uuid4(), uuid4()
    cov = diff_coverage([_ch(a, 1), _ch(b, 2)], {a, b})
    assert cov.unplanned == [] and cov.unplanned_count == 0


def test_empty_spec_means_every_chapter_is_unplanned():
    # the PH21 empty state: a manuscript with no plan at all.
    ids = [uuid4() for _ in range(3)]
    cov = diff_coverage([_ch(c, i) for i, c in enumerate(ids)], set())
    assert cov.unplanned_count == 3


def test_reading_order_is_preserved():
    # the spine arrives ordered; the tray must read in book order, not hash order.
    ids = [uuid4() for _ in range(5)]
    cov = diff_coverage([_ch(c, i) for i, c in enumerate(ids)], set())
    assert [c["sort_order"] for c in cov.unplanned] == [0, 1, 2, 3, 4]


def test_planned_ids_compare_across_uuid_and_str():
    """The spine's `chapter_id` arrives as a JSON STRING; the repo's planned set is
    asyncpg UUIDs. A raw `in` between the two types silently matches NOTHING — every
    chapter would look unplanned. This is the cross-service-normalization bug class."""
    cid = uuid4()
    cov = diff_coverage([_ch(cid, 1)], {UUID(str(cid))})
    assert cov.unplanned_count == 0


def test_a_spec_node_with_no_chapter_id_plans_nothing():
    """Forward-compat with 27-V2-A3: once `outline_chapter_required` is swapped, a
    chapter can be PLANNED before its prose exists (chapter_id NULL). Such a node
    covers no manuscript chapter, so it must not mask a real one. The repo's
    predicate drops the NULLs, so the planned set simply never contains them."""
    orphan = uuid4()
    cov = diff_coverage([_ch(orphan, 1)], set())  # spec has nodes, none linked
    assert cov.unplanned_count == 1


# ── OUT-5: refs capped, counts EXACT ──────────────────────────────────────────


def test_tray_caps_but_the_count_stays_exact():
    n = UNPLANNED_CAP + 37
    cov = diff_coverage([_ch(uuid4(), i) for i in range(n)], set())
    assert len(cov.unplanned) == UNPLANNED_CAP   # list truncated
    assert cov.unplanned_count == n              # count EXACT — never truncated
    assert cov.unplanned_capped is True


def test_exactly_at_cap_is_not_flagged_capped():
    cov = diff_coverage([_ch(uuid4(), i) for i in range(UNPLANNED_CAP)], set())
    assert cov.unplanned_capped is False


def test_title_is_single_line_and_bounded():
    cov = diff_coverage([_ch(uuid4(), 1, "A" * 400 + "\n\ttail")], set())
    title = cov.unplanned[0]["title"]
    assert "\n" not in title and len(title) <= 160 and title.endswith("…")


# ── degraded: absent, never zero ──────────────────────────────────────────────


class _DownBook:
    async def list_chapters(self, book_id, bearer, *, limit=2000, raise_on_404=False):
        raise BookClientError(502, "BOOK_SERVICE_UNAVAILABLE")


class _NotFoundBook:
    """book-service 404s. `list_chapters` normally SWALLOWS that into `[]` — which for a caller
    that reasons about ABSENCE reads as a confirmed-empty book. compute_coverage must pass
    raise_on_404 so it degrades instead of reporting a green-looking zero."""

    async def list_chapters(self, book_id, bearer, *, limit=2000, raise_on_404=False):
        if raise_on_404:
            raise BookClientError(404, "BOOK_NOT_FOUND")
        return []


class _HugeBook:
    """A spine BIGGER than the scan ceiling — the count becomes a floor, and must say so."""

    def __init__(self, n):
        self._n = n
        self.limits: list[int] = []

    async def list_chapters(self, book_id, bearer, *, limit=2000, raise_on_404=False):
        self.limits.append(limit)
        return [_ch(uuid4(), i) for i in range(min(self._n, limit))]


class _Outline:
    def __init__(self, planned=None):
        self._planned = planned or set()
        self.called = False

    async def planned_chapter_ids(self, book_id):
        self.called = True
        return self._planned


@pytest.mark.asyncio
async def test_book_service_down_degrades_it_never_zeroes():
    outline = _Outline()
    cov = await compute_coverage(uuid4(), "bearer", book=_DownBook(), outline=outline)
    assert cov.degraded is True
    assert cov.unplanned == [] and cov.unplanned_count == 0  # meaningless — see flag
    assert cov.warning and "not zero" in cov.warning
    # and we don't pay for the spec read we can't use
    assert outline.called is False


@pytest.mark.asyncio
async def test_a_404_DEGRADES_it_does_not_report_zero_unplanned():
    """The finding: `list_chapters` swallows a 404 into `[]`. This caller reasons about absence, so
    a 404 would have rendered "nothing is unplanned" over a book we could not read at all."""
    outline = _Outline()
    cov = await compute_coverage(uuid4(), "bearer", book=_NotFoundBook(), outline=outline)
    assert cov.degraded is True
    assert cov.warning and "not zero" in cov.warning
    assert outline.called is False


@pytest.mark.asyncio
async def test_the_spine_read_is_EXHAUSTIVE_not_the_2000_default():
    """`list_chapters`'s `limit` is a real CEILING (it truncates silently), so the default 2000
    would cap `unplanned_count` on a 10k-chapter book — a number documented as EXACT. An upstream
    truncation that quietly caps the count makes the whole exact-count contract moot."""
    book = _HugeBook(3000)
    cov = await compute_coverage(uuid4(), "bearer", book=book, outline=_Outline())
    assert book.limits[0] >= 100_000        # asked for far more than any real book
    assert cov.unplanned_count == 3000      # and got them ALL — not 2000
    assert cov.spine_truncated is False


@pytest.mark.asyncio
async def test_hitting_the_ceiling_marks_the_count_a_FLOOR():
    book = _HugeBook(200_000)  # bigger than the ceiling itself
    cov = await compute_coverage(uuid4(), "bearer", book=book, outline=_Outline())
    assert cov.spine_truncated is True      # we could not even COUNT them all
    assert cov.unplanned_count == 100_000   # a lower bound, and flagged as such
