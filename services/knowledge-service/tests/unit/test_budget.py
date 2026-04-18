"""K16.11 — Unit tests for budget enforcement."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.jobs.budget import can_start_job, record_spending


_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()


def _mock_pool(budget=Decimal("10"), spent=Decimal("3"), month_key="2026-04"):
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "monthly_budget_usd": budget,
        "current_month_spent_usd": spent,
        "current_month_key": month_key,
    })
    pool.execute = AsyncMock()
    return pool


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_can_start_within_budget(mock_key):
    pool = _mock_pool(budget=Decimal("10"), spent=Decimal("3"))
    result = await can_start_job(pool, _TEST_USER, _TEST_PROJECT, Decimal("2"))
    assert result.allowed is True
    assert result.warning is None


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_can_start_exceeds_budget(mock_key):
    pool = _mock_pool(budget=Decimal("10"), spent=Decimal("9"))
    result = await can_start_job(pool, _TEST_USER, _TEST_PROJECT, Decimal("3"))
    assert result.allowed is False
    assert "exceed" in result.reason


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_can_start_no_budget_unlimited(mock_key):
    pool = _mock_pool(budget=None, spent=Decimal("100"))
    result = await can_start_job(pool, _TEST_USER, _TEST_PROJECT, Decimal("50"))
    assert result.allowed is True


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_can_start_warning_at_80_percent(mock_key):
    pool = _mock_pool(budget=Decimal("10"), spent=Decimal("7"))
    result = await can_start_job(pool, _TEST_USER, _TEST_PROJECT, Decimal("2"))
    assert result.allowed is True
    assert result.warning is not None
    assert "80%" in result.warning


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-05")
async def test_month_rollover_resets_counter(mock_key):
    pool = _mock_pool(budget=Decimal("10"), spent=Decimal("9"), month_key="2026-04")
    result = await can_start_job(pool, _TEST_USER, _TEST_PROJECT, Decimal("5"))
    # After rollover, spent resets to 0, so $5 is within $10 budget
    assert result.allowed is True
    # Should have called execute to reset the counter
    pool.execute.assert_called_once()


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_project_not_found(mock_key):
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    result = await can_start_job(pool, _TEST_USER, _TEST_PROJECT, Decimal("1"))
    assert result.allowed is False


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_record_spending(mock_key):
    pool = AsyncMock()
    pool.execute = AsyncMock()
    await record_spending(pool, _TEST_USER, _TEST_PROJECT, Decimal("1.50"))
    pool.execute.assert_called_once()
