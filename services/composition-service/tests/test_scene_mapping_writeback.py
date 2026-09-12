"""T7 — the decompiler's back-link write-back.

WHY THIS EXISTS. `scenes.source_scene_id` is the sole trigger for the whole ``written_*`` chain:
it is what makes book-service emit ``chapter.scenes_linked``, which reconciles
``outline_node.written_*``, which the Plan Hub's "written" badge reads. The decompiler has always
COMPUTED the mappings — ``scene_decompile.py`` even documents the write-back as
idempotent-on-retry ("a retry after a failed write-back returns the SAME mappings") and names its
owner ("the index owner writes scenes.source_scene_id") — but **no caller ever consumed them**.
Both ``materialize-scenes`` routes returned them to a caller that threw them away, so a
hand-authored book could never populate that chain at all.

The behaviour that must not regress is as much about the FAILURE path as the happy one: the
extraction is already committed by the time the write-back runs, so a failure must not raise (it
would fail a user action that actually succeeded) and must not be swallowed either (a missing
back-link is indistinguishable from success). It is reported.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.clients.book_client import BookClientError
from app.routers.outline import _write_back_scene_mappings


def _result(mappings):
    """A stand-in for MaterializeResult — only `to_dict()` is consumed."""
    payload = {
        "book_id": "b", "work_resolved": True, "project_id": "p",
        "scenes_total": len(mappings), "created": len(mappings), "matched": 0,
        "skipped_authored": 0, "mappings": mappings, "chapters": 1, "detail": None,
    }
    return SimpleNamespace(to_dict=lambda: dict(payload))


class _Books:
    def __init__(self, *, linked=0, skipped=0, raises=None):
        self.calls = []
        self._linked, self._skipped, self._raises = linked, skipped, raises

    async def apply_scene_mappings(self, book_id, owner_user_id, mappings):
        self.calls.append((book_id, owner_user_id, mappings))
        if self._raises:
            raise self._raises
        return {"linked": self._linked, "skipped": self._skipped}


MAPPINGS = [
    {"chapter_id": str(uuid4()), "sort_order": 1, "outline_node_id": str(uuid4())},
    {"chapter_id": str(uuid4()), "sort_order": 2, "outline_node_id": str(uuid4())},
]


@pytest.mark.asyncio
async def test_mappings_are_handed_to_their_owner():
    """The whole point: the mappings must actually leave the service."""
    books = _Books(linked=2)
    book_id, owner = uuid4(), uuid4()

    out = await _write_back_scene_mappings(
        _result(MAPPINGS), book_id=book_id, owner_user_id=owner, books=books,
    )

    assert len(books.calls) == 1, "the decompiler's mappings were computed and then dropped"
    called_book, called_owner, called_mappings = books.calls[0]
    assert called_book == book_id
    assert called_owner == owner, "the owner must be re-asserted at the write boundary"
    assert called_mappings == MAPPINGS
    assert out["scene_link_writeback"] == {"attempted": 2, "linked": 2, "ok": True}


@pytest.mark.asyncio
async def test_a_failed_writeback_is_reported_and_does_not_raise():
    """Degraded, never silent — and never fatal.

    Raising would fail an extraction that already committed; swallowing would make a book with no
    back-links look identical to one with them. Neither is acceptable, so it is reported.
    """
    books = _Books(raises=BookClientError(502, "BOOK_SERVICE_UNAVAILABLE", "connection refused"))

    out = await _write_back_scene_mappings(
        _result(MAPPINGS), book_id=uuid4(), owner_user_id=uuid4(), books=books,
    )

    wb = out["scene_link_writeback"]
    assert wb["ok"] is False, "a failed write-back reported success"
    assert wb["attempted"] == 2 and wb["linked"] == 0
    assert wb["error"] == "BOOK_SERVICE_UNAVAILABLE", "the reason must survive to the caller"
    # The extraction's own results are untouched — it really did succeed.
    assert out["created"] == 2 and out["work_resolved"] is True


@pytest.mark.asyncio
async def test_no_mappings_makes_no_call_but_still_reports():
    """An empty extraction is a legitimate success, not a silent skip."""
    books = _Books()
    out = await _write_back_scene_mappings(
        _result([]), book_id=uuid4(), owner_user_id=uuid4(), books=books,
    )
    assert books.calls == [], "called book-service with nothing to write"
    assert out["scene_link_writeback"] == {"attempted": 0, "linked": 0, "ok": True}


@pytest.mark.asyncio
async def test_partial_link_is_reported_honestly():
    """`source_scene_id IS NULL` means a re-run legitimately links fewer rows than it sends.

    That is not a failure — but the numbers must be the REAL ones, so a caller can tell
    "already linked" from "nothing happened".
    """
    books = _Books(linked=1, skipped=1)
    out = await _write_back_scene_mappings(
        _result(MAPPINGS), book_id=uuid4(), owner_user_id=uuid4(), books=books,
    )
    assert out["scene_link_writeback"] == {"attempted": 2, "linked": 1, "ok": True}


def test_every_materialize_route_writes_the_mappings_back():
    """DRIFT-LOCK, in the spirit of scenes_linked_parity_test.go.

    The original defect was not a broken write-back — it was TWO routes that each computed the
    mappings and returned them unused. A third route (or a revert of either) would reintroduce
    exactly that, silently, and every other test here would stay green. No DB, so it cannot be
    skipped into a false green.
    """
    src = Path(__file__).resolve().parents[1] / "app" / "routers" / "outline.py"
    text = src.read_text(encoding="utf-8")

    materialize_calls = len(re.findall(r"await materialize_scenes\(", text))
    writeback_calls = len(re.findall(r"await _write_back_scene_mappings\(", text))

    assert materialize_calls > 0, "the decompiler routes vanished — update this lock deliberately"
    assert writeback_calls >= materialize_calls, (
        f"{materialize_calls} materialize_scenes call(s) but only {writeback_calls} write-back(s): "
        "a route computes the back-link mappings and drops them, which is the exact defect T7 fixed"
    )
    # And nothing may return the raw result dict around those routes any more.
    assert "return result.to_dict()" not in text, (
        "a materialize route returns to_dict() directly again — its mappings reach nobody"
    )
