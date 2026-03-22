"""
Unit tests for _recover_stale_chapters — Plan L2 fix.

Worker startup scans for chapter_translations stuck in 'running' for > 2 hours
(crash-after-ack window) and marks them failed, increments job counters,
and attempts job finalization.
"""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

import sys
import os

# worker.py is at the service root, not inside a package — add it to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import FakeRecord


JOB_A = uuid4()
JOB_B = uuid4()


# ── No stale chapters ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_no_op_when_nothing_stale():
    """When fetch returns empty, no execute calls must be made."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()

    from worker import _recover_stale_chapters
    await _recover_stale_chapters(pool)

    pool.execute.assert_not_called()


# ── Single job ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_increments_failed_chapters_counter():
    """failed_chapters on the parent job must be incremented by the count of stale chapters."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[
        FakeRecord({"job_id": JOB_A}),
        FakeRecord({"job_id": JOB_A}),  # 2 stale chapters for same job
    ])
    pool.execute = AsyncMock()

    from worker import _recover_stale_chapters
    await _recover_stale_chapters(pool)

    # First execute call should increment failed_chapters by 2
    first_sql, first_count, first_job = (
        pool.execute.call_args_list[0].args[0],
        pool.execute.call_args_list[0].args[1],
        pool.execute.call_args_list[0].args[2],
    )
    assert "failed_chapters" in first_sql
    assert first_count == 2
    assert first_job == JOB_A


@pytest.mark.asyncio
async def test_recovery_attempts_finalization_after_counter_update():
    """After incrementing counter, a finalization UPDATE must be attempted."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[FakeRecord({"job_id": JOB_A})])
    pool.execute = AsyncMock()

    from worker import _recover_stale_chapters
    await _recover_stale_chapters(pool)

    sqls = [c.args[0] for c in pool.execute.call_args_list]
    assert any("finished_at" in sql for sql in sqls), "Finalization UPDATE not found"
    assert any("total_chapters" in sql for sql in sqls)


@pytest.mark.asyncio
async def test_recovery_makes_two_execute_calls_per_job():
    """Each affected job needs exactly 2 execute calls: counter + finalization."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[FakeRecord({"job_id": JOB_A})])
    pool.execute = AsyncMock()

    from worker import _recover_stale_chapters
    await _recover_stale_chapters(pool)

    assert pool.execute.call_count == 2


# ── Multiple jobs ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_handles_two_distinct_jobs():
    """Two distinct jobs each get their own counter increment and finalization."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[
        FakeRecord({"job_id": JOB_A}),
        FakeRecord({"job_id": JOB_B}),
    ])
    pool.execute = AsyncMock()

    from worker import _recover_stale_chapters
    await _recover_stale_chapters(pool)

    # 2 jobs × 2 execute calls each = 4 total
    assert pool.execute.call_count == 4

    all_args = [c.args for c in pool.execute.call_args_list]
    job_ids_seen = {arg for args in all_args for arg in args if arg in (JOB_A, JOB_B)}
    assert JOB_A in job_ids_seen
    assert JOB_B in job_ids_seen


@pytest.mark.asyncio
async def test_recovery_groups_chapters_by_job():
    """3 stale chapters across 2 jobs must produce correct per-job counts."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[
        FakeRecord({"job_id": JOB_A}),
        FakeRecord({"job_id": JOB_A}),   # 2 from JOB_A
        FakeRecord({"job_id": JOB_B}),   # 1 from JOB_B
    ])
    pool.execute = AsyncMock()

    from worker import _recover_stale_chapters
    await _recover_stale_chapters(pool)

    # Collect (count, job_id) from increment calls (every other call)
    # The increment SQL contains "failed_chapters + $1" (3 positional args: sql, count, job_id).
    # The finalization SQL also mentions failed_chapters but only has 2 args (sql, job_id).
    # Distinguish by arg count.
    increment_calls = [
        c for c in pool.execute.call_args_list
        if len(c.args) == 3
    ]
    counts_by_job = {c.args[2]: c.args[1] for c in increment_calls}
    assert counts_by_job[JOB_A] == 2
    assert counts_by_job[JOB_B] == 1
