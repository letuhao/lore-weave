"""W4 — consumed_tokens ledger integration (DB-gated).

The replay-prevention headline at the DB level: ConsumedTokenRepo.consume claims a
jti the FIRST time (True) and rejects the replay (False, ON CONFLICT DO NOTHING).
Two distinct jtis both claim. Gated on TEST_COMPOSITION_DB_URL (a throwaway DB).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.consumed_tokens import ConsumedTokenRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # MANDATORY (CLAUDE.md test-parallelization): this file DROPs/re-migrates tables on the
    # shared dev PG. Without the group, xdist schedules it on a DIFFERENT worker than the
    # other real-DB files and they drop each other's tables mid-run — the counts then lie.
    pytest.mark.xdist_group("pg"),
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        await run_migrations(p)
        async with p.acquire() as c:
            await c.execute("TRUNCATE consumed_tokens")
        yield p
    finally:
        async with p.acquire() as c:
            await c.execute("TRUNCATE consumed_tokens")
        await p.close()


async def test_consume_first_wins_replay_rejected(pool):
    repo = ConsumedTokenRepo(pool)
    exp = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
    jti = "sha256:replay-test"
    first = await repo.consume(jti=jti, descriptor="composition.motif_adopt", exp=exp)
    second = await repo.consume(jti=jti, descriptor="composition.motif_adopt", exp=exp)
    assert first is True   # first claim wins
    assert second is False  # replay of the SAME jti is rejected


async def test_distinct_jtis_both_claim(pool):
    repo = ConsumedTokenRepo(pool)
    exp = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
    a = await repo.consume(jti="jti-a", descriptor="composition.motif_mine", exp=exp)
    b = await repo.consume(jti="jti-b", descriptor="composition.motif_mine", exp=exp)
    assert a is True and b is True


async def test_table_shape(pool):
    """The F0-frozen consumed_tokens shape: jti PK, descriptor, exp, consumed_at."""
    async with pool.acquire() as c:
        cols = {
            r["column_name"]
            for r in await c.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'consumed_tokens'"
            )
        }
    assert {"jti", "descriptor", "exp", "consumed_at"} <= cols
