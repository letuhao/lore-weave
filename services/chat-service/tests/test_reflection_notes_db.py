"""WS-5.1 — reflection_notes substrate, against REAL Postgres.

Proves the PER-USER tier + the UPSERT idempotency (one note per user per day, re-capture
REPLACES) + owner-scoped range read (a second user's notes never leak). xdist_group("pg").
"""
import os
import uuid
from datetime import date

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
        # ensure the WS-5.1 table exists (idempotent — matches the migration)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS reflection_notes (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              owner_user_id UUID NOT NULL, entry_date DATE NOT NULL,
              went_well TEXT, to_improve TEXT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              UNIQUE (owner_user_id, entry_date))
        """)
    yield p
    await p.close()


async def _upsert(c, uid, d, well, improve):
    return await c.fetchval(
        """INSERT INTO reflection_notes (owner_user_id, entry_date, went_well, to_improve)
           VALUES ($1,$2,$3,$4)
           ON CONFLICT (owner_user_id, entry_date) DO UPDATE
             SET went_well=EXCLUDED.went_well, to_improve=EXCLUDED.to_improve, updated_at=now()
           RETURNING id""",
        str(uid), d, well, improve,
    )


@pytest.mark.asyncio
async def test_upsert_is_idempotent_per_user_per_day(pool):
    uid = uuid.uuid4()
    d = date(2026, 7, 8)
    async with pool.acquire() as c:
        id1 = await _upsert(c, uid, d, "shipped auth", "more tests")
        id2 = await _upsert(c, uid, d, "shipped auth + billing", "write more tests")  # same day
        assert id1 == id2, "same (owner, day) must REPLACE, not duplicate"
        rows = await c.fetch("SELECT went_well, to_improve FROM reflection_notes WHERE owner_user_id=$1", str(uid))
        assert len(rows) == 1
        assert rows[0]["went_well"] == "shipped auth + billing"  # replaced
        await c.execute("DELETE FROM reflection_notes WHERE owner_user_id=$1", str(uid))


@pytest.mark.asyncio
async def test_range_read_is_owner_scoped(pool):
    ua, ub = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await _upsert(c, ua, date(2026, 7, 6), "A mon", None)
        await _upsert(c, ua, date(2026, 7, 9), "A thu", None)
        await _upsert(c, ua, date(2026, 7, 20), "A out-of-range", None)  # outside window
        await _upsert(c, ub, date(2026, 7, 7), "B tue", None)  # other user
        rows = await c.fetch(
            "SELECT entry_date, went_well FROM reflection_notes "
            "WHERE owner_user_id=$1 AND entry_date BETWEEN $2 AND $3 ORDER BY entry_date",
            str(ua), date(2026, 7, 6), date(2026, 7, 12),
        )
        wells = [r["went_well"] for r in rows]
        assert wells == ["A mon", "A thu"]  # in-window + owner only; B never leaks; out-of-range excluded
        await c.execute("DELETE FROM reflection_notes WHERE owner_user_id = ANY($1)", [ua, ub])
