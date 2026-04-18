"""K13.1 — unit tests for the nightly anchor-score refresh job."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.jobs.compute_anchor_score import RefreshResult, refresh_anchor_scores


def _conn_returning(rows: list[dict], *, lock_acquired: bool = True) -> MagicMock:
    """Fake asyncpg Connection: fetchval() returns the advisory-lock bool on
    the first call and None on subsequent unlock call; fetch() returns rows.
    """
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)

    fetchval_calls = {"n": 0}

    async def fetchval_side(sql: str, *args):
        fetchval_calls["n"] += 1
        if "pg_try_advisory_lock" in sql:
            return lock_acquired
        if "pg_advisory_unlock" in sql:
            return True
        raise AssertionError(f"unexpected fetchval sql: {sql!r}")

    conn.fetchval = AsyncMock(side_effect=fetchval_side)
    return conn


def _pool_with_conn(conn: MagicMock) -> MagicMock:
    """Wrap `conn` in a pool whose `acquire()` is an async context manager."""
    pool = MagicMock()

    @asynccontextmanager
    async def fake_acquire():
        yield conn

    pool.acquire = fake_acquire
    return pool


def _session_factory():
    """Factory that returns a fresh async-context-manager per call."""
    sessions: list[MagicMock] = []

    @asynccontextmanager
    async def factory():
        s = MagicMock()
        sessions.append(s)
        yield s

    factory.sessions = sessions  # type: ignore[attr-defined]
    return factory


@pytest.mark.asyncio
async def test_iterates_every_project_and_sums_updates(monkeypatch):
    u1, u2 = str(uuid4()), str(uuid4())
    p1, p2, p3 = str(uuid4()), str(uuid4()), str(uuid4())
    conn = _conn_returning([
        {"user_id": u1, "project_id": p1},
        {"user_id": u1, "project_id": p2},
        {"user_id": u2, "project_id": p3},
    ])
    pool = _pool_with_conn(conn)

    calls = []

    async def fake_recompute(session, *, user_id, project_id):
        calls.append((user_id, project_id))
        return (10, 100)

    monkeypatch.setattr(
        "app.jobs.compute_anchor_score.recompute_anchor_score", fake_recompute,
    )

    factory = _session_factory()
    result = await refresh_anchor_scores(pool, factory)

    assert calls == [(u1, p1), (u1, p2), (u2, p3)]
    assert result == RefreshResult(
        projects_processed=3,
        entities_updated=30,
        projects_failed=0,
        lock_skipped=False,
    )
    # One fresh session per project — proves per-project isolation.
    assert len(factory.sessions) == 3  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_per_project_failure_does_not_abort_sweep(monkeypatch):
    u = str(uuid4())
    p_bad, p_ok1, p_ok2 = str(uuid4()), str(uuid4()), str(uuid4())
    conn = _conn_returning([
        {"user_id": u, "project_id": p_bad},
        {"user_id": u, "project_id": p_ok1},
        {"user_id": u, "project_id": p_ok2},
    ])
    pool = _pool_with_conn(conn)

    async def fake_recompute(session, *, user_id, project_id):
        if project_id == p_bad:
            raise RuntimeError("neo4j hiccup")
        return (5, 50)

    monkeypatch.setattr(
        "app.jobs.compute_anchor_score.recompute_anchor_score", fake_recompute,
    )

    result = await refresh_anchor_scores(pool, _session_factory())

    assert result.projects_processed == 2
    assert result.entities_updated == 10
    assert result.projects_failed == 1
    assert result.lock_skipped is False


@pytest.mark.asyncio
async def test_no_projects_returns_zero(monkeypatch):
    conn = _conn_returning([])
    pool = _pool_with_conn(conn)

    async def fake_recompute(*a, **kw):
        raise AssertionError("must not be called when no projects exist")

    monkeypatch.setattr(
        "app.jobs.compute_anchor_score.recompute_anchor_score", fake_recompute,
    )

    result = await refresh_anchor_scores(pool, _session_factory())

    assert result == RefreshResult(0, 0, 0, lock_skipped=False)


@pytest.mark.asyncio
async def test_query_filters_archived_and_extraction_disabled(monkeypatch):
    conn = _conn_returning([])
    pool = _pool_with_conn(conn)

    async def fake_recompute(*a, **kw):
        return (0, 0)

    monkeypatch.setattr(
        "app.jobs.compute_anchor_score.recompute_anchor_score", fake_recompute,
    )

    await refresh_anchor_scores(pool, _session_factory())

    sql = conn.fetch.call_args.args[0]
    assert "is_archived = false" in sql
    assert "extraction_enabled = true" in sql


@pytest.mark.asyncio
async def test_skips_when_advisory_lock_not_acquired(monkeypatch):
    """Second concurrent caller sees pg_try_advisory_lock → false and bails."""
    conn = _conn_returning([], lock_acquired=False)
    pool = _pool_with_conn(conn)

    async def fake_recompute(*a, **kw):
        raise AssertionError("must not run when lock is contended")

    monkeypatch.setattr(
        "app.jobs.compute_anchor_score.recompute_anchor_score", fake_recompute,
    )

    result = await refresh_anchor_scores(pool, _session_factory())

    assert result == RefreshResult(0, 0, 0, lock_skipped=True)
    # fetch must not have been called — we bail before reading rows.
    conn.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_advisory_lock_released_even_on_error(monkeypatch):
    """If rows() raises, pg_advisory_unlock must still fire (finally)."""
    conn = _conn_returning([])
    # Make fetch raise to trigger the error path.
    conn.fetch = AsyncMock(side_effect=RuntimeError("pool exploded"))
    pool = _pool_with_conn(conn)

    async def fake_recompute(*a, **kw):
        return (0, 0)

    monkeypatch.setattr(
        "app.jobs.compute_anchor_score.recompute_anchor_score", fake_recompute,
    )

    with pytest.raises(RuntimeError, match="pool exploded"):
        await refresh_anchor_scores(pool, _session_factory())

    # Unlock must have been invoked despite the exception.
    unlock_calls = [
        c for c in conn.fetchval.call_args_list
        if "pg_advisory_unlock" in c.args[0]
    ]
    assert len(unlock_calls) == 1
