"""K17.9 — integration test for `eval.persist` against live Postgres."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from eval.persist import persist_benchmark_report
from eval.run_benchmark import BenchmarkReport


def _report(passed: bool = True) -> BenchmarkReport:
    recall = 0.85 if passed else 0.10
    return BenchmarkReport(
        recall_at_3=recall,
        mrr=0.72,
        avg_score_positive=0.70,
        negative_control_max_score=0.30,
        stddev_recall=0.02,
        stddev_mrr=0.03,
        runs=3,
        thresholds={
            "recall_at_3": 0.75,
            "mrr": 0.65,
            "avg_score_positive": 0.60,
            "negative_control_max_score": 0.50,
            "max_stddev": 0.05,
            "min_runs": 3,
        },
    )


async def _make_project(conn) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO knowledge_projects (user_id, name, project_type)
        VALUES (gen_random_uuid(), 'k17.9-persist-test', 'general')
        RETURNING project_id
        """
    )
    return str(row["project_id"])


@pytest.mark.asyncio
async def test_persist_writes_row_and_returns_id(pool):
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)

    new_id = await persist_benchmark_report(
        pool,
        project_id=UUID(project_id),
        embedding_provider_id=None,
        embedding_model="bge-m3",
        run_id="integration-test-run",
        report=_report(passed=True),
    )
    assert isinstance(new_id, UUID)

    # Row actually landed with the right fields.
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT project_id, embedding_model, run_id, recall_at_3, mrr,
                   avg_score_positive, stddev, negative_control_pass, passed,
                   raw_report
            FROM project_embedding_benchmark_runs
            WHERE benchmark_run_id = $1
            """,
            new_id,
        )
    assert str(row["project_id"]) == project_id
    assert row["embedding_model"] == "bge-m3"
    assert row["run_id"] == "integration-test-run"
    assert row["recall_at_3"] == pytest.approx(0.85)
    assert row["passed"] is True
    assert row["negative_control_pass"] is True
    assert row["raw_report"] is not None


@pytest.mark.asyncio
async def test_persist_marks_failed_when_thresholds_violated(pool):
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)

    await persist_benchmark_report(
        pool,
        project_id=UUID(project_id),
        embedding_provider_id=None,
        embedding_model="bge-m3",
        run_id="fail-run",
        report=_report(passed=False),
    )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT passed FROM project_embedding_benchmark_runs
            WHERE project_id = $1 AND run_id = 'fail-run'
            """,
            UUID(project_id),
        )
    assert row["passed"] is False


@pytest.mark.asyncio
async def test_persist_second_run_with_same_id_raises_unique(pool):
    """UNIQUE (project_id, embedding_model, run_id) rejects replays —
    the CLI defaults run_id to a timestamp so operators don't hit this
    by accident."""
    import asyncpg
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)

    await persist_benchmark_report(
        pool,
        project_id=UUID(project_id),
        embedding_provider_id=None,
        embedding_model="bge-m3",
        run_id="duplicate-run",
        report=_report(),
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await persist_benchmark_report(
            pool,
            project_id=UUID(project_id),
            embedding_provider_id=None,
            embedding_model="bge-m3",
            run_id="duplicate-run",
            report=_report(),
        )
