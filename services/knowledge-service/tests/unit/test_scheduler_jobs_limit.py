"""Cycle 3 (session 46) — unit tests for the LIMIT parameter on
scheduler-class jobs (reconciler + quarantine cleanup + orphan
source cleanup). Integration coverage against real Neo4j lives in
tests/integration/db/.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.quarantine_cleanup import run_quarantine_cleanup
from app.jobs.reconcile_evidence_count import reconcile_evidence_count


# ── D-K11.9-01 + P-K11.9-01 reconciler LIMIT ────────────────────────


@pytest.mark.asyncio
async def test_reconciler_rejects_nonpositive_limit():
    with pytest.raises(ValueError, match="limit_per_label must be positive"):
        await reconcile_evidence_count(
            MagicMock(), user_id="u-1", limit_per_label=0,
        )
    with pytest.raises(ValueError, match="limit_per_label must be positive"):
        await reconcile_evidence_count(
            MagicMock(), user_id="u-1", limit_per_label=-1,
        )


@pytest.mark.asyncio
async def test_reconciler_threads_limit_into_cypher(monkeypatch):
    """The limit value should be forwarded to run_write for each label."""
    captured_limits: list[int | None] = []

    result = MagicMock()
    result.single = AsyncMock(return_value={"fixed": 0})

    async def fake_run_write(session, cypher, **kwargs):
        captured_limits.append(kwargs.get("limit"))
        return result

    monkeypatch.setattr(
        "app.jobs.reconcile_evidence_count.run_write", fake_run_write,
    )

    await reconcile_evidence_count(
        MagicMock(), user_id="u-1", limit_per_label=500,
    )
    # Three labels × limit=500
    assert captured_limits == [500, 500, 500]


@pytest.mark.asyncio
async def test_reconciler_none_limit_forwards_as_none(monkeypatch):
    """limit_per_label=None (default) should forward as None (no cap)."""
    captured_limits: list[int | None] = []

    result = MagicMock()
    result.single = AsyncMock(return_value={"fixed": 0})

    async def fake_run_write(session, cypher, **kwargs):
        captured_limits.append(kwargs.get("limit"))
        return result

    monkeypatch.setattr(
        "app.jobs.reconcile_evidence_count.run_write", fake_run_write,
    )

    await reconcile_evidence_count(MagicMock(), user_id="u-1")
    assert captured_limits == [None, None, None]


# ── P-K15.10-01 quarantine LIMIT ────────────────────────────────────


@pytest.mark.asyncio
async def test_quarantine_rejects_nonpositive_limit():
    with pytest.raises(ValueError, match="limit must be positive"):
        await run_quarantine_cleanup(MagicMock(), limit=0)
    with pytest.raises(ValueError, match="limit must be positive"):
        await run_quarantine_cleanup(MagicMock(), limit=-42)


@pytest.mark.asyncio
async def test_quarantine_threads_limit_into_cypher():
    """Limit should flow through to session.run as a $limit param."""
    captured: dict = {}
    result = MagicMock()
    result.single = AsyncMock(return_value={"invalidated": 0})
    sess = MagicMock()

    async def fake_run(cypher, **kwargs):
        captured.update(kwargs)
        return result

    sess.run = fake_run
    await run_quarantine_cleanup(sess, user_id="u-1", limit=100)
    assert captured["limit"] == 100
    assert captured["user_id"] == "u-1"


@pytest.mark.asyncio
async def test_quarantine_none_limit_forwards_as_none():
    """The default None limit should be passed through (not silently swapped)."""
    captured: dict = {}
    result = MagicMock()
    result.single = AsyncMock(return_value={"invalidated": 0})
    sess = MagicMock()

    async def fake_run(cypher, **kwargs):
        captured.update(kwargs)
        return result

    sess.run = fake_run
    await run_quarantine_cleanup(sess)
    assert captured["limit"] is None
