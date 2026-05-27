"""P2 — unit tests for ExtractionLeavesRepo helpers.

D-P2-STALE-CLAIM-LIFESPAN-HOOK regression-lock tests for
`reset_stale_claims`. The hook in `app/main.py` invokes this on every
service startup so workers that died mid-claim don't leave rows stuck
in `running` indefinitely.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repositories.extraction_leaves import ExtractionLeavesRepo


@pytest.mark.asyncio
async def test_reset_stale_claims_returns_count_from_update_tag():
    """asyncpg's execute() returns 'UPDATE N'; the parser must extract N."""
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="UPDATE 7")
    repo = ExtractionLeavesRepo(pool)
    n = await repo.reset_stale_claims()
    assert n == 7


@pytest.mark.asyncio
async def test_reset_stale_claims_zero_when_no_rows_stale():
    """Healthy state: no rows stuck in 'running' for >30min → returns 0,
    no error. Hook must be safe to run on every startup."""
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="UPDATE 0")
    repo = ExtractionLeavesRepo(pool)
    n = await repo.reset_stale_claims()
    assert n == 0


@pytest.mark.asyncio
async def test_reset_stale_claims_sql_targets_running_status_only():
    """L5 idempotency lock: the WHERE clause MUST filter status='running'
    so concurrent recovery from multiple replicas is safe (a row reset
    to 'pending' by replica A is invisible to replica B's same UPDATE)."""
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="UPDATE 0")
    repo = ExtractionLeavesRepo(pool)
    await repo.reset_stale_claims()
    pool.execute.assert_awaited_once()
    sql = pool.execute.await_args.args[0]
    assert "status = 'running'" in sql, f"sql must filter running: {sql}"
    assert "INTERVAL '30 minutes'" in sql, f"sql must scope to >30min stale: {sql}"
    assert "SET status = 'pending'" in sql, f"sql must reset to pending: {sql}"


@pytest.mark.asyncio
async def test_reset_stale_claims_handles_malformed_command_tag():
    """Defensive: if asyncpg ever returns something other than 'UPDATE N'
    (driver version drift, mock leakage), the parser falls back to 0
    rather than raising. The hook is best-effort; a parse error must
    not crash startup."""
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="weird tag without trailing int")
    repo = ExtractionLeavesRepo(pool)
    n = await repo.reset_stale_claims()
    assert n == 0


@pytest.mark.asyncio
async def test_reset_stale_claims_appends_recovery_breadcrumb():
    """The UPDATE concatenates a '[stale-claim recovery at <ts>]'
    marker into error_message so operators can audit which rows were
    reset by the lifespan hook vs which failed for other reasons."""
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="UPDATE 1")
    repo = ExtractionLeavesRepo(pool)
    await repo.reset_stale_claims()
    sql = pool.execute.await_args.args[0]
    assert "stale-claim recovery" in sql
