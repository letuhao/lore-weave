"""IX-10 (spec 26 / RB-5) — chapter.scenes_reparsed consumer handler.

Knowledge is the consumer side of the FROZEN cross-service contract (spec 26 IX-10 —
book-service's producer emits exactly these four fields):
  chapter.scenes_reparsed {book_id, chapter_id, published_revision_id, parse_version}
The `_event` helper below optionally adds a `scene_count` field to prove the consumer
TOLERATES an unknown extra field (forward-compat) — it is not part of the frozen shape.

WS-0.1 (spec: 2026-07-11-publish-independent-kg-indexing §3.3, P0-4) — the invalidation
is now **CHAPTER-scoped** (`delete_by_chapter`), not book-scoped. Re-parsing chapter 7
only moves chapter 7's scene index, so wiping the other 199 chapters' cached leaves
forced a full-book LLM re-extract for zero index change. Under publish-independent
indexing ("add to knowledge" is a frequent per-chapter click) that would be ruinous.

These tests prove the WIRING (which repo method, which scope arg). They deliberately do
NOT prove that the SQL actually spares the other chapters' rows — a mock cannot prove
that. The real-SQL proof lives in
tests/integration/db/test_extraction_leaves_chapter_scope.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.events.dispatcher import EventData, EventDispatcher
from app.events.handlers import handle_chapter_scenes_reparsed

_BOOK = uuid4()
_CHAPTER = uuid4()
_REVISION = uuid4()


def _reparsed_event(*, book_id=str(_BOOK), chapter_id=str(_CHAPTER),
                    parse_version=3, scene_count=5, published_revision_id=str(_REVISION),
                    aggregate_id=None):
    """Build an event carrying the FROZEN payload shape. Any field passed as
    None is omitted (to exercise the malformed-payload paths)."""
    payload: dict = {}
    if book_id is not None:
        payload["book_id"] = book_id
    if chapter_id is not None:
        payload["chapter_id"] = chapter_id
    if published_revision_id is not None:
        payload["published_revision_id"] = published_revision_id
    if parse_version is not None:
        payload["parse_version"] = parse_version
    if scene_count is not None:
        payload["scene_count"] = scene_count
    return EventData(
        stream="loreweave:events:chapter",
        message_id="42-0",
        event_type="chapter.scenes_reparsed",
        aggregate_id=aggregate_id if aggregate_id is not None else (chapter_id or str(uuid4())),
        payload=payload,
        source="book",
        raw={},
    )


def _patch_leaves_repo(monkeypatch, *, returns=(4, 2)):
    """Patch ExtractionLeavesRepo so BOTH delete scopes are spies. Returns the
    repo mock so callers can assert which scope fired — asserting on the mock we
    expect is not enough; we must also assert the other one did NOT fire."""
    repo_instance = MagicMock()
    repo_instance.delete_by_chapter = AsyncMock(return_value=returns)
    repo_instance.delete_by_book = AsyncMock(return_value=returns)
    monkeypatch.setattr(
        "app.events.handlers.ExtractionLeavesRepo",
        lambda _pool: repo_instance,
    )
    return repo_instance


@pytest.mark.asyncio
async def test_scenes_reparsed_invalidates_chapter_scoped(monkeypatch):
    """WS-0.1 headline: the handler invalidates the CHAPTER, not the book.

    The book-scoped assertion is the load-bearing half — it is the regression lock
    on P0-4 (one index click must not wipe a 200-chapter book's extraction cache).
    """
    repo = _patch_leaves_repo(monkeypatch)

    await handle_chapter_scenes_reparsed(_reparsed_event(), pool=AsyncMock())

    repo.delete_by_chapter.assert_awaited_once()
    assert str(repo.delete_by_chapter.await_args.args[0]) == str(_CHAPTER)
    # The whole point of WS-0.1: the book-wide wipe must NOT fire.
    repo.delete_by_book.assert_not_awaited()


@pytest.mark.asyncio
async def test_scenes_reparsed_dispatches_via_event_type(monkeypatch):
    """Wiring/allowlist proof: registering the handler on the K14 dispatcher
    and dispatching a chapter.scenes_reparsed event routes to it and triggers
    the invalidation (the dispatcher matches by exact event_type)."""
    repo = _patch_leaves_repo(monkeypatch)
    dispatcher = EventDispatcher()
    dispatcher.register("chapter.scenes_reparsed", handle_chapter_scenes_reparsed)

    handled = await dispatcher.dispatch(_reparsed_event(), pool=AsyncMock())

    assert handled is True
    repo.delete_by_chapter.assert_awaited_once()
    assert str(repo.delete_by_chapter.await_args.args[0]) == str(_CHAPTER)


@pytest.mark.asyncio
async def test_scenes_reparsed_idempotent_on_replay(monkeypatch):
    """At-least-once delivery: a redelivered event invalidates the same chapter
    again. delete_by_chapter is naturally idempotent (a second call deletes 0),
    and the handler stays chapter-scoped on every delivery."""
    repo = _patch_leaves_repo(monkeypatch, returns=(0, 0))
    pool = AsyncMock()
    ev = _reparsed_event()

    await handle_chapter_scenes_reparsed(ev, pool=pool)
    await handle_chapter_scenes_reparsed(ev, pool=pool)  # replay

    assert repo.delete_by_chapter.await_count == 2
    scopes = {str(c.args[0]) for c in repo.delete_by_chapter.await_args_list}
    assert scopes == {str(_CHAPTER)}  # every delivery scoped to the same chapter


@pytest.mark.asyncio
async def test_scenes_reparsed_falls_back_to_aggregate_id_for_chapter(monkeypatch):
    """The chapter.* convention lets chapter_id arrive as the aggregate id. The
    handler must still resolve a chapter scope from it (NOT widen to the book)."""
    repo = _patch_leaves_repo(monkeypatch)
    agg = uuid4()

    await handle_chapter_scenes_reparsed(
        _reparsed_event(chapter_id=None, aggregate_id=str(agg)), pool=AsyncMock()
    )

    repo.delete_by_chapter.assert_awaited_once()
    assert str(repo.delete_by_chapter.await_args.args[0]) == str(agg)
    repo.delete_by_book.assert_not_awaited()


@pytest.mark.asyncio
async def test_scenes_reparsed_unusable_chapter_id_widens_to_book_not_skip(monkeypatch, caplog):
    """Deliberate degradation, and NOT a silent skip.

    If the chapter scope is unresolvable, we widen to the book rather than skip:
    over-deleting costs an LLM re-extract, but UNDER-deleting leaves a stale cache
    the graph then re-derives from a scene index that no longer exists — corruption.
    When the scope is unknown, spend money rather than corrupt the graph.

    It must WARN, so the degradation can never rot unnoticed (no-silent-success).
    """
    repo = _patch_leaves_repo(monkeypatch)

    with caplog.at_level("WARNING"):
        await handle_chapter_scenes_reparsed(
            _reparsed_event(chapter_id="not-a-uuid", aggregate_id="also-not-a-uuid"),
            pool=AsyncMock(),
        )

    repo.delete_by_book.assert_awaited_once()
    assert str(repo.delete_by_book.await_args.args[0]) == str(_BOOK)
    repo.delete_by_chapter.assert_not_awaited()
    assert any("BOOK-scoped" in r.message for r in caplog.records), \
        "the widened fallback must WARN — a silent widen would hide a producer bug"


@pytest.mark.asyncio
async def test_scenes_reparsed_missing_book_id_skips(monkeypatch):
    """Malformed payload (no book_id) → clean skip: no invalidation, no raise
    (one bad event must not wedge the consumer loop)."""
    repo = _patch_leaves_repo(monkeypatch)

    await handle_chapter_scenes_reparsed(
        _reparsed_event(book_id=None), pool=AsyncMock()
    )

    repo.delete_by_chapter.assert_not_awaited()
    repo.delete_by_book.assert_not_awaited()


@pytest.mark.asyncio
async def test_scenes_reparsed_invalid_book_id_skips(monkeypatch):
    """A non-UUID book_id is also a graceful skip (defensive parse)."""
    repo = _patch_leaves_repo(monkeypatch)

    await handle_chapter_scenes_reparsed(
        _reparsed_event(book_id="not-a-uuid"), pool=AsyncMock()
    )

    repo.delete_by_chapter.assert_not_awaited()
    repo.delete_by_book.assert_not_awaited()
