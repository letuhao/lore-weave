"""K19b.8 — integration tests for JobLogsRepo."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.db.models import ProjectCreate
from app.db.repositories.extraction_jobs import (
    ExtractionJobCreate,
    ExtractionJobsRepo,
)
from app.db.repositories.job_logs import JobLogsRepo
from app.db.repositories.projects import ProjectsRepo


async def _make_job(pool, user_id: UUID) -> UUID:
    """Seed a project + extraction job so job_logs can point at a real
    parent row (the FK requires it)."""
    projects_repo = ProjectsRepo(pool)
    jobs_repo = ExtractionJobsRepo(pool)
    proj = await projects_repo.create(
        user_id,
        ProjectCreate(name="Log test", project_type="general"),
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


@pytest.mark.asyncio
async def test_append_returns_log_id_and_list_reads_back(pool):
    repo = JobLogsRepo(pool)
    user = uuid4()
    job_id = await _make_job(pool, user)

    log_id = await repo.append(user, job_id, "info", "chapter processed")
    assert isinstance(log_id, int)
    assert log_id > 0

    rows = await repo.list(user, job_id)
    assert len(rows) == 1
    assert rows[0].log_id == log_id
    assert rows[0].level == "info"
    assert rows[0].message == "chapter processed"
    assert rows[0].context == {}


@pytest.mark.asyncio
async def test_append_persists_context_as_jsonb(pool):
    repo = JobLogsRepo(pool)
    user = uuid4()
    job_id = await _make_job(pool, user)

    await repo.append(
        user, job_id, "warning", "retry attempt",
        context={"chapter_id": "abc123", "attempt": 2},
    )
    rows = await repo.list(user, job_id)
    assert rows[0].context == {"chapter_id": "abc123", "attempt": 2}


@pytest.mark.asyncio
async def test_list_cursor_pagination_via_since_log_id(pool):
    repo = JobLogsRepo(pool)
    user = uuid4()
    job_id = await _make_job(pool, user)

    ids: list[int] = []
    for i in range(5):
        ids.append(await repo.append(user, job_id, "info", f"event {i}"))

    # First page: 3 items from start.
    page1 = await repo.list(user, job_id, limit=3)
    assert [r.log_id for r in page1] == ids[:3]

    # Second page: from last log_id of page1.
    page2 = await repo.list(user, job_id, since_log_id=page1[-1].log_id, limit=3)
    assert [r.log_id for r in page2] == ids[3:]


@pytest.mark.asyncio
async def test_list_limit_clamped_to_max(pool):
    from app.db.repositories.job_logs import LOGS_MAX_LIMIT

    repo = JobLogsRepo(pool)
    user = uuid4()
    job_id = await _make_job(pool, user)

    for i in range(3):
        await repo.append(user, job_id, "info", f"event {i}")

    # Huge limit gets clamped; 3 < 200 so we just see all 3.
    rows = await repo.list(user, job_id, limit=LOGS_MAX_LIMIT * 10)
    assert len(rows) == 3

    # Zero clamps up to 1.
    rows_one = await repo.list(user, job_id, limit=0)
    assert len(rows_one) == 1


@pytest.mark.asyncio
async def test_list_user_isolation_and_cascade_delete(pool):
    """Cross-user reads return []. Deleting a job cascades to its logs
    so there's no dangling-log risk."""
    repo = JobLogsRepo(pool)
    jobs_repo = ExtractionJobsRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    job_a = await _make_job(pool, user_a)
    job_b = await _make_job(pool, user_b)

    await repo.append(user_a, job_a, "info", "a-event")
    await repo.append(user_b, job_b, "info", "b-event")

    a_logs = await repo.list(user_a, job_a)
    assert len(a_logs) == 1 and a_logs[0].message == "a-event"

    # User B reading job A → empty (user_id predicate).
    cross = await repo.list(user_b, job_a)
    assert cross == []

    # Cascade: delete user_a's project, job_a → job_logs rows for job_a.
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM knowledge_projects WHERE user_id = $1", user_a,
        )
    a_after = await repo.list(user_a, job_a)
    assert a_after == []
    # User B's logs are untouched.
    b_after = await repo.list(user_b, job_b)
    assert len(b_after) == 1
