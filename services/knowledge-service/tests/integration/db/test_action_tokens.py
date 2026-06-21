"""KM6 — consumed_tokens ledger integration tests (real Postgres via `pool`).

Proves the §13.4 single-use guarantee: first claim wins, replay loses, and a
concurrent double-claim of the same jti yields EXACTLY one winner (the PK
serializes them).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.repositories.action_tokens import ActionTokenRepo

pytestmark = pytest.mark.asyncio

_EXP = datetime.now(timezone.utc) + timedelta(minutes=10)


async def test_first_claim_wins_replay_loses(pool):
    repo = ActionTokenRepo(pool)
    jti = str(uuid4())
    first = await repo.consume(jti=jti, descriptor="kg_schema_edit", exp=_EXP)
    assert first is True
    replay = await repo.consume(jti=jti, descriptor="kg_schema_edit", exp=_EXP)
    assert replay is False


async def test_distinct_jtis_both_claim(pool):
    repo = ActionTokenRepo(pool)
    a = await repo.consume(jti=str(uuid4()), descriptor="kg_schema_edit", exp=_EXP)
    b = await repo.consume(jti=str(uuid4()), descriptor="kg_schema_edit", exp=_EXP)
    assert a is True and b is True


async def test_concurrent_double_claim_exactly_one_winner(pool):
    # Two repos on the SAME pool race to claim one jti — the PK must serialize them
    # so exactly one wins (the replay-safety guarantee under concurrency).
    repo = ActionTokenRepo(pool)
    jti = str(uuid4())
    results = await asyncio.gather(
        repo.consume(jti=jti, descriptor="kg_schema_edit", exp=_EXP),
        repo.consume(jti=jti, descriptor="kg_schema_edit", exp=_EXP),
    )
    assert sorted(results) == [False, True]
