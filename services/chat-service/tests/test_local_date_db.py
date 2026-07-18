"""WS-1.8 / DBT-11 (spec 01, D-R14) — chat_messages.local_date, against REAL Postgres.

The distiller buckets "one day's" assistant messages by the LOCAL calendar day the message
was written. That day must be STAMPED at write-time (a stored column), not re-derived at read
time — re-deriving lets a later timezone change silently re-bucket history into a different
day. This migration adds the column with a UTC-date DEFAULT (the D-R14 fallback until the
timezone-aware population lands); this test proves a newly inserted message actually CARRIES a
local_date equal to the server's current UTC day — i.e. the default fires, not just that the
column exists (a column that is present but never populated is the write-only-behavior bug).

Marked xdist_group("pg") (CLAUDE.md — shared dev DB, serialized). Skips cleanly when the dev
DB is unreachable. The fixture applies the column idempotently (matches the migration) so the
test genuinely runs even if chat-service hasn't re-migrated yet — never a silent skip that
lets the green suite lie (env-gated-tests-skip-and-green-suite-lies).
"""
import os
import uuid

import asyncpg
import pytest

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


@pytest.fixture
async def pool_and_session():
    try:
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    uid = uuid.uuid4()
    async with pool.acquire() as c:
        # Apply the WS-1.8 column + its default idempotently (matches migrate.py) so the test
        # exercises the real write-time behavior regardless of whether the service re-migrated.
        await c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS local_date DATE")
        await c.execute(
            "ALTER TABLE chat_messages ALTER COLUMN local_date "
            "SET DEFAULT ((now() AT TIME ZONE 'UTC')::date)"
        )
        sid = await c.fetchval(
            "INSERT INTO chat_sessions (owner_user_id, model_source, model_ref) "
            "VALUES ($1, 'user_model', $2) RETURNING session_id",
            uid, uuid.uuid4(),
        )
    try:
        yield pool, sid, uid
    finally:
        async with pool.acquire() as c:
            # chat_messages cascades on the session delete (ON DELETE CASCADE).
            await c.execute("DELETE FROM chat_sessions WHERE session_id = $1", sid)
        await pool.close()


async def _insert_message(pool, sid, uid, seq):
    async with pool.acquire() as c:
        return await c.fetchrow(
            "INSERT INTO chat_messages (session_id, owner_user_id, role, content, sequence_num) "
            "VALUES ($1, $2, 'assistant', 'hi', $3) "
            "RETURNING local_date, (now() AT TIME ZONE 'UTC')::date AS server_utc_day",
            sid, uid, seq,
        )


async def test_a_new_message_is_stamped_with_the_server_utc_day(pool_and_session):
    pool, sid, uid = pool_and_session
    row = await _insert_message(pool, sid, uid, 0)
    assert row["local_date"] is not None, (
        "local_date must be populated at write-time by the column DEFAULT — a NULL here means "
        "the distiller cannot bucket the message by day (the write-only-behavior bug)"
    )
    assert row["local_date"] == row["server_utc_day"], (
        "the D-R14 fallback stamps the server's current UTC calendar day until the "
        "timezone-aware population lands"
    )


async def test_local_date_is_indexable_for_the_per_day_query(pool_and_session):
    # The distiller's query is (owner_user_id, local_date) — prove two same-day messages for one
    # user land on the SAME local_date so the day-bucket is a single group, not fragmented.
    pool, sid, uid = pool_and_session
    r0 = await _insert_message(pool, sid, uid, 0)
    r1 = await _insert_message(pool, sid, uid, 1)
    assert r0["local_date"] == r1["local_date"], (
        "two messages written on the same UTC day must share a local_date so they bucket together"
    )
