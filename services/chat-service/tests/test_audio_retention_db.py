"""WS-4.3 — the per-user audio-retention sweeper, against REAL Postgres.

The crux is the per-user resolution: a segment is deleted when it is older than its
OWNER'S effective TTL = LEAST(deploy_ceiling, user_choice ?? ceiling). A single global
DELETE (the old behavior) would either over-retain a privacy-conscious user's audio or
delete a default user's audio too early. This proves the LEAST/COALESCE by effect on
three users at once. Marked xdist_group("pg") (shared dev DB); skips if unreachable.
"""
import os
import uuid

import asyncpg
import pytest

from app.services.audio_retention import delete_expired_audio

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


@pytest.fixture
async def pool():
    try:
        p = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    async with p.acquire() as c:
        # match the real schema idempotently so the test runs pre-migration too
        await c.execute("ALTER TABLE user_chat_ai_prefs ADD COLUMN IF NOT EXISTS voice JSONB")
    yield p
    await p.close()


async def _seed_segment(c, user_id, *, age_hours, retention=None):
    """Insert a prefs row (with optional retention) + a message + one audio segment
    aged `age_hours`. Returns the segment's object_key."""
    if retention is not None:
        await c.execute(
            "INSERT INTO user_chat_ai_prefs (owner_user_id, voice) VALUES ($1, $2::jsonb) "
            "ON CONFLICT (owner_user_id) DO UPDATE SET voice = EXCLUDED.voice",
            user_id, f'{{"audio_retention_hours": {retention}}}',
        )
    sid = await c.fetchval(
        "INSERT INTO chat_sessions (owner_user_id, model_source, model_ref) "
        "VALUES ($1, 'user_model', $2) RETURNING session_id",
        user_id, str(uuid.uuid4()),
    )
    mid = await c.fetchval(
        "INSERT INTO chat_messages (message_id, session_id, owner_user_id, role, content, sequence_num) "
        "VALUES ($1,$2,$3,'assistant','hi',1) RETURNING message_id",
        uuid.uuid4(), sid, user_id,
    )
    key = f"audio/{uuid.uuid4()}.mp3"
    await c.execute(
        "INSERT INTO message_audio_segments "
        "(message_id, session_id, user_id, segment_index, object_key, sentence_text, created_at) "
        "VALUES ($1,$2,$3,0,$4,'hi', now() - make_interval(hours => $5))",
        mid, sid, user_id, key, age_hours,
    )
    return key


@pytest.mark.asyncio
async def test_sweeper_resolves_ttl_per_user(pool):
    ceiling = 48
    async with pool.acquire() as c:
        u_short = uuid.uuid4()   # retention 1h; a 5h-old segment → EXPIRED
        u_default = uuid.uuid4()  # no setting; a 5h-old segment → kept (< 48h ceiling)
        u_zero = uuid.uuid4()     # retention 0h; ANY segment → EXPIRED immediately
        key_short = await _seed_segment(c, u_short, age_hours=5, retention=1)
        key_default = await _seed_segment(c, u_default, age_hours=5)  # inherits ceiling
        key_zero = await _seed_segment(c, u_zero, age_hours=1, retention=0)

        deleted = await delete_expired_audio(pool, ceiling)

        assert key_short in deleted, "short-retention user's aged segment must be swept"
        assert key_zero in deleted, "retention=0 means delete on next sweep"
        assert key_default not in deleted, "a default user under the ceiling must be kept"

        # the kept row is really still there; the swept ones are really gone
        remaining = await c.fetch(
            "SELECT object_key FROM message_audio_segments WHERE object_key = ANY($1)",
            [key_short, key_default, key_zero],
        )
        remaining_keys = {r["object_key"] for r in remaining}
        assert remaining_keys == {key_default}

        # cleanup this test's rows
        await c.execute(
            "DELETE FROM chat_sessions WHERE owner_user_id = ANY($1)",
            [u_short, u_default, u_zero],
        )
        await c.execute(
            "DELETE FROM user_chat_ai_prefs WHERE owner_user_id = ANY($1)",
            [u_short, u_default, u_zero],
        )
