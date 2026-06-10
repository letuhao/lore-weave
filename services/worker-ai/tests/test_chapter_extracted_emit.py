"""Auto-Draft Factory S1 (decision H) — knowledge.chapter_extracted emit.

Locks the outbox row shape campaign-service's projection consumer depends on:
event_type, aggregate_type='knowledge' (→ loreweave:events:knowledge), and the
(user_id, book_id, chapter_id) correlation tuple. Best-effort: never raises.
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.outbox_emit import (
    emit_chapter_extracted,
    emit_chapter_extracted_best_effort,
    CHAPTER_EXTRACTED_EVENT,
)

USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROJ = "99999999-9999-9999-9999-999999999999"
BOOK = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CHAP = "11111111-1111-1111-1111-111111111111"


async def test_emit_inserts_correct_outbox_row():
    ex = AsyncMock()
    await emit_chapter_extracted_best_effort(
        ex, user_id=USER, project_id=PROJ, book_id=BOOK, chapter_id=CHAP,
    )
    ex.execute.assert_awaited_once()
    args = ex.execute.call_args.args
    sql = args[0]
    assert "outbox_events" in sql
    assert "'knowledge'" in sql  # aggregate_type → loreweave:events:knowledge
    # args: (sql, aggregate_id, event_type, payload_json)
    assert str(args[1]) == CHAP            # aggregate_id = chapter_id
    assert args[2] == CHAPTER_EXTRACTED_EVENT
    payload = json.loads(args[3])
    assert payload["user_id"] == USER
    assert payload["book_id"] == BOOK
    assert payload["chapter_id"] == CHAP
    assert payload["status"] == "extracted"


async def test_emit_book_id_none_serialized():
    ex = AsyncMock()
    await emit_chapter_extracted_best_effort(
        ex, user_id=USER, project_id=PROJ, book_id=None, chapter_id=CHAP,
    )
    payload = json.loads(ex.execute.call_args.args[3])
    assert payload["book_id"] is None


async def test_emit_best_effort_never_raises():
    ex = AsyncMock()
    ex.execute.side_effect = RuntimeError("db down")
    # Must NOT propagate — a lost emit cannot fail the extraction.
    await emit_chapter_extracted_best_effort(
        ex, user_id=USER, project_id=PROJ, book_id=BOOK, chapter_id=CHAP,
    )


# ── D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: transactional variant ─────────────────

async def test_transactional_emit_inserts_same_row_shape():
    ex = AsyncMock()
    await emit_chapter_extracted(
        ex, user_id=USER, project_id=PROJ, book_id=BOOK, chapter_id=CHAP,
    )
    args = ex.execute.call_args.args
    assert "outbox_events" in args[0] and "'knowledge'" in args[0]
    assert str(args[1]) == CHAP
    assert args[2] == CHAPTER_EXTRACTED_EVENT
    assert json.loads(args[3])["status"] == "extracted"


async def test_transactional_emit_RAISES_so_tx_rolls_back():
    # The whole point of the transactional variant: on failure it must PROPAGATE
    # so the enclosing cursor-advance transaction rolls back together (no advanced
    # cursor without the completion event — the silent-loss window this closes).
    ex = AsyncMock()
    ex.execute.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await emit_chapter_extracted(
            ex, user_id=USER, project_id=PROJ, book_id=BOOK, chapter_id=CHAP,
        )
