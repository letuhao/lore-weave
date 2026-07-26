"""WS-5.6 / C2 (SD-C2) — reflection_dismissals substrate, against REAL Postgres.

Proves the PER-USER tier + the dismiss idempotency (UNIQUE(owner, pattern_key), a double-dismiss is
a no-op) + owner-scoped read (a second user's tombstones never leak into the first user's set — the
worker fetches dismissed keys per-user and must not cross-tenant them). xdist_group("pg").
"""
import os
import uuid

import asyncpg
import pytest

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


@pytest.fixture
async def pool():
    try:
        p = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    async with p.acquire() as c:
        # ensure the C2 table exists (idempotent — matches the migration)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS reflection_dismissals (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              owner_user_id UUID NOT NULL, pattern_key TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              UNIQUE (owner_user_id, pattern_key))
        """)
    yield p
    await p.close()


async def _dismiss(c, uid, key):
    await c.execute(
        """INSERT INTO reflection_dismissals (owner_user_id, pattern_key)
           VALUES ($1,$2) ON CONFLICT (owner_user_id, pattern_key) DO NOTHING""",
        str(uid), key,
    )


@pytest.mark.asyncio
async def test_dismiss_is_idempotent_per_owner_and_key(pool):
    uid = uuid.uuid4()
    async with pool.acquire() as c:
        await _dismiss(c, uid, "co_occurrence:migration")
        await _dismiss(c, uid, "co_occurrence:migration")  # same key again → no-op, no dup
        rows = await c.fetch(
            "SELECT pattern_key FROM reflection_dismissals WHERE owner_user_id=$1", str(uid))
        assert [r["pattern_key"] for r in rows] == ["co_occurrence:migration"]  # exactly one row
        await c.execute("DELETE FROM reflection_dismissals WHERE owner_user_id=$1", str(uid))


@pytest.mark.asyncio
async def test_dismissed_keys_read_is_owner_scoped(pool):
    ua, ub = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await _dismiss(c, ua, "co_occurrence:migration")
        await _dismiss(c, ua, "journaling_gap")
        await _dismiss(c, ub, "co_occurrence:standup")  # other user's tombstone
        rows = await c.fetch(
            "SELECT pattern_key FROM reflection_dismissals WHERE owner_user_id=$1 ORDER BY pattern_key",
            str(ua))
        keys = [r["pattern_key"] for r in rows]
        assert keys == ["co_occurrence:migration", "journaling_gap"]  # B's tombstone never leaks
        await c.execute("DELETE FROM reflection_dismissals WHERE owner_user_id = ANY($1)", [ua, ub])
