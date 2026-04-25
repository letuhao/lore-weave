"""K16.11 — Unit tests for budget enforcement."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.jobs.budget import (
    can_start_job,
    check_user_monthly_budget,
    record_spending,
)


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


# ── K16.12: check_user_monthly_budget (user-wide aggregate) ──────────


def _mock_user_pool(
    user_budget: Decimal | None,
    project_totals: Decimal,
    summary_totals: Decimal = Decimal("0"),
) -> AsyncMock:
    """Three fetchrow calls in sequence:
      1. user_knowledge_budgets SELECT
      2. SUM-across-projects (knowledge_projects)
      3. SUM-across-summary (knowledge_summary_spending) — C16-BUILD

    Queue responses via ``side_effect`` so they fire in order. The
    third query was added in C16-BUILD when check_user_monthly_budget
    was extended to fold non-project-attributable summary regen spend
    into the user-wide aggregation. Existing tests get summary=0 by
    default, preserving their assertions."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(
        side_effect=[
            {"ai_monthly_budget_usd": user_budget},
            {"total": project_totals},
            {"total": summary_totals},
        ],
    )
    return pool


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_check_user_budget_allowed_when_no_cap(mock_key):
    pool = _mock_user_pool(user_budget=None, project_totals=Decimal("123.45"))
    result = await check_user_monthly_budget(pool, _TEST_USER, Decimal("50"))
    assert result.allowed is True
    assert result.monthly_budget is None
    assert "no user monthly budget" in result.reason


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_check_user_budget_allowed_within_cap(mock_key):
    pool = _mock_user_pool(
        user_budget=Decimal("100"),
        project_totals=Decimal("30"),
    )
    result = await check_user_monthly_budget(pool, _TEST_USER, Decimal("20"))
    assert result.allowed is True
    assert result.monthly_spent == Decimal("30")
    assert result.monthly_budget == Decimal("100")
    assert result.warning is None


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_check_user_budget_blocks_over_cap(mock_key):
    pool = _mock_user_pool(
        user_budget=Decimal("50"),
        project_totals=Decimal("45"),
    )
    result = await check_user_monthly_budget(pool, _TEST_USER, Decimal("10"))
    assert result.allowed is False
    assert "exceed" in result.reason
    assert result.monthly_budget == Decimal("50")


@pytest.mark.asyncio
@patch("app.jobs.budget._current_month_key", return_value="2026-04")
async def test_check_user_budget_warns_at_80_percent(mock_key):
    # 70 spent + 20 estimate = 90 projected; 90/100 = 0.9 >= 0.8.
    pool = _mock_user_pool(
        user_budget=Decimal("100"),
        project_totals=Decimal("70"),
    )
    result = await check_user_monthly_budget(pool, _TEST_USER, Decimal("20"))
    assert result.allowed is True
    assert result.warning is not None
    assert "80%" in result.warning
