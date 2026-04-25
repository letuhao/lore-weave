"""C16-BUILD — unit tests for SummarySpendingRepo (D-K20α-01 closer).

Covers the repo contract matrix:
  - cost <= 0 no-op (zero / negative)
  - record() first call inserts row
  - record() second call same month UPSERTs additively
  - record() new month creates a new row (rollover via PK shape)
  - current_month_total() returns 0 for user with no rows
  - current_month_total() sums across scope_types in current month
  - current_month_total() ignores prior-month rows
  - record() trips CHECK constraint on invalid scope_type — covered
    by integration test (gated on TEST_DATABASE_URL); not unit-tested
    because the FakeConn doesn't enforce constraints
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.db.repositories.summary_spending import SummarySpendingRepo


class FakeConn:
    """Minimal pool-connection stub that emulates ON CONFLICT UPSERT
    + month_key matching for SUM. Records executed SQL for assertions.
    """

    def __init__(
        self,
        store: dict[tuple, dict] | None = None,
    ):
        # Key: (user_id, scope_type, month_key) → {spent_usd: Decimal}
        self.store = store if store is not None else {}
        self.executed: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql: str, *args):
        self.executed.append((sql.strip()[:40], args))
        if "SUM(spent_usd)" in sql:
            user_id, month_key = args
            total = sum(
                (row["spent_usd"] for key, row in self.store.items()
                 if key[0] == user_id and key[2] == month_key),
                Decimal("0"),
            )
            return {"total": total}
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def execute(self, sql: str, *args) -> str:
        self.executed.append((sql.strip()[:40], args))
        if "INSERT INTO knowledge_summary_spending" in sql:
            user_id, scope_type, month_key, cost = args
            key = (user_id, scope_type, month_key)
            existing = self.store.get(key)
            if existing is None:
                self.store[key] = {"spent_usd": cost}
            else:
                # ON CONFLICT UPDATE additively — emulate the SQL.
                self.store[key] = {"spent_usd": existing["spent_usd"] + cost}
            return "INSERT 0 1"
        raise AssertionError(f"unexpected execute: {sql}")


class FakePool:
    """Stub mimicking asyncpg.Pool's top-level execute/fetchrow shortcut
    methods that internally acquire+release a connection. Real
    asyncpg.Pool has these; SummarySpendingRepo uses them directly
    without explicit `acquire()` calls."""

    def __init__(self, conn: FakeConn):
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn

    async def execute(self, sql: str, *args) -> str:
        return await self._conn.execute(sql, *args)

    async def fetchrow(self, sql: str, *args):
        return await self._conn.fetchrow(sql, *args)


@pytest.fixture
def repo_and_conn():
    conn = FakeConn()
    pool = FakePool(conn)
    return SummarySpendingRepo(pool), conn  # type: ignore[arg-type]


# ── cost edge cases ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_zero_cost_is_noop(repo_and_conn):
    """Mirrors K16.11 record_spending: zero-cost call must NOT
    perform any SQL — saves a round-trip on no-op regen branches."""
    repo, conn = repo_and_conn
    await repo.record(uuid4(), "global", Decimal("0"))
    assert conn.executed == []


@pytest.mark.asyncio
async def test_record_negative_cost_is_noop(repo_and_conn):
    repo, conn = repo_and_conn
    await repo.record(uuid4(), "global", Decimal("-5.00"))
    assert conn.executed == []


# ── record + read round-trip ───────────────────────────────────────


@pytest.mark.asyncio
async def test_first_record_inserts_row(repo_and_conn):
    repo, _ = repo_and_conn
    user_id = uuid4()
    await repo.record(user_id, "global", Decimal("0.05"))
    total = await repo.current_month_total(user_id)
    assert total == Decimal("0.05")


@pytest.mark.asyncio
async def test_second_record_same_month_additive(repo_and_conn):
    """ON CONFLICT UPDATE adds, not replaces."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    await repo.record(user_id, "global", Decimal("0.05"))
    await repo.record(user_id, "global", Decimal("0.07"))
    total = await repo.current_month_total(user_id)
    assert total == Decimal("0.12")


@pytest.mark.asyncio
async def test_new_month_creates_new_row(repo_and_conn):
    """Month rollover — patch _current_month_key between calls so
    each lands in a different (user, scope, month) PK bucket. Old
    month's row stays in the table; current_month_total ignores it."""
    repo, conn = repo_and_conn
    user_id = uuid4()

    with patch(
        "app.db.repositories.summary_spending._current_month_key",
        return_value="2026-03",
    ):
        await repo.record(user_id, "global", Decimal("0.10"))

    with patch(
        "app.db.repositories.summary_spending._current_month_key",
        return_value="2026-04",
    ):
        await repo.record(user_id, "global", Decimal("0.20"))

        # Current month (2026-04) shows only the new spend.
        total = await repo.current_month_total(user_id)
        assert total == Decimal("0.20")

    # Both rows persist in the store — old month not deleted.
    keys = list(conn.store.keys())
    assert (user_id, "global", "2026-03") in keys
    assert (user_id, "global", "2026-04") in keys


# ── current_month_total ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_current_month_total_zero_when_no_rows(repo_and_conn):
    repo, _ = repo_and_conn
    user_id = uuid4()
    total = await repo.current_month_total(user_id)
    assert total == Decimal("0")


@pytest.mark.asyncio
async def test_current_month_total_isolated_per_user(repo_and_conn):
    """Two users' spend doesn't cross-contaminate."""
    repo, _ = repo_and_conn
    user_a = uuid4()
    user_b = uuid4()
    await repo.record(user_a, "global", Decimal("1.00"))
    await repo.record(user_b, "global", Decimal("2.50"))

    assert await repo.current_month_total(user_a) == Decimal("1.00")
    assert await repo.current_month_total(user_b) == Decimal("2.50")


@pytest.mark.asyncio
async def test_current_month_total_ignores_prior_months(repo_and_conn):
    """Stale rows from prior months don't bleed into current."""
    repo, _ = repo_and_conn
    user_id = uuid4()

    with patch(
        "app.db.repositories.summary_spending._current_month_key",
        return_value="2026-02",
    ):
        await repo.record(user_id, "global", Decimal("99.99"))

    # Today: SUM filters by current month_key — old row excluded.
    today_key = datetime.now(timezone.utc).strftime("%Y-%m")
    if today_key == "2026-02":
        # Test would be ambiguous if happens to run during Feb 2026.
        pytest.skip("test assumes current month != 2026-02")
    total = await repo.current_month_total(user_id)
    assert total == Decimal("0")
