"""SC11 Phase 2 — the mirror's event consumer.

THE FAILURE THESE TESTS EXIST TO PREVENT, in knowledge-service's own words: an unregistered
event_type is dropped at DEBUG and ACKED — *"the event is acked into the void. A perfect silent
success."* Both ends look healthy. book-service emits, the relay ships, the consumer acks. And the
mirror silently goes stale, so the Plan Hub renders a written book as unwritten, forever, with
nobody ever seeing an error.

A wiring bug in an event consumer does not crash. It goes quiet. So the wiring itself has to be a
test.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.events.consumer import (
    CHAPTER_STREAM,
    REQUIRED_EVENTS,
    CompositionEventConsumer,
    _parse,
)


def _consumer(**kw) -> CompositionEventConsumer:
    return CompositionEventConsumer(
        "redis://x", AsyncMock(), book_base_url="http://book", jwt_secret="s" * 32, **kw)


def test_EVERY_required_event_has_a_handler_or_the_mirror_goes_SILENTLY_stale():
    """The whole point. If `chapter.scenes_linked` were emitted and never registered here, every
    publish would look healthy from both ends while the mirror rotted — no error, no log, no
    symptom until a user notices their written book renders as unwritten.

    The consumer refuses to CONSTRUCT with a missing handler, so the failure is a loud crash at
    boot rather than a quiet afternoon."""
    c = _consumer()
    assert REQUIRED_EVENTS <= set(c._handlers), (
        f"no handler for {sorted(REQUIRED_EVENTS - set(c._handlers))} — those events would be "
        "ACKED INTO THE VOID and the mirror would silently go stale"
    )


def test_a_missing_handler_FAILS_AT_CONSTRUCTION_not_at_runtime():
    """Loud at boot beats quiet forever. A required event with no handler must not be discoverable
    only by a user noticing wrong data months later."""
    with patch.dict(
        CompositionEventConsumer.__init__.__globals__,
        {"REQUIRED_EVENTS": frozenset({"chapter.scenes_linked", "chapter.never_registered"})},
    ):
        with pytest.raises(RuntimeError, match="chapter.never_registered"):
            _consumer()


def test_the_mirror_listens_to_the_stream_the_relay_actually_ships_to():
    """book-service's outbox rows carry aggregate_type='chapter', and worker-infra's OutboxRelay
    routes them to `loreweave:events:<aggregate_type>`. Listen anywhere else and every event is
    delivered to nobody — the two halves would be correct in isolation and dead together."""
    assert CHAPTER_STREAM == "loreweave:events:chapter"
    assert CompositionEventConsumer.streams == [CHAPTER_STREAM]
    # Its own group — it must not steal messages from knowledge-service's extractor.
    assert CompositionEventConsumer.group == "composition-mirror"


def test_the_chapter_stream_carries_events_we_do_NOT_handle_and_ignoring_them_is_correct():
    """`chapter.created`, `chapter.saved`, `chapter.published`, `chapter.kg_indexed`… all ride the
    same stream. Ignoring them is right. Ignoring one we DEPEND on is the silent-success bug — which
    is why the distinction is enforced by REQUIRED_EVENTS, not by hoping."""
    c = _consumer()
    assert "chapter.published" not in c._handlers
    assert "chapter.saved" not in c._handlers
    assert "chapter.scenes_linked" in c._handlers


def test_prose_gone_events_BOTH_clear_the_mirror():
    """spec §5.2b. A trashed/deleted chapter takes its scenes with it, and `source_scene_id` is
    never touched — so NO scenes_linked fires. Without these two handlers the mirror would keep
    claiming prose the author has deleted."""
    c = _consumer()
    # `is` on bound methods fails (each attribute access makes a new object) — compare the
    # underlying function, which is what "the same handler" actually means.
    assert (c._handlers["chapter.trashed"].__func__
            is c._handlers["chapter.deleted"].__func__), (
        "trashed and deleted must clear identically — the prose is gone either way")


def test_parse_reads_the_relay_wire_format():
    """The relay writes `event_type` / `aggregate_id` / `payload` (JSON string) as stream fields.
    A parse that silently produced an empty payload would make every handler a no-op."""
    ch, book = uuid.uuid4(), uuid.uuid4()
    ev = _parse(CHAPTER_STREAM, "1-0", {
        "event_type": "chapter.scenes_linked",
        "aggregate_id": str(ch),
        "payload": json.dumps({"book_id": str(book), "chapter_id": str(ch)}),
    })
    assert ev is not None
    assert ev.event_type == "chapter.scenes_linked"
    assert ev.payload["book_id"] == str(book)
    assert ev.payload["chapter_id"] == str(ch)


def test_an_event_with_no_type_is_unparseable_and_acked_not_retried_forever():
    assert _parse(CHAPTER_STREAM, "1-0", {"payload": "{}"}) is None


def test_a_malformed_payload_degrades_to_empty_rather_than_crashing_the_consumer():
    """One poison message must not wedge the whole stream. It degrades to an empty payload, the
    handler finds no book_id, warns, and moves on."""
    ev = _parse(CHAPTER_STREAM, "1-0", {"event_type": "chapter.scenes_linked", "payload": "not json"})
    assert ev is not None and ev.payload == {}


@pytest.mark.asyncio
async def test_an_UNREADABLE_book_service_RAISES_so_the_event_RETRIES_and_never_blanks_a_chapter():
    """THE most dangerous path in the mirror. If book-service is down we do not know whether the
    prose exists — and "I could not look" must never be reconciled into "there is no prose", which
    would blank a fully written chapter on a transient blip.

    The handler must RAISE (→ the base's retry → DLQ), never swallow into a reconcile-to-empty."""
    from app.engine.scene_decompile import BookSceneFetchError

    c = _consumer()
    book, ch = uuid.uuid4(), uuid.uuid4()
    c._owner_of = AsyncMock(return_value=uuid.uuid4())

    with patch("app.events.consumer.reconcile_one_chapter",
               side_effect=BookSceneFetchError(502, "down")):
        with pytest.raises(BookSceneFetchError):
            await c.handle(CHAPTER_STREAM, "1-0", {
                "event_type": "chapter.scenes_linked",
                "aggregate_id": str(ch),
                "payload": json.dumps({"book_id": str(book), "chapter_id": str(ch)}),
            })


@pytest.mark.asyncio
async def test_a_WORK_LESS_book_is_a_NO_OP_not_an_error():
    """SC11: "a Work-less book still browses." No Work ⇒ no spec nodes ⇒ nothing to mirror. It must
    not raise (which would retry forever and dead-letter a perfectly normal book)."""
    c = _consumer()
    c._owner_of = AsyncMock(return_value=None)
    book, ch = uuid.uuid4(), uuid.uuid4()

    with patch("app.events.consumer.reconcile_one_chapter") as rec:
        await c.handle(CHAPTER_STREAM, "1-0", {
            "event_type": "chapter.scenes_linked",
            "aggregate_id": str(ch),
            "payload": json.dumps({"book_id": str(book), "chapter_id": str(ch)}),
        })
        rec.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_reads_the_REAL_wire_shape_scene_id_not_id():
    """THE BUG THE LIVE SMOKE FOUND, and the reason a mocked client is not evidence.

    book-service's `GET /v1/books/{id}/scenes` names the scene's own id **`scene_id`**, not `id`.
    I read `it.get("id")` — got None for every row — silently produced ZERO links — and the mirror
    reconciled cleanly to empty on every single publish. No error. No log. `linked=0`, which reads
    exactly like "this chapter has no linked prose".

    Every unit test still passed, because every one of them fed dicts with the `"id"` key I had
    INVENTED. A mock encodes your assumption; it cannot contradict it. Only the column failing to
    stamp on a live publish exposed it.

    So this test asserts against the wire shape book-service ACTUALLY returns.
    """
    import httpx
    from app.services import written_verdict_service as svc

    scene, node, ch = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    real_body = {  # verbatim shape from a live GET /v1/books/{id}/scenes
        "items": [{
            "scene_id": scene,               # <- NOT "id"
            "book_id": str(uuid.uuid4()),
            "chapter_id": ch,
            "source_scene_id": node,
            "sort_order": 0,
            "leaf_text": "prose.",
            "lifecycle_state": "active",
        }],
        "next_cursor": None,
    }

    class _Resp:
        status_code = 200
        def json(self): return real_body

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return _Resp()

    with patch.object(httpx, "AsyncClient", lambda *a, **kw: _Client()):
        rows = await svc.fetch_scene_links("http://book", uuid.UUID(ch), "b")

    assert rows[0]["id"] == scene, (
        "the scene id was dropped — every link would be skipped and the mirror would "
        "reconcile to EMPTY on every publish, silently")
    assert rows[0]["source_scene_id"] == node
