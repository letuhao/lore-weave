"""user_chat_ai_prefs persistence against REAL Postgres — the deep field-merge
+ version-guard SQL a mock can't validate (spec §4.5).

Marked xdist_group("pg") (CLAUDE.md — shared dev DB, serialized). Skips cleanly
when the dev DB is unreachable / unmigrated.
"""
import os
import uuid

import asyncpg
import pytest

from app.db.user_chat_ai_prefs import VersionConflict, get_prefs, patch_prefs

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


@pytest.fixture
async def pool_and_user():
    try:
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    uid = uuid.uuid4()  # a throwaway user so we never collide with real rows
    async with pool.acquire() as c:
        has_table = await c.fetchval(
            "SELECT to_regclass('public.user_chat_ai_prefs') IS NOT NULL")
        if not has_table:
            await pool.close()
            pytest.skip("user_chat_ai_prefs not migrated on dev DB")
    try:
        yield pool, uid
    finally:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM user_chat_ai_prefs WHERE owner_user_id = $1", uid)
        await pool.close()


async def test_defaults_when_no_row(pool_and_user):
    pool, uid = pool_and_user
    p = await get_prefs(pool, owner_user_id=uid)
    assert p.persisted is False
    assert p.context == {"mode": "auto"}
    assert p.version == 0


async def test_patch_creates_then_field_merges(pool_and_user):
    pool, uid = pool_and_user
    p1 = await patch_prefs(pool, owner_user_id=uid, patch={"behavior": {"temperature": 0.7}})
    assert p1.version == 1 and p1.behavior == {"temperature": 0.7}
    # a second patch of a DIFFERENT leaf must preserve the first (deep merge)
    p2 = await patch_prefs(pool, owner_user_id=uid, patch={"behavior": {"top_p": 0.9}})
    assert p2.version == 2
    assert p2.behavior == {"temperature": 0.7, "top_p": 0.9}


async def test_patch_null_leaf_clears(pool_and_user):
    pool, uid = pool_and_user
    await patch_prefs(pool, owner_user_id=uid, patch={"behavior": {"temperature": 0.7, "top_p": 0.9}})
    p = await patch_prefs(pool, owner_user_id=uid, patch={"behavior": {"temperature": None}})
    assert p.behavior == {"top_p": 0.9}


async def test_version_conflict_raises(pool_and_user):
    pool, uid = pool_and_user
    await patch_prefs(pool, owner_user_id=uid, patch={"voice": {"speed": 1.0}})  # version 1
    with pytest.raises(VersionConflict):
        await patch_prefs(
            pool, owner_user_id=uid, patch={"voice": {"speed": 2.0}}, expected_version=0
        )
    # correct version succeeds
    p = await patch_prefs(pool, owner_user_id=uid, patch={"voice": {"speed": 2.0}}, expected_version=1)
    assert p.version == 2 and p.voice["speed"] == 2.0
