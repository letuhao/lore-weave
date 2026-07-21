"""P3 (book-structure-pipeline §4.6, Option C) — the book-lifecycle mirror's event consumer.

THE FAILURE THESE GUARD AGAINST (knowledge-service's own words): an unregistered event_type dropped at
DEBUG and ACKED — "acked into the void, a perfect silent success". book-service emits, the relay ships, the
consumer acks, and a trashed book's structure keeps rendering as live forever with nobody seeing an error.
A wiring bug in an event consumer does not crash — it goes quiet. So the wiring is a test.

The REAL column-stamp proof is the live e2e (a live publish is the only thing that can contradict a mock —
see the written-verdict `scene_id`-not-`id` lesson); these lock the wiring + the re-read contract.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.clients.book_client import BookClientError
from app.events.book_lifecycle_consumer import (
    BOOK_STREAM,
    REQUIRED_EVENTS,
    BookLifecycleConsumer,
    _parse_payload,
)


def _consumer(**kw) -> BookLifecycleConsumer:
    return BookLifecycleConsumer("redis://x", AsyncMock(), book_client=AsyncMock(), **kw)


def test_the_mirror_listens_to_the_stream_the_relay_actually_ships_to():
    """book-service's outbox rows carry aggregate_type='book', and worker-infra's OutboxRelay routes them
    to `loreweave:events:<aggregate_type>`. Listen anywhere else and every event is delivered to nobody."""
    assert BOOK_STREAM == "loreweave:events:book"
    assert BookLifecycleConsumer.streams == [BOOK_STREAM]
    # Its own group — must not steal messages from the written-verdict mirror or any other consumer.
    assert BookLifecycleConsumer.group == "composition-book-lifecycle"


def test_a_missing_handler_FAILS_AT_CONSTRUCTION_not_at_runtime():
    """A required event with no route must crash at boot, not go quiet until a user notices a trashed
    book's structure still showing months later."""
    with patch.dict(
        BookLifecycleConsumer.__init__.__globals__,
        {"REQUIRED_EVENTS": frozenset({"book.lifecycle_changed", "book.never_registered"})},
    ):
        with pytest.raises(RuntimeError, match="book.never_registered"):
            _consumer()


@pytest.mark.asyncio
async def test_a_valid_event_RE_READS_the_projection_then_applies_that_lifecycle():
    """The core contract: the event carries only {book_id}; the consumer RE-READS the current lifecycle
    (order-/replay-safe) and applies THAT — never a payload-carried state."""
    c = _consumer()
    book = uuid.uuid4()
    c._book_client.get_book_lifecycle = AsyncMock(return_value="trashed")
    c._apply = AsyncMock()

    await c.handle(BOOK_STREAM, "1-0", {
        "event_type": "book.lifecycle_changed",
        "aggregate_id": str(book),
        "payload": json.dumps({"book_id": str(book)}),
    })

    c._book_client.get_book_lifecycle.assert_awaited_once_with(book)
    c._apply.assert_awaited_once_with(book, "trashed")


@pytest.mark.asyncio
async def test_an_unrelated_book_event_is_IGNORED_without_a_re_read():
    """loreweave:events:book may carry other book.* events later; ignoring THOSE is correct (and must not
    even hit book-service). Ignoring `book.lifecycle_changed` would be the silent-success bug."""
    c = _consumer()
    c._book_client.get_book_lifecycle = AsyncMock()
    c._apply = AsyncMock()

    await c.handle(BOOK_STREAM, "1-0", {
        "event_type": "book.something_else",
        "aggregate_id": str(uuid.uuid4()),
        "payload": "{}",
    })

    c._book_client.get_book_lifecycle.assert_not_called()
    c._apply.assert_not_called()


@pytest.mark.asyncio
async def test_an_UNREADABLE_book_service_RAISES_so_the_event_RETRIES_never_mislabels_live():
    """THE dangerous path. If book-service is down we do not know the book's lifecycle — and "I could not
    look" must never be applied as "still active", which would leave a trashed book's structure showing.
    The handler must RAISE (→ base retry → DLQ), never swallow into a default."""
    c = _consumer()
    book = uuid.uuid4()
    c._book_client.get_book_lifecycle = AsyncMock(
        side_effect=BookClientError(502, "BOOK_SERVICE_UNAVAILABLE"))
    c._apply = AsyncMock()

    with pytest.raises(BookClientError):
        await c.handle(BOOK_STREAM, "1-0", {
            "event_type": "book.lifecycle_changed",
            "aggregate_id": str(book),
            "payload": json.dumps({"book_id": str(book)}),
        })
    c._apply.assert_not_called()  # never mirror on an unknown lifecycle


@pytest.mark.asyncio
async def test_an_event_without_book_id_is_ACKED_not_retried_forever():
    """A malformed event with no book_id (and no aggregate_id) is unrecoverable — warn + ack, never a
    retry storm. It must NOT hit book-service or apply."""
    c = _consumer()
    c._book_client.get_book_lifecycle = AsyncMock()
    c._apply = AsyncMock()

    await c.handle(BOOK_STREAM, "1-0", {"event_type": "book.lifecycle_changed", "payload": "{}"})

    c._book_client.get_book_lifecycle.assert_not_called()
    c._apply.assert_not_called()


def test_book_id_falls_back_to_aggregate_id_when_payload_is_malformed():
    """The relay writes aggregate_id as a top-level field; a poison payload must still recover the book_id
    from it rather than wedging the stream."""
    assert _parse_payload({"payload": "not json"}) == {}


def test_REQUIRED_EVENTS_is_exactly_the_lifecycle_event():
    assert REQUIRED_EVENTS == frozenset({"book.lifecycle_changed"})
