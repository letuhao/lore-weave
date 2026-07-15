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
