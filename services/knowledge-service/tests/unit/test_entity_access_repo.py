"""Unit tests for EntityAccessRepo (Track 4 P0 — salience substrate).

Spy-pool level: proves the upsert SQL is issued with de-duped ids, that the
recorder NEVER raises (fire-and-forget contract), that empty input skips the
pool, and that load_salience maps rows. A real-PG integration test covers the
actual ON CONFLICT increment + tenancy isolation.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.repositories.entity_access import EntityAccessRepo, EntitySalience


def _pool_with_conn():
    conn = AsyncMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = AsyncMock()
    pool.acquire = _acquire
    return pool, conn


@pytest.mark.asyncio
async def test_record_accesses_issues_dedup_sorted_upsert():
    pool, conn = _pool_with_conn()
    repo = EntityAccessRepo(pool)
    user_id, project_id = uuid4(), uuid4()

    n = await repo.record_accesses(user_id, project_id, ["b", "a", "b", "", "a"])

    assert n == 2  # {"a","b"} — de-duped, empties dropped
    conn.execute.assert_awaited_once()
    args = conn.execute.await_args.args
    assert args[1] == user_id and args[2] == project_id
    assert args[3] == ["a", "b"]  # sorted + deduped


@pytest.mark.asyncio
async def test_record_accesses_empty_skips_pool():
    pool, conn = _pool_with_conn()
    repo = EntityAccessRepo(pool)
    assert await repo.record_accesses(uuid4(), uuid4(), []) == 0
    assert await repo.record_accesses(uuid4(), uuid4(), ["", None]) == 0  # type: ignore[list-item]
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_accesses_never_raises():
    # fire-and-forget: a telemetry write must not break a context build.
    pool = AsyncMock()

    @asynccontextmanager
    async def _boom():
        raise RuntimeError("pg down")
        yield  # pragma: no cover

    pool.acquire = _boom
    repo = EntityAccessRepo(pool)
    assert await repo.record_accesses(uuid4(), uuid4(), ["a"]) == 0  # swallowed → 0


@pytest.mark.asyncio
async def test_load_salience_maps_rows():
    pool, conn = _pool_with_conn()
    now = datetime.now(timezone.utc)
    conn.fetch = AsyncMock(return_value=[
        {"entity_id": "e1", "retrieval_count": 7, "decayed_score": 3.5,
         "last_retrieved_at": now, "feedback_score": 2.0},
    ])
    repo = EntityAccessRepo(pool)
    out = await repo.load_salience(uuid4(), uuid4())
    assert out == {"e1": EntitySalience("e1", 7, 3.5, now, feedback_score=2.0)}


@pytest.mark.asyncio
async def test_record_accesses_stamps_session_id():
    # P3b — the session stamp rides the upsert params for feedback attribution.
    pool, conn = _pool_with_conn()
    repo = EntityAccessRepo(pool)
    sid = uuid4()
    await repo.record_accesses(uuid4(), uuid4(), ["a"], session_id=sid)
    args = conn.execute.await_args.args
    assert "last_session_id" in args[0]
    assert args[4] == sid  # $4 = session stamp


@pytest.mark.asyncio
async def test_apply_feedback_scopes_by_tenant_session_and_window():
    pool, conn = _pool_with_conn()
    conn.execute = AsyncMock(return_value="UPDATE 3")
    repo = EntityAccessRepo(pool)
    user, proj, sid = uuid4(), uuid4(), uuid4()
    turn_at = datetime.now(timezone.utc)

    n = await repo.apply_feedback(user, proj, sid, 1, turn_at)

    assert n == 3
    sql, *params = conn.execute.await_args.args
    assert "user_id = $1 AND project_id = $2" in sql      # tenancy scope
    assert "last_session_id = $3" in sql                   # session attribution
    assert "BETWEEN" in sql                                # time window
    assert params[:4] == [user, proj, sid, 1.0]


@pytest.mark.asyncio
async def test_apply_feedback_never_raises():
    pool = AsyncMock()

    @asynccontextmanager
    async def _boom():
        raise RuntimeError("pg down")
        yield  # pragma: no cover

    pool.acquire = _boom
    repo = EntityAccessRepo(pool)
    assert await repo.apply_feedback(
        uuid4(), uuid4(), uuid4(), -1, datetime.now(timezone.utc)
    ) == 0


@pytest.mark.asyncio
async def test_load_salience_swallows_error():
    pool = AsyncMock()

    @asynccontextmanager
    async def _boom():
        raise RuntimeError("pg down")
        yield  # pragma: no cover

    pool.acquire = _boom
    repo = EntityAccessRepo(pool)
    assert await repo.load_salience(uuid4(), uuid4()) == {}
