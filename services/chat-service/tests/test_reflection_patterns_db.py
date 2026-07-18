"""R1 (D-REFLECTION-PATTERNS-FEED) — reflection_patterns substrate, against REAL Postgres.

Drives the ACTUAL handler functions (no SQL duplication) to prove: get-or-REPLACE per (owner, week_end);
the READ returns the LATEST week EXCLUDING the user's tombstoned patterns (so a dismiss takes effect on
refresh); owner-scoped. xdist_group("pg").
"""
import os
import uuid

import asyncpg
import pytest

from app.routers.internal import (
    ReflectionPatternIn,
    ReflectionPatternsPut,
    list_reflection_patterns,
    put_reflection_patterns,
)

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


@pytest.fixture
async def pool():
    try:
        p = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    async with p.acquire() as c:
        await c.execute("""
            CREATE TABLE IF NOT EXISTS reflection_patterns (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              owner_user_id UUID NOT NULL, week_start DATE NOT NULL, week_end DATE NOT NULL,
              detector_code TEXT NOT NULL, summary TEXT NOT NULL, pattern_key TEXT NOT NULL,
              evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              UNIQUE (owner_user_id, week_end, pattern_key))
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS reflection_dismissals (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              owner_user_id UUID NOT NULL, pattern_key TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              UNIQUE (owner_user_id, pattern_key))
        """)
    yield p
    await p.close()


def _pat(code, key, summary="s"):
    return ReflectionPatternIn(detector_code=code, summary=summary, pattern_key=key, evidence_refs=[])


@pytest.mark.asyncio
async def test_put_read_tombstone_and_get_or_replace(pool):
    uid = uuid.uuid4()
    async with pool.acquire():
        pass
    try:
        # (1) PUT two patterns for week ending 07-12.
        await put_reflection_patterns(
            ReflectionPatternsPut(
                owner_user_id=uid, week_start="2026-07-06", week_end="2026-07-12",
                patterns=[_pat("co_occurrence", "co_occurrence:migration"),
                          _pat("journaling_gap", "journaling_gap")],
            ),
            db=pool,
        )
        got = await list_reflection_patterns(user_id=uid, week_end=None, db=pool)
        keys = {p["pattern_key"] for p in got["patterns"]}
        assert keys == {"co_occurrence:migration", "journaling_gap"}
        assert got["week_end"] == "2026-07-12"

        # (2) tombstone one → the READ excludes it (dismiss takes effect on refresh, server is SoT).
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO reflection_dismissals (owner_user_id, pattern_key) VALUES ($1,$2)",
                str(uid), "co_occurrence:migration")
        got2 = await list_reflection_patterns(user_id=uid, week_end=None, db=pool)
        assert {p["pattern_key"] for p in got2["patterns"]} == {"journaling_gap"}

        # (3) a LATER week's PUT becomes the latest; the read follows max(week_end).
        await put_reflection_patterns(
            ReflectionPatternsPut(
                owner_user_id=uid, week_start="2026-07-13", week_end="2026-07-19",
                patterns=[_pat("journaling_gap", "journaling_gap")],
            ),
            db=pool,
        )
        got3 = await list_reflection_patterns(user_id=uid, week_end=None, db=pool)
        assert got3["week_end"] == "2026-07-19"

        # (4) get-or-REPLACE: re-PUT the SAME week with a DIFFERENT set → the old set is gone.
        await put_reflection_patterns(
            ReflectionPatternsPut(
                owner_user_id=uid, week_start="2026-07-13", week_end="2026-07-19",
                patterns=[_pat("co_occurrence", "co_occurrence:standup")],
            ),
            db=pool,
        )
        got4 = await list_reflection_patterns(user_id=uid, week_end="2026-07-19", db=pool)
        assert {p["pattern_key"] for p in got4["patterns"]} == {"co_occurrence:standup"}

        # (5) empty PUT clears a week (a calm week has no chips).
        await put_reflection_patterns(
            ReflectionPatternsPut(owner_user_id=uid, week_start="2026-07-13", week_end="2026-07-19", patterns=[]),
            db=pool,
        )
        got5 = await list_reflection_patterns(user_id=uid, week_end="2026-07-19", db=pool)
        assert got5["patterns"] == []
    finally:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM reflection_patterns WHERE owner_user_id=$1", str(uid))
            await c.execute("DELETE FROM reflection_dismissals WHERE owner_user_id=$1", str(uid))


@pytest.mark.asyncio
async def test_explicit_week_end_calm_week_does_not_fall_back_to_a_prior_week(pool):
    # cold-review H1 — the chips must correspond to the DISPLAYED draft's week. A calm latest week (no
    # stored patterns) queried by its explicit week_end must return [] — NEVER a stale prior week's set.
    uid = uuid.uuid4()
    try:
        # week W-1 had patterns; week W is calm (cleared to empty).
        await put_reflection_patterns(
            ReflectionPatternsPut(owner_user_id=uid, week_start="2026-07-06", week_end="2026-07-12",
                                  patterns=[_pat("journaling_gap", "journaling_gap")]),
            db=pool,
        )
        await put_reflection_patterns(
            ReflectionPatternsPut(owner_user_id=uid, week_start="2026-07-13", week_end="2026-07-19", patterns=[]),
            db=pool,
        )
        # the FE asks for week W (the displayed draft's week) explicitly → no chips, no W-1 fallback.
        got = await list_reflection_patterns(user_id=uid, week_end="2026-07-19", db=pool)
        assert got["patterns"] == []
    finally:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM reflection_patterns WHERE owner_user_id=$1", str(uid))


@pytest.mark.asyncio
async def test_read_is_owner_scoped(pool):
    ua, ub = uuid.uuid4(), uuid.uuid4()
    try:
        for u in (ua, ub):
            await put_reflection_patterns(
                ReflectionPatternsPut(owner_user_id=u, week_start="2026-07-06", week_end="2026-07-12",
                                      patterns=[_pat("journaling_gap", f"journaling_gap:{u}")]),
                db=pool,
            )
        got = await list_reflection_patterns(user_id=ua, week_end=None, db=pool)
        assert {p["pattern_key"] for p in got["patterns"]} == {f"journaling_gap:{ua}"}  # B never leaks
    finally:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM reflection_patterns WHERE owner_user_id = ANY($1)", [ua, ub])
