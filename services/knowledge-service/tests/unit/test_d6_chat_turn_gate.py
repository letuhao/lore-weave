"""WS-1.3 — the D6 per-turn extraction gate.

    may_extract_chat_turn = (NOT is_assistant) AND chat_turn_extraction_enabled

DERIVED, never stored. FAILS CLOSED.

WHY THIS EXISTS. The assistant is an ALL-DAY chat session. Extracting knowledge from every
turn of it would:
  - double-count every fact (the daily distiller extracts them again from the confirmed entry)
  - multiply LLM spend by ~100x
  - and, worst, CANONIZE unreviewed, off-the-cuff chat as trusted knowledge about the
    user's real colleagues — the exact thing the human-review inbox exists to prevent.

The facts come ONCE A DAY, from the entry the human confirmed.

WHY IT IS TESTED BY EFFECT. The gate's answer used to be computed and then only LOGGED
while the enqueue ran anyway — a decorative gate. So these tests assert that NOTHING IS
QUEUED, not that a boolean was returned. (The repo's own rule: a stored-but-unread flag is
a bug, not a feature.)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events.dispatcher import EventData
from app.events.gating import may_extract_chat_turn
from app.events.handlers import handle_chat_turn

_USER = uuid4()
_PROJECT = uuid4()
_SESSION = uuid4()


def _pool(row):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=row)
    pool.execute = AsyncMock()
    return pool


def _turn_event():
    return EventData(
        stream="loreweave:events:chat",
        message_id="1-0",
        event_type="chat.turn_completed",
        aggregate_id=str(uuid4()),
        payload={"project_id": str(_PROJECT), "user_id": str(_USER), "session_id": str(_SESSION)},
        source="chat",
        raw={},
    )


# ── the derived gate ──


@pytest.mark.asyncio
async def test_assistant_project_never_extracts_per_turn():
    pool = _pool({"is_assistant": True, "chat_turn_extraction_enabled": True})
    assert await may_extract_chat_turn(pool, _PROJECT, _USER) is False, (
        "the assistant project must NEVER extract per turn — even with the flag ON. Its "
        "facts come once a day from the CONFIRMED entry. Per-turn extraction would canonize "
        "an entire unreviewed work conversation."
    )


@pytest.mark.asyncio
async def test_normal_project_extracts_when_enabled():
    pool = _pool({"is_assistant": False, "chat_turn_extraction_enabled": True})
    assert await may_extract_chat_turn(pool, _PROJECT, _USER) is True


@pytest.mark.asyncio
async def test_normal_project_with_the_flag_off_does_not_extract():
    pool = _pool({"is_assistant": False, "chat_turn_extraction_enabled": False})
    assert await may_extract_chat_turn(pool, _PROJECT, _USER) is False


@pytest.mark.asyncio
async def test_missing_project_fails_CLOSED():
    """A false negative (a turn not extracted) is trivially recoverable — the daily
    distiller catches it. A false positive (a private, all-day work conversation extracted
    as canon) is not. So every failure path returns False."""
    pool = _pool(None)
    assert await may_extract_chat_turn(pool, _PROJECT, _USER) is False


# ── proven by EFFECT: nothing is QUEUED ──


@pytest.mark.asyncio
async def test_assistant_turn_queues_NOTHING(monkeypatch):
    """THE ONE THAT MATTERS.

    The old gate computed its answer and then only LOGGED it while the enqueue ran anyway.
    A gate that does not gate is not a gate. This asserts the DOWNSTREAM EFFECT: for the
    assistant project, no extraction row is written at all.
    """
    queue = AsyncMock()
    repo = MagicMock()
    repo.queue_event = queue
    monkeypatch.setattr("app.events.handlers.ExtractionPendingRepo", lambda _p: repo)

    pool = _pool({"is_assistant": True, "chat_turn_extraction_enabled": True, "user_id": _USER})

    await handle_chat_turn(_turn_event(), pool=pool)

    queue.assert_not_awaited(), (
        "an assistant chat turn was QUEUED for extraction. Every turn of an 8-hour work "
        "session would be extracted as trusted canon about the user's real colleagues — "
        "unreviewed, and at ~100x the intended LLM spend."
    )


@pytest.mark.asyncio
async def test_normal_turn_still_queues(monkeypatch):
    """The gate must not break chat extraction for ordinary projects."""
    queue = AsyncMock()
    repo = MagicMock()
    repo.queue_event = queue
    monkeypatch.setattr("app.events.handlers.ExtractionPendingRepo", lambda _p: repo)
    monkeypatch.setattr("app.events.handlers.should_extract", AsyncMock(return_value=True))

    pool = _pool({"is_assistant": False, "chat_turn_extraction_enabled": True, "user_id": _USER})

    with patch("app.events.handlers.get_chat_client", create=True):
        await handle_chat_turn(_turn_event(), pool=pool)

    queue.assert_awaited(), "a NORMAL project's chat turn must still be queued"
