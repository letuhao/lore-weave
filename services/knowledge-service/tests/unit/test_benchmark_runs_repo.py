"""T2-close-1b — unit tests for `BenchmarkRunsRepo`."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.repositories.benchmark_runs import BenchmarkRun, BenchmarkRunsRepo


def _fake_row(**overrides):
    now = datetime.now(timezone.utc)
    defaults = {
        "benchmark_run_id": uuid4(),
        "project_id": uuid4(),
        "embedding_provider_id": None,
        "embedding_model": "bge-m3",
        "run_id": "run-1",
        "recall_at_3": 0.85,
        "mrr": 0.72,
        "avg_score_positive": 0.70,
        "stddev": 0.03,
        "negative_control_pass": True,
        "passed": True,
        "raw_report": {"runs": 3},
        "created_at": now,
    }
    defaults.update(overrides)
    return defaults


def _pool(conn):
    pool = AsyncMock()

    @asynccontextmanager
    async def fake_acquire():
        yield conn
    pool.acquire = fake_acquire
    return pool


@pytest.mark.asyncio
async def test_get_latest_with_model_uses_three_way_filter():
    """User + project + model filters all present in the SQL."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_fake_row())
    repo = BenchmarkRunsRepo(_pool(conn))

    user_id = uuid4()
    project_id = uuid4()
    result = await repo.get_latest(user_id, project_id, embedding_model="bge-m3")

    assert isinstance(result, BenchmarkRun)
    sql = conn.fetchrow.await_args.args[0]
    # The three-column WHERE is the distinguishing shape — a regression
    # that dropped the embedding_model filter would leak results from
    # a different model into the gate check.
    assert "b.project_id = $1" in sql
    assert "p.user_id = $2" in sql
    assert "b.embedding_model = $3" in sql
    assert "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_get_latest_without_model_omits_model_filter():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_fake_row())
    repo = BenchmarkRunsRepo(_pool(conn))

    await repo.get_latest(uuid4(), uuid4(), embedding_model=None)

    sql = conn.fetchrow.await_args.args[0]
    assert "embedding_model" not in sql


@pytest.mark.asyncio
async def test_get_latest_returns_none_when_empty():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    repo = BenchmarkRunsRepo(_pool(conn))

    result = await repo.get_latest(uuid4(), uuid4(), "bge-m3")
    assert result is None


@pytest.mark.asyncio
async def test_get_latest_parses_raw_report_json_string():
    """asyncpg returns JSONB as str when no codec is registered —
    the repo must json.loads it back into a dict."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_fake_row(
        raw_report=json.dumps({"recall_at_3": 0.85, "runs": 3}),
    ))
    repo = BenchmarkRunsRepo(_pool(conn))

    result = await repo.get_latest(uuid4(), uuid4())
    assert isinstance(result.raw_report, dict)
    assert result.raw_report["runs"] == 3


@pytest.mark.asyncio
async def test_get_latest_tolerates_null_raw_report():
    """Legacy rows with NULL raw_report shouldn't crash — return {}."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_fake_row(raw_report=None))
    repo = BenchmarkRunsRepo(_pool(conn))

    result = await repo.get_latest(uuid4(), uuid4())
    assert result.raw_report == {}
