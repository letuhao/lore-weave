"""K16.14 — Unit tests for stats cache updater."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.jobs.stats_updater import increment_stats, reconcile_project_stats

_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()


@pytest.mark.asyncio
async def test_increment_stats():
    pool = AsyncMock()
    pool.execute = AsyncMock()

    await increment_stats(
        pool, _TEST_USER, _TEST_PROJECT,
        entities=5, facts=3, events=2,
    )

    pool.execute.assert_called_once()
    call_args = pool.execute.call_args
    assert _TEST_USER in call_args.args
    assert _TEST_PROJECT in call_args.args


@pytest.mark.asyncio
async def test_reconcile_project_stats():
    pool = AsyncMock()
    pool.execute = AsyncMock()

    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"c": 10})
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)

    counts = await reconcile_project_stats(
        pool, mock_session, _TEST_USER, _TEST_PROJECT,
    )

    assert counts["stat_entity_count"] == 10
    assert counts["stat_fact_count"] == 10
    assert counts["stat_event_count"] == 10
    # 3 Neo4j queries (Entity, Fact, Event) + 1 Postgres update
    assert mock_session.run.call_count == 3
    pool.execute.assert_called_once()
