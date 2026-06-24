"""KG-ML M2 — unit tests for the translation.published outbox emit helper."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.translation_events import emit_translation_published


@pytest.mark.asyncio
async def test_emit_translation_published_envelope():
    """The 3 chokepoints share ONE envelope: event_type + aggregate_type
    'translation' (routes to loreweave:events:translation) + the payload the
    knowledge consumer reads (book_id/chapter_id/target_language)."""
    conn = AsyncMock()
    user_id, book_id, chapter_id, ctid = uuid4(), uuid4(), uuid4(), uuid4()

    await emit_translation_published(
        conn,
        user_id=user_id,
        book_id=book_id,
        chapter_id=chapter_id,
        chapter_translation_id=ctid,
        target_language="vi",
        source="auto_promote",
    )

    conn.execute.assert_awaited_once()
    sql, agg_id, payload_json = conn.execute.await_args.args
    assert "INSERT INTO outbox_events" in sql
    assert "'translation.published'" in sql and "'translation'" in sql
    assert agg_id == ctid  # aggregate_id = chapter_translation_id
    payload = json.loads(payload_json)
    assert payload == {
        "user_id": str(user_id),
        "book_id": str(book_id),
        "chapter_id": str(chapter_id),
        "chapter_translation_id": str(ctid),
        "target_language": "vi",
        "source": "auto_promote",
    }


@pytest.mark.asyncio
async def test_emit_accepts_str_ids():
    """IDs may arrive as str (asyncpg row values) — must not raise."""
    conn = AsyncMock()
    await emit_translation_published(
        conn,
        user_id="u", book_id="b", chapter_id="c",
        chapter_translation_id=str(uuid4()),
        target_language="en", source="manual",
    )
    conn.execute.assert_awaited_once()
