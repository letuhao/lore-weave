"""24 PH20 Row-3 — `POST /books/{book_id}/chapters/reorder`, the ONE gesture that crosses the
service seam and PERMUTES THE REAL MANUSCRIPT.

It had no route tests at all. That is the worst place in this feature to have none: a bug here
does not render wrong, it *reorders the user's book*. (One already shipped — the FE asked
book-service for `{limit: 500}`, book-service clamps to 100, and Row-3's undo consequently moved a
chapter to position 1 on any >100-chapter book. `749805ca6`.)

The two halves this pins:
  • the EDIT gate (BPS-8) fires BEFORE either service is touched;
  • book-service's own 4xx rules are relayed VERBATIM, never flattened to a 500;
  • a mirror-resync failure is reported as 502 MIRROR_RESYNC_FAILED — the manuscript IS reordered
    and only composition's mirror is stale, and saying "OK" over that would be a silent-success lie.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clients.book_client import BookClientError
from app.routers.arc import router

USER = UUID("00000000-0000-0000-0000-0000000000aa")
BOOK = UUID("00000000-0000-0000-0000-0000000000cc")
CH_A, CH_B = uuid4(), uuid4()


class _FakeBook:
    """book-service. `reorder_raises` simulates ITS rule rejections (400/404/409)."""

    def __init__(self, *, reorder_raises=None, list_raises=None, chapters=None):
        self.reorder_raises = reorder_raises
        self.list_raises = list_raises
        self.chapters = chapters if chapters is not None else [
            {"chapter_id": str(CH_B), "title": "B", "sort_order": 1},
            {"chapter_id": str(CH_A), "title": "A", "sort_order": 2},
        ]
        self.reorder_calls: list[tuple] = []

    async def reorder_chapters(self, book_id, chapter_id, after_chapter_id, bearer):
        self.reorder_calls.append((book_id, chapter_id, after_chapter_id))
        if self.reorder_raises:
            raise self.reorder_raises
        return {"ok": True}

    async def list_chapters(self, book_id, bearer, *, limit=2000):
        if self.list_raises:
            raise self.list_raises
        return self.chapters


class _FakeOutline:
    def __init__(self, raises=None):
        self.raises = raises
        self.resync_calls: list[dict] = []

    async def resync_reading_order(self, book_id, chapter_sorts):
        self.resync_calls.append({"book_id": book_id, "sorts": chapter_sorts})
        if self.raises:
            raise self.raises
        return 7  # nodes moved


def _client(level, *, book=None, outline=None):
    from app.deps import get_book_client_dep, get_grant_client_dep, get_outline_repo
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return level

        async def resolve_access(self, book_id, user_id):
            return level, "active"

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "bearer"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_book_client_dep] = lambda: book or _FakeBook()
    app.dependency_overrides[get_outline_repo] = lambda: outline or _FakeOutline()
    return TestClient(app)


def _post(c, after=None):
    return c.post(
        f"/v1/composition/books/{BOOK}/chapters/reorder",
        json={"chapter_id": str(CH_A), "after_chapter_id": str(after) if after else None},
    )


# ── the happy path: both halves run, in order ─────────────────────────────────


def test_reorders_the_manuscript_then_rebuilds_the_mirror():
    from app.grant_client import GrantLevel

    book, outline = _FakeBook(), _FakeOutline()
    r = _post(_client(GrantLevel.EDIT, book=book, outline=outline), after=CH_B)
    assert r.status_code == 200
    assert r.json() == {"book_id": str(BOOK), "resynced": 7}

    # 1. book-service permuted the manuscript…
    assert book.reorder_calls == [(BOOK, CH_A, CH_B)]
    # 2. …and the mirror was rebuilt from the NEW truth it read back (not from the request).
    assert outline.resync_calls[0]["sorts"] == {CH_B: 1, CH_A: 2}


def test_after_none_moves_to_the_front():
    from app.grant_client import GrantLevel

    book = _FakeBook()
    assert _post(_client(GrantLevel.EDIT, book=book)).status_code == 200
    assert book.reorder_calls[0][2] is None  # None ⇒ "make it chapter 1"


# ── the gate fires BEFORE anything is touched (BPS-8) ─────────────────────────


def test_no_grant_is_404_and_the_manuscript_is_never_touched():
    from app.grant_client import GrantLevel

    book, outline = _FakeBook(), _FakeOutline()
    r = _post(_client(GrantLevel.NONE, book=book, outline=outline))
    assert r.status_code == 404  # uniform no-oracle
    assert book.reorder_calls == [] and outline.resync_calls == []


def test_view_only_cannot_reorder_the_manuscript():
    from app.grant_client import GrantLevel

    book = _FakeBook()
    r = _post(_client(GrantLevel.VIEW, book=book))
    assert r.status_code == 403  # EDIT is required — a reader may not permute the book
    assert book.reorder_calls == []


# ── book-service owns the rules; relay them VERBATIM ──────────────────────────


@pytest.mark.parametrize("status", [400, 404, 409])
def test_book_service_rule_rejections_are_relayed_not_flattened(status):
    """A chapter that isn't in the book, an after_id from ANOTHER book, a non-active lifecycle —
    these are book-service's rules. Flattening them to a 502 would tell the user "the service is
    down" about their own bad request."""
    from app.grant_client import GrantLevel

    book = _FakeBook(reorder_raises=BookClientError(status, "CHAPTER_NOT_FOUND"))
    outline = _FakeOutline()
    r = _post(_client(GrantLevel.EDIT, book=book, outline=outline))
    assert r.status_code == status
    assert r.json()["detail"]["code"] == "CHAPTER_NOT_FOUND"
    assert outline.resync_calls == []  # the mirror is NOT rebuilt over a failed reorder


