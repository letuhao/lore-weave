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
from app.projection.store import (
    count_summary,
    get_job,
    list_jobs,
    list_jobs_paged,
    upsert_job_event,
)
from loreweave_jobs import JobEvent, JobStatus

DSN = os.environ.get("JOBS_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="JOBS_TEST_PG_DSN unset")


def _ev(owner, job_id, status, ts, *, kind="extraction", parent=None, service="knowledge",
        model=None, cost_usd=None, tokens_in=None, tokens_out=None, params=None, title=None):
    return JobEvent(
        service=service, job_id=job_id, owner_user_id=owner, kind=kind,
        status=status, parent_job_id=parent, occurred_at=ts.isoformat(),
        model=model, cost_usd=cost_usd, tokens_in=tokens_in, tokens_out=tokens_out,
        params=params, title=title,
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
async def test_p4_usage_coalesce_merge(pool, owner):
    """P4: latest non-null wins. A later event that OMITS cost/tokens must keep the
    accumulated values (COALESCE), and a later event with a new cost overwrites."""
    jid = str(uuid.uuid4())
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, t0,
                                     model="qwen2.5-7b", cost_usd=1.0, tokens_in=100, tokens_out=20))
    # a later running WITHOUT usage fields must not wipe them
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, t0 + timedelta(minutes=1)))
    job = await get_job(pool, owner, "knowledge", jid)
    assert job["cost_usd"] == 1.0 and job["tokens_in"] == 100
    assert job["model"] == "qwen2.5-7b"
    # a later running WITH a new cumulative cost overwrites; tokens_in untouched (kept)
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, t0 + timedelta(minutes=2),
                                     cost_usd=2.5, tokens_out=80))
    job = await get_job(pool, owner, "knowledge", jid)
    assert job["cost_usd"] == 2.5            # overwritten
    assert job["tokens_in"] == 100           # kept (never re-sent)
    assert job["tokens_out"] == 80           # overwritten


@pytest.mark.asyncio
async def test_p4_params_jsonb_roundtrip(pool, owner):
    jid = str(uuid.uuid4())
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, t0,
                                     params={"concurrency": 4, "scope": "ch 1-4000"}))
    job = await get_job(pool, owner, "knowledge", jid)
    assert job["params"] == {"concurrency": 4, "scope": "ch 1-4000"}


@pytest.mark.asyncio
async def test_paged_history_offset_total_and_created_order(pool, owner):
    """History mode: offset+total, ORDER BY created_at DESC (stable)."""
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, jid in enumerate(ids):
        await upsert_job_event(pool, _ev(owner, jid, JobStatus.COMPLETED, t0 + timedelta(minutes=i)))
    page1, total = await list_jobs_paged(pool, owner, bucket="history", offset=0, limit=2)
    assert total == 3 and len(page1) == 2
    # newest-created first
    assert [r["job_id"] for r in page1] == [ids[2], ids[1]]
    page2, total2 = await list_jobs_paged(pool, owner, bucket="history", offset=2, limit=2)
    assert total2 == 3 and [r["job_id"] for r in page2] == [ids[0]]


@pytest.mark.asyncio
async def test_bucket_active_excludes_terminal(pool, owner):
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    running = str(uuid.uuid4())
    done = str(uuid.uuid4())
    await upsert_job_event(pool, _ev(owner, running, JobStatus.RUNNING, t0))
    await upsert_job_event(pool, _ev(owner, done, JobStatus.COMPLETED, t0))
    active, _ = await list_jobs(pool, owner, bucket="active", limit=50)
    assert [r["job_id"] for r in active] == [running]
    hist, total = await list_jobs_paged(pool, owner, bucket="history", offset=0, limit=50)
    assert [r["job_id"] for r in hist] == [done] and total == 1


@pytest.mark.asyncio
async def test_widened_search_matches_model_and_kind(pool, owner):
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    jid = str(uuid.uuid4())
    await upsert_job_event(pool, _ev(owner, jid, JobStatus.RUNNING, t0,
                                     kind="translation", service="translation",
                                     model="gemini-2.0", title="vi translate"))
    # match by model (not in the title)
    by_model, _ = await list_jobs(pool, owner, q="gemini", limit=50)
    assert [r["job_id"] for r in by_model] == [jid]
    # match by kind
    by_kind, _ = await list_jobs(pool, owner, q="translat", limit=50)
    assert jid in [r["job_id"] for r in by_kind]
    # match by job_id fragment
    by_id, _ = await list_jobs(pool, owner, q=jid[:8], limit=50)
    assert [r["job_id"] for r in by_id] == [jid]


@pytest.mark.asyncio
async def test_count_summary_buckets_top_level_only(pool, owner):
    t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    parent = str(uuid.uuid4())
    await upsert_job_event(pool, _ev(owner, parent, JobStatus.RUNNING, t0, kind="campaign"))
    await upsert_job_event(pool, _ev(owner, str(uuid.uuid4()), JobStatus.RUNNING, t0, parent=parent))  # child — excluded
    await upsert_job_event(pool, _ev(owner, str(uuid.uuid4()), JobStatus.COMPLETED, t0))
    await upsert_job_event(pool, _ev(owner, str(uuid.uuid4()), JobStatus.FAILED, t0))
    await upsert_job_event(pool, _ev(owner, str(uuid.uuid4()), JobStatus.CANCELLED, t0))
    s = await count_summary(pool, owner)
    assert s == {"active": 1, "completed": 1, "failed": 1, "cancelled": 1}  # child not counted


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
