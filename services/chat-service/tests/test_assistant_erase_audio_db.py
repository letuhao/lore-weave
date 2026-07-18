"""WS-4.4 — the D-R27 assistant-data erasure must also delete the voice audio OBJECTS.

The DELETE cascades chat_sessions → chat_messages → message_audio_segments ROWS, but the
cascade can't RETURN the MinIO object_keys, so the audio objects were ORPHANED — "hard
deleted" audio still readable in the bucket, an erasure hole. This proves by effect that
the object_keys are collected BEFORE the cascade and delete_object is called for each,
SCOPED to assistant sessions (a normal chat's audio is never touched). Real Postgres;
delete_object is spied (no MinIO needed). Marked xdist_group("pg"); skips if PG down.
"""
import os
import uuid

import asyncpg
import pytest

import app.storage.minio_client as minio_client
from app.routers.internal import erase_assistant_data

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


@pytest.fixture
async def pool():
    try:
        p = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    yield p
    await p.close()


async def _seed(c, user_id, *, kind):
    sid = await c.fetchval(
        "INSERT INTO chat_sessions (owner_user_id, model_source, model_ref, session_kind) "
        "VALUES ($1, 'user_model', $2, $3) RETURNING session_id",
        user_id, str(uuid.uuid4()), kind,
    )
    mid = await c.fetchval(
        "INSERT INTO chat_messages (message_id, session_id, owner_user_id, role, content, sequence_num) "
        "VALUES ($1,$2,$3,'assistant','hi',1) RETURNING message_id",
        uuid.uuid4(), sid, user_id,
    )
    key = f"audio/{uuid.uuid4()}.mp3"
    await c.execute(
        "INSERT INTO message_audio_segments "
        "(message_id, session_id, user_id, segment_index, object_key, sentence_text) "
        "VALUES ($1,$2,$3,0,$4,'hi')",
        mid, sid, user_id, key,
    )
    return sid, key


@pytest.mark.asyncio
async def test_erase_deletes_assistant_audio_objects_only(pool, monkeypatch):
    deleted_keys: list[str] = []

    async def _spy(key):
        deleted_keys.append(key)

    monkeypatch.setattr(minio_client, "delete_object", _spy)

    uid = uuid.uuid4()
    async with pool.acquire() as c:
        _, key_assistant = await _seed(c, uid, kind="assistant")
        chat_sid, key_chat = await _seed(c, uid, kind="chat")

    try:
        result = await erase_assistant_data(user_id=uid, book_id=None, db=pool)

        # the assistant audio OBJECT is deleted; the normal-chat audio object is NOT
        assert key_assistant in deleted_keys, "orphaned assistant audio object must be deleted"
        assert key_chat not in deleted_keys, "a normal chat's audio must never be touched"
        assert result["deleted_audio_objects"] == 1

        async with pool.acquire() as c:
            # the assistant segment ROW cascaded away; the chat segment ROW survives
            assert await c.fetchval(
                "SELECT count(*) FROM message_audio_segments WHERE object_key=$1", key_assistant
            ) == 0
            assert await c.fetchval(
                "SELECT count(*) FROM message_audio_segments WHERE object_key=$1", key_chat
            ) == 1
    finally:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM chat_sessions WHERE owner_user_id=$1", uid)
