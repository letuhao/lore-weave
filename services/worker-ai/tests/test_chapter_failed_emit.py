"""S3c-2b — knowledge.chapter_failed emit on provider circuit-open.

Locks the outbox row shape campaign-service consumes to auto-pause: event_type,
aggregate_type='knowledge' (→ loreweave:events:knowledge), error_code. Best-
effort: never raises.
"""

import json
from unittest.mock import AsyncMock

from app.outbox_emit import (
    emit_chapter_failed_best_effort,
    CHAPTER_FAILED_EVENT,
)

USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROJ = "99999999-9999-9999-9999-999999999999"
BOOK = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CHAP = "11111111-1111-1111-1111-111111111111"


async def test_emit_failed_row_shape():
    ex = AsyncMock()
    await emit_chapter_failed_best_effort(
        ex, user_id=USER, project_id=PROJ, book_id=BOOK,
        chapter_id=CHAP, error_code="LLM_CIRCUIT_OPEN",
    )
    args = ex.execute.call_args.args
    assert "'knowledge'" in args[0]            # aggregate_type → knowledge stream
    assert str(args[1]) == CHAP                # aggregate_id = chapter_id
    assert args[2] == CHAPTER_FAILED_EVENT
    payload = json.loads(args[3])
    assert payload["error_code"] == "LLM_CIRCUIT_OPEN"
    assert payload["chapter_id"] == CHAP
    assert payload["book_id"] == BOOK


async def test_emit_failed_best_effort_never_raises():
    ex = AsyncMock()
    ex.execute.side_effect = RuntimeError("db down")
    await emit_chapter_failed_best_effort(
        ex, user_id=USER, project_id=PROJ, book_id=BOOK,
        chapter_id=CHAP, error_code="LLM_CIRCUIT_OPEN",
    )
