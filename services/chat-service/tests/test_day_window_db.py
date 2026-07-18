"""WS-1.8 (spec 06 §Q10) — the distiller's day-window read, against REAL Postgres.

This proves the SQL, not a mock's echo: the read is the distiller's ONLY input seam and it
enforces two safety properties in the query itself — ASSISTANT-ONLY (only sessions bound to the
named diary book_id; a user's novel/roleplay chats are never returned) and OWNER-SCOPED (only the
named user). A mocked pool would just replay whatever rows we feed it and prove neither filter
(mocked-client-hides-server-side-filters). So we insert a deliberately adversarial fixture —
another book, another user, an error turn, another day — and assert the window is EXACTLY the
right messages, chronological across sessions, with truncation + tool_names surfaced.

Marked xdist_group("pg") (CLAUDE.md — shared dev DB, serialized). Skips cleanly when the dev DB
is unreachable; applies the local_date column idempotently so it runs pre-migration too (never a
silent skip that lets the green suite lie).
"""
import json
import os
import uuid
from datetime import date, datetime, timezone

import asyncpg
import pytest

from app.routers.internal import day_window

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")

DAY_X = date(2026, 3, 10)
DAY_Y = date(2026, 3, 11)


@pytest.fixture
async def pool():
    try:
        p = await asyncpg.create_pool(DSN, min_size=1, max_size=3)
    except Exception:
        pytest.skip("dev postgres unreachable")
    async with p.acquire() as c:
        await c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS local_date DATE")
        # T-4 discriminator — apply idempotently so the test runs pre-migration too.
        await c.execute(
            "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS session_kind TEXT NOT NULL DEFAULT 'chat'"
        )
    try:
        yield p
    finally:
        await p.close()


async def _ins_session(c, owner, book_id, session_kind="chat"):
    return await c.fetchval(
        "INSERT INTO chat_sessions (owner_user_id, model_source, model_ref, book_id, session_kind) "
        "VALUES ($1, 'user_model', $2, $3, $4) RETURNING session_id",
        str(owner), str(uuid.uuid4()), (str(book_id) if book_id else None), session_kind,
    )


async def _ins_msg(c, sid, owner, seq, day, *, role="user", content="hi",
                   is_error=False, created_at=None, tool_calls=None, exclude_from_memory=False):
    await c.execute(
        "INSERT INTO chat_messages "
        "(session_id, owner_user_id, role, content, sequence_num, local_date, is_error, created_at, "
        " tool_calls, exclude_from_memory) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, COALESCE($8, now()), $9::jsonb, $10)",
        str(sid), str(owner), role, content, seq, day, is_error, created_at,
        json.dumps(tool_calls) if tool_calls is not None else None, exclude_from_memory,
    )


@pytest.fixture
async def world(pool):
    """User A has a diary (book D) + a novel (book N); user B has their own diary. Returns the
    ids and cleans up every session (messages cascade) afterward."""
    userA, userB = uuid.uuid4(), uuid.uuid4()
    bookD, bookN, bookD2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sessions = []
    async with pool.acquire() as c:
        s_diary1 = await _ins_session(c, userA, bookD, "assistant")  # assistant session 1 (book D)
        s_diary2 = await _ins_session(c, userA, bookD, "assistant")  # assistant session 2 (same book/day)
        s_novel = await _ins_session(c, userA, bookN, "chat")        # a NON-assistant session (book N)
        s_other = await _ins_session(c, userB, bookD2, "assistant")  # another USER's assistant session
        # T-4 adversarial: a session bound to the diary book D but session_kind='chat' — must be
        # EXCLUDED, proving session_kind (not book_id) is the discriminator.
        s_diary_chat = await _ins_session(c, userA, bookD, "chat")
        sessions = [s_diary1, s_diary2, s_novel, s_other, s_diary_chat]

        t = lambda h, m: datetime(2026, 3, 10, h, m, tzinfo=timezone.utc)  # noqa: E731
        # Included (user A, assistant sessions, day X, non-error) — interleaved across two sessions
        # so the ORDER BY created_at is genuinely cross-session, not just per-session sequence_num.
        await _ins_msg(c, s_diary1, userA, 0, DAY_X, content="09:00 first", created_at=t(9, 0))
        await _ins_msg(c, s_diary2, userA, 0, DAY_X, content="10:00 second",
                       role="assistant", created_at=t(10, 0),
                       tool_calls=[{"tool": "glossary_recall", "ok": True}, {"tool": "x"}])
        await _ins_msg(c, s_diary1, userA, 1, DAY_X, content="11:00 third", created_at=t(11, 0))
        # Excluded — every WHERE clause gets one adversarial row:
        await _ins_msg(c, s_diary1, userA, 2, DAY_X, content="ERR", is_error=True, created_at=t(12, 0))
        await _ins_msg(c, s_diary1, userA, 3, DAY_Y, content="next day", created_at=datetime(2026, 3, 11, 9, 0, tzinfo=timezone.utc))
        await _ins_msg(c, s_novel, userA, 0, DAY_X, content="NOVEL chat", created_at=t(9, 30))
        await _ins_msg(c, s_other, userB, 0, DAY_X, content="OTHER user", created_at=t(9, 45))
        # a diary-BOOK-bound but chat-KIND session — excluded by the session_kind discriminator:
        await _ins_msg(c, s_diary_chat, userA, 0, DAY_X, content="DIARY-BOOK but CHAT kind", created_at=t(9, 50))
    try:
        yield {"userA": userA, "userB": userB, "bookD": bookD, "s_diary1": s_diary1}
    finally:
        async with pool.acquire() as c:
            for sid in sessions:
                await c.execute("DELETE FROM chat_sessions WHERE session_id = $1", str(sid))


