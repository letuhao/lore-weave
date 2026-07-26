"""D-REFLECTION-WIRE — the reflection consumer's decode + ack contract."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.reflection_consumer import run_one_reflection_message


class _Recaller:
    def __init__(self, facts): self.recall_facts_range = AsyncMock(return_value=facts)


class _Book:
    def __init__(self): self.writes = []
    async def write_diary_entry(self, **kw):
        self.writes.append(kw); return {"chapter_id": "r1"}


class _Chat:
    """C2 — a fake ChatAssistantClient recording its calls + returning canned notes/dismissals."""
    def __init__(self, notes=None, dismissed=frozenset()):
        self._notes = notes or []
        self._dismissed = dismissed
        self.notes_calls = []
        self.dismiss_calls = []
        self.pattern_puts = []  # R1 — records (user_id, week_start, week_end, patterns)
    async def list_reflection_notes(self, *, user_id, date_from, date_to):
        self.notes_calls.append((user_id, date_from, date_to)); return self._notes
    async def list_dismissed_pattern_keys(self, *, user_id):
        self.dismiss_calls.append(user_id); return self._dismissed
    async def put_reflection_patterns(self, *, user_id, week_start, week_end, patterns):
        self.pattern_puts.append((user_id, week_start, week_end, patterns)); return True


def _fields(**over):
    f = {"user_id": "u1", "book_id": "b1", "week_start": "2026-07-06",
         "week_end": "2026-07-12", "entry_zone": "UTC", "language": "en"}
    f.update(over); return f


@pytest.mark.asyncio
async def test_valid_message_runs_reflection_and_acks():
    book = _Book()
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "Shipped auth.", "event_date": "2026-07-06"}]),
        book_client=book, fields=_fields())
    assert ack is True
    assert book.writes and book.writes[0]["journal_kind"] == "reflection"


@pytest.mark.asyncio
async def test_malformed_message_is_acked_dropped():
    book = _Book()
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([]), book_client=book, fields={"user_id": "u1"})  # missing fields
    assert ack is True  # poison dropped, not retried
    assert book.writes == []


@pytest.mark.asyncio
async def test_distress_message_short_circuits_writes_nothing_and_acks():
    book = _Book()
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "I want to die", "event_date": "2026-07-08"}]),
        book_client=book, fields=_fields())
    assert ack is True and book.writes == []  # short-circuit, terminal → ack, no write


@pytest.mark.asyncio
async def test_bytes_encoded_fields_decode():
    book = _Book()
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "x", "event_date": "2026-07-06"}]),
        book_client=book, fields={k.encode(): v.encode() for k, v in _fields().items()})
    assert ack is True and book.writes  # redis returns bytes; must decode


# ── C2 (SD-C2) — reflection_notes feed co-occurrence; dismissals tombstone LIVE ──

_RECURRING_NOTES = [
    {"entry_date": "2026-07-06", "went_well": "focused on the migration plan", "to_improve": ""},
    {"entry_date": "2026-07-07", "went_well": "more migration progress", "to_improve": "less meetings"},
]


@pytest.mark.asyncio
async def test_reflection_notes_from_chat_client_feed_the_cooccurrence_detector():
    # The co-occurrence detector has NO substrate unless the consumer fetches the week's notes from
    # chat-service. With a chat_client wired, a term recurring on ≥2 days surfaces as a pattern.
    book, chat = _Book(), _Chat(notes=_RECURRING_NOTES)
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "x", "event_date": "2026-07-06"}]),
        book_client=book, chat_client=chat, fields=_fields())
    assert ack is True
    # fetched the WEEK's notes (the message's [week_start, week_end]) + the user's dismissals
    assert chat.notes_calls == [("u1", "2026-07-06", "2026-07-12")]
    assert chat.dismiss_calls == ["u1"]
    body = book.writes[0]["body"]
    assert "migration" in body  # the recurring theme surfaced from the notes → co-occurrence fired


@pytest.mark.asyncio
async def test_dismissed_pattern_key_is_tombstoned_live():
    # WS-5.6 tombstone LIVE: a dismissed pattern_key fetched from chat-service drops the matching
    # pattern AT DETECTION — it never resurfaces as a fresh row, even though the term still recurs.
    book = _Book()
    chat = _Chat(notes=_RECURRING_NOTES, dismissed=frozenset({"co_occurrence:migration"}))
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "x", "event_date": "2026-07-06"}]),
        book_client=book, chat_client=chat, fields=_fields())
    assert ack is True
    body = book.writes[0]["body"]
    assert "migration" not in body  # tombstoned → dropped, never surfaced


# ── R1 (D-REFLECTION-PATTERNS-FEED) — the structured patterns are persisted for the FE chip feed ──


@pytest.mark.asyncio
async def test_structured_patterns_are_persisted_for_the_fe_feed():
    # A reflected week PUTs its structured (tombstone-filtered) patterns to chat, keyed by the week,
    # so the FE can render dismissable chips (the dismiss CHAIN already exists; it had nothing to render).
    book, chat = _Book(), _Chat(notes=_RECURRING_NOTES)
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "x", "event_date": "2026-07-06"}]),
        book_client=book, chat_client=chat, fields=_fields())
    assert ack is True
    assert len(chat.pattern_puts) == 1
    uid, ws, we, patterns = chat.pattern_puts[0]
    assert (uid, ws, we) == ("u1", "2026-07-06", "2026-07-12")
    keys = {p["pattern_key"] for p in patterns}
    assert "co_occurrence:migration" in keys  # the co-occurrence chip is fed
    # every fed pattern carries the fields the FE dismiss chip needs
    for p in patterns:
        assert p["detector_code"] and p["pattern_key"] and "summary" in p


@pytest.mark.asyncio
async def test_short_circuit_clears_the_pattern_feed():
    # A distress short-circuit must PUT an empty set (clearing any stale chips) — the FE must never show
    # chips against a distress acknowledgement.
    book, chat = _Book(), _Chat(notes=_RECURRING_NOTES)
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "I want to die", "event_date": "2026-07-08"}]),
        book_client=book, chat_client=chat, fields=_fields())
    assert ack is True and book.writes == []       # short-circuit: no draft
    assert chat.pattern_puts == [("u1", "2026-07-06", "2026-07-12", [])]  # chips cleared


@pytest.mark.asyncio
async def test_notes_fetch_unavailable_is_retried_not_written_safety_fail_closed():
    # cold-review MED-1: the notes feed the fail-CLOSED Gate-3 safety screen. If chat-service is
    # unavailable, the consumer must UN-ACK (retry), NOT write a reflection that skipped screening
    # note-borne distress. A dismissals blip, by contrast, is safe to degrade — but that path isn't
    # even reached when notes fail.
    from app.clients import ChatAssistantUnavailable

    class _DownChat:
        async def list_reflection_notes(self, **kw):
            raise ChatAssistantUnavailable("chat-service down")
        async def list_dismissed_pattern_keys(self, **kw):
            raise AssertionError("must not be reached — notes failed first")

    book = _Book()
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "x", "event_date": "2026-07-06"}]),
        book_client=book, chat_client=_DownChat(), fields=_fields())
    assert ack is False           # un-acked → the base consumer retries
    assert book.writes == []      # nothing written while the safety screen's input is unavailable


@pytest.mark.asyncio
async def test_no_chat_client_degrades_to_no_notes_not_a_crash():
    # Back-compat: without a chat_client the consumer still runs (empty notes/dismissals), it just
    # can't fire the co-occurrence detector — a reflection with fewer detectors, never a failure.
    book = _Book()
    ack = await run_one_reflection_message(
        knowledge_client=_Recaller([{"content": "x", "event_date": "2026-07-06"}]),
        book_client=book, fields=_fields())  # chat_client defaults None
    assert ack is True and book.writes
