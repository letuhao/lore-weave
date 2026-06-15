"""Real-Postgres integration tests for the projection store.

The SQL-level invariants — keyset cursor pagination (the param TYPES, esp. the
::timestamptz cursor bound) and the monotonic ON-CONFLICT upsert — CANNOT be
proven against a mock pool: a spy records whatever you pass, so a str-vs-datetime
or a wrong WHERE never fails. These run against a real DB.

Gated on `JOBS_TEST_PG_DSN` (e.g. postgres://loreweave:loreweave_dev@postgres:5432/
loreweave_jobs); skipped when unset so the default unit run needs no DB. Each test
uses a unique owner UUID + cleans up, so it is safe against a shared dev DB."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

asyncpg = pytest.importorskip("asyncpg")

from app.migrate import run_migrations
from app.projection.store import get_job, list_jobs, upsert_job_event
from loreweave_jobs import JobEvent, JobStatus

DSN = os.environ.get("JOBS_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="JOBS_TEST_PG_DSN unset")


def _ev(owner, job_id, status, ts, *, kind="extraction", parent=None):
    return JobEvent(
        service="knowledge", job_id=job_id, owner_user_id=owner, kind=kind,
        status=status, parent_job_id=parent, occurred_at=ts.isoformat(),
    )


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    await run_migrations(p)
    yield p
    await p.close()


@pytest.fixture
async def owner(pool):
    oid = str(uuid.uuid4())
    yield oid
    await pool.execute("DELETE FROM job_projection WHERE owner_user_id=$1::uuid", oid)


@pytest.mark.asyncio
async def test_cursor_pagination_does_not_crash_and_is_complete(pool, owner):
    """The HIGH the live-smoke missed: a 2nd page binds the cursor ts to a
    ::timestamptz param. A str there raises 'expected datetime'."""
    base = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, jid in enumerate(ids):
        await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, base + timedelta(minutes=i)))

    page1, cur = await list_jobs(pool, owner, limit=2)
    assert len(page1) == 2 and cur is not None
    # 2nd page — this is the line that 500'd before the fix.
    page2, cur2 = await list_jobs(pool, owner, limit=2, cursor=cur)
    assert len(page2) == 1 and cur2 is None
    seen = {r["job_id"] for r in page1 + page2}
    assert seen == set(ids)  # complete, no overlap, no gap


@pytest.mark.asyncio
async def test_monotonic_terminal_wins_over_late_running(pool, owner):
    jid = str(uuid.uuid4())
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, t0))
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.COMPLETED, t0 + timedelta(minutes=1)))
    # a redelivered/older RUNNING must NOT resurrect a COMPLETED job
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, t0 + timedelta(minutes=2)))
    job = await get_job(pool, owner, "knowledge", jid)
    assert job["status"] == "completed"


@pytest.mark.asyncio
async def test_monotonic_forward_only_among_nonterminal(pool, owner):
    jid = str(uuid.uuid4())
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, t0 + timedelta(minutes=5)))
    # an OLDER pending arriving late must not regress a newer running
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.PENDING, t0))
    job = await get_job(pool, owner, "knowledge", jid)
    assert job["status"] == "running"


@pytest.mark.asyncio
async def test_owner_scoping_and_parent_children(pool, owner):
    other = str(uuid.uuid4())
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    parent_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    try:
        await upsert_job_event(pool, _ev(owner, parent_id, JobStatus.RUNNING, t0, kind="campaign"))
        await upsert_job_event(pool, _ev(owner, child_id, JobStatus.RUNNING, t0, parent=parent_id))
        await upsert_job_event(pool, _ev(other, str(uuid.uuid4()), JobStatus.RUNNING, t0))
        # top-level view: only the parent (child has parent_job_id set), only this owner
        top, _ = await list_jobs(pool, owner, limit=50)
        assert [r["job_id"] for r in top] == [parent_id]
        assert top[0]["child_count"] == 1
        # children view
        kids, _ = await list_jobs(pool, owner, parent=parent_id, limit=50)
        assert [r["job_id"] for r in kids] == [child_id]
        # cross-owner detail → None (anti-oracle 404 upstream)
        assert await get_job(pool, owner, "knowledge", child_id) is not None
        assert await get_job(pool, other, "knowledge", child_id) is None
    finally:
        await pool.execute("DELETE FROM job_projection WHERE owner_user_id=$1::uuid", other)
