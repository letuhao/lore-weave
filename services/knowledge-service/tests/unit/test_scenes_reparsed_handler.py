"""IX-10 (spec 26 / RB-5) — chapter.scenes_reparsed consumer handler.

Knowledge is the consumer side of the FROZEN cross-service contract (spec 26 IX-10 —
book-service's producer emits exactly these four fields):
  chapter.scenes_reparsed {book_id, chapter_id, published_revision_id, parse_version}
The `_event` helper below optionally adds a `scene_count` field to prove the consumer
TOLERATES an unknown extra field (forward-compat) — it is not part of the frozen shape.
On receipt the handler invalidates the book's extraction cache (book-scoped)
via the existing `ExtractionLeavesRepo.delete_by_book` path (F6), so a re-parse
re-derives the graph from the fresh index.
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
                    parse_version=3, scene_count=5, published_revision_id=str(_REVISION)):
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
        aggregate_id=chapter_id or str(uuid4()),
        payload=payload,
        source="book",
        raw={},
    )


def _patch_leaves_repo(monkeypatch, *, returns=(4, 2)):
    """Patch ExtractionLeavesRepo so delete_by_book is a spy. Returns the
    AsyncMock so callers can assert the book-scoped invalidation fired."""
    delete_by_book = AsyncMock(return_value=returns)
    repo_instance = MagicMock()
    repo_instance.delete_by_book = delete_by_book
    monkeypatch.setattr(
        "app.events.handlers.ExtractionLeavesRepo",
        lambda _pool: repo_instance,
    )
    return delete_by_book


@pytest.mark.asyncio
async def test_scenes_reparsed_invalidates_book_scoped(monkeypatch):
    """Happy path: the handler invalidates the extraction cache for the
    event's book_id (book-scoped, all ops via delete_by_book default)."""
    delete_by_book = _patch_leaves_repo(monkeypatch)
    pool = AsyncMock()

    await handle_chapter_scenes_reparsed(_reparsed_event(), pool=pool)

    delete_by_book.assert_awaited_once()
    # Book-scoped: the ONLY positional arg is the book_id (ops defaults to all).
    args = delete_by_book.await_args.args
    assert str(args[0]) == str(_BOOK)


@pytest.mark.asyncio
async def test_scenes_reparsed_dispatches_via_event_type(monkeypatch):
    """Wiring/allowlist proof: registering the handler on the K14 dispatcher
    and dispatching a chapter.scenes_reparsed event routes to it and triggers
    the invalidation (the dispatcher matches by exact event_type)."""
    delete_by_book = _patch_leaves_repo(monkeypatch)
    dispatcher = EventDispatcher()
    dispatcher.register("chapter.scenes_reparsed", handle_chapter_scenes_reparsed)

    handled = await dispatcher.dispatch(_reparsed_event(), pool=AsyncMock())

    assert handled is True
    delete_by_book.assert_awaited_once()
    assert str(delete_by_book.await_args.args[0]) == str(_BOOK)


@pytest.mark.asyncio
async def test_scenes_reparsed_idempotent_on_replay(monkeypatch):
    """At-least-once delivery: a redelivered event invalidates the same book
    again. delete_by_book is naturally idempotent (a second call deletes 0),
    and the handler stays book-scoped on every delivery."""
    delete_by_book = _patch_leaves_repo(monkeypatch, returns=(0, 0))
    pool = AsyncMock()
    ev = _reparsed_event()

    await handle_chapter_scenes_reparsed(ev, pool=pool)
    await handle_chapter_scenes_reparsed(ev, pool=pool)  # replay

    assert delete_by_book.await_count == 2
    scopes = {str(c.args[0]) for c in delete_by_book.await_args_list}
    assert scopes == {str(_BOOK)}  # every delivery scoped to the same book


@pytest.mark.asyncio
async def test_scenes_reparsed_missing_book_id_skips(monkeypatch):
    """Malformed payload (no book_id) → clean skip: no invalidation, no raise
    (one bad event must not wedge the consumer loop)."""
    delete_by_book = _patch_leaves_repo(monkeypatch)

    await handle_chapter_scenes_reparsed(
        _reparsed_event(book_id=None), pool=AsyncMock()
    )

    delete_by_book.assert_not_awaited()


@pytest.mark.asyncio
async def test_scenes_reparsed_invalid_book_id_skips(monkeypatch):
    """A non-UUID book_id is also a graceful skip (defensive parse)."""
    delete_by_book = _patch_leaves_repo(monkeypatch)

    await handle_chapter_scenes_reparsed(
        _reparsed_event(book_id="not-a-uuid"), pool=AsyncMock()
    )

    delete_by_book.assert_not_awaited()