async def test_session_kind_is_the_discriminator_not_book_id(pool, world):
    # T-4 (sealed): the discriminator is session_kind='assistant', NOT a book_id=diary derivation.
    # Called WITHOUT a book_id scope, the read returns the user's assistant-session messages and
    # EXCLUDES a session bound to the diary BOOK but marked session_kind='chat'.
    out = await day_window(user_id=world["userA"], local_date=DAY_X, book_id=None, limit=5000, db=pool)
    contents = [m["content"] for m in out["messages"]]
    assert "DIARY-BOOK but CHAT kind" not in contents, "session_kind must gate, not book_id"
    assert "NOVEL chat" not in contents
    assert contents == ["09:00 first", "10:00 second", "11:00 third"]
    assert out["book_id"] is None  # no scope passed → session_kind alone gated


async def test_returns_only_this_users_assistant_messages_for_the_day(pool, world):
    out = await day_window(user_id=world["userA"], book_id=world["bookD"], local_date=DAY_X, limit=5000, db=pool)
    contents = [m["content"] for m in out["messages"]]
    # Exactly the three non-error, book-D, day-X messages — nothing from the novel book, the other
    # user, the error turn, or the next day.
    assert contents == ["09:00 first", "10:00 second", "11:00 third"], (
        f"day-window leaked or dropped rows: {contents}"
    )
    assert out["message_count"] == 3
    assert out["truncated"] is False
    assert out["local_date"] == "2026-03-10"


async def test_dont_remember_turn_is_excluded_from_the_day_window(pool, world):
    # WS-2.9 (spec 09 §Q6) — a message flagged exclude_from_memory (a "don't remember this" / grounding-off
    # turn) is NOT distilled: the day-window read must drop it, or the escape hatch leaks into the diary.
    async with pool.acquire() as c:
        await _ins_msg(c, world["s_diary1"], world["userA"], 50, DAY_X,
                       content="SECRET do-not-remember", created_at=datetime(2026, 3, 10, 13, 0, tzinfo=timezone.utc),
                       exclude_from_memory=True)
    out = await day_window(user_id=world["userA"], book_id=world["bookD"], local_date=DAY_X, limit=5000, db=pool)
    contents = [m["content"] for m in out["messages"]]
    assert "SECRET do-not-remember" not in contents, "a don't-remember turn leaked into the day-window"
    # the ordinary turns are unaffected
    assert contents == ["09:00 first", "10:00 second", "11:00 third"]


async def test_tool_names_surface_for_the_self_feeding_guard(pool, world):
    out = await day_window(user_id=world["userA"], book_id=world["bookD"], local_date=DAY_X, limit=5000, db=pool)
    by_content = {m["content"]: m for m in out["messages"]}
    # The map step's §Q9 self-feeding guard needs the tool names of each assistant turn.
    assert by_content["10:00 second"]["tool_names"] == ["glossary_recall", "x"]
    assert by_content["09:00 first"]["tool_names"] == []  # a plain user turn has none


async def test_window_is_capped_and_truncation_is_signalled(pool, world):
    # limit below the day's size → the OLDEST `limit` messages + truncated=true (bounded prefix,
    # never an unbounded stream into the worker).
    out = await day_window(user_id=world["userA"], book_id=world["bookD"], local_date=DAY_X, limit=2, db=pool)
    assert out["message_count"] == 2
    assert out["truncated"] is True
    assert [m["content"] for m in out["messages"]] == ["09:00 first", "10:00 second"]


async def test_a_book_with_no_assistant_day_returns_empty_not_error(pool, world):
    out = await day_window(user_id=world["userA"], book_id=world["bookD"], local_date=date(2026, 1, 1), limit=5000, db=pool)
    assert out == {
        "user_id": str(world["userA"]),
        "book_id": str(world["bookD"]),
        "local_date": "2026-01-01",
        "message_count": 0,
        "truncated": False,
        "messages": [],
    }
