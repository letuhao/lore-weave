"""K16.12 — integration tests for UserBudgetsRepo."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.repositories.user_budgets import UserBudgetsRepo


@pytest.mark.asyncio
async def test_get_returns_none_when_no_row(pool):
    repo = UserBudgetsRepo(pool)
    assert await repo.get(uuid4()) is None


@pytest.mark.asyncio
async def test_upsert_inserts_new_row(pool):
    repo = UserBudgetsRepo(pool)
    user = uuid4()
    await repo.upsert(user, Decimal("25.50"))
    assert await repo.get(user) == Decimal("25.5000")


@pytest.mark.asyncio
async def test_upsert_updates_existing_row_without_pk_conflict(pool):
    """Second upsert hits ON CONFLICT DO UPDATE path, not a PK violation."""
    repo = UserBudgetsRepo(pool)
    user = uuid4()
    await repo.upsert(user, Decimal("10"))
    await repo.upsert(user, Decimal("99.9999"))
    assert await repo.get(user) == Decimal("99.9999")

    # Only one row for this user.
    count = await pool.fetchval(
        "SELECT count(*) FROM user_knowledge_budgets WHERE user_id = $1",
        user,
    )
    assert count == 1


@pytest.mark.asyncio
async def test_upsert_with_none_clears_cap_but_row_persists(pool):
    """Passing None writes NULL to the column; the row stays for
    audit trails (updated_at still bumped). Reads return None."""
    repo = UserBudgetsRepo(pool)
    user = uuid4()
    await repo.upsert(user, Decimal("50"))
    await repo.upsert(user, None)
    assert await repo.get(user) is None
    count = await pool.fetchval(
        "SELECT count(*) FROM user_knowledge_budgets WHERE user_id = $1",
        user,
    )
    assert count == 1


@pytest.mark.asyncio
async def test_user_isolation(pool):
    """User A's cap must not leak into user B's read."""
    repo = UserBudgetsRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    await repo.upsert(user_a, Decimal("100"))
    await repo.upsert(user_b, Decimal("5"))
    assert await repo.get(user_a) == Decimal("100.0000")
    assert await repo.get(user_b) == Decimal("5.0000")