def test_an_unexpected_book_status_becomes_502():
    from app.grant_client import GrantLevel

    book = _FakeBook(reorder_raises=BookClientError(500, "BOOM"))
    r = _post(_client(GrantLevel.EDIT, book=book))
    assert r.status_code == 502


# ── the partial-failure truth: 502, not a fake 200 ────────────────────────────


def test_a_failed_mirror_resync_is_502_and_SAYS_the_manuscript_moved():
    """THE case that must never be a silent success. book-service has already committed the
    permutation; only composition's mirror is stale. Reporting 200 would leave the user believing
    everything is consistent when the canon anchors still point at the OLD story order."""
    from app.grant_client import GrantLevel

    book = _FakeBook(list_raises=BookClientError(503, "BOOK_SERVICE_UNAVAILABLE"))
    r = _post(_client(GrantLevel.EDIT, book=book))
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["code"] == "MIRROR_RESYNC_FAILED"
    # and it must tell the user the manuscript DID change + that a retry repairs it (both halves
    # are idempotent, which is what makes "re-issue this request" honest advice).
    assert "WAS reordered" in detail["detail"]
    assert "re-issue" in detail["detail"]
    assert book.reorder_calls  # the manuscript really was permuted


def test_the_mirror_read_skips_chapters_with_no_sort_order():
    """A malformed spine row must not become a `None` key in the resync map — it would blow up the
    renumber, AFTER the manuscript had already been permuted."""
    from app.grant_client import GrantLevel

    book = _FakeBook(chapters=[
        {"chapter_id": str(CH_A), "title": "A", "sort_order": 1},
        {"chapter_id": None, "title": "junk", "sort_order": 2},
        {"chapter_id": str(CH_B), "title": "B", "sort_order": None},
    ])
    outline = _FakeOutline()
    r = _post(_client(GrantLevel.EDIT, book=book, outline=outline))
    assert r.status_code == 200
    assert outline.resync_calls[0]["sorts"] == {CH_A: 1}  # only the well-formed row survives
