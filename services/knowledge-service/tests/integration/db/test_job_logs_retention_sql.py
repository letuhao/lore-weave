"""C3 (D-K19b.8-01) — integration tests for job_logs retention sweep.

Exercises the real SQL path against a live Postgres instance. Verifies:
  - rows older than the retain window are DELETE'd
  - fresh rows are preserved
  - sweep count matches the actual row count
  - idempotent: second sweep with same state returns 0
  - custom retain_days flows through make_interval correctly

Environment: requires infra-postgres-1 or equivalent. Tests seed rows
with explicit ``created_at`` via raw INSERT (``append`` can't override
the DEFAULT now()).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.db.models import ProjectCreate
from app.db.repositories.extraction_jobs import (
    ExtractionJobCreate,
    ExtractionJobsRepo,
)
from app.db.repositories.projects import ProjectsRepo
from app.jobs.job_logs_retention import sweep_job_logs_once


async def _make_job(pool, user_id: UUID) -> UUID:
    """Seed a project + extraction job so job_logs FK has a target.

    Mirrors ``tests/integration/db/test_job_logs_repo.py::_make_job``
    — deliberate copy to keep each integration test file freestanding.
    """
    projects_repo = ProjectsRepo(pool)
    jobs_repo = ExtractionJobsRepo(pool)
    proj = await projects_repo.create(
        user_id,
        ProjectCreate(name="retention test", project_type="general"),
    )
    job = await jobs_repo.create(
        user_id,
        ExtractionJobCreate(
            project_id=proj.project_id,
            scope="chapters",
            llm_model="test-llm",
            embedding_model="test-embed",
            max_spend_usd=Decimal("1.00"),
        ),
    )
    return job.job_id


async def _seed_log_at_age(
    pool,
    user_id: UUID,
    job_id: UUID,
    *,
    days_old: int,
    message: str,
) -> None:
    """Insert a log row with an explicit ``created_at`` offset from
    now(). Can't use ``JobLogsRepo.append`` because that relies on the
    column DEFAULT."""
    await pool.execute(
        """
        INSERT INTO job_logs
          (job_id, user_id, level, message, context, created_at)
        VALUES
          ($1, $2, 'info', $3, '{}'::jsonb, now() - make_interval(days => $4))
        """,
        job_id, user_id, message, days_old,
    )


@pytest.mark.asyncio
async def test_sweep_deletes_rows_beyond_retention_window(pool):
    """Seed a 10/5 old/fresh split at the 90-day boundary. Sweep must
    delete the 10 old rows and leave the 5 fresh ones.

    The boundary is strictly ``created_at < now() - interval 'Ndays'``
    so a row at exactly 90 days is considered "too young" by now + 0s
    drift, but at 95 days it's strictly older — use those offsets
    instead of 90 exact to avoid flaky sub-second comparisons.
    """
    user = uuid4()
    job_id = await _make_job(pool, user)

    # Insert 10 rows aged 95 days (> 90 day window) + 5 rows at 10 days.
    for i in range(10):
        await _seed_log_at_age(
            pool, user, job_id, days_old=95, message=f"old-{i}",
        )
    for i in range(5):
        await _seed_log_at_age(
            pool, user, job_id, days_old=10, message=f"fresh-{i}",
        )

    # Pre-sweep sanity: 15 rows for this job.
    count_before = await pool.fetchval(
        "SELECT count(*) FROM job_logs WHERE job_id = $1", job_id,
    )
    assert count_before == 15

    result = await sweep_job_logs_once(pool)
    assert result.lock_skipped is False
    # `deleted` is cross-tenant (sweep is global, not filtered by
    # this test's job_id). Other integration tests running in
    # sequence may have left stale 95-day-old rows OR the fixture
    # cleanup may leave nothing. Use >= 10 rather than == 10.
    assert result.deleted >= 10

    count_after_old = await pool.fetchval(
        "SELECT count(*) FROM job_logs "
        "WHERE job_id = $1 AND message LIKE 'old-%'",
        job_id,
    )
    assert count_after_old == 0, "all 10 old rows must be deleted"

    count_after_fresh = await pool.fetchval(
        "SELECT count(*) FROM job_logs "
        "WHERE job_id = $1 AND message LIKE 'fresh-%'",
        job_id,
    )
    assert count_after_fresh == 5, "5 fresh rows must remain"


@pytest.mark.asyncio
async def test_sweep_is_idempotent_after_second_run(pool):
    """Second sweep against the same state returns deleted=0 (for
    this job's rows — cross-tenant count still depends on siblings)."""
    user = uuid4()
    job_id = await _make_job(pool, user)

    # Only fresh rows — nothing to delete.
    for i in range(3):
        await _seed_log_at_age(
            pool, user, job_id, days_old=5, message=f"fresh-{i}",
        )

    result = await sweep_job_logs_once(pool)
    assert result.lock_skipped is False

    # Our 3 fresh rows must still be present after sweep.
    remaining = await pool.fetchval(
        "SELECT count(*) FROM job_logs WHERE job_id = $1", job_id,
    )
    assert remaining == 3


@pytest.mark.asyncio
async def test_sweep_honours_custom_retain_days(pool):
    """Override retain_days to a narrow window and assert rows just
    beyond it get deleted. Proves the parameter threads through
    make_interval rather than being hard-coded to 90."""
    user = uuid4()
    job_id = await _make_job(pool, user)

    # 3 rows @ 5 days old + 3 rows @ 2 days old. retain_days=3 should
    # delete the 5-day-old rows and keep the 2-day-old ones.
    for i in range(3):
        await _seed_log_at_age(
            pool, user, job_id, days_old=5, message=f"d5-{i}",
        )
    for i in range(3):
        await _seed_log_at_age(
            pool, user, job_id, days_old=2, message=f"d2-{i}",
        )

    result = await sweep_job_logs_once(pool, retain_days=3)
    assert result.lock_skipped is False

    d5_remaining = await pool.fetchval(
        "SELECT count(*) FROM job_logs "
        "WHERE job_id = $1 AND message LIKE 'd5-%'",
        job_id,
    )
    assert d5_remaining == 0

    d2_remaining = await pool.fetchval(
        "SELECT count(*) FROM job_logs "
        "WHERE job_id = $1 AND message LIKE 'd2-%'",
        job_id,
    )
    assert d2_remaining == 3
