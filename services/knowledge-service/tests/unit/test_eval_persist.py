"""K17.9 — unit tests for `eval.persist.persist_benchmark_report`."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from eval.persist import persist_benchmark_report
from eval.run_benchmark import BenchmarkReport


def _report(
    *, recall_at_3: float = 0.85, mrr: float = 0.72,
    avg_pos: float = 0.70, neg_max: float = 0.30,
    stddev_recall: float = 0.02, stddev_mrr: float = 0.03,
) -> BenchmarkReport:
    return BenchmarkReport(
        recall_at_3=recall_at_3,
        mrr=mrr,
        avg_score_positive=avg_pos,
        negative_control_max_score=neg_max,
        stddev_recall=stddev_recall,
        stddev_mrr=stddev_mrr,
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


def _fake_pool(conn):
    pool = AsyncMock()

    @asynccontextmanager
    async def fake_acquire():
        yield conn

    pool.acquire = fake_acquire
    return pool


@pytest.mark.asyncio
async def test_persist_writes_passing_row():
    new_id = uuid4()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"benchmark_run_id": new_id})
    pool = _fake_pool(conn)

    project_id = uuid4()
    returned_id = await persist_benchmark_report(
        pool,
        project_id=project_id,
        embedding_provider_id=None,
        embedding_model="bge-m3",
        run_id="benchmark-2026-04-19",
        report=_report(),
    )

    assert returned_id == new_id
    # INSERT SQL + bound params.
    call = conn.fetchrow.await_args
    sql = call.args[0]
    assert "INSERT INTO project_embedding_benchmark_runs" in sql
    assert "RETURNING benchmark_run_id" in sql
    # The 10 param positions in order: project_id, provider_id, model,
    # run_id, recall, mrr, avg_pos, stddev (max of recall/mrr), neg_pass, passed.
    params = call.args[1:]
    assert params[0] == project_id
    assert params[1] is None  # provider_id
    assert params[2] == "bge-m3"
    assert params[3] == "benchmark-2026-04-19"
    assert params[4] == 0.85  # recall_at_3
    assert params[5] == 0.72  # mrr
    assert params[6] == 0.70  # avg_score_positive
    # stddev column = max(stddev_recall, stddev_mrr)
    assert params[7] == pytest.approx(0.03)
    assert params[8] is True   # negative_control_pass: 0.30 <= 0.50
    assert params[9] is True   # passed (all thresholds met)
    # raw_report is JSON string.
    parsed = json.loads(params[10])
    assert parsed["recall_at_3"] == 0.85


@pytest.mark.asyncio
async def test_persist_marks_failed_when_threshold_violated():
    """Report with recall_at_3=0.10 fails the 0.75 threshold —
    `passed` must be False even though we're still writing the row
    (keeping the evidence for the FE / reviewer)."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"benchmark_run_id": uuid4()})
    pool = _fake_pool(conn)

    failing = _report(recall_at_3=0.10)
    await persist_benchmark_report(
        pool,
        project_id=uuid4(),
        embedding_provider_id=None,
        embedding_model="bge-m3",
        run_id="run-x",
        report=failing,
    )

    # args[0] is the SQL string, so param $N lives at args[N].
    assert conn.fetchrow.await_args.args[11] is not None  # raw_report written
    assert conn.fetchrow.await_args.args[10] is False    # passed=False


@pytest.mark.asyncio
async def test_persist_marks_negative_control_fail():
    """Negative control exceeded threshold — `negative_control_pass`
    bit goes False, and since one of the gates now fails, `passed`
    also goes False."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"benchmark_run_id": uuid4()})
    pool = _fake_pool(conn)

    noisy = _report(neg_max=0.92)
    await persist_benchmark_report(
        pool,
        project_id=uuid4(),
        embedding_provider_id=None,
        embedding_model="bge-m3",
        run_id="run-y",
        report=noisy,
    )

    # args[0] is the SQL string, so param $N lives at args[N].
    assert conn.fetchrow.await_args.args[9] is False   # negative_control_pass
    assert conn.fetchrow.await_args.args[10] is False  # passed


@pytest.mark.asyncio
async def test_persist_includes_provider_id_when_set():
    provider_id = uuid4()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"benchmark_run_id": uuid4()})
    pool = _fake_pool(conn)

    await persist_benchmark_report(
        pool,
        project_id=uuid4(),
        embedding_provider_id=provider_id,
        embedding_model="bge-m3",
        run_id="run-z",
        report=_report(),
    )

    assert conn.fetchrow.await_args.args[2] == provider_id
