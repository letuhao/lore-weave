"""T2-close-1b — integration tests for `BenchmarkRunsRepo` against
live Postgres. Skipped without `TEST_KNOWLEDGE_DB_URL`.
"""
from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.db.repositories.benchmark_runs import BenchmarkRunsRepo


async def _make_project(pool: asyncpg.Pool, user_id: UUID) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO knowledge_projects (user_id, name, project_type)
            VALUES ($1, $2, 'general')
            RETURNING project_id
            """,
            user_id, f"bm-test-{uuid4().hex[:6]}",
        )
    return row["project_id"]


async def _insert_run(
    pool: asyncpg.Pool,
    project_id: UUID,
    *,
    embedding_model: str = "bge-m3",
    run_id: str = "test-run",
    passed: bool = True,
    recall: float = 0.85,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO project_embedding_benchmark_runs (
              project_id, embedding_model, run_id,
              recall_at_3, passed, raw_report
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            """,
            project_id, embedding_model, run_id, recall, passed,
            json.dumps({"runs": 3}),
        )


@pytest.mark.asyncio
async def test_get_latest_returns_most_recent_row(pool):
    user_id = uuid4()
    project_id = await _make_project(pool, user_id)
    # Two runs — the second should win.
    await _insert_run(pool, project_id, run_id="run-old", recall=0.70)
    # Sleep 10 ms so created_at differs reliably; Postgres default
    # now() has µs precision so this is more than enough.
    await asyncio.sleep(0.01)
    await _insert_run(pool, project_id, run_id="run-new", recall=0.95)

    repo = BenchmarkRunsRepo(pool)
    latest = await repo.get_latest(user_id, project_id, "bge-m3")

    assert latest is not None
    assert latest.run_id == "run-new"
    assert latest.recall_at_3 == pytest.approx(0.95)
    assert latest.raw_report["runs"] == 3


@pytest.mark.asyncio
async def test_get_latest_filters_by_embedding_model(pool):
    user_id = uuid4()
    project_id = await _make_project(pool, user_id)
    await _insert_run(pool, project_id, embedding_model="bge-m3", run_id="bge-run")
    await _insert_run(pool, project_id, embedding_model="text-embedding-3-small", run_id="openai-run")

    repo = BenchmarkRunsRepo(pool)
    bge_latest = await repo.get_latest(user_id, project_id, "bge-m3")
    openai_latest = await repo.get_latest(user_id, project_id, "text-embedding-3-small")

    assert bge_latest is not None and bge_latest.run_id == "bge-run"
    assert openai_latest is not None and openai_latest.run_id == "openai-run"


@pytest.mark.asyncio
async def test_get_latest_without_model_returns_any_latest(pool):
    user_id = uuid4()
    project_id = await _make_project(pool, user_id)
    await _insert_run(pool, project_id, embedding_model="bge-m3", run_id="first")
    await asyncio.sleep(0.01)
    await _insert_run(
        pool, project_id, embedding_model="text-embedding-3-small",
        run_id="second",
    )

    repo = BenchmarkRunsRepo(pool)
    latest = await repo.get_latest(user_id, project_id, embedding_model=None)
    assert latest is not None
    # Cross-model, most recent wins regardless of model.
    assert latest.run_id == "second"


@pytest.mark.asyncio
async def test_get_latest_cross_user_isolation(pool):
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)
    await _insert_run(pool, project_a, run_id="user-a-run")

    repo = BenchmarkRunsRepo(pool)
    # User A sees their own run.
    found = await repo.get_latest(user_a, project_a, "bge-m3")
    assert found is not None
    # User B asking for user A's project → None (no existence-leak).
    not_found = await repo.get_latest(user_b, project_a, "bge-m3")
    assert not_found is None


@pytest.mark.asyncio
async def test_get_latest_returns_none_when_no_runs(pool):
    user_id = uuid4()
    project_id = await _make_project(pool, user_id)

    repo = BenchmarkRunsRepo(pool)
    assert await repo.get_latest(user_id, project_id, "bge-m3") is None
    assert await repo.get_latest(user_id, project_id) is None  # no model filter too
